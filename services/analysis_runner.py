import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

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

    def run(
        self,
        script: AnalysisScript,
        config: dict[str, Any],
        logger=None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        resume_event: threading.Event | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        logger = logger or logging.getLogger(__name__)

        def report(status: str, **fields: Any) -> None:
            if progress_callback:
                progress_callback({'status': status, **fields})

        def wait_until_resumed() -> bool:
            if cancel_event and cancel_event.is_set():
                return False
            if resume_event and not resume_event.is_set():
                report('paused')
                while not resume_event.wait(0.2):
                    if cancel_event and cancel_event.is_set():
                        return False
                report('resumed')
            return not cancel_event or not cancel_event.is_set()

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
        report('discovered', total=len(clips), completed=0, processed=0, skipped=0, remaining=len(clips))
        output_dir.mkdir(parents=True, exist_ok=True)
        previous: Any = None
        processed = 0
        completed = 0
        skipped = 0
        for clip in clips:
            if not wait_until_resumed():
                report('cancelled', total=len(clips), completed=completed, processed=processed, skipped=skipped, remaining=len(clips) - completed)
                return f'{script.name}: cancelled after {completed} clip(s); output saved to {output_dir}'
            output_file = output_dir / f'{script.key}_{clip.stem}.json'
            if skip_existing and output_file.exists():
                existing = json.loads(output_file.read_text(encoding='utf-8'))
                self.client.validate_result(existing, script.key)
                previous = existing
                completed += 1
                skipped += 1
                report('skipped', total=len(clips), completed=completed, processed=processed, skipped=skipped, remaining=len(clips) - completed, clip=clip.name)
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
            report('processing', total=len(clips), completed=completed, processed=processed, skipped=skipped, remaining=len(clips) - completed, clip=clip.name)
            logger.info('analysis_clip_started', extra={'event': 'analysis_clip_started', 'script': script.key, 'clip': str(clip)})
            result = self.client.request(payload, previous)
            save_atomic_json(output_file, result)
            previous = result
            processed += 1
            completed += 1
            report('completed', total=len(clips), completed=completed, processed=processed, skipped=skipped, remaining=len(clips) - completed, clip=clip.name)
            logger.info('analysis_clip_completed', extra={'event': 'analysis_clip_completed', 'script': script.key, 'clip': str(clip)})
        logger.info('analysis_completed', extra={'event': 'analysis_completed', 'script': script.key, 'processed': processed, 'output_dir': str(output_dir)})
        report('finished', total=len(clips), completed=completed, processed=processed, skipped=skipped, remaining=0)
        return f'{script.name}: processed {processed} clip(s); output saved to {output_dir}'