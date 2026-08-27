"""Application-level orchestration for video cutting and clip analysis."""

from pathlib import Path
import threading
from typing import Any, Callable

from plugins.base import AnalysisScript
from services.analysis_runner import AnalysisRunner
from services.api_client import BufferedAPIClient
from video_processor import VideoProcessor


class PipelineService:
    """Coordinates domain services without depending on NiceGUI or widget state."""

    def __init__(self, api_url: str, request_timeout: int, max_retries: int):
        self.api_url = api_url
        self.request_timeout = request_timeout
        self.max_retries = max_retries

    @staticmethod
    def cut_video(ffmpeg_path: str, input_file: Path, output_dir: Path, duration: int) -> str:
        return VideoProcessor.split_video(ffmpeg_path, input_file, output_dir, duration)

    def analyze(
        self,
        script: AnalysisScript,
        config: dict[str, Any],
        logger=None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        resume_event: threading.Event | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        client = BufferedAPIClient(self.api_url, self.request_timeout, self.max_retries)
        return AnalysisRunner(client).run(script, config, logger, progress_callback, resume_event, cancel_event)