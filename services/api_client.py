import json
import logging
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
    def extract_result(response: dict[str, Any]) -> Any:
        for key in ('$val_json', 'val_json', 'response', 'result'):
            if key in response:
                return BufferedAPIClient.clean_json(response[key])
        return BufferedAPIClient.clean_json(response)

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