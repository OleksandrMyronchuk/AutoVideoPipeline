import json
import logging
import re
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

        if script.hooks.merge_json:
            return self._merge_json_fields(script, config, report)

        missing_keys = [key for key in ('input_dir', 'output_dir') if not config.get(key)]
        if missing_keys:
            raise APIProcessingError(f'{script.name} is missing required configuration fields: {", ".join(missing_keys)}.')
        input_dir = Path(str(config['input_dir']))
        output_dir = Path(str(config['output_dir']))
        workflow_path = str(config.get('workflow_path', ''))
        skip_existing = bool(config.get('skip_existing', True))
        logger.info('analysis_started', extra={'event': 'analysis_started', 'script': script.key, 'input_dir': str(input_dir), 'output_dir': str(output_dir)})
        prompt_path = AnalysisRunner._resolve_prompt_template(script, config)
        if prompt_path is None:
            raise APIProcessingError(f'{script.name} has no prompt file configured.')
        template = prompt_path.read_text(encoding='utf-8-sig').strip()
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

    @staticmethod
    def _normalize_clip_id(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(int(value)).zfill(4)
        text = str(value).strip()
        if not text:
            return None
        matches = re.findall(r'\d+', text)
        if not matches:
            return None
        raw_id = matches[-1]
        if raw_id.isdigit():
            return raw_id.zfill(4)
        return raw_id

    @staticmethod
    def _resolve_prompt_template(script: AnalysisScript, config: dict[str, Any]) -> Path | None:
        candidates: list[str] = []
        for key in ('request_file',):
            value = config.get(key)
            if value:
                candidates.append(str(value))
        if script.prompt_file:
            candidates.append(script.prompt_file)
        for item in script.configs:
            if item.key == 'request_file' or item.field_type == 'prompt':
                value = config.get(item.key, item.default)
                if value:
                    candidates.append(str(value))

        seen: set[str] = set()
        for candidate in candidates:
            value = candidate.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            path = Path(value)
            if path.is_file():
                return path
            if not path.is_absolute():
                workspace_root = script.workspace_root or Path(__file__).parents[1]
                workspace_candidate = workspace_root / path
                if workspace_candidate.is_file():
                    return workspace_candidate
        return None

    @staticmethod
    def _merge_json_fields(script: AnalysisScript, config: dict[str, Any], report: Callable[..., None]) -> str:
        input_configs = [item for item in script.configs if item.field_type == 'input' and config.get(item.key)]
        output_value = next((config.get(item.key) for item in script.configs if item.field_type == 'output' and config.get(item.key)), None)
        if not input_configs:
            raise APIProcessingError('Add at least one JSON input field.')
        if not output_value:
            raise APIProcessingError('Add a JSON output field.')

        source_files: list[tuple[Any, Path]] = []
        for item in input_configs:
            value = config.get(item.key)
            path = Path(str(value))
            if path.is_file():
                source_files.append((item, path))
            elif path.is_dir():
                source_files.extend((item, file_path) for file_path in sorted(path.glob('*.json')) if file_path.is_file())
            else:
                raise APIProcessingError(f'JSON input path does not exist: {path}')

        if not source_files:
            raise APIProcessingError('No JSON files found in the configured input paths.')
        report('discovered', total=len(source_files), completed=0, processed=0, skipped=0, remaining=len(source_files))

        grouped: dict[str, dict[str, list[Any]]] = {}
        for item, source_file in source_files:
            try:
                parsed = json.loads(source_file.read_text(encoding='utf-8-sig'))
            except (OSError, json.JSONDecodeError) as error:
                raise APIProcessingError(f'Could not read JSON file {source_file}: {error}') from error
            entry_values = parsed if isinstance(parsed, list) else [parsed]
            group_name = item.merge_group or item.key
            for value in entry_values:
                if not isinstance(value, dict):
                    continue
                clip_id = AnalysisRunner._normalize_clip_id(value.get('clip_id'))
                if clip_id is None:
                    clip_id = AnalysisRunner._normalize_clip_id(source_file.stem)
                if clip_id is None:
                    clip_id = 'unknown'
                clip_entry = grouped.setdefault(clip_id, {})
                clip_entry.setdefault(group_name, []).append(value)

        ordered = {
            key: grouped[key]
            for key in sorted(grouped, key=lambda item: (0 if item.isdigit() else 1, int(item) if item.isdigit() else item))
        }

        output_file = Path(str(output_value))
        output_file.parent.mkdir(parents=True, exist_ok=True)
        save_atomic_json(output_file, ordered)
        report('finished', total=len(source_files), completed=len(source_files), processed=len(source_files), skipped=0, remaining=0)
        return f'{script.name}: merged {len(source_files)} JSON file(s) into {output_file}'