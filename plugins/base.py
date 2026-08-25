from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ScriptConfig:
    key: str
    name: str
    description: str
    default: Any = None
    kind: str = 'text'


@dataclass
class AnalysisScript:
    key: str
    name: str
    description: str
    prompt_file: str
    configs: list[ScriptConfig] = field(default_factory=list)
    workspace_root: Path | None = field(default=None, repr=False, compare=False)


class ScriptPlugin(Protocol):
    def get_script(self) -> AnalysisScript: ...