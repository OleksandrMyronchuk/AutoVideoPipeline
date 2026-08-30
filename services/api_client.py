import json
import logging
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class APIProcessingError(RuntimeError):
    """Raised when an API response cannot safely advance a pipeline."""


class BufferedAPIClient:
    def __init__(self, api_url: str, timeout: int = 9999, max_retries: int = 3, logger=None):
        self.api_url = api_url
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()
        retry = Retry(total=max_retries, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=['POST'])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def request(self, payload: dict[str, Any], previous_response: Any = None) -> Any:
        self.seed_buffer()
        self.logger.info('api_request_started', extra={'event': 'api_request_started', 'url': self.api_url, 'script': payload.get('analysis_script'), 'clip': payload.get('$file')})
        try:
            response = self.session.post(self.api_url, json=payload, timeout=self.timeout)
        except requests.RequestException as error:
            self.logger.warning('api_request_failed', extra={'event': 'api_request_failed', 'error': str(error)})
            raise APIProcessingError(f'API request failed: {error}') from error
        if response.status_code != 200:
            self.logger.warning('api_request_failed', extra={'event': 'api_request_failed', 'status_code': response.status_code})
            raise APIProcessingError(f'API returned HTTP {response.status_code}: {response.text[:300]}')

        try:
            response_data = response.json()
        except json.JSONDecodeError:
            response_data = {'$val_json': response.text}
        parsed = self.extract_result(response_data)
        self.validate_result(parsed, payload.get('analysis_script'))
        if self.is_empty(parsed, response.text):
            raise APIProcessingError('API returned an empty response or nothing. Pipeline stopped to protect the buffer state.')
        if self.is_duplicate(parsed, previous_response):
            raise APIProcessingError('Duplicate API response detected. Pipeline stopped to prevent repeated output.')
        self.logger.info('api_request_completed', extra={'event': 'api_request_completed', 'script': payload.get('analysis_script'), 'clip': payload.get('$file')})
        return parsed

    @staticmethod
    def seed_buffer() -> None:
        """Reset the external response buffer before every request."""
        commands = ['clip'] if os.name == 'nt' else (['pbcopy'] if sys.platform == 'darwin' else ['xclip', '-selection', 'clipboard'])
        try:
            subprocess.run(commands, input=b'nothing', check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise APIProcessingError(f'Could not seed the API buffer: {error}') from error

    @staticmethod
    def extract_result(response: Any) -> Any:
        result = response
        for _ in range(3):
            result = BufferedAPIClient.clean_json(result)
            if not isinstance(result, dict):
                break
            wrapped_key = next((key for key in ('$val_json', 'val_json', 'response', 'result') if key in result), None)
            if wrapped_key is None:
                break
            result = result[wrapped_key]
        return BufferedAPIClient.clean_json(result)

    @staticmethod
    def clean_json(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip()
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
        if match:
            text = match.group(1).strip()
        starts = [index for index in (text.find('{'), text.find('[')) if index >= 0]
        end = max(text.rfind('}'), text.rfind(']'))
        if starts and end > min(starts):
            text = text[min(starts):end + 1]
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def validate_result(result: Any, script_key: Any) -> None:
        if not isinstance(result, dict):
            raise APIProcessingError('API returned JSON, but the result is not a JSON object.')
        if isinstance(result.get('error'), str):
            raise APIProcessingError(f"API workflow error: {result['error']}")
        if script_key == 'event_timeline':
            required = {'events'}
            if set(result) != required:
                extra = set(result) - required
                if extra:
                    raise APIProcessingError(f"Event timeline result contains unexpected fields: {', '.join(sorted(extra))}.")
            missing = required - result.keys()
            if missing:
                raise APIProcessingError(f"Event timeline result is missing required fields: {', '.join(sorted(missing))}.")
            if not isinstance(result['events'], list):
                raise APIProcessingError('Event timeline events must be an array.')
            categories = {'combat', 'item_pickup', 'item_interaction', 'spatial_progression', 'trap', 'damage', 'audio_trigger', 'other'}
            intensities = {'low', 'medium', 'high'}
            for event in result['events']:
                required_event = {'start_sec', 'end_sec', 'category', 'action_summary', 'audio_triggers', 'intensity'}
                if not isinstance(event, dict) or not required_event <= event.keys():
                    raise APIProcessingError('Event timeline contains an invalid event.')
                if set(event) != required_event:
                    raise APIProcessingError('Event timeline event contains unexpected fields.')
                start_sec = event['start_sec']
                end_sec = event['end_sec']
                if (isinstance(start_sec, bool) or isinstance(end_sec, bool) or
                        not isinstance(start_sec, (int, float)) or not isinstance(end_sec, (int, float)) or
                        not math.isfinite(start_sec) or not math.isfinite(end_sec) or
                        not 0 <= start_sec <= end_sec):
                    raise APIProcessingError('Event timeline timestamps must be numbers with 0 <= start_sec <= end_sec.')
                if event['category'] not in categories or event['intensity'] not in intensities:
                    raise APIProcessingError('Event timeline category or intensity is invalid.')
                if not isinstance(event['action_summary'], str) or not event['action_summary'].strip():
                    raise APIProcessingError('Event timeline action_summary must be a non-empty string.')
                if not isinstance(event['audio_triggers'], list) or not all(isinstance(trigger, str) for trigger in event['audio_triggers']):
                    raise APIProcessingError('Event timeline audio_triggers must be an array of strings.')
            return
        if script_key != 'narration_dialogues':
            return
        required = {'clip_summary', 'active_mission', 'dialogue_events', 'quest_updates'}
        missing = required - result.keys()
        if missing:
            raise APIProcessingError(f'Narration result is missing required fields: {", ".join(sorted(missing))}.')
        if not isinstance(result['dialogue_events'], list) or not isinstance(result['quest_updates'], list):
            raise APIProcessingError('Narration result dialogue_events and quest_updates must be arrays.')
        placeholder_text = 'Brief 1-2 sentence overview of narrative progress during this clip.'
        if result.get('clip_summary') == placeholder_text or result.get('active_mission') == 'Current main objective visible on UI or stated in dialogue, or None/Unknown':
            raise APIProcessingError('Narration workflow returned the prompt schema instead of an analysis result.')
        for event in result['dialogue_events']:
            if not isinstance(event, dict) or not {'start_sec', 'end_sec', 'speaker', 'transcript'} <= event.keys():
                raise APIProcessingError('Narration result contains an invalid dialogue event.')
            if not isinstance(event['start_sec'], (int, float)) or not isinstance(event['end_sec'], (int, float)) or not 0 <= event['start_sec'] <= event['end_sec'] <= 60:
                raise APIProcessingError('Narration dialogue timestamps must be numbers between 0 and 60 seconds.')
        for update in result['quest_updates']:
            if not isinstance(update, dict) or not {'timestamp_sec', 'objective_text', 'status'} <= update.keys():
                raise APIProcessingError('Narration result contains an invalid quest update.')
            if not isinstance(update['timestamp_sec'], (int, float)) or not 0 <= update['timestamp_sec'] <= 60:
                raise APIProcessingError('Narration quest timestamps must be numbers between 0 and 60 seconds.')

    @staticmethod
    def is_empty(parsed: Any, raw_text: str) -> bool:
        if parsed is None or parsed == '' or parsed == {} or parsed == []:
            return True
        return str(parsed).strip().strip('"\'').lower() in {'nothing', 'none', 'null'} or not raw_text.strip()

    @staticmethod
    def is_duplicate(current: Any, previous: Any) -> bool:
        if previous is None:
            return False
        return current == previous if isinstance(current, (dict, list)) and isinstance(previous, (dict, list)) else str(current).strip() == str(previous).strip()


def save_atomic_json(filepath: Path, data: Any) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temporary = filepath.with_suffix(f'{filepath.suffix}.tmp')
    try:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(filepath)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise