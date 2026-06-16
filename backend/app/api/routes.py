"""All HTTP routes for the JARVIS backend.

Grouped into routers by concern and aggregated into `api_router`. Routes are
thin: they validate input, call the Brain/Orchestrator, and serialize results.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.orchestrator import Orchestrator
from app.deps import get_brain
from app.llm.registry import ModelSpec
from app.model_router.modes import Mode
from app.schemas.api import (
    ApprovalDecision,
    ChatRequest,
    ChatResponse,
    EmergencyStop,
    MemoryAddRequest,
    MemorySearchRequest,
    ModelToggle,
)
from app.services.container import Brain
from app.tools.base import tool_public_dict

api_router = APIRouter()


# --------------------------------------------------------------------------
# chat
# --------------------------------------------------------------------------
@api_router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(req: ChatRequest, brain: Brain = Depends(get_brain)) -> ChatResponse:
    mode_override: Mode | None = None
    if req.mode:
        try:
            mode_override = Mode(req.mode)
        except ValueError as exc:
            raise HTTPException(400, f"Unknown mode '{req.mode}'") from exc
    orch = Orchestrator(brain)
    result = await orch.run(req.message, mode_override=mode_override)
    return ChatResponse(**result.__dict__)


# --------------------------------------------------------------------------
# tasks
# --------------------------------------------------------------------------
@api_router.get("/tasks", tags=["tasks"])
async def list_tasks(brain: Brain = Depends(get_brain)) -> dict:
    return {"tasks": [t.public() for t in brain.tasks.all()]}


@api_router.get("/tasks/{task_id}", tags=["tasks"])
async def get_task(task_id: str, brain: Brain = Depends(get_brain)) -> dict:
    task = brain.tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task.public()


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------
def _model_dict(spec: ModelSpec) -> dict:
    return {
        "key": spec.key,
        "provider": spec.provider,
        "model_name": spec.model_name,
        "display_name": spec.display_name,
        "strengths": spec.strengths,
        "weaknesses": spec.weaknesses,
        "max_context": spec.max_context,
        "cost_type": spec.cost_type.value,
        "privacy_level": spec.privacy_level,
        "speed_level": spec.speed_level,
        "reasoning_level": spec.reasoning_level,
        "coding_level": spec.coding_level,
        "vision_support": spec.vision_support,
        "tool_calling_support": spec.tool_calling_support,
        "enabled": spec.enabled,
        "fallback_priority": spec.fallback_priority,
        "task_affinity": [t.value for t in spec.task_affinity],
    }


@api_router.get("/models", tags=["models"])
async def list_models(brain: Brain = Depends(get_brain)) -> dict:
    return {"models": [_model_dict(s) for s in brain.registry.all()]}


@api_router.post("/models/{provider}/{model_name}/toggle", tags=["models"])
async def toggle_model(
    provider: str, model_name: str, body: ModelToggle, brain: Brain = Depends(get_brain)
) -> dict:
    key = f"{provider}/{model_name}"
    if not brain.registry.set_enabled(key, body.enabled):
        raise HTTPException(404, "Model not found")
    return {"key": key, "enabled": body.enabled}


@api_router.get("/models/health", tags=["models"])
async def models_health(brain: Brain = Depends(get_brain)) -> dict:
    out = {}
    for spec in brain.registry.enabled():
        out[spec.key] = await brain.registry.health(spec.key)
    return {"health": out}


# --------------------------------------------------------------------------
# agents
# --------------------------------------------------------------------------
@api_router.get("/agents", tags=["agents"])
async def list_agents(brain: Brain = Depends(get_brain)) -> dict:
    return {
        "agents": [
            {
                "key": a.key,
                "display_name": a.display_name,
                "default_task_type": a.default_task_type.value,
                "allowed_permissions": [p.value for p in a.allowed_permissions],
                "system_prompt": a.system_prompt,
            }
            for a in brain.agents.values()
        ]
    }


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------
@api_router.get("/tools", tags=["tools"])
async def list_tools(brain: Brain = Depends(get_brain)) -> dict:
    return {"tools": [tool_public_dict(t) for t in brain.tools.all()]}


# --------------------------------------------------------------------------
# approvals
# --------------------------------------------------------------------------
@api_router.get("/approvals", tags=["approvals"])
async def list_approvals(brain: Brain = Depends(get_brain)) -> dict:
    return {"approvals": [a.public() for a in brain.approvals.all()]}


@api_router.get("/approvals/pending", tags=["approvals"])
async def pending_approvals(brain: Brain = Depends(get_brain)) -> dict:
    return {"approvals": [a.public() for a in brain.approvals.pending()]}


@api_router.post("/approvals/{approval_id}/decision", tags=["approvals"])
async def decide_approval(
    approval_id: str, body: ApprovalDecision, brain: Brain = Depends(get_brain)
) -> dict:
    approval = brain.approvals.resolve(
        approval_id, body.approved, trust=body.trust, note=body.note
    )
    if not approval:
        raise HTTPException(404, "Approval not found")
    return approval.public()


# --------------------------------------------------------------------------
# memory
# --------------------------------------------------------------------------
@api_router.post("/memory/add", tags=["memory"])
async def memory_add(body: MemoryAddRequest, brain: Brain = Depends(get_brain)) -> dict:
    item = brain.memory.add(body.text, collection=body.collection, source=body.source)
    return {"id": item.id}


@api_router.post("/memory/search", tags=["memory"])
async def memory_search(body: MemorySearchRequest, brain: Brain = Depends(get_brain)) -> dict:
    hits = brain.memory.search(body.query, collection=body.collection, limit=body.limit)
    return {
        "hits": [
            {"id": h.item.id, "score": h.score, "text": h.item.text, "source": h.item.source}
            for h in hits
        ]
    }


@api_router.get("/memory/stats", tags=["memory"])
async def memory_stats(brain: Brain = Depends(get_brain)) -> dict:
    return {"count": brain.memory.count(), "collections": brain.memory.collections()}


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------
@api_router.get("/audit", tags=["audit"])
async def audit_log(limit: int = 100, brain: Brain = Depends(get_brain)) -> dict:
    return {"entries": [e.__dict__ for e in brain.audit.recent(limit)]}


# --------------------------------------------------------------------------
# workflows
# --------------------------------------------------------------------------
@api_router.get("/workflows", tags=["workflows"])
async def list_workflows() -> dict:
    from app.workflows.definitions import SEED_WORKFLOWS, workflow_public

    return {"workflows": [workflow_public(w) for w in SEED_WORKFLOWS]}


@api_router.post("/workflows/{key}/run", tags=["workflows"])
async def run_workflow(key: str, brain: Brain = Depends(get_brain)) -> dict:
    run = await brain.workflows.run(key)
    if run.status == "failed" and run.error and "Unknown workflow" in run.error:
        raise HTTPException(404, run.error)
    return run.public()


@api_router.get("/workflows/runs", tags=["workflows"])
async def workflow_runs(brain: Brain = Depends(get_brain)) -> dict:
    return {"runs": [r.public() for r in brain.workflows.runs()]}


# --------------------------------------------------------------------------
# control (emergency stop) + health
# --------------------------------------------------------------------------
@api_router.post("/control/stop", tags=["control"])
async def emergency_stop(body: EmergencyStop, brain: Brain = Depends(get_brain)) -> dict:
    brain.set_emergency_stop(body.engaged)
    brain.audit.record(
        agent="system", tool="emergency_stop",
        output_summary=f"emergency_stop={'engaged' if body.engaged else 'released'}",
        risk="high", approval_status="n/a",
    )
    return {"emergency_stop": brain.emergency_stop}


@api_router.get("/health", tags=["health"])
async def health(brain: Brain = Depends(get_brain)) -> dict:
    return {
        "status": "ok",
        "emergency_stop": brain.emergency_stop,
        "models_enabled": len(brain.registry.enabled()),
        "tools": len(brain.tools.all()),
        "agents": len(brain.agents),
        "providers": list(brain.providers.keys()),
        "tasks": len(brain.tasks.all()),
        "pending_approvals": len(brain.approvals.pending()),
    }
