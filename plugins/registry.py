import importlib.util
import logging
from pathlib import Path

from .base import AnalysisScript
from .builtin import builtin_scripts


logger = logging.getLogger(__name__)


class ScriptRegistry:
    def __init__(self, external_dir: Path):
        self.external_dir = external_dir.resolve()
        self.workspace_dir = self.external_dir.parent / '.script_workspaces'
        self.scripts = {script.key: script for script in builtin_scripts()}
        self.load_external()

    def load_external(self):
        self._load_external_dir(self.external_dir)
        if not self.workspace_dir.is_dir():
            return
        for workspace in self.workspace_dir.iterdir():
            self._load_external_dir(workspace / 'plugins', workspace)

    def _load_external_dir(self, directory: Path, workspace_root: Path | None = None):
        if not directory.is_dir():
            return
        for file in directory.glob('*.py'):
            if file.stem in {'__init__', 'base', 'builtin', 'registry'}:
                continue
            module_name = f'avp_plugin_{workspace_root.name}_{file.stem}' if workspace_root else file.stem
            spec = importlib.util.spec_from_file_location(module_name, file)
            if not spec or not spec.loader:
                continue
            try:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                factory = getattr(module, 'get_script', None)
                if factory:
                    script = factory()
                    if isinstance(script, AnalysisScript):
                        script.workspace_root = workspace_root
                        self.scripts[script.key] = script
                    else:
                        logger.warning('ignored plugin without AnalysisScript file=%s', file)
                else:
                    logger.warning('ignored plugin without get_script file=%s', file)
            except Exception:
                logger.exception('ignored plugin that failed to load file=%s', file)

    def all(self) -> list[AnalysisScript]:
        return list(self.scripts.values())

    def get(self, key: str) -> AnalysisScript:
        return self.scripts[key]

    @staticmethod
    def prompt_text(script: AnalysisScript) -> str:
        root = script.workspace_root or Path(__file__).parents[1]
        prompt_file = root / script.prompt_file
        return prompt_file.read_text(encoding='utf-8').strip()