import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    input_path: str = r'A:\stalker_walkthrough.mp4'
    output_path: str = r'A:\clips'
    segment_duration: int = 60
    ffmpeg_path: str = 'Auto-detect'
    analysis_api_url: str = 'http://localhost:8085/request_custom_path'
    analysis_workflow_path: str = r'A:\aistudio_g37_norm'
    analysis_clips_dir: str = r'A:\clips'
    analysis_output_dir: str = r'A:\data_2'
    analysis_state_file: str = r'A:\settings\state.json'
    analysis_request_dir: str = r'A:\requests'
    analysis_request_file: str = r'A:\requests\request1.txt'
    analysis_skip_existing: bool = True
    analysis_request_timeout: int = 9999
    analysis_max_retries: int = 3
    last_page: str = 'cut'


class SettingsStore:
    def __init__(self, settings_file: Path):
        self.settings_file = settings_file

    def load(self) -> AppSettings:
        try:
            values = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return AppSettings()

        defaults = AppSettings()
        last_page = values.get('last_page', defaults.last_page)
        if not isinstance(last_page, str) or last_page not in {'cut', 'analyze', 'settings'}:
            last_page = defaults.last_page
        return AppSettings(
            input_path=values.get('input_path', defaults.input_path),
            output_path=values.get('output_path', defaults.output_path),
            segment_duration=self._duration(values.get('segment_duration', defaults.segment_duration), defaults.segment_duration),
            ffmpeg_path=values.get('ffmpeg_path', defaults.ffmpeg_path),
            analysis_api_url=values.get('analysis_api_url', defaults.analysis_api_url),
            analysis_workflow_path=values.get('analysis_workflow_path', defaults.analysis_workflow_path),
            analysis_clips_dir=values.get('analysis_clips_dir', defaults.analysis_clips_dir),
            analysis_output_dir=values.get('analysis_output_dir', defaults.analysis_output_dir),
            analysis_state_file=values.get('analysis_state_file', defaults.analysis_state_file),
            analysis_request_dir=values.get('analysis_request_dir', defaults.analysis_request_dir),
            analysis_request_file=values.get('analysis_request_file', defaults.analysis_request_file),
            analysis_skip_existing=bool(values.get('analysis_skip_existing', defaults.analysis_skip_existing)),
            analysis_request_timeout=self._duration(values.get('analysis_request_timeout', defaults.analysis_request_timeout), defaults.analysis_request_timeout),
            analysis_max_retries=self._duration(values.get('analysis_max_retries', defaults.analysis_max_retries), defaults.analysis_max_retries),
            last_page=last_page,
        )

    def save(self, settings: AppSettings) -> None:
        self.settings_file.write_text(json.dumps(asdict(settings), indent=2) + '\n', encoding='utf-8')

    @staticmethod
    def _duration(value, fallback: int) -> int:
        try:
            duration = int(value)
        except (TypeError, ValueError):
            return fallback
        return duration if duration > 0 else fallback