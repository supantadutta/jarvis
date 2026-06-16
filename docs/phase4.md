# Phase 4 — Advanced

Implemented & tested in this release:

## Self-evaluation loop (`app/eval/evaluations.py`)
The Verifier's verdicts (in deep-work / verifier / debate / cascade modes) are
recorded per `(model, task_type)` as a rolling success rate. Before each request
the orchestrator feeds `EvaluationStore.to_router_performance()` into the Model
Router, so the system **learns which models do well at which tasks** and routes
accordingly. Exposed at `GET /api/evaluations`.

## Fine-tuning dataset export (`app/eval/dataset.py`)
Completed tasks export to **JSONL** in the chat-messages format
(`{"messages":[{role,content}...]}`) for local fine-tuning/eval. Secrets are
redacted; data never leaves the machine. `POST /api/dataset/export`.

## Plugin system (`app/plugins/loader.py`)
Drop a `*_plugin.py` exposing `register(registry)` into a plugins dir to add new
tools **without touching the core**. Plugins still run through the
ToolExecutor → Permission Guard, so they can't bypass approvals/allowlists.
Loading is opt-in and audited. `GET /api/plugins`.

```python
# example_plugin.py
from app.tools.base import ToolSpec, ToolResult
from app.security.permissions import PermissionLevel, RiskLevel

async def _run(ctx, args):
    return ToolResult(ok=True, output="hi", summary="example")

def register(registry):
    registry.register(ToolSpec(name="example", description="demo",
        permission=PermissionLevel.SAFE_READ, risk=RiskLevel.NONE, func=_run))
```

## MCP adapter (`app/integrations/mcp.py`)
Exports the tool registry as an MCP `tools/list` manifest (JSON Schema input +
`x-jarvis` governance annotations: permission, risk, requires_approval) so
MCP-aware clients can discover JARVIS capabilities. `GET /api/mcp/manifest`.
A consumer scaffold (`MCPClientScaffold`) is provided for calling external MCP
servers.

## Design-only (future)

- **Wake word**: openWakeWord / Porcupine listens locally; on trigger it opens
  the same push-to-talk pipeline (`docs/voice_setup.md`). Risky actions still
  require voice confirmation + the approval card. No always-on cloud streaming.
- **Home Assistant**: a `homeassistant` integration calling the HA REST/WebSocket
  API behind `CREDENTIAL_ACCESS` + domain allowlist; device control is
  HIGH_RISK (approval). Treat HA state as untrusted data.
- **Workflow marketplace**: signed, sandboxed workflow/plugin bundles with a
  manifest (required permissions surfaced for review before install) — install
  is an explicit, audited approval.
