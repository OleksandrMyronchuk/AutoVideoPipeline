import logging
from pathlib import Path
from uuid import UUID, uuid4

from nicegui import run, ui

from config import AppSettings, SettingsStore
from plugins.registry import ScriptRegistry
from services.analysis_runner import AnalysisRunner
from services.api_client import APIProcessingError, BufferedAPIClient
from services.file_system_provider import FileSystemProvider
from video_processor import VideoProcessor


logger = logging.getLogger(__name__)


class VideoPipelineUI:
    def __init__(self, settings_store: SettingsStore):
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.registry = ScriptRegistry(Path(__file__).with_name('plugins'))
        self.file_system = None
        self.editor_workspace = Path(__file__).with_name('.script_workspaces') / f'script-{uuid4().hex}'
        self.running = False
        self.pages = {}

    def build(self, initial_page='cut'):
        ui.colors(primary='#f97316', secondary='#202d43', accent='#fb923c', dark='#111827')
        ui.add_head_html('''
            <style>
                body { margin: 0; background: #070b14; color: #f8fafc; }
                .app-sidebar { background: #0b1220; }
                .app-panel { background: #182235; }
                .app-input .q-field__control { background: #202d43; }
                .app-input .q-field__native, .app-input .q-field__label { color: #f8fafc; }
                .muted { color: #93a4bd; }
                .q-linear-progress { background: #202d43; }
                .nicegui-card, .q-card { background: #293952 !important; color: #ffffff !important; }
                .nicegui-card .text-slate-300, .q-card .text-slate-300 { color: #e2e8f0 !important; }
                .editor-layout { background: #0f172a; border-radius: 12px; padding: 12px; }
                .editor-explorer { background: #111c2e; border-radius: 8px; min-width: 220px; resize: horizontal; overflow: auto; }
                .editor-surface { background: #0b1220; border-radius: 8px; min-width: 0; }
                .editor-host { min-width: 0; resize: vertical; overflow: auto; }
                .editor-host > div { height: 100%; width: 100%; }
                .editor-layout .q-separator { background: #263650; }
                .editor-explorer .q-tree { color: #dbe7f5; }
                .editor-explorer .q-tree__label { color: #dbe7f5; }
                .editor-explorer .q-tree__icon { color: #8db4df; }
            </style>
        ''')
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
        ui.button(label, icon=icon, on_click=lambda: ui.navigate.to(route)).props('flat align=left').classes('w-full text-slate-300 justify-start')

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
            self.script_list = ui.column().classes('w-full gap-3')
            self.render_script_list()

    def render_script_list(self):
        self.script_list.clear()
        with self.script_list:
            for script in self.registry.all():
                with ui.card().classes('nicegui-card w-full border border-slate-600 p-4'):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.column().classes('gap-1'):
                            ui.label(script.name).classes('text-white text-lg font-semibold')
                            ui.label(script.description).classes('muted')
                        with ui.row().classes('items-center gap-1'):
                            ui.button('Edit', icon='edit', on_click=lambda item=script: self.open_script(item)).props('flat')
                            if script.workspace_root:
                                ui.button('Rename', icon='drive_file_rename_outline', on_click=lambda item=script: self.open_rename_script(item)).props('flat')
                                ui.button('Delete', icon='delete', on_click=lambda item=script: self.confirm_delete_script(item)).props('flat color=negative')

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
        self.open_editor(script)

    def show_prompt(self, script, parent_dialog):
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
                    ui.button('Create a New Script', icon='add', on_click=lambda: self.open_new_script_editor(dialog)).props('unelevated').classes('w-full bg-orange-600')
                    ui.label('Allow you to create a new script using hooks.').classes('muted text-sm')
            ui.button('Close', on_click=dialog.close).props('flat').classes('mt-2')
        dialog.open()

    def open_new_script_editor(self, parent_dialog):
        parent_dialog.close()
        workspace_id = uuid4().hex
        workspace = Path(__file__).with_name('.script_workspaces') / workspace_id
        provider = FileSystemProvider(workspace)
        provider.write('plugins/my_script.py', self.default_plugin_content(workspace_id))
        provider.write('prompts/my_prompt.txt', 'Analyze this video and return structured JSON.\n')
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
        default_file = 'plugins/my_script.py'
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
                    ui.label('FILES').classes('muted text-xs font-semibold tracking-wider mb-2')
                    ui.label('PLUGINS + PROMPTS').classes('text-slate-400 text-xs font-semibold mb-1')
                    ui.label(f'Workspace: {workspace_id}').classes('muted text-xs mb-2')
                    selected_folder = {'path': 'plugins'}
                    workspace_tree = ui.tree(
                        self.file_system.tree(),
                        label_key='label',
                        on_select=lambda event: self.select_editor_tree_item(event, editor_id, selected_folder),
                    ).props('dense no-connectors').classes('w-full text-slate-200')
                    ui.separator().classes('my-2')
                    ui.button('Create file', icon='note_add', on_click=lambda: self.create_provider_file(False, workspace_tree, selected_folder)).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
                    ui.button('Create folder', icon='create_new_folder', on_click=lambda: self.create_provider_file(True, workspace_tree, selected_folder)).props('flat align=left').classes('w-full justify-start text-slate-300 text-xs')
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
        default_file = f'prompts/{Path(script.prompt_file).name}' if script else 'plugins/my_script.py'
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

    async def select_editor_tree_item(self, event, editor_id, selected_folder):
        relative_path = event.value
        try:
            path = self.file_system.safe_path(relative_path)
            if path.is_dir():
                selected_folder['path'] = relative_path
                return
            selected_folder['path'] = path.parent.relative_to(self.file_system.workspace_root).as_posix()
            await self.load_editor_file(relative_path, editor_id)
        except (OSError, ValueError) as error:
            ui.notify(str(error), type='negative')

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
            ui.markdown('''Create `plugins/my_script.py` and `prompts/my_script.txt`, then restart the app:\n\n```python\nfrom plugins.base import AnalysisScript, ScriptConfig\n\ndef get_script():\n    return AnalysisScript(\n        key="my_script",\n        name="My Script",\n        description="What this script analyzes.",\n        prompt_file="prompts/my_script.txt",\n        configs=[ScriptConfig("input_dir", "Input clips folder", "Where clips are read from.", r"A:\\clips")],\n    )\n```\n\nThe registry imports files in `plugins/` that expose `get_script()`. Keep processing logic in a separate service module and use `BufferedAPIClient` for API calls. It stops safely on HTTP failures, network failures, empty or `nothing` responses, and duplicate responses.''').classes('text-slate-200 mt-4')
            ui.button('Close', on_click=dialog.close).props('flat').classes('mt-5')
        dialog.open()

    async def run_analysis(self, script, fields, prompt, dialog):
        dialog.close()
        try:
            input_dir = Path(fields['input_dir'].value)
            output_dir = Path(fields['output_dir'].value)
            request_file = Path(fields['request_file'].value)
            client = BufferedAPIClient(self.settings.analysis_api_url, self.settings.analysis_request_timeout, self.settings.analysis_max_retries)
            runner = AnalysisRunner(client)
            result = await run.io_bound(runner.run, script, input_dir, output_dir, fields['workflow_path'].value, request_file, fields['skip_existing'].value)
            self.log.push(result)
            ui.notify('Analysis complete', type='positive')
        except (APIProcessingError, OSError, ValueError) as error:
            self.log.push(f'Analysis stopped: {error}')
            ui.notify('Analysis stopped safely. See Activity for details.', type='negative')

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
