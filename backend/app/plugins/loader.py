"""Plugin system (Phase 4).

A plugin is a Python module exposing `register(registry: ToolRegistry) -> None`
(and optional `PLUGIN_META`). Plugins extend JARVIS with new tools *without*
touching the core; they still go through the Permission Guard like any tool, so
a plugin can never bypass approvals or allowlists.

Discovery: explicit module list, or a directory of `*_plugin.py` files. Loading
is opt-in (off by default) and every loaded plugin is audited.
"""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

from app.tools.base import ToolRegistry


@dataclass
class LoadedPlugin:
    name: str
    source: str
    tools_added: list[str] = field(default_factory=list)
    error: str | None = None


class PluginManager:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.loaded: list[LoadedPlugin] = []

    def _apply(self, name: str, source: str, module) -> LoadedPlugin:
        before = set(self.registry.names())
        lp = LoadedPlugin(name=name, source=source)
        register = getattr(module, "register", None)
        if not callable(register):
            lp.error = "plugin has no register(registry) function"
            self.loaded.append(lp)
            return lp
        try:
            register(self.registry)
            lp.tools_added = sorted(set(self.registry.names()) - before)
        except Exception as exc:  # noqa: BLE001
            lp.error = str(exc)
        self.loaded.append(lp)
        return lp

    def load_module(self, dotted: str) -> LoadedPlugin:
        try:
            module = importlib.import_module(dotted)
        except Exception as exc:  # noqa: BLE001
            lp = LoadedPlugin(name=dotted, source=dotted, error=str(exc))
            self.loaded.append(lp)
            return lp
        return self._apply(dotted, dotted, module)

    def load_path(self, path: str) -> LoadedPlugin:
        p = Path(path)
        spec = importlib.util.spec_from_file_location(p.stem, str(p))
        if spec is None or spec.loader is None:
            lp = LoadedPlugin(name=p.stem, source=str(p), error="cannot load spec")
            self.loaded.append(lp)
            return lp
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            lp = LoadedPlugin(name=p.stem, source=str(p), error=str(exc))
            self.loaded.append(lp)
            return lp
        return self._apply(p.stem, str(p), module)

    def load_directory(self, directory: str, suffix: str = "_plugin.py") -> list[LoadedPlugin]:
        d = Path(directory)
        if not d.is_dir():
            return []
        return [self.load_path(str(f)) for f in sorted(d.glob(f"*{suffix}"))]

    def summary(self) -> list[dict]:
        return [
            {"name": lp.name, "source": lp.source, "tools_added": lp.tools_added, "error": lp.error}
            for lp in self.loaded
        ]
