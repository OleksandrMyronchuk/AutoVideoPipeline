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
    field_type: str = 'input'

    def value_for(self, saved: dict[str, Any], fallback: Any = None) -> Any:
        if self.key in saved:
            return saved[self.key]
        return self.default if self.default is not None else fallback


@dataclass
class ScriptHooks:
    include_previous_result: bool = False
    merge_json: bool = False


@dataclass
class AnalysisScript:
    key: str
    name: str
    description: str
    prompt_file: str
    configs: list[ScriptConfig] = field(default_factory=list)
    hooks: ScriptHooks = field(default_factory=ScriptHooks)
    workspace_root: Path | None = field(default=None, repr=False, compare=False)


class ScriptPlugin(Protocol):
    def get_script(self) -> AnalysisScript: ...