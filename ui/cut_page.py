from pathlib import Path

from nicegui import run, ui

from services.pipeline_service import PipelineService
from video_processor import VideoProcessor


class CutPageMixin:
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

    async def on_upload(self, event):
        target = Path(__file__).parents[1] / 'uploads' / event.file.name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(await event.file.read())
        self.update_input_value(str(target.resolve()))
        if not self.settings.output_path:
            self.update_output_value(str(target.parent.resolve() / 'clips'))
        ui.notify('Video uploaded')

    def use_input_folder(self):
        if self.settings.input_path:
            self.update_output_value(str(Path(self.settings.input_path).parent / 'clips'))

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
            message = await run.io_bound(PipelineService.cut_video, ffmpeg, input_file, output_dir, self.settings.segment_duration)
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