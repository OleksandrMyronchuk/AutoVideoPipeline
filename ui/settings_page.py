from nicegui import ui


class SettingsPageMixin:
    def build_settings_page(self):
        with ui.column().classes('w-full max-w-5xl gap-0') as page:
            self.pages['settings'] = page
            self.page_header('Settings', 'Control where files come from and how the pipeline runs.')
            self.settings_input_field = ui.input('Default source video', value=self.settings.input_path, on_change=self.update_input).classes('app-input w-full')
            self.settings_output_field = ui.input('Default output folder', value=self.settings.output_path, on_change=self.update_output).classes('app-input w-full mt-4')
            self.ffmpeg_field = ui.input('FFmpeg executable', value=self.settings.ffmpeg_path, on_change=self.update_ffmpeg).classes('app-input w-full')
            ui.label('Use Auto-detect to prefer imageio-ffmpeg, then fall back to FFmpeg on PATH.').classes('muted text-sm mt-2')
            self.settings_duration_field = ui.number('Default clip length (seconds)', value=self.settings.segment_duration, min=1, max=86400, step=1, on_change=self.update_duration).classes('app-input w-64 mt-7')
            ui.label('ANALYZE VIDEO DEFAULTS').classes('muted text-xs font-semibold tracking-wider mt-8')
            for key, label in (
                ('analysis_api_url', 'Analysis API URL'),
                ('analysis_workflow_path', 'Analysis workflow path'),
                ('analysis_clips_dir', 'Analysis input clips folder'),
                ('analysis_output_dir', 'Analysis output folder'),
                ('analysis_request_dir', 'Analysis request folder'),
                ('analysis_request_file', 'Analysis prompt file'),
                ('analysis_state_file', 'Analysis checkpoint file'),
            ):
                ui.input(label, value=getattr(self.settings, key), on_change=lambda event, name=key: self.update_analysis_setting(name, event)).classes('app-input w-full mt-3')
            with ui.row().classes('w-full gap-4 mt-3'):
                ui.number('API timeout (seconds)', value=self.settings.analysis_request_timeout, min=1, step=1, on_change=lambda event: self.update_analysis_number('analysis_request_timeout', event)).classes('app-input flex-1')
                ui.number('Maximum retries', value=self.settings.analysis_max_retries, min=0, step=1, on_change=lambda event: self.update_analysis_number('analysis_max_retries', event)).classes('app-input flex-1')
            ui.checkbox('Skip existing analysis outputs', value=self.settings.analysis_skip_existing, on_change=lambda event: self.update_analysis_bool('analysis_skip_existing', event)).classes('mt-3')
            ui.button('Save settings', icon='save', on_click=self.save_settings).props('unelevated').classes('bg-orange-600 text-white mt-7 px-5')

    def update_input(self, event):
        self.update_input_value(event.value)

    def update_input_value(self, value):
        self.settings.input_path = value
        self.input_field.value = value
        self.settings_input_field.value = value
        self.settings_store.save(self.settings)

    def update_output(self, event):
        self.update_output_value(event.value)

    def update_output_value(self, value):
        self.settings.output_path = value
        self.output_field.value = value
        self.settings_output_field.value = value
        self.settings_store.save(self.settings)

    def update_ffmpeg(self, event):
        self.settings.ffmpeg_path = event.value.strip() or 'Auto-detect'
        self.engine_label.text = f'Engine: {self.settings.ffmpeg_path}'
        self.settings_store.save(self.settings)

    def update_duration(self, event):
        if event.value:
            self.settings.segment_duration = int(event.value)
            self.duration_field.value = self.settings.segment_duration
            self.settings_duration_field.value = self.settings.segment_duration
            self.settings_store.save(self.settings)

    def update_analysis_setting(self, name, event):
        setattr(self.settings, name, event.value)
        self.settings_store.save(self.settings)

    def update_analysis_number(self, name, event):
        if event.value is not None:
            setattr(self.settings, name, int(event.value))
            self.settings_store.save(self.settings)

    def update_analysis_bool(self, name, event):
        setattr(self.settings, name, bool(event.value))
        self.settings_store.save(self.settings)

    def save_settings(self):
        self.settings_store.save(self.settings)
        self.status.text = 'Settings saved'
        self.log.push('Settings updated.')
        ui.notify('Settings saved')