import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

from nicegui import ui

from config import AppSettings, SettingsStore
from plugins.base import ScriptConfig
from plugins.registry import ScriptRegistry
from services.file_system_provider import FileSystemProvider
from ui.analysis_page import AnalysisPageMixin
from ui.cut_page import CutPageMixin
from ui.navigation import NavigationMixin
from ui.settings_page import SettingsPageMixin


logger = logging.getLogger(__name__)


class VideoPipelineUI(NavigationMixin, SettingsPageMixin, AnalysisPageMixin, CutPageMixin):
    def __init__(self, settings_store: SettingsStore):
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.registry = ScriptRegistry(Path(__file__).with_name('plugins'))
        self.editor_workspace = Path(__file__).with_name('.script_workspaces') / f'script-{uuid4().hex}'
        self.file_system = FileSystemProvider(self.editor_workspace)
        self.running = False
        self.pages = {}

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
        prompt_path = (Path(__file__).with_name('.script_workspaces') / workspace_id / 'prompts' / 'my_prompt.txt').resolve()
        return f"from plugins.base import AnalysisScript, ScriptConfig\n\n\ndef get_script():\n    return AnalysisScript(key='{key}', name='My Script', description='Describe this script.', prompt_file='prompts/my_prompt.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Where clips are read from.', None), ScriptConfig('request_file', 'Prompt file', 'Prompt file used for this script.', {str(prompt_path)!r})])\n"

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


__all__ = ['VideoPipelineUI']


_facade_ready = True