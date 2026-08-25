import logging
import os
import socket
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from config import SettingsStore
from interface import VideoPipelineUI


log_dir = Path(__file__).with_name('.script_workspaces')
log_dir.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(log_dir / 'script_editor.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
logging.getLogger().addHandler(file_handler)
logging.getLogger().setLevel(logging.INFO)

nicegui_app.add_static_files('/monaco', Path(__file__).with_name('node_modules') / 'monaco-editor' / 'min')


def build_page(page):
	settings_store = SettingsStore(Path(__file__).with_name('settings.json'))
	app = VideoPipelineUI(settings_store)
	app.build(page)


@ui.page('/')
def index_page():
	build_page('cut')


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
	settings_store = SettingsStore(Path(__file__).with_name('settings.json'))
	app = VideoPipelineUI(settings_store)
	app.build_editor_page()


@ui.page('/script_editor/{workspace_id}')
def existing_script_editor_page(workspace_id: str):
	settings_store = SettingsStore(Path(__file__).with_name('settings.json'))
	app = VideoPipelineUI(settings_store)
	app.build_editor_page(workspace_id)


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


port = find_available_port(int(os.environ.get('AVP_PORT', '8080')))
ui.run(title='Auto Video Pipeline', port=port, reload=False)
