from pathlib import Path

from nicegui import run, ui

from plugins.base import ScriptConfig
from services.api_client import APIProcessingError
from services.logging_utils import get_pipeline_logger
from services.pipeline_service import PipelineService


class AnalysisPageMixin:
    def build_analyze_page(self):
        with ui.column().classes('w-full max-w-5xl gap-0') as page:
            self.pages['analyze'] = page
            self.page_header('Analyze Video', 'Choose an analysis script and configure its inputs before running.')
            with ui.row().classes('w-full items-center justify-between mb-4'):
                ui.label('AVAILABLE SCRIPTS').classes('muted text-xs font-semibold tracking-wider')
                ui.button('Add script', icon='add', on_click=self.open_script_menu).props('outline')

            ui.add_head_html('''
                <style>
                    .script-card { transition: opacity .18s ease, transform .18s ease, border-color .18s ease; }
                    .script-card.is-dragging { opacity: .42; transform: scale(.985); }
                    .script-drag-handle { cursor: grab; color: #93a4bd; user-select: none; }
                    .script-drag-handle:active { cursor: grabbing; }
                    .script-drop-zone { height: 8px; border: 1px dashed transparent; border-radius: 4px; transition: height .18s ease, border-color .18s ease, background .18s ease; }
                    .script-drop-zone.is-visible { height: 28px; border-color: #fb923c; background: rgba(249, 115, 22, .12); }
                    .script-drop-zone.is-over { background: rgba(249, 115, 22, .28); box-shadow: 0 0 0 1px rgba(251, 146, 60, .4); }
                </style>
            ''')

            ui.add_body_html('''
                <script>
                    (() => {
                        if (window.__avpDragDropInitialized) return;
                        window.__avpDragDropInitialized = true;

                        let draggedKey = null;

                        const clearDropZones = () => {
                            document.querySelectorAll('.script-drop-zone').forEach(zone => {
                                zone.classList.remove('is-visible', 'is-over');
                            });
                        };

                        document.addEventListener('dragstart', (event) => {
                            const handle = event.target.closest('.script-drag-handle');
                            if (!handle) return;
                            draggedKey = handle.dataset.scriptKey;
                            const card = document.querySelector(`.script-card[data-script-key="${CSS.escape(draggedKey)}"]`);
                            if (card) card.classList.add('is-dragging');
                            document.querySelectorAll('.script-drop-zone').forEach(zone => zone.classList.add('is-visible'));
                            event.dataTransfer.effectAllowed = 'move';
                            event.dataTransfer.setData('text/plain', draggedKey);
                        });

                        document.addEventListener('dragover', (event) => {
                            if (!draggedKey) return;
                            event.preventDefault();
                            event.dataTransfer.dropEffect = 'move';

                            document.querySelectorAll('.script-drop-zone').forEach(item => item.classList.remove('is-over'));

                            const zone = event.target.closest('.script-drop-zone');
                            if (zone) {
                                zone.classList.add('is-over');
                                return;
                            }

                            const card = event.target.closest('.script-card');
                            if (card) {
                                const bounds = card.getBoundingClientRect();
                                const cards = [...document.querySelectorAll('.script-card')];
                                const index = cards.indexOf(card);
                                const dropIndex = event.clientY < (bounds.top + bounds.height / 2) ? index : index + 1;
                                document.querySelector(`.script-drop-zone[data-drop-index="${dropIndex}"]`)?.classList.add('is-over');
                            }
                        });

                        document.addEventListener('drop', (event) => {
                            if (!draggedKey) return;
                            event.preventDefault();

                            const cards = [...document.querySelectorAll('.script-card')];
                            const order = cards.map(c => c.dataset.scriptKey);
                            const from = order.indexOf(draggedKey);

                            const zone = event.target.closest('.script-drop-zone');
                            let insertionIndex = zone ? Number(zone.dataset.dropIndex) : NaN;

                            const card = event.target.closest('.script-card');
                            if (!Number.isInteger(insertionIndex) && card) {
                                const bounds = card.getBoundingClientRect();
                                const index = cards.indexOf(card);
                                insertionIndex = event.clientY < (bounds.top + bounds.height / 2) ? index : index + 1;
                            }

                            document.querySelectorAll('.script-card').forEach(c => c.classList.remove('is-dragging'));
                            clearDropZones();

                            const movingKey = draggedKey;
                            draggedKey = null;

                            if (from < 0 || !Number.isInteger(insertionIndex)) return;
                            if (insertionIndex === from || insertionIndex === from + 1) return;

                            order.splice(from, 1);
                            const targetIndex = insertionIndex > from ? insertionIndex - 1 : insertionIndex;
                            order.splice(targetIndex, 0, movingKey);

                            if (typeof emitEvent === 'function') {
                                emitEvent('script_reorder', {order: order});
                            }
                        });

                        document.addEventListener('dragend', () => {
                            document.querySelectorAll('.script-card').forEach(c => c.classList.remove('is-dragging'));
                            clearDropZones();
                            draggedKey = null;
                        });
                    })();
                </script>
            ''')

            ui.on('script_reorder', self.reorder_scripts)
            self.script_list = ui.column().classes('w-full gap-3')
            self.render_script_list()

    def render_script_list(self):
        self.script_list.clear()
        scripts = self.ordered_scripts()
        with self.script_list:
            for index, script in enumerate(scripts):
                ui.element('div').props(f'data-drop-index="{index}"').classes('script-drop-zone w-full')
                with ui.card().props(f'data-script-key="{script.key}"').classes('script-card nicegui-card w-full border border-slate-600 p-4'):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-3 min-w-0'):
                            ui.icon('drag_indicator').props(f'draggable=true data-script-key="{script.key}"').classes('script-drag-handle shrink-0')
                            with ui.column().classes('gap-1 min-w-0'):
                                ui.label(script.name).classes('text-white text-lg font-semibold')
                                ui.label(script.description).classes('muted')
                        with ui.row().classes('items-center gap-1'):
                            ui.button('Configure & Run', icon='play_arrow', on_click=lambda item=script: self.open_script(item)).props('unelevated').classes('bg-orange-600 text-white')
                            ui.button('Read', icon='menu_book', on_click=lambda item=script: self.show_prompt(item, None)).props('flat')
                            ui.button('Edit', icon='edit', on_click=lambda item=script: self.open_editor(item)).props('flat')
                            if script.workspace_root:
                                ui.button('Rename', icon='drive_file_rename_outline', on_click=lambda item=script: self.open_rename_script(item)).props('flat')
                                ui.button('Delete', icon='delete', on_click=lambda item=script: self.confirm_delete_script(item)).props('flat color=negative')
            ui.element('div').props(f'data-drop-index="{len(scripts)}"').classes('script-drop-zone w-full')

    def ordered_scripts(self):
        scripts = {script.key: script for script in self.registry.all()}
        saved_order = [key for key in self.settings.analysis_script_order if key in scripts]
        new_keys = [key for key in scripts if key not in saved_order]
        order = saved_order + new_keys
        if order != self.settings.analysis_script_order:
            self.settings.analysis_script_order = order
            self.settings_store.save(self.settings)
        return [scripts[key] for key in order]

    def reorder_scripts(self, event):
        args = getattr(event, 'args', event)
        if isinstance(args, dict):
            order = args.get('order', [])
        elif isinstance(args, list) and args and isinstance(args[0], dict):
            order = args[0].get('order', [])
        elif isinstance(args, list):
            order = args
        else:
            order = []

        available = {script.key for script in self.registry.all()}
        if not isinstance(order, list) or not all(isinstance(key, str) for key in order):
            return
        if set(order) != available or len(order) != len(available):
            return
        self.settings.analysis_script_order = order
        self.settings_store.save(self.settings)
        self.render_script_list()

    def open_rename_script(self, script):
        with ui.dialog() as dialog, ui.card().classes('nicegui-card text-white w-[min(560px,92vw)] p-5'):
            ui.label('Rename script').classes('text-xl font-semibold')
            name_input = ui.input('Script name', value=script.name).classes('w-full mt-4')

            def rename():
                try:
                    self.registry.rename(script, name_input.value or '')
                    self.render_script_list()
                    dialog.close()
                    ui.notify('Script renamed', type='positive')
                except (OSError, ValueError) as error:
                    ui.notify(str(error), type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Rename', on_click=rename).props('unelevated').classes('bg-orange-600 text-white')
        dialog.open()

    def confirm_delete_script(self, script):
        with ui.dialog() as dialog, ui.card().classes('nicegui-card text-white w-[min(560px,92vw)] p-5'):
            ui.label(f'Delete {script.name}?').classes('text-xl font-semibold')
            ui.label('This permanently removes the script workspace and its files.').classes('muted mt-2')

            def delete():
                try:
                    self.registry.delete(script)
                    self.render_script_list()
                    dialog.close()
                    ui.notify('Script deleted', type='positive')
                except (OSError, ValueError) as error:
                    ui.notify(str(error), type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Delete', on_click=delete).props('unelevated color=negative')
        dialog.open()

    def open_script(self, script):
        saved = self.settings.analysis_script_configs.get(script.key, {})
        configs = list(script.configs)
        shared_configs = (
            ScriptConfig('input_dir', 'Input clips folder', 'Folder containing video clips to analyze.', self.settings.analysis_clips_dir),
            ScriptConfig('output_dir', 'Output folder', 'Folder where analysis JSON files are written.', self.settings.analysis_output_dir),
            ScriptConfig('request_file', 'Prompt file', 'Optional file containing an extra prompt template.', self.settings.analysis_request_file),
            ScriptConfig('workflow_path', 'Workflow path', 'Workflow path sent to the API.', self.settings.analysis_workflow_path),
            ScriptConfig('skip_existing', 'Skip existing outputs', 'Do not send clips that already have an output JSON.', self.settings.analysis_skip_existing, 'boolean'),
        )
        declared_keys = {config.key for config in configs}
        configs.extend(config for config in shared_configs if config.key not in declared_keys)
        with ui.dialog() as dialog, ui.card().classes('nicegui-card text-white w-[min(760px,94vw)] p-6'):
            ui.label(script.name).classes('text-2xl font-semibold')
            ui.label(script.description).classes('muted mt-1')
            ui.textarea(value=self.registry.prompt_text(script)).props('readonly outlined').classes('w-full mt-4')
            fields = {}
            with ui.column().classes('w-full gap-3 mt-4'):
                for config in configs:
                    value = config.value_for(saved, self.default_config_value(config.key))
                    if config.kind == 'boolean':
                        fields[config.key] = ui.checkbox(config.name, value=bool(value))
                    elif config.kind == 'number':
                        fields[config.key] = ui.number(config.name, value=value, step=1).classes('w-full')
                    else:
                        fields[config.key] = ui.input(config.name, value='' if value is None else str(value)).classes('w-full')
                    ui.label(config.description).classes('muted text-xs -mt-2')

            async def run_script():
                values = {key: field.value for key, field in fields.items()}
                missing = [config.name for config in configs if config.value_for(values) in (None, '')]
                if missing:
                    ui.notify(f'Required fields: {", ".join(missing)}', type='negative')
                    return
                self.settings.analysis_script_configs[script.key] = values
                self.settings_store.save(self.settings)
                await self.run_analysis(script, fields, None, dialog)

            with ui.row().classes('w-full justify-end gap-2 mt-5'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Run analysis', icon='play_arrow', on_click=run_script).props('unelevated').classes('bg-orange-600 text-white')
        dialog.open()

    def default_config_value(self, key):
        return {
            'input_dir': self.settings.analysis_clips_dir,
            'output_dir': self.settings.analysis_output_dir,
            'request_file': self.settings.analysis_request_file,
            'workflow_path': self.settings.analysis_workflow_path,
            'skip_existing': self.settings.analysis_skip_existing,
        }.get(key)

    def show_prompt(self, script, parent_dialog):
        if parent_dialog:
            parent_dialog.close()
        with ui.dialog() as dialog, ui.card().classes('bg-slate-800 text-white w-[min(720px,90vw)] p-6'):
            ui.label(f'{script.name} prompt').classes('text-2xl font-semibold')
            ui.textarea(value=self.registry.prompt_text(script)).props('readonly outlined').classes('w-full mt-5')
            ui.button('Close', on_click=dialog.close).props('flat').classes('mt-4')
        dialog.open()

    async def run_analysis(self, script, fields, prompt, dialog):
        dialog.close()
        try:
            input_dir = Path(fields['input_dir'].value)
            output_dir = Path(fields['output_dir'].value)
            config = {key: field.value for key, field in fields.items()}
            pipeline_logger = get_pipeline_logger('analysis', script=script.key)
            pipeline_logger.event('analysis_requested', input_dir=str(input_dir), output_dir=str(output_dir))
            service = PipelineService(self.settings.analysis_api_url, self.settings.analysis_request_timeout, self.settings.analysis_max_retries)
            result = await run.io_bound(service.analyze, script, config, pipeline_logger)
            self.log.push(result)
            ui.notify('Analysis complete', type='positive')
        except (APIProcessingError, OSError, ValueError) as error:
            self.log.push(f'Analysis stopped: {error}')
            ui.notify('Analysis stopped safely. See Activity for details.', type='negative')