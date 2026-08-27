import json
import logging
from pathlib import Path
from typing import Any

from plugins.base import AnalysisScript
from services.api_client import APIProcessingError, BufferedAPIClient, save_atomic_json


class AnalysisRunner:
    def __init__(self, client: BufferedAPIClient):
        self.client = client

    @staticmethod
    def _request_text(template: str, script: AnalysisScript, previous: Any) -> str:
        if not script.hooks.include_previous_result or previous is None:
            return template
        return (
            f'{template}\n\n'
            'PRIOR CLIP ANALYSIS (context only; analyze the supplied current clip):\n'
            f'{json.dumps(previous, ensure_ascii=False, indent=2)}\n'
        )

    def run(self, script: AnalysisScript, config: dict[str, Any], logger=None) -> str:
        logger = logger or logging.getLogger(__name__)
        input_dir = Path(config['input_dir'])
        output_dir = Path(config['output_dir'])
        workflow_path = str(config.get('workflow_path', ''))
        request_file = Path(config.get('request_file', ''))
        skip_existing = bool(config.get('skip_existing', True))
        logger.info('analysis_started', extra={'event': 'analysis_started', 'script': script.key, 'input_dir': str(input_dir), 'output_dir': str(output_dir)})
        template = request_file.read_text(encoding='utf-8-sig').strip() if request_file.is_file() else Path(__file__).parents[1].joinpath(script.prompt_file).read_text(encoding='utf-8').strip()
        if not template:
            raise APIProcessingError('The analysis prompt is empty. Pipeline stopped.')
        clips = sorted(path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.flv'})
        if not clips:
            raise APIProcessingError(f'No video clips found in {input_dir}.')
        output_dir.mkdir(parents=True, exist_ok=True)
        previous: Any = None
        processed = 0
        for clip in clips:
            output_file = output_dir / f'{script.key}_{clip.stem}.json'
            if skip_existing and output_file.exists():
                existing = json.loads(output_file.read_text(encoding='utf-8'))
                self.client.validate_result(existing, script.key)
                previous = existing
                logger.info('analysis_clip_skipped', extra={'event': 'analysis_clip_skipped', 'script': script.key, 'clip': str(clip)})
                continue
            request_text = self._request_text(template, script, previous)
            payload = {
                'ExecutionWorkflowPath': workflow_path,
                '$file': str(clip.resolve()),
                '$text': request_text,
                'debug_mode': True,
                'analysis_script': script.key,
                'script_config': config,
            }
            logger.info('analysis_clip_started', extra={'event': 'analysis_clip_started', 'script': script.key, 'clip': str(clip)})
            result = self.client.request(payload, previous)
            save_atomic_json(output_file, result)
            previous = result
            processed += 1
            logger.info('analysis_clip_completed', extra={'event': 'analysis_clip_completed', 'script': script.key, 'clip': str(clip)})
        logger.info('analysis_completed', extra={'event': 'analysis_completed', 'script': script.key, 'processed': processed, 'output_dir': str(output_dir)})
        return f'{script.name}: processed {processed} clip(s); output saved to {output_dir}'