import shutil
import subprocess
from pathlib import Path


class VideoProcessor:
    @staticmethod
    def resolve_ffmpeg(configured_path: str) -> str | None:
        if configured_path.strip().lower() != 'auto-detect':
            return configured_path.strip() or None
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            return shutil.which('ffmpeg')

    @staticmethod
    def split_video(ffmpeg_path: str, input_file: Path, output_dir: Path, duration: int) -> str:
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg_path, '-y', '-i', str(input_file), '-c', 'copy', '-map', '0',
            '-segment_time', str(duration), '-f', 'segment', '-reset_timestamps', '1',
            str(output_dir / 'chunk_%04d.mp4'),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, OSError) as error:
            detail = getattr(error, 'stderr', None) or str(error)
            raise RuntimeError(f'FFmpeg failed: {detail[-600:]}') from error

        if completed.stderr:
            return f'Finished. Clips saved to {output_dir}\n{completed.stderr.splitlines()[-1]}'
        return f'Finished. Clips saved to {output_dir}'