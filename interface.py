import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

from nicegui import run, ui

from config import AppSettings, SettingsStore
from plugins.base import ScriptConfig
from plugins.registry import ScriptRegistry
from services.api_client import APIProcessingError
from services.file_system_provider import FileSystemProvider
from services.logging_utils import get_pipeline_logger
from services.pipeline_service import PipelineService
from ui.theme import configure_theme
from ui.cut_page import CutPageMixin


logger = logging.getLogger(__name__)


class VideoPipelineUI(CutPageMixin):
    VALID_PAGES = {'cut', 'analyze', 'settings'}

    def __init__(self, settings_store: SettingsStore):
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.registry = ScriptRegistry(Path(__file__).with_name('plugins'))
        self.editor_workspace = Path(__file__).with_name('.script_workspaces') / f'script-{uuid4().hex}'
        self.file_system = FileSystemProvider(self.editor_workspace)
        self.running = False
        self.pages = {}

    def build(self, initial_page='cut'):
        initial_page = initial_page if initial_page in self.VALID_PAGES else 'cut'
        self.settings.last_page = initial_page
        self.settings_store.save(self.settings)
        configure_theme()
        with ui.left_drawer(value=True).classes('app-sidebar w-64 p-5'):
            ui.label('AVP').classes('bg-orange-600 text-white text-2xl font-black px-3 py-1 rounded-sm')
            ui.label('AUTO VIDEO\nPIPELINE').classes('text-white text-lg font-semibold mt-4 mb-10 whitespace-pre-line')
            self.nav_button('content_cut', 'Cut Video', 'cut')
            self.nav_button('analytics', 'Analyze Video', 'analyze')
            self.nav_button('settings', 'Settings', 'settings')
            ui.space()
            ui.label('LOCAL PROCESSING').classes('text-slate-500 text-xs font-semibold')

        with ui.column().classes('w-full min-h-screen p-8 md:p-12 app-panel'):
            self.build_cut_page()
            self.build_analyze_page()
            self.build_settings_page()
        self.show_page(initial_page)

    def nav_button(self, icon, label, page):
        route = f'/{page}_video' if page != 'settings' else '/settings'
        ui.button(label, icon=icon, on_click=lambda: self.navigate_to_page(page, route)).props('flat align=left').classes('w-full text-slate-300 justify-start')

    def navigate_to_page(self, page, route):
        if page in self.VALID_PAGES:
            self.settings.last_page = page
            self.settings_store.save(self.settings)
        ui.navigate.to(route)

    def page_header(self, title, subtitle):
        ui.label(title).classes('text-white text-4xl font-semibold')
        ui.label(subtitle).classes('muted mt-1 mb-8')

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
                            document.getElementById('c' + __BRIDGE_ID__).dispatchEvent(new CustomEvent('scriptReorder', {detail: {order}, bubbles: false}));
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
            self.script_reorder_bridge.on('script-reorder', self.reorder_scripts, js_handler='(event) => emit(event.detail)')
            self.script_list = ui.column().classes('w-full gap-3')
            self.render_script_list()

    def render_script_list(self):
        self.script_list.clear()
        scripts = self.ordered_scripts()
        with self.script_list:
            for index, script in enumerate(scripts):
                ui.element('div').props(f'data-drop-index="{index}"').classes('script-drop-zone')
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
            ui.element('div').props(f'data-drop-index="{len(scripts)}"').classes('script-drop-zone')

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
        order = event.args.get('order', [])
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

    def open_script_menu(self):
        with ui.dialog() as dialog, ui.card().classes('nicegui-card text-white w-[min(900px,94vw)] p-6'):
            ui.label('Add a script').classes('text-2xl font-semibold')
            with ui.row().classes('w-full items-stretch gap-4 mt-6'):
                with ui.column().classes('flex-1 gap-1'):
                    ui.button('Read Docs', icon='menu_book', on_click=lambda: self.show_plugin_docs(dialog)).props('outline').classes('w-full')
                    ui.label('Open complete and cohesive documentation.').classes('muted text-sm')
                with ui.column().classes('flex-1 gap-1'):
                    ui.button('Create a New Script', icon='add', on_click=lambda: self.open_new_script_dialog(dialog)).props('unelevated').classes('w-full bg-orange-600')
                    ui.label('Allow you to create a new script using hooks.').classes('muted text-sm')
            ui.button('Close', on_click=dialog.close).props('flat').classes('mt-2')
        dialog.open()

    def open_new_script_dialog(self, parent_dialog):
        parent_dialog.close()
        with ui.dialog() as dialog, ui.card().classes('nicegui-card text-white w-[min(560px,92vw)] p-5'):
            ui.label('Name your script').classes('text-xl font-semibold')
            name_input = ui.input('Script name').classes('w-full mt-4')

            def create():
                name = (name_input.value or '').strip()
                if not name:
                    ui.notify('Script name cannot be empty.', type='negative')
                    return
                self.open_new_script_editor(dialog, name)

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Create', on_click=create).props('unelevated').classes('bg-orange-600 text-white')
        dialog.open()

    def open_new_script_editor(self, dialog, name):
        dialog.close()
        workspace_id = uuid4().hex
        workspace = Path(__file__).with_name('.script_workspaces') / workspace_id
        provider = FileSystemProvider(workspace)
        provider.write('plugins/my_script.py', self.default_plugin_content(workspace_id))
        provider.write('prompts/my_prompt.txt', 'Analyze this video and return structured JSON.\n')
        (workspace / '.script.json').write_text(json.dumps({'name': name}, indent=2) + '\n', encoding='utf-8')
        self.registry.reload()
        self.render_script_list()
        logger.info('new script opened workspace_id=%s root=%s', workspace_id, workspace.resolve())
        ui.run_javascript(f"window.open('/script_editor/{workspace_id}', '_blank', 'noopener,noreferrer')")

    def build_editor_page(self, workspace_id=None):
        workspace_id = workspace_id or uuid4().hex
        try:
            workspace_id = UUID(workspace_id).hex
        except (AttributeError, ValueError):
            raise ValueError('Invalid script workspace.') from None
        self.editor_workspace = Path(__file__).with_name('.script_workspaces') / workspace_id
        self.file_system = FileSystemProvider(self.editor_workspace)
        if not self.file_system._file_paths():
            self.file_system.write('plugins/my_script.py', self.default_plugin_content(workspace_id))
            self.file_system.write('prompts/my_prompt.txt', 'Analyze this video and return structured JSON.\n')
            logger.info('starter files created workspace_id=%s root=%s', workspace_id, self.editor_workspace.resolve())
        logger.info('script editor page opened workspace_id=%s root=%s files=%s', workspace_id, self.editor_workspace.resolve(), self.file_system._file_paths())
        files = self.file_system._file_paths()
        default_file = next((path for path in files if path.startswith('plugins/') and path.endswith('.py')), 'plugins/my_script.py')
        editor_id = 'new-script-editor'
        ui.add_head_html('''
            <style>
                #c3.nicegui-content { margin: -16px !important; }
                body { margin: 0; background: #101318; color: #f4f6f8; }
                .editor-layout, .editor-explorer, .editor-surface { background: transparent; }
                .editor-layout { border-radius: 0; padding: 12px 0; }
                .editor-explorer { border-radius: 0; }
                .editor-explorer .q-tree__node-header-content,
                .editor-explorer .q-tree__label { color: #f4f6f8 !important; transition: color 0.3s; }
                .editor-explorer .q-tree__icon,
                .editor-explorer .q-tree__node-header .q-icon { color: #a9c7e8 !important; }
                .editor-explorer .q-tree__node-header:hover .q-tree__node-header-content { color: #ffb36b !important; }
                .editor-surface .text-muted, .editor-surface .muted,
                .editor-explorer .muted { color: #b8c2ce !important; }
                .editor-dialog .q-field__label,
                .editor-dialog .q-field__native { color: #ffffff !important; }
                .editor-dialog .q-field__control { background: #202d43 !important; }
            </style>
        ''')
        with ui.column().classes('w-full min-h-screen text-white p-5 md:p-8'):
            with ui.row().classes('w-full items-end justify-between gap-4 mb-5'):
                with ui.column().classes('gap-1'):
                    ui.label('Create a New Script').classes('text-3xl font-semibold')
                    ui.label('Build a plugin and its prompt in one focused workspace.').classes('muted')
                ui.label('SCRIPT WORKSPACE').classes('text-orange-400 text-xs font-semibold tracking-wider')
            with ui.row().classes('editor-layout w-full items-stretch gap-3 flex-col md:flex-row'):
                with ui.column().classes('editor-explorer w-full md:w-72 shrink-0 p-3 gap-1'):
                    with ui.row().classes('w-full items-center justify-between mb-2'):
                        ui.label('FILES').classes('muted text-xs font-semibold tracking-wider')
                        expand_button = ui.button('Collapse all', icon='unfold_less', on_click=lambda: toggle_folders()).props('flat dense').classes('text-slate-300 text-xs')
                    ui.label('PLUGINS + PROMPTS').classes('text-slate-400 text-xs font-semibold mb-1')
                    ui.label(f'Workspace: {workspace_id}').classes('muted text-xs mb-2')
                    selected_folder = {'path': 'plugins'}
                    selected_item = {'path': None}
                    folders_expanded = {'value': True}
                    workspace_tree = ui.tree(
                        self.file_system.tree(),
                        label_key='label',
                        on_select=lambda event: self.select_editor_tree_item(event, editor_id, selected_folder, selected_item),
                    ).props('dense no-connectors').classes('w-full text-slate-200')

                    def toggle_folders():
                        folder_paths = self.editor_folder_paths(workspace_tree.props['nodes'])
                        if folders_expanded['value']:
                            workspace_tree.collapse(folder_paths)
                            expand_button.text = 'Expand all'
                            expand_button.props('icon=unfold_more')
                        else:
                            workspace_tree.expand(folder_paths)
                            expand_button.text = 'Collapse all'
                            expand_button.props('icon=unfold_less')
                        folders_expanded['value'] = not folders_expanded['value']
                        expand_button.update()

                    workspace_tree.expand(self.editor_folder_paths(workspace_tree.props['nodes']))
                    ui.separator().classes('my-2')
                    ui.button('Create file', icon='note_add', on_click=lambda: self.create_provider_file(False, workspace_tree, selected_folder)).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
                    ui.button('Create folder', icon='create_new_folder', on_click=lambda: self.create_provider_file(True, workspace_tree, selected_folder)).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
                    ui.button('Rename', icon='drive_file_rename_outline', on_click=lambda: self.rename_provider_item(workspace_tree, selected_folder, selected_item, editor_id)).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
                    ui.button('Delete', icon='delete', on_click=lambda: self.confirm_delete_provider_item(workspace_tree, selected_folder, selected_item)).props('flat align=left color=negative').classes('w-full justify-start text-xs')
                with ui.column().classes('editor-surface flex-1 min-w-0 p-3'):
                    ui.label('EDITOR').classes('muted text-xs font-semibold tracking-wider mb-2')
                    ui.button('Save', icon='save', on_click=lambda: self.save_active_editor(editor_id)).props('unelevated').classes('bg-orange-600 text-white self-start mb-2')
                    editor_container = ui.html(f'<div id="{editor_id}" style="height:min(72vh, 720px);min-height:420px;max-height:80vh;width:100%;"></div>', sanitize=False).classes('editor-host w-full')
            ui.label('Changes save with Ctrl+S / Cmd+S.').classes('muted text-xs mt-3')
        ui.add_body_html('''
            <script>
                window.avpEditors = window.avpEditors || {};
                window.avpCreateEditor = function(id, value, path) {
                    const create = function() {
                        window.require.config({paths: {vs: '/monaco/vs'}});
                        window.require(['vs/editor/editor.main'], function() {
                            const editor = monaco.editor.create(document.getElementById(id), {value: value, language: path.endsWith('.py') ? 'python' : 'plaintext', theme: 'vs-dark', automaticLayout: true, minimap: {enabled: false}});
                            window.avpEditors[id] = {instance: editor, path: path};
                            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function() {
                                emitEvent('editor-save', {path: window.avpEditors[id].path, value: editor.getValue()});
                            });
                        });
                    };
                    if (window.avpMonacoReady) {
                        create();
                    } else {
                        const loader = document.createElement('script');
                        loader.src = '/monaco/vs/loader.js';
                        loader.onload = function() {
                            window.avpMonacoReady = true;
                            create();
                        };
                        document.body.appendChild(loader);
                    }
                };
                window.avpSetEditorFile = function(id, path, value) {
                    if (window.avpEditors[id]) {
                        window.avpEditors[id].path = path;
                        window.avpEditors[id].instance.setValue(value);
                    }
                };
            </script>
        ''')
        editor_container.on('editor-save', self.save_editor_event)
        ui.timer(0.5, lambda: ui.run_javascript(f'window.avpCreateEditor({editor_id!r}, {self.read_editor_file(default_file)!r}, {default_file!r})'), once=True)

    def open_editor(self, script=None, mode='edit'):
        workspace_id = script.workspace_root.name if script and script.workspace_root else uuid4().hex
        ui.run_javascript(f"window.open('/script_editor/{workspace_id}', '_blank', 'noopener,noreferrer')")
        return

        plugin_dir = Path(__file__).with_name('plugins')
        prompt_dir = Path(__file__).with_name('prompts')
        editor_files = sorted([f'plugins/{path.name}' for path in plugin_dir.glob('*.py') if path.stem not in {'__init__', 'base', 'builtin', 'registry'}] + [f'prompts/{path.name}' for path in prompt_dir.glob('*.txt')])
        default_file = f'prompts/{Path(script.prompt_file).name}' if script else 'plugins/narration_dialogues.py'
        if default_file not in editor_files:
            editor_files.append(default_file)
        editor_files = sorted(set(editor_files))
        editor_id = f'script-editor-{id(self)}'
        with ui.dialog() as dialog, ui.card().classes('nicegui-card text-white w-[min(1100px,96vw)] p-5'):
            ui.label(f'Edit {script.name}' if script else 'Create a New Script').classes('text-2xl font-semibold')
            with ui.row().classes('w-full items-stretch gap-4 mt-4'):
                with ui.column().classes('w-64 shrink-0 bg-slate-900/60 p-3 rounded gap-1'):
                    ui.label('FILE MANAGER').classes('muted text-xs font-semibold tracking-wider mb-2')
                    file_buttons = {}
                    for filename in editor_files:
                        file_buttons[filename] = ui.button(filename, on_click=lambda name=filename: self.load_editor_file(name, editor_id)).props('flat align=left').classes('w-full justify-start text-slate-200 text-xs')
                    ui.separator().classes('my-2')
                    ui.button('New plugin file', icon='add', on_click=lambda: self.create_editor_file('plugins')).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
                    ui.button('New prompt file', icon='add', on_click=lambda: self.create_editor_file('prompts')).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
                editor_container = ui.html(f'<div id="{editor_id}" style="height:520px;width:100%;border:1px solid #475569"></div>', sanitize=False).classes('flex-1')
            ui.add_head_html('''
                <script src="/monaco/vs/loader.js"></script>
                <script>
                    window.avpEditors = window.avpEditors || {};
                    function avpCreateEditor(id, value, path) {
                        window.require.config({paths: {vs: '/monaco/vs'}});
                        window.require(['vs/editor/editor.main'], function() {
                            const editor = monaco.editor.create(document.getElementById(id), {value: value, language: 'python', theme: 'vs-dark', automaticLayout: true, minimap: {enabled: false}});
                            window.avpEditors[id] = {instance: editor, path: path};
                            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function() {
                                emitEvent('editor-save', {path: window.avpEditors[id].path, value: editor.getValue()});
                            });
                        });
                    }
                    function avpSetEditorFile(id, path, value) {
                        if (window.avpEditors[id]) {
                            window.avpEditors[id].path = path;
                            window.avpEditors[id].instance.setValue(value);
                        }
                    }
                </script>
            ''')
            ui.timer(0.5, lambda: ui.run_javascript(f'window.avpCreateEditor({editor_id!r}, {self.read_editor_file(default_file)!r}, {default_file!r})'), once=True)
            editor_container.on('editor-save', self.save_editor_event)
            ui.label('Use Ctrl+S / Cmd+S to save the active file.').classes('muted text-xs mt-3')
            ui.button('Close', on_click=dialog.close).props('flat').classes('mt-2')
        dialog.open()

    @staticmethod
    def editor_folder_paths(nodes):
        paths = []
        for node in nodes:
            if 'children' in node:
                paths.append(node['id'])
                paths.extend(VideoPipelineUI.editor_folder_paths(node['children']))
        return paths

    def create_editor_file(self, folder):
        directory = Path(__file__).with_name(folder)
        extension = '.py' if folder == 'plugins' else '.txt'
        stem = 'my_script' if folder == 'plugins' else 'my_prompt'
        candidate = directory / f'{stem}{extension}'
        index = 1
        while candidate.exists():
            candidate = directory / f'{stem}_{index}{extension}'
            index += 1
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if folder == 'plugins':
            candidate.write_text("from plugins.base import AnalysisScript, ScriptConfig\n\n\ndef get_script():\n    return AnalysisScript(key='my_script', name='My Script', description='Describe this script.', prompt_file='prompts/my_prompt.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Where clips are read from.', None)])\n", encoding='utf-8')
        else:
            candidate.write_text('Analyze this video and return structured JSON.\n', encoding='utf-8')
        ui.notify(f'Created {folder}/{candidate.name}', type='positive')

    async def select_editor_tree_item(self, event, editor_id, selected_folder, selected_item):
        relative_path = event.value
        try:
            path = self.file_system.safe_path(relative_path)
            selected_item['path'] = relative_path
            if path.is_dir():
                selected_folder['path'] = relative_path
                return
            selected_folder['path'] = path.parent.relative_to(self.file_system.workspace_root).as_posix()
            await self.load_editor_file(relative_path, editor_id)
        except (OSError, ValueError) as error:
            ui.notify(str(error), type='negative')

    def rename_provider_item(self, workspace_tree, selected_folder, selected_item, editor_id):
        relative_path = selected_item['path']
        if not relative_path:
            ui.notify('Select a file or folder first.', type='negative')
            return
        if relative_path in FileSystemProvider.ALLOWED_DIRECTORIES:
            ui.notify('The plugins and prompts folders cannot be renamed.', type='negative')
            return
        path = Path(relative_path)
        with ui.dialog() as dialog, ui.card().classes('editor-dialog bg-slate-800 text-white w-[min(560px,92vw)] p-5'):
            ui.label(f'Rename {relative_path}').classes('text-xl font-semibold')
            name_input = ui.input('Name', value=path.name).classes('w-full mt-4')

            def rename_item():
                name = (name_input.value or '').strip()
                if not name or '/' in name or '\\' in name or name in {'.', '..'}:
                    ui.notify('Enter a valid name.', type='negative')
                    return
                new_path = f'{path.parent.as_posix()}/{name}'
                try:
                    self.file_system.rename(relative_path, new_path)
                    workspace_tree.props['nodes'] = self.file_system.tree()
                    workspace_tree.update()
                    selected_item['path'] = new_path
                    selected_folder['path'] = path.parent.as_posix()
                    ui.run_javascript(f"if (window.avpEditors[{editor_id!r}] && window.avpEditors[{editor_id!r}].path === {relative_path!r}) window.avpEditors[{editor_id!r}].path = {new_path!r};")
                    dialog.close()
                    ui.notify(f'Renamed to {new_path}', type='positive')
                except (OSError, ValueError) as error:
                    ui.notify(str(error), type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Rename', on_click=rename_item).props('unelevated').classes('bg-orange-600 text-white')
        dialog.open()

    def confirm_delete_provider_item(self, workspace_tree, selected_folder, selected_item):
        relative_path = selected_item['path']
        if not relative_path:
            ui.notify('Select a file or folder first.', type='negative')
            return
        if relative_path in FileSystemProvider.ALLOWED_DIRECTORIES:
            ui.notify('The plugins and prompts folders cannot be deleted.', type='negative')
            return
        with ui.dialog() as dialog, ui.card().classes('editor-dialog bg-slate-800 text-white w-[min(560px,92vw)] p-5'):
            ui.label(f'Delete {relative_path}?').classes('text-xl font-semibold')
            ui.label('This permanently removes the selected item and its contents.').classes('muted mt-2')

            def delete_item():
                try:
                    self.file_system.delete(relative_path)
                    workspace_tree.props['nodes'] = self.file_system.tree()
                    workspace_tree.update()
                    selected_item['path'] = None
                    selected_folder['path'] = 'plugins'
                    dialog.close()
                    ui.notify(f'Deleted {relative_path}', type='positive')
                except (OSError, ValueError) as error:
                    logger.exception('editor item deletion failed root=%s path=%s', self.editor_workspace, relative_path)
                    ui.notify(str(error), type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Delete', on_click=delete_item).props('unelevated color=negative')
        dialog.open()

    def create_provider_file(self, directory, workspace_tree, selected_folder):
        folder = selected_folder['path']
        extension = '' if directory else ('.txt' if folder.split('/', 1)[0] == 'prompts' else '.py')
        default = f'{folder}/new_folder' if directory else f'{folder}/new_file{extension}'
        prompt = 'Folder name' if directory else f'File name ({extension} files)'
        with ui.dialog() as dialog, ui.card().classes('editor-dialog bg-slate-800 text-white w-[min(560px,92vw)] p-5'):
            ui.label('Create folder' if directory else 'Create file').classes('text-xl font-semibold')
            ui.label(f'Location: {folder}').classes('muted text-xs mt-2')
            name_input = ui.input(prompt, value=default).classes('w-full mt-4')

            def create_item():
                name = (name_input.value or '').strip().replace('\\', '/')
                if '/' not in name:
                    name = f'{folder}/{name}'
                try:
                    self.file_system.create(name, directory)
                    workspace_tree.props['nodes'] = self.file_system.tree()
                    workspace_tree.update()
                    workspace_tree.expand([name.split('/', 1)[0]])
                    logger.info('editor item created root=%s path=%s directory=%s', self.editor_workspace, name, directory)
                    dialog.close()
                    ui.notify(f'Created {name}', type='positive')
                except (OSError, ValueError) as error:
                    logger.exception('editor item creation failed root=%s path=%s directory=%s', self.editor_workspace, name, directory)
                    ui.notify(str(error), type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Create', on_click=create_item).props('unelevated').classes('bg-orange-600 text-white')
        dialog.open()

    def editor_path(self, relative_path):
        return self.file_system.safe_path(relative_path)

    def read_editor_file(self, relative_path):
        path = self.file_system.safe_path(relative_path)
        return self.file_system.read(relative_path) if path.is_file() else self.default_plugin_content(self.editor_workspace.name)

    async def load_editor_file(self, relative_path, editor_id):
        try:
            content = self.read_editor_file(relative_path)
            await ui.run_javascript(f'window.avpSetEditorFile({editor_id!r}, {relative_path!r}, {content!r})')
        except (OSError, ValueError) as error:
            ui.notify(str(error), type='negative')

    async def save_active_editor(self, editor_id):
        result = await ui.run_javascript(
            f'''(() => {{
                const editor = window.avpEditors[{editor_id!r}];
                return editor ? {{path: editor.path, value: editor.instance.getValue()}} : null;
            }})()'''
        )
        if not result or not result.get('path'):
            ui.notify('No editor file is active.', type='negative')
            return
        try:
            self.file_system.write(result['path'], result.get('value', ''))
            logger.info('editor save button completed root=%s path=%s', self.editor_workspace, result['path'])
            ui.notify(f"Saved {result['path']}", type='positive')
        except (OSError, ValueError) as error:
            logger.exception('editor save button failed root=%s result=%r', self.editor_workspace, result)
            ui.notify(str(error), type='negative')

    def save_editor_event(self, event):
        try:
            relative_path = event.args['path']
            content = event.args['value']
            self.file_system.write(relative_path, content)
            logger.info('editor save completed root=%s path=%s', self.editor_workspace, relative_path)
            ui.notify(f'Saved {relative_path}', type='positive')
        except (KeyError, OSError, ValueError) as error:
            logger.exception('editor save failed root=%s event=%r', self.editor_workspace, event.args)
            ui.notify(str(error), type='negative')

    @staticmethod
    def default_plugin_content(workspace_id):
        key = f'my_script_{workspace_id[:8]}'
        return f"from plugins.base import AnalysisScript, ScriptConfig\n\n\ndef get_script():\n    return AnalysisScript(key='{key}', name='My Script', description='Describe this script.', prompt_file='prompts/my_prompt.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Where clips are read from.', None)])\n"

    async def save_editor_file(self, file_select, editor_id):
        relative_path = file_select.value
        if not relative_path:
            ui.notify('Choose a file first.', type='negative')
            return
        content = await ui.run_javascript(f'window.avpEditors[{editor_id!r}]?.instance.getValue() || ""')
        try:
            self.file_system.write(relative_path, content)
            ui.notify(f'Saved {relative_path}', type='positive')
        except (OSError, ValueError) as error:
            ui.notify(str(error), type='negative')

    def show_plugin_docs(self, parent_dialog):
        parent_dialog.close()
        with ui.dialog() as dialog, ui.card().classes('bg-slate-800 text-white w-[min(820px,92vw)] p-6'):
            ui.label('Plugin documentation').classes('text-2xl font-semibold')
            ui.markdown('''Create `plugins/my_script.py` and `prompts/my_prompt.txt`, then restart the app:\n\n```python\nfrom plugins.base import AnalysisScript, ScriptConfig\n\ndef get_script():\n    return AnalysisScript(\n        key="my_script",\n        name="My Script",\n        description="What this script analyzes.",\n        prompt_file="prompts/my_prompt.txt",\n        configs=[ScriptConfig("input_dir", "Input clips folder", "Where clips are read from.", r"A:\\clips")],\n    )\n```\n\nThe registry imports files in `plugins/` that expose `get_script()`. Keep processing logic in a separate service module and use `BufferedAPIClient` for API calls. It stops safely on HTTP failures, network failures, empty or `nothing` responses, and duplicate responses.''').classes('text-slate-200 mt-4')
            ui.button('Close', on_click=dialog.close).props('flat').classes('mt-5')
        dialog.open()

    async def run_analysis(self, script, fields, prompt, dialog):
        dialog.close()
        try:
            input_dir = Path(fields['input_dir'].value)
            output_dir = Path(fields['output_dir'].value)
            request_file = Path(fields['request_file'].value)
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

    def show_page(self, page_name):
        for name, page in self.pages.items():
            page.set_visibility(name == page_name)

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

    def update_analysis_setting(self, name, event):
        setattr(self.settings, name, event.value)

    def update_analysis_number(self, name, event):
        if event.value is not None:
            setattr(self.settings, name, int(event.value))

    def update_analysis_bool(self, name, event):
        setattr(self.settings, name, bool(event.value))

    def save_settings(self):
        self.settings_store.save(self.settings)
        self.status.text = 'Settings saved'
        self.log.push('Settings updated.')
        ui.notify('Settings saved')

