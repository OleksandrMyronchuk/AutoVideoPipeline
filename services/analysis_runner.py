import json
from pathlib import Path
from typing import Any

from plugins.base import AnalysisScript
from services.api_client import APIProcessingError, BufferedAPIClient, save_atomic_json


class AnalysisRunner:
    def __init__(self, client: BufferedAPIClient):
        self.client = client

    def run(self, script: AnalysisScript, input_dir: Path, output_dir: Path, workflow_path: str, request_file: Path, skip_existing: bool = True) -> str:
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
                previous = json.loads(output_file.read_text(encoding='utf-8'))
                continue
            payload = {
                'ExecutionWorkflowPath': workflow_path,
                '$file': str(clip.resolve()),
                '$text': template,
                'debug_mode': True,
                'analysis_script': script.key,
            }
            result = self.client.request(payload, previous)
            save_atomic_json(output_file, result)
            previous = result
            processed += 1
        return f'{script.name}: processed {processed} clip(s); output saved to {output_dir}'