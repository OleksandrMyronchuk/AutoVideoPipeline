import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    input_path: str = r'A:\stalker_walkthrough.mp4'
    output_path: str = r'A:\clips'
    segment_duration: int = 60
    ffmpeg_path: str = 'Auto-detect'


class SettingsStore:
    def __init__(self, settings_file: Path):
        self.settings_file = settings_file

    def load(self) -> AppSettings:
        try:
            values = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return AppSettings()

        defaults = AppSettings()
        return AppSettings(
            input_path=values.get('input_path', defaults.input_path),
            output_path=values.get('output_path', defaults.output_path),
            segment_duration=self._duration(values.get('segment_duration', defaults.segment_duration), defaults.segment_duration),
            ffmpeg_path=values.get('ffmpeg_path', defaults.ffmpeg_path),
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