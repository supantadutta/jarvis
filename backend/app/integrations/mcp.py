"""MCP (Model Context Protocol) adapter (Phase 4).

Exports the JARVIS tool registry as an MCP-style `tools/list` manifest so other
MCP-aware clients can discover JARVIS's capabilities, and provides a consumer
scaffold for calling external MCP servers. Exposed tools still execute through
the ToolExecutor → Permission Guard, so MCP access never bypasses approvals.
"""
from __future__ import annotations

from app.tools.base import ToolRegistry, ToolSpec


def _json_schema(spec: ToolSpec) -> dict:
    """Best-effort JSON Schema from the tool's simple input_schema annotations."""
    props: dict = {}
    required: list[str] = []
    for key, ann in (spec.input_schema or {}).items():
        optional = isinstance(ann, str) and ann.endswith("?")
        base = ann[:-1] if optional else ann
        jtype = {
            "str": "string", "int": "integer", "float": "number",
            "bool": "boolean", "list": "array", "dict": "object",
        }.get(base, "string")
        props[key] = {"type": jtype}
        if not optional:
            required.append(key)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def tool_to_mcp(spec: ToolSpec) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "inputSchema": _json_schema(spec),
        # JARVIS-specific governance annotations (non-standard, informational).
        "x-jarvis": {
            "permission": spec.permission.value,
            "risk": spec.risk.value,
            "requires_approval": spec.requires_approval
            or spec.uses_credential
            or spec.is_irreversible,
        },
    }


def export_tool_manifest(registry: ToolRegistry) -> dict:
    """Return an MCP `tools/list`-shaped manifest of the registry."""
    return {"tools": [tool_to_mcp(t) for t in registry.all()]}


class MCPClientScaffold:
    """Placeholder for consuming an external MCP server (Phase 4+)."""

    def __init__(self, server_url: str | None) -> None:
        self.server_url = server_url

    def configured(self) -> bool:
        return bool(self.server_url)

    async def list_tools(self) -> dict:  # pragma: no cover - external
        raise RuntimeError("External MCP client is a scaffold; implement transport in Phase 4+.")
