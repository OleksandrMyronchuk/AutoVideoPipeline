import logging
import threading
from queue import Queue
from pathlib import Path

from nicegui import run, ui

from plugins.base import ScriptConfig
from services.api_client import APIProcessingError
from services.logging_utils import get_pipeline_logger
from services.pipeline_service import PipelineService


logger = logging.getLogger(__name__)


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
                    .script-drop-zone.is-visible { height: 30px; border-color: #fb923c; background: rgba(249, 115, 22, .12); }
                    .script-drop-zone.is-over { background: rgba(249, 115, 22, .28); box-shadow: 0 0 0 1px rgba(251, 146, 60, .4); }
                </style>
            ''')
            
            self.script_reorder_bridge = ui.element('div').classes('hidden')
            reorder_bridge_id = self.script_reorder_bridge.id
            
            ui.add_body_html('''
                <script>
                    (() => {
                        // Store the latest bridge ID safely against SPA navigation
                        window.__avpReorderBridgeId = 'c' + __BRIDGE_ID__;
                        
                        if (window.__avpDragDropInitialized) return;
                        window.__avpDragDropInitialized = true;

                        let draggedKey = null;
                        const clearDropZones = () => document.querySelectorAll('.script-drop-zone').forEach(zone => zone.classList.remove('is-visible', 'is-over'));

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
                            const zone = event.target.closest('.script-drop-zone');
                            document.querySelectorAll('.script-drop-zone').forEach(item => item.classList.remove('is-over'));
                            if (zone) {
                                zone.classList.add('is-over');
                                return;
                            }
                            const card = event.target.closest('.script-card');
                            if (card) {
                                const bounds = card.getBoundingClientRect();
                                const index = [...document.querySelectorAll('.script-card')].indexOf(card);
                                document.querySelector(`.script-drop-zone[data-drop-index="${event.clientY < bounds.top + bounds.height / 2 ? index : index + 1}"]`)?.classList.add('is-over');
                            }
                        });

                        document.addEventListener('drop', (event) => {
                            if (!draggedKey) return;
                            event.preventDefault();
                            const order = [...document.querySelectorAll('.script-card')].map(card => card.dataset.scriptKey);
                            const from = order.indexOf(draggedKey);
                            const zone = event.target.closest('.script-drop-zone');
                            let insertionIndex = zone ? Number(zone.dataset.dropIndex) : NaN;
                            
                            const card = event.target.closest('.script-card');
                            if (!Number.isInteger(insertionIndex) && card) {
                                const bounds = card.getBoundingClientRect();
                                const index = order.indexOf(card.dataset.scriptKey);
                                insertionIndex = event.clientY < bounds.top + bounds.height / 2 ? index : index + 1;
                            }
                            if (from < 0 || !Number.isInteger(insertionIndex)) return;

                            order.splice(from, 1);
                            order.splice(insertionIndex - (from < insertionIndex ? 1 : 0), 0, draggedKey);

                            const bridge = document.getElementById(window.__avpReorderBridgeId);
                            if (bridge) {
                                // Must match the exact casing Vue natively registers (kebab-case)
                                bridge.dispatchEvent(new CustomEvent('script-reorder', { detail: { order: order }, bubbles: false }));
                            }

                            document.querySelectorAll('.script-card').forEach(card => card.classList.remove('is-dragging'));
                            clearDropZones();
                            draggedKey = null;
                        });

                        document.addEventListener('dragend', () => {
                            document.querySelectorAll('.script-card').forEach(card => card.classList.remove('is-dragging'));
                            clearDropZones();
                            draggedKey = null;
                        });
                    })();
                </script>
            '''.replace('__BRIDGE_ID__', str(reorder_bridge_id)))
            
            # args=['detail'] instructs NiceGUI to safely unwrap the CustomEvent's detail field.
            self.script_reorder_bridge.on('script-reorder', self.reorder_scripts, args=['detail'])
            
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
        order = []
        try:
            # Accommodates different payload unwrapping styles across NiceGUI versions
            if hasattr(event, 'args'):
                if isinstance(event.args, dict):
                    if 'detail' in event.args and isinstance(event.args['detail'], dict):
                        order = event.args['detail'].get('order', [])
                    else:
                        order = event.args.get('order', [])
                elif isinstance(event.args, list) and event.args:
                    if isinstance(event.args[0], dict) and 'order' in event.args[0]:
                        order = event.args[0].get('order', [])
        except Exception:
            pass
            
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
                        fields[config.key] = ui.checkbox(config.name, value=bool(value), on_change=lambda event, key=config.key: self.save_analysis_script_value(script.key, key, event.value))
                    elif config.kind == 'number':
                        fields[config.key] = ui.number(config.name, value=value, step=1, on_change=lambda event, key=config.key: self.save_analysis_script_value(script.key, key, event.value)).classes('w-full')
                    else:
                        fields[config.key] = ui.input(config.name, value='' if value is None else str(value), on_change=lambda event, key=config.key: self.save_analysis_script_value(script.key, key, event.value)).classes('w-full')
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

    def save_analysis_script_value(self, script_key, key, value):
        self.settings.analysis_script_configs.setdefault(script_key, {})[key] = value
        self.settings_store.save(self.settings)

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
        progress_queue = Queue()
        resume_event = threading.Event()
        resume_event.set()
        cancel_event = threading.Event()
        with ui.dialog() as progress_dialog, ui.card().classes('nicegui-card text-white w-[min(620px,92vw)] p-6'):
            ui.label(f'Running {script.name}').classes('text-2xl font-semibold')
            progress_status = ui.label('Discovering video clips...').classes('muted mt-1')
            with ui.element('div').classes('relative w-full mt-5'):
                progress_bar = ui.linear_progress(value=0, show_value=False).props('instant-feedback').classes('w-full')
                progress_percentage = ui.label('[0%]').classes('absolute inset-0 flex items-center justify-center text-white pointer-events-none')
            progress_counts = ui.label('Waiting for file count...').classes('text-slate-300 mt-2')
            progress_current = ui.label('').classes('muted text-sm mt-2 break-all')
            with ui.row().classes('w-full justify-end gap-2 mt-5'):
                progress_pause = ui.button('Pause', icon='pause', on_click=lambda: toggle_pause()).props('outline')
                progress_cancel = ui.button('Cancel', icon='stop', on_click=lambda: cancel_analysis()).props('flat color=negative')
                progress_close = ui.button('Close', on_click=progress_dialog.close).props('flat')
                progress_close.disable()

            def toggle_pause():
                if resume_event.is_set():
                    resume_event.clear()
                    progress_pause.text = 'Resume'
                    progress_pause.props('icon=play_arrow')
                    progress_status.text = 'Paused. No new API requests will start.'
                else:
                    resume_event.set()
                    progress_pause.text = 'Pause'
                    progress_pause.props('icon=pause')

            def cancel_analysis():
                cancel_event.set()
                resume_event.set()
                progress_cancel.disable()
                progress_pause.disable()
                progress_status.text = 'Cancelling after the current request...'
                progress_dialog.close()

            def update_progress():
                while not progress_queue.empty():
                    update = progress_queue.get_nowait()
                    total = update.get('total', 0)
                    completed = update.get('completed', 0)
                    progress_bar.value = completed / total if total else 0
                    progress_percentage.text = f'[{round(completed / total * 100) if total else 0}%]'
                    progress_counts.text = f'{completed} processed, {update.get("remaining", 0)} remaining of {total}'
                    progress_current.text = f'Current file: {update["clip"]}' if update.get('clip') else ''
                    status = update.get('status')
                    progress_status.text = {
                        'discovered': 'Clips discovered. Starting analysis...',
                        'processing': 'Analyzing current clip...',
                        'skipped': 'Skipped existing result.',
                        'completed': 'Clip analysis complete.',
                        'finished': 'Analysis complete.',
                        'paused': 'Paused. No new API requests will start.',
                        'resumed': 'Resuming analysis...',
                        'cancelled': 'Analysis cancelled safely.',
                    }.get(status, 'Analysis stopped.')
                    if status in {'finished', 'cancelled'}:
                        progress_close.enable()

            progress_timer = ui.timer(0.2, update_progress)
        progress_dialog.open()

        def on_progress(update):
            progress_queue.put(update)

        try:
            input_dir = Path(fields['input_dir'].value)
            output_dir = Path(fields['output_dir'].value)
            config = {key: field.value for key, field in fields.items()}
            pipeline_logger = get_pipeline_logger('analysis', script=script.key)
            pipeline_logger.event('analysis_requested', input_dir=str(input_dir), output_dir=str(output_dir))
            service = PipelineService(self.settings.analysis_api_url, self.settings.analysis_request_timeout, self.settings.analysis_max_retries)
            result = await run.io_bound(service.analyze, script, config, pipeline_logger, on_progress, resume_event, cancel_event)
            update_progress()
            self.log.push(result)
            if cancel_event.is_set():
                ui.notify('Analysis cancelled safely', type='warning')
            else:
                ui.notify('Analysis complete', type='positive')
        except (APIProcessingError, OSError, ValueError) as error:
            progress_queue.put({'status': 'failed', 'clip': str(error)})
            update_progress()
            progress_close.enable()
            self.log.push(f'Analysis stopped: {error}')
            ui.notify('Analysis stopped safely. See Activity for details.', type='negative')
        finally:
            progress_timer.cancel()