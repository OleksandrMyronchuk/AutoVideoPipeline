from pathlib import Path

from nicegui import ui

from config import SettingsStore
from interface import VideoPipelineUI


settings_store = SettingsStore(Path(__file__).with_name('settings.json'))
app = VideoPipelineUI(settings_store)
app.build()
ui.run(title='Auto Video Pipeline', port=8080, reload=False)
