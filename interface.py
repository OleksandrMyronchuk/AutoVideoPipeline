from pathlib import Path

from nicegui import run, ui

from config import AppSettings, SettingsStore
from video_processor import VideoProcessor


class VideoPipelineUI:
    def __init__(self, settings_store: SettingsStore):
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.running = False
        self.pages = {}

    def build(self):
        ui.colors(primary='#f97316', secondary='#202d43', accent='#fb923c', dark='#111827')
        ui.add_head_html('''
            <style>
                body { background: #111827; color: #f8fafc; }
                .app-sidebar { background: #0b1220; }
                .app-panel { background: #182235; }
                .app-input .q-field__control { background: #202d43; }
                .app-input .q-field__native, .app-input .q-field__label { color: #f8fafc; }
                .muted { color: #93a4bd; }
                .q-linear-progress { background: #202d43; }
            </style>
        ''')
        with ui.left_drawer(value=True).classes('app-sidebar w-64 p-5'):
            ui.label('AVP').classes('bg-orange-600 text-white text-2xl font-black px-3 py-1 rounded-sm')
            ui.label('AUTO VIDEO\nPIPELINE').classes('text-white text-lg font-semibold mt-4 mb-10 whitespace-pre-line')
            self.nav_button('content_cut', 'Cut Video', 'cut')
            self.nav_button('settings', 'Settings', 'settings')
            ui.space()
            ui.label('LOCAL PROCESSING').classes('text-slate-500 text-xs font-semibold')

        with ui.column().classes('w-full min-h-screen p-8 md:p-12 app-panel'):
            self.build_cut_page()
            self.build_settings_page()
        self.show_page('cut')

    def nav_button(self, icon, label, page):
        ui.button(label, icon=icon, on_click=lambda: self.show_page(page)).props('flat align=left').classes('w-full text-slate-300 justify-start')

    def page_header(self, title, subtitle):
        ui.label(title).classes('text-white text-4xl font-semibold')
        ui.label(subtitle).classes('muted mt-1 mb-8')

    def build_cut_page(self):
        with ui.column().classes('w-full max-w-5xl gap-0') as page:
            self.pages['cut'] = page
            self.page_header('Cut Video', 'Split a long video into clean, editable clips.')
            with ui.row().classes('w-full items-end gap-3'):
                self.input_field = ui.input('Source video', value=self.settings.input_path, on_change=self.update_input).classes('app-input flex-1')
                ui.upload(label='Upload video', auto_upload=True, on_upload=self.on_upload).props('accept=.mp4,.mov,.mkv,.avi,.webm').classes('shrink-0')
            with ui.row().classes('w-full items-end gap-3 mt-5'):
                self.output_field = ui.input('Output folder', value=self.settings.output_path, on_change=self.update_output).classes('app-input flex-1')
                ui.button('Use input folder', icon='folder', on_click=self.use_input_folder).props('outline').classes('shrink-0')
            with ui.row().classes('w-full items-end gap-12 mt-8'):
                self.duration_field = ui.number('Clip length (seconds)', value=self.settings.segment_duration, min=1, max=86400, step=1, on_change=self.update_duration).classes('app-input w-52')
                self.engine_label = ui.label(f'Engine: {self.settings.ffmpeg_path}').classes('muted pb-3')
            with ui.row().classes('w-full items-center mt-8'):
                self.start_button = ui.button('Start Cutting', icon='play_arrow', on_click=self.start_cutting).props('unelevated').classes('bg-orange-600 text-white px-5')
                self.status = ui.label('Ready to split your video').classes('muted ml-3')
            ui.label('ACTIVITY').classes('muted text-xs font-semibold tracking-wider mt-6')
            self.log = ui.log(max_lines=12).classes('w-full h-48 bg-slate-900/50 text-slate-300 p-3 font-mono text-xs')

    def build_settings_page(self):
        with ui.column().classes('w-full max-w-5xl gap-0') as page:
            self.pages['settings'] = page
            self.page_header('Settings', 'Control where files come from and how the pipeline runs.')
            self.settings_input_field = ui.input('Default source video', value=self.settings.input_path, on_change=self.update_input).classes('app-input w-full')
            self.settings_output_field = ui.input('Default output folder', value=self.settings.output_path, on_change=self.update_output).classes('app-input w-full mt-4')
            self.ffmpeg_field = ui.input('FFmpeg executable', value=self.settings.ffmpeg_path, on_change=self.update_ffmpeg).classes('app-input w-full')
            ui.label('Use Auto-detect to prefer imageio-ffmpeg, then fall back to FFmpeg on PATH.').classes('muted text-sm mt-2')
            self.settings_duration_field = ui.number('Default clip length (seconds)', value=self.settings.segment_duration, min=1, max=86400, step=1, on_change=self.update_duration).classes('app-input w-64 mt-7')
            ui.button('Save settings', icon='save', on_click=self.save_settings).props('unelevated').classes('bg-orange-600 text-white mt-7 px-5')

    def show_page(self, page_name):
        for name, page in self.pages.items():
            page.set_visibility(name == page_name)

    async def on_upload(self, event):
        target = Path('uploads') / event.file.name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(await event.file.read())
        self.update_input_value(str(target.resolve()))
        if not self.settings.output_path:
            self.update_output_value(str(target.parent.resolve() / 'clips'))
        ui.notify('Video uploaded')

    def use_input_folder(self):
        if self.settings.input_path:
            self.update_output_value(str(Path(self.settings.input_path).parent / 'clips'))

    def update_input(self, event):
        self.update_input_value(event.value)

    def update_input_value(self, value):
        self.settings.input_path = value
        self.input_field.value = value
        self.settings_input_field.value = value

    def update_output(self, event):
        self.update_output_value(event.value)

    def update_output_value(self, value):
        self.settings.output_path = value
        self.output_field.value = value
        self.settings_output_field.value = value

    def update_ffmpeg(self, event):
        self.settings.ffmpeg_path = event.value.strip() or 'Auto-detect'
        self.engine_label.text = f'Engine: {self.settings.ffmpeg_path}'

    def update_duration(self, event):
        if event.value:
            self.settings.segment_duration = int(event.value)
            self.duration_field.value = self.settings.segment_duration
            self.settings_duration_field.value = self.settings.segment_duration

    def save_settings(self):
        self.settings_store.save(self.settings)
        self.status.text = 'Settings saved'
        self.log.push('Settings updated.')
        ui.notify('Settings saved')

    async def start_cutting(self):
        if self.running:
            return
        input_file = Path(self.settings.input_path.strip())
        output_dir = Path(self.settings.output_path.strip())
        if not input_file.is_file():
            ui.notify('Choose an existing video file first.', type='negative')
            return
        ffmpeg = VideoProcessor.resolve_ffmpeg(self.settings.ffmpeg_path)
        if not ffmpeg:
            ui.notify('FFmpeg was not found. Configure it in Settings.', type='negative')
            return
        self.running = True
        self.start_button.disable()
        self.status.text = 'Cutting video...'
        self.log.push(f'Splitting {input_file.name} into {self.settings.segment_duration}s clips...')
        try:
            message = await run.io_bound(VideoProcessor.split_video, ffmpeg, input_file, output_dir, self.settings.segment_duration)
            self.log.push(message)
            self.status.text = 'Cut complete'
            ui.notify('Video cutting complete', type='positive')
        except RuntimeError as error:
            self.log.push(str(error))
            self.status.text = 'Cut failed'
            ui.notify('FFmpeg failed. See Activity for details.', type='negative')
        finally:
            self.running = False
            self.start_button.enable()
