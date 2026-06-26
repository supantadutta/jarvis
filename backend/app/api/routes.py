"""All HTTP routes for the JARVIS backend.

Grouped into routers by concern and aggregated into `api_router`. Routes are
thin: they validate input, call the Brain/Orchestrator, and serialize results.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.agents.orchestrator import Orchestrator
from app.deps import get_brain
from app.llm.registry import ModelSpec
from app.model_router.modes import Mode
from app.schemas.api import (
    AddModelRequest,
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
def _parse_mode(value: str | None) -> Mode | None:
    if not value:
        return None
    try:
        return Mode(value)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown mode '{value}'") from exc


@api_router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(req: ChatRequest, brain: Brain = Depends(get_brain)) -> ChatResponse:
    orch = Orchestrator(brain)
    result = await orch.run(req.message, mode_override=_parse_mode(req.mode))
    return ChatResponse(**result.__dict__)


@api_router.post("/chat/stream", tags=["chat"])
async def chat_stream(req: ChatRequest, brain: Brain = Depends(get_brain)):
    """Server-Sent Events: emits progress events then streams the answer in
    chunks. (Underlying provider token-streaming lands with streaming-capable
    providers; this already gives the dashboard a live, incremental UX.)"""
    import json as _json

    from fastapi.responses import StreamingResponse

    mode_override = _parse_mode(req.mode)

    async def gen():
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {_json.dumps(data)}\n\n"

        async for event, data in Orchestrator(brain).stream_answer(
            req.message, mode_override=mode_override
        ):
            yield sse(event, data)

    return StreamingResponse(gen(), media_type="text/event-stream")


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


@api_router.post("/models", tags=["models"])
async def add_model(body: AddModelRequest, brain: Brain = Depends(get_brain)) -> dict:
    """Connect ANY model at runtime from the dashboard (no code edits)."""
    spec = brain.add_model_source(**body.model_dump())
    brain.audit.record(agent="system", tool="add_model",
                       output_summary=f"added model {spec.key} (kind={body.kind})",
                       risk="low", approval_status="n/a")
    return {"added": _model_dict(spec)}


@api_router.delete("/models/{provider}/{model_name}", tags=["models"])
async def delete_model(provider: str, model_name: str, brain: Brain = Depends(get_brain)) -> dict:
    key = f"{provider}/{model_name}"
    if not brain.remove_model(key):
        raise HTTPException(404, "Model not found")
    return {"removed": key}


@api_router.get("/providers", tags=["models"])
async def list_providers(brain: Brain = Depends(get_brain)) -> dict:
    bound = list(brain.providers.keys())
    return {"bound": bound, "configs": brain.provider_configs()}


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
# voice (Phase 2 push-to-talk)
# --------------------------------------------------------------------------
@api_router.post("/voice/command", tags=["voice"])
async def voice_command(req: ChatRequest, brain: Brain = Depends(get_brain)) -> dict:
    """Route an already-transcribed voice command through the orchestrator.

    Transcription happens client-side or via /voice/transcribe (faster-whisper).
    Risky actions still go through the normal approval queue — voice never
    bypasses approvals. `req.message` is the transcript."""
    from app.agents.orchestrator import Orchestrator

    result = await Orchestrator(brain).run(req.message, mode_override=_parse_mode(req.mode))
    brain.audit.record(
        agent="voice", tool="voice_command", input_summary=req.message,
        output_summary=result.answer, risk="low", approval_status="auto",
    )
    return {
        "transcript": req.message,
        "task_id": result.task_id,
        "answer": result.answer,
        "pending_approvals": result.pending_approvals,
    }


@api_router.get("/voice/status", tags=["voice"])
async def voice_status() -> dict:
    from app.voice.engine import is_voice_available

    return {"available": is_voice_available(), "engine": "faster-whisper"}


# --------------------------------------------------------------------------
# scheduler
# --------------------------------------------------------------------------
@api_router.get("/scheduler/due", tags=["workflows"])
async def scheduler_due(brain: Brain = Depends(get_brain)) -> dict:
    from datetime import datetime

    now = datetime.now()
    return {"now": now.isoformat(), "due": brain.scheduler.due(now)}


@api_router.post("/scheduler/tick", tags=["workflows"])
async def scheduler_tick(brain: Brain = Depends(get_brain)) -> dict:
    """Manually run any due workflows now (for testing / on-demand)."""
    from datetime import datetime

    ran = await brain.scheduler.run_due(datetime.now())
    return {"ran": ran}


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
# Cognitive Processing Engine v2 — /api/brain/*
# --------------------------------------------------------------------------
@api_router.post("/brain/run", tags=["brain"])
async def brain_run(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    """THE unified entry point: one engine analyzes the request and auto-selects
    the execution strategy (chat / autonomous / graph), or honors an explicit
    `execution`. Shares one analyzer, budget, quality + learning path."""
    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(400, "command is required")
    result = await brain.engine.run(
        command, execution=payload.get("execution", "auto"),
        mode=payload.get("mode"), max_steps=payload.get("max_steps", 8))
    return result.public()


@api_router.post("/brain/analyze", tags=["brain"])
async def brain_analyze(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(400, "command is required")
    return brain.analyzer.analyze(command, mode_override=payload.get("mode")).model_dump()


@api_router.post("/brain/plan", tags=["brain"])
async def brain_plan(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(400, "command is required")
    analysis = brain.analyzer.analyze(command, mode_override=payload.get("mode"))
    from app.brain.router_v2 import choose_strategy

    strategy = payload.get("strategy") or choose_strategy(analysis).value
    plan = brain.planner_v2.plan(analysis, strategy=strategy)
    return {"analysis": analysis.model_dump(), "strategy": strategy, "plan": plan.model_dump()}


@api_router.post("/brain/execute", tags=["brain"])
async def brain_execute(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    import uuid

    from app.brain.graph import GraphExecutor

    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(400, "command is required")
    analysis = brain.analyzer.analyze(command, mode_override=payload.get("mode"))
    plan = brain.planner_v2.plan(analysis, strategy=payload.get("strategy", ""))
    task_id = uuid.uuid4().hex[:12]
    private = not analysis.cloud_allowed

    if payload.get("background"):
        async def _job(job):
            res = await GraphExecutor(brain, private_mode=private).run(plan)
            brain.graph_runs[task_id] = res.public()
            return brain.graph_runs[task_id]

        brain.processing_queue.register("brain_graph", _job)
        job = brain.processing_queue.enqueue("brain_graph", {"task_id": task_id})
        return {"task_id": task_id, "job_id": job.id, "background": True,
                "plan_nodes": len(plan.nodes)}

    result = await GraphExecutor(brain, private_mode=private).run(plan)
    brain.graph_runs[task_id] = result.public()
    return {"task_id": task_id, **result.public()}


@api_router.get("/brain/status", tags=["brain"])
async def brain_status(brain: Brain = Depends(get_brain)) -> dict:
    return {
        "resources": brain.resource_monitor.snapshot(),
        "response_cache": brain.response_cache.stats(),
        "memory_layers": brain.layered_memory.stats(),
        "queue": {"jobs": len(brain.processing_queue.all())},
        "models_enabled": len(brain.registry.enabled()),
        "emergency_stop": brain.emergency_stop,
    }


@api_router.post("/brain/memory/search", tags=["brain"])
async def brain_memory_search(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    hits = brain.layered_memory.recall(
        payload.get("query", ""), layers=payload.get("layers"),
        for_cloud=payload.get("for_cloud", False), limit=payload.get("limit", 5))
    return {"hits": [
        {"text": h.text, "layer": h.layer, "score": h.score, "source": h.source,
         "privacy": h.privacy} for h in hits]}


@api_router.post("/brain/evaluate", tags=["brain"])
async def brain_evaluate(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    from app.brain.learning import TaskFeedback

    fb = TaskFeedback(**payload)
    return brain.feedback.record(fb)


@api_router.get("/brain/models/health", tags=["brain"])
async def brain_models_health(brain: Brain = Depends(get_brain)) -> dict:
    out = {}
    for spec in brain.registry.enabled():
        out[spec.key] = await brain.registry.health(spec.key)
    return {"health": out, "leaderboard": brain.feedback.leaderboard()}


@api_router.get("/brain/queue", tags=["brain"])
async def brain_queue(brain: Brain = Depends(get_brain)) -> dict:
    return {"jobs": [j.public() for j in brain.processing_queue.all()]}


@api_router.get("/brain/graph/{task_id}", tags=["brain"])
async def brain_graph(task_id: str, brain: Brain = Depends(get_brain)) -> dict:
    res = brain.graph_runs.get(task_id)
    if res is None:
        raise HTTPException(404, "graph run not found")
    return res


@api_router.post("/brain/benchmarks/run", tags=["brain"])
async def brain_benchmarks() -> dict:
    from app.brain.benchmarks import run_all

    return run_all()


# --------------------------------------------------------------------------
# autonomous agent loop (goal -> reason -> act -> observe -> repeat)
# --------------------------------------------------------------------------
@api_router.post("/agent/run", tags=["agent"])
async def agent_run(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    """Give JARVIS a goal; it reasons with a connected model and takes guard-gated
    actions (web, files, memory, reports, …) until done. Risky steps create
    approvals you resolve in the queue."""
    goal = (payload.get("goal") or "").strip()
    if not goal:
        raise HTTPException(400, "goal is required")
    result = await brain.autonomous.run(
        goal, max_steps=payload.get("max_steps", 8),
        allowed_tools=payload.get("allowed_tools"),
    )
    return result.public()


# --------------------------------------------------------------------------
# self-learning (web research -> memory)
# --------------------------------------------------------------------------
@api_router.post("/learn", tags=["learn"])
async def learn(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    """Autonomously research a topic from the web and store it in memory.

    Requires host network access (blocked in PRIVATE_MODE). Fetched content is
    treated as untrusted."""
    if not brain.settings.allow_network:
        raise HTTPException(403, "Network access is disabled (allow_network=false).")
    topic = (payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "topic is required")
    result = await brain.learner.learn(topic, max_sources=payload.get("max_sources", 3))
    return result


# --------------------------------------------------------------------------
# SOC / cybersecurity (defensive, lab-authorized)
# --------------------------------------------------------------------------
@api_router.get("/soc/event/{event_id}", tags=["soc"])
async def soc_event(event_id: int) -> dict:
    from app.soc.defensive import explain_event_id

    return explain_event_id(event_id)


@api_router.post("/soc/attack-map", tags=["soc"])
async def soc_attack_map(payload: dict) -> dict:
    from app.soc.defensive import map_to_attack

    return {"techniques": map_to_attack(payload.get("behavior", ""))}


@api_router.post("/soc/splunk", tags=["soc"])
async def soc_splunk(payload: dict) -> dict:
    from app.soc.defensive import DetectionSpec, build_logscale_query, build_splunk_spl

    spec = DetectionSpec(
        index=payload.get("index", "*"),
        event_id=payload.get("event_id"),
        field_filters=payload.get("field_filters", {}),
        threshold=payload.get("threshold"),
        by_fields=payload.get("by_fields", []),
    )
    return {"spl": build_splunk_spl(spec), "logscale": build_logscale_query(spec)}


# --------------------------------------------------------------------------
# documents (Markdown/DOCX/PDF/XLSX generation)
# --------------------------------------------------------------------------
@api_router.post("/documents/generate", tags=["documents"])
async def documents_generate(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    from datetime import datetime, timezone

    from app.documents.generators import DocumentModel, Section, generate

    fmt = payload.get("format", "md")
    title = payload.get("title", "document")
    doc = DocumentModel(
        title=title,
        sections=[Section(**s) for s in payload.get("sections", [])]
        or [Section(heading="Content", body=payload.get("content", ""))],
        table_headers=payload.get("table_headers", []),
        table_rows=payload.get("table_rows", []),
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = f"{brain.settings.notes_dir}/{title.replace('/', '_')}-{ts}.{fmt}"
    try:
        out = generate(doc, fmt, path)
        return {"ok": True, "path": out}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


# --------------------------------------------------------------------------
# integrations (GitHub README, email/ICS drafts — drafts only, no send)
# --------------------------------------------------------------------------
@api_router.post("/integrations/readme", tags=["integrations"])
async def integrations_readme(payload: dict) -> dict:
    from app.integrations.github import ProjectInfo, build_readme

    info = ProjectInfo(
        name=payload.get("name", "project"),
        description=payload.get("description", ""),
        features=payload.get("features", []),
        tech_stack=payload.get("tech_stack", []),
        install_cmds=payload.get("install_cmds", []),
        usage=payload.get("usage", ""),
        license=payload.get("license", "MIT"),
    )
    return {"readme": build_readme(info)}


@api_router.post("/integrations/email/draft", tags=["integrations"])
async def integrations_email_draft(payload: dict) -> dict:
    from app.integrations.email_calendar import compose_email_draft

    draft = compose_email_draft(
        to=payload.get("to", []), subject=payload.get("subject", ""),
        body=payload.get("body", ""), cc=payload.get("cc"),
        signature=payload.get("signature"),
    )
    # Drafts only — sending is a HIGH_RISK action handled via the approval queue.
    return {"draft": draft.public(), "note": "Draft only; sending requires approval."}


# --------------------------------------------------------------------------
# Phase 4: evaluations, dataset export, plugins, MCP manifest
# --------------------------------------------------------------------------
@api_router.get("/evaluations", tags=["eval"])
async def evaluations(brain: Brain = Depends(get_brain)) -> dict:
    return {"evaluations": brain.evaluations.summary()}


@api_router.post("/dataset/export", tags=["eval"])
async def dataset_export(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    from datetime import datetime, timezone

    from app.eval.dataset import export_tasks_jsonl

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = f"{brain.settings.notes_dir}/dataset-{ts}.jsonl"
    n = export_tasks_jsonl(brain.tasks.all(limit=10000), path, system=payload.get("system"))
    return {"path": path, "rows": n}


@api_router.get("/plugins", tags=["plugins"])
async def list_plugins(brain: Brain = Depends(get_brain)) -> dict:
    return {"plugins": brain.plugins.summary()}


@api_router.get("/mcp/manifest", tags=["mcp"])
async def mcp_manifest(brain: Brain = Depends(get_brain)) -> dict:
    from app.integrations.mcp import export_tool_manifest

    return export_tool_manifest(brain.tools)


# --------------------------------------------------------------------------
# settings (non-secret config summary) + credentials (masked metadata)
# --------------------------------------------------------------------------
@api_router.get("/settings", tags=["settings"])
async def get_settings_summary(brain: Brain = Depends(get_brain)) -> dict:
    s = brain.settings
    # Never return secret values — only whether a provider is configured.
    return {
        "app_name": s.app_name,
        "environment": s.environment,
        "default_mode": s.default_mode,
        "vector_backend": s.vector_backend,
        "allow_low_risk_write": s.allow_low_risk_write,
        "trusted_terminal_read": s.trusted_terminal_read,
        "allow_network": s.allow_network,
        "max_cascade_attempts": s.max_cascade_attempts,
        "scheduler_enabled": s.scheduler_enabled,
        "telegram_enabled": s.telegram_enabled,
        "voice_enabled": s.voice_enabled,
        "browser_headless": s.browser_headless,
        "allowed_domains": s.allowed_domains,
        "allowed_paths_count": len(s.allowed_paths),
        "providers_configured": {
            "ollama": True,
            "openai": bool(s.openai_api_key),
            "anthropic": bool(s.anthropic_api_key),
            "google": bool(s.google_api_key),
            "groq": bool(s.groq_api_key),
            "openrouter": bool(s.openrouter_api_key),
            "github": bool(s.github_token),
            "whatsapp": bool(s.whatsapp_access_token),
            "n8n": bool(s.n8n_base_url),
        },
    }


@api_router.patch("/settings", tags=["settings"])
async def update_settings(updates: dict, brain: Brain = Depends(get_brain)) -> dict:
    """Apply safe, non-secret policy toggles at runtime (rebuilds the guard).

    Allowed keys: allow_low_risk_write, trusted_terminal_read, allow_network,
    max_cascade_attempts, default_mode. Anything else is ignored."""
    applied = brain.apply_policy_update(updates)
    if not applied:
        raise HTTPException(400, "No mutable policy keys in request.")
    brain.audit.record(agent="system", tool="update_settings",
                       output_summary=f"policy updated: {list(applied)}",
                       risk="medium", approval_status="n/a")
    return {"applied": applied}


@api_router.post("/credentials", tags=["credentials"])
async def add_credential(payload: dict, brain: Brain = Depends(get_brain)) -> dict:
    """Add a credential the assistant may use to automate a portal (after
    approval). The secret is stored in the encrypted vault (when configured) and
    only masked metadata is ever returned."""
    from app.security.credentials import CredentialMeta

    name = (payload.get("name") or "").strip()
    platform = (payload.get("platform") or "").strip()
    if not name or not platform:
        raise HTTPException(400, "name and platform are required")
    secret = payload.get("secret")
    ref = f"cred:{name}"
    if secret:
        try:
            brain.vault.set(ref, secret)
        except Exception:  # noqa: BLE001 - NullVault when no VAULT_KEY
            pass
    brain.credentials.register(CredentialMeta(
        name=name, platform=platform, kind=payload.get("kind", "password"),
        username=payload.get("username"), vault_ref=ref,
        scopes=payload.get("scopes", []), requires_approval=True))
    brain.audit.record(agent="credential", tool="add_credential",
                       output_summary=f"registered credential '{name}' for {platform}",
                       risk="medium", approval_status="n/a")
    return {"added": name, "platform": platform, "secret_stored": bool(secret)}


@api_router.get("/credentials", tags=["credentials"])
async def list_credentials(brain: Brain = Depends(get_brain)) -> dict:
    # Metadata only; usernames masked; secret values never present.
    return {"credentials": brain.credentials.list_public()}


@api_router.post("/credentials/{name}/revoke", tags=["credentials"])
async def revoke_credential(name: str, brain: Brain = Depends(get_brain)) -> dict:
    ok = brain.credentials.revoke(name)
    if not ok:
        raise HTTPException(404, "Credential not found")
    brain.audit.record(agent="credential", tool="revoke",
                       output_summary=f"revoked credential {name}", risk="medium")
    return {"name": name, "revoked": True}


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


@api_router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Live agent-activity timeline: sends a snapshot of recent events, then
    streams new audit/agent events as they happen."""
    import asyncio

    brain = get_brain()
    await websocket.accept()
    await websocket.send_json({"type": "snapshot", "events": brain.events.snapshot()})
    queue = brain.events.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        brain.events.unsubscribe(queue)


@api_router.get("/metrics", tags=["observability"])
async def metrics(brain: Brain = Depends(get_brain)):
    from fastapi.responses import PlainTextResponse

    from app.observability.metrics import METRICS

    cache = brain.response_cache.stats()
    gauges = {
        "jarvis_models_enabled": len(brain.registry.enabled()),
        "jarvis_tools_total": len(brain.tools.all()),
        "jarvis_pending_approvals": len(brain.approvals.pending()),
        "jarvis_tasks_total": len(brain.tasks.all()),
        "jarvis_queue_jobs": len(brain.processing_queue.all()),
        "jarvis_response_cache_hit_rate": cache["hit_rate"],
        "jarvis_response_cache_size": cache["size"],
        "jarvis_emergency_stop": int(brain.emergency_stop),
        "jarvis_audit_entries": len(brain.audit.recent(10000)),
    }
    return PlainTextResponse(METRICS.render(gauges), media_type="text/plain; version=0.0.4")


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
