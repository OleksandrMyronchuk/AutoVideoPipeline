import logging
import os
import socket
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from config import SettingsStore
from interface import VideoPipelineUI
from services.logging_utils import PipelineFormatter


PROJECT_ROOT = Path(__file__).parents[1]
SETTINGS_FILE = PROJECT_ROOT / 'settings.json'
WORKSPACE_DIR = PROJECT_ROOT / '.script_workspaces'
SETTINGS_STORE = SettingsStore(SETTINGS_FILE)


def configure_logging() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(WORKSPACE_DIR / 'script_editor.log', encoding='utf-8')
    handler.setFormatter(PipelineFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def configure_static_files() -> None:
    nicegui_app.add_static_files('/monaco', PROJECT_ROOT / 'node_modules' / 'monaco-editor' / 'min')


def build_page(page: str | None = None) -> None:
    settings = SETTINGS_STORE.load()
    VideoPipelineUI(SETTINGS_STORE).build(page or settings.last_page)


def build_editor_page(workspace_id: str | None = None) -> None:
    VideoPipelineUI(SETTINGS_STORE).build_editor_page(workspace_id)


def find_available_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(('0.0.0.0', preferred))
            return preferred
        except OSError:
            probe.bind(('0.0.0.0', 0))
            fallback = probe.getsockname()[1]
            logging.getLogger(__name__).warning('port %d is busy; using port %d', preferred, fallback)
            return fallback


def register_routes() -> None:
    @ui.page('/')
    def index_page():
        build_page()

    @ui.page('/cut_video')
    def cut_video_page():
        build_page('cut')

    @ui.page('/analyze_video')
    def analyze_video_page():
        build_page('analyze')

    @ui.page('/settings')
    def settings_page():
        build_page('settings')

    @ui.page('/script_editor')
    def script_editor_page():
        build_editor_page()

    @ui.page('/script_editor/{workspace_id}')
    def existing_script_editor_page(workspace_id: str):
        build_editor_page(workspace_id)


def run() -> None:
    configure_logging()
    configure_static_files()
    register_routes()
    nicegui_app.on_shutdown(SETTINGS_STORE.save_latest)
    port = find_available_port(int(os.environ.get('AVP_PORT', '8080')))
    ui.run(title='Auto Video Pipeline', port=port, reload=False)