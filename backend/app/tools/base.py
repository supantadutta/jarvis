"""Typed tool registry.

Every tool declares its schema, permission level, risk, approval requirement,
timeout, and allow-scopes. Tools are executed *only* through the ToolExecutor,
which consults the Permission Guard first — an agent can never run a tool
directly or bypass the guard.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.security.permissions import PermissionLevel, RiskLevel

ToolFunc = Callable[["ToolContext", dict[str, Any]], Awaitable["ToolResult"]]


@dataclass
class ToolContext:
    """Runtime context handed to a tool implementation."""

    settings: Any
    workspace_root: str
    services: dict[str, Any] = field(default_factory=dict)
    agent_key: str | None = None
    model_key: str | None = None
    user_command: str | None = None
    private_mode: bool = False


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    summary: str = ""
    error: str | None = None
    screenshot_ref: str | None = None
    artifacts: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class ToolSpec:
    name: str
    description: str
    permission: PermissionLevel
    risk: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False  # explicit override; guard still has final say
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 30.0
    allowed_paths: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    is_irreversible: bool = False
    uses_credential: bool = False
    supports_dry_run: bool = False
    rollback: str | None = None  # human description of how to roll back
    audit_fields: list[str] = field(default_factory=list)
    func: ToolFunc | None = None

    # Extractors so the guard can pull path/domain/command from arbitrary args.
    path_arg: str | None = None
    domain_arg: str | None = None
    command_arg: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' already registered")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def by_permission(self, level: PermissionLevel) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.permission == level]


def tool_public_dict(spec: ToolSpec) -> dict[str, Any]:
    """Serializable view of a tool (no callable) for the API/dashboard."""
    return {
        "name": spec.name,
        "description": spec.description,
        "permission": spec.permission.value,
        "risk": spec.risk.value,
        "requires_approval": spec.requires_approval,
        "input_schema": spec.input_schema,
        "output_schema": spec.output_schema,
        "timeout_s": spec.timeout_s,
        "is_irreversible": spec.is_irreversible,
        "uses_credential": spec.uses_credential,
        "supports_dry_run": spec.supports_dry_run,
        "rollback": spec.rollback,
    }
