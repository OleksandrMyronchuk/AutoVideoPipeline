import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class FileSystemProvider:
    """Provider for the isolated plugin and prompt workspace."""

    ALLOWED_EXTENSIONS = {'.py', '.txt', '.json', '.md'}
    ALLOWED_DIRECTORIES = {'plugins', 'prompts'}

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        for directory in self.ALLOWED_DIRECTORIES:
            (self.workspace_root / directory).mkdir(exist_ok=True)
        logger.info('workspace initialized root=%s', self.workspace_root)

    def safe_path(self, relative_path: str) -> Path:
        path = (self.workspace_root / relative_path).resolve()
        if self.workspace_root not in path.parents and path != self.workspace_root:
            raise ValueError('Path must remain inside the scripts workspace.')
        relative = path.relative_to(self.workspace_root)
        if not relative.parts or relative.parts[0] not in self.ALLOWED_DIRECTORIES:
            raise ValueError('Only plugin and prompt files can be opened here.')
        if path.suffix and path.suffix not in self.ALLOWED_EXTENSIONS:
            raise ValueError('Only script and prompt files can be opened here.')
        return path

    def tree(self) -> list[dict]:
        tree = [self._node(path) for path in sorted(self.workspace_root.iterdir(), key=lambda item: item.name.lower()) if path.is_dir() and path.name in self.ALLOWED_DIRECTORIES]
        logger.info('workspace tree root=%s files=%s', self.workspace_root, self._file_paths())
        return tree

    def read(self, relative_path: str) -> str:
        path = self.safe_path(relative_path)
        content = path.read_text(encoding='utf-8')
        logger.info('workspace read root=%s path=%s bytes=%d', self.workspace_root, relative_path, len(content.encode('utf-8')))
        return content

    def write(self, relative_path: str, content: str) -> None:
        path = self.safe_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        logger.info('workspace write root=%s path=%s bytes=%d', self.workspace_root, relative_path, len(content.encode('utf-8')))

    def create(self, relative_path: str, directory: bool = False) -> None:
        path = self.safe_path(relative_path)
        if directory:
            path.mkdir(parents=True, exist_ok=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=False)
        logger.info('workspace create root=%s path=%s directory=%s', self.workspace_root, relative_path, directory)

    def _file_paths(self) -> list[str]:
        return sorted(path.relative_to(self.workspace_root).as_posix() for path in self.workspace_root.rglob('*') if path.is_file() and self._visible(path))

    def _node(self, path: Path) -> dict:
        relative = path.relative_to(self.workspace_root).as_posix()
        node = {'id': relative, 'label': path.name, 'icon': 'folder' if path.is_dir() else 'description'}
        if path.is_dir():
            node['children'] = [self._node(child) for child in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())) if self._visible(child)]
        return node

    @staticmethod
    def _visible(path: Path) -> bool:
        return path.name not in {'.git', '.venv', '__pycache__', 'node_modules', '.script.json'} and (path.is_dir() or path.suffix in FileSystemProvider.ALLOWED_EXTENSIONS)