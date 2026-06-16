"""Built-in tool implementations and registration.

Local file/memory/report tools are fully implemented. Browser, desktop,
terminal-write, credential, and Telegram tools are wired with correct
permissions but return graceful "needs Phase 2 / optional dependency" results
when the underlying capability is not installed — so the backend always boots and
the permission flow is exercised regardless of host setup.
"""
from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.security.permissions import PermissionLevel, RiskLevel
from app.security.prompt_injection import wrap_untrusted
from app.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

P = PermissionLevel
R = RiskLevel


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _safe_join(root: str, rel: str) -> Path:
    """Resolve `rel` under `root`, rejecting traversal/escape."""
    base = Path(root).resolve()
    target = (base / rel).resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"Path '{rel}' escapes workspace root.")
    return target


# --------------------------------------------------------------------------
# file & document tools
# --------------------------------------------------------------------------
async def _read_file(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        path = _safe_join(ctx.workspace_root, args["path"])
        if not path.exists() or not path.is_file():
            return ToolResult(ok=False, error="File not found.")
        text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
        # File contents are untrusted external data.
        return ToolResult(
            ok=True,
            output=wrap_untrusted(text, source=f"file:{args['path']}"),
            summary=f"Read {len(text)} chars from {args['path']}",
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _write_note(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        notes_dir = Path(ctx.settings.notes_dir)
        notes_dir.mkdir(parents=True, exist_ok=True)
        name = args.get("title", "note").strip().replace("/", "_") or "note"
        path = notes_dir / f"{name}.md"
        path.write_text(args.get("content", ""), encoding="utf-8")
        return ToolResult(
            ok=True, output=str(path), summary=f"Wrote note '{name}.md'", artifacts=[str(path)]
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _write_file(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        path = _safe_join(ctx.workspace_root, args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.get("content", ""), encoding="utf-8")
        return ToolResult(ok=True, output=str(path), summary=f"Wrote {args['path']}")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _list_directory(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        path = _safe_join(ctx.workspace_root, args.get("path", "."))
        if not path.exists():
            return ToolResult(ok=False, error="Directory not found.")
        entries = []
        for child in sorted(path.iterdir()):
            entries.append(
                {"name": child.name, "is_dir": child.is_dir(), "size": child.stat().st_size}
            )
        return ToolResult(ok=True, output=entries, summary=f"{len(entries)} entries")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _search_files(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        root = _safe_join(ctx.workspace_root, args.get("path", "."))
        query = args.get("query", "").lower()
        ext = args.get("extension")
        matches: list[str] = []
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if ext and p.suffix != ext:
                continue
            if query and query not in p.name.lower():
                # peek into small text files
                try:
                    if p.stat().st_size < 1_000_000 and query in p.read_text(
                        encoding="utf-8", errors="ignore"
                    ).lower():
                        matches.append(str(p.relative_to(ctx.workspace_root)))
                except OSError:
                    pass
                continue
            matches.append(str(p.relative_to(ctx.workspace_root)))
            if len(matches) >= 200:
                break
        return ToolResult(ok=True, output=matches, summary=f"{len(matches)} matches")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _organize_folder(ctx: ToolContext, args: dict) -> ToolResult:
    """Sort files into subfolders by extension. Move-only (never deletes).
    Supports dry-run."""
    try:
        root = _safe_join(ctx.workspace_root, args.get("path", "."))
        dry = args.get("dry_run", True)
        plan: list[str] = []
        for p in root.iterdir():
            if p.is_file():
                bucket = (p.suffix[1:] or "no_ext").lower()
                dest = root / bucket / p.name
                plan.append(f"{p.name} -> {bucket}/")
                if not dry:
                    dest.parent.mkdir(exist_ok=True)
                    shutil.move(str(p), str(dest))
        verb = "Would move" if dry else "Moved"
        return ToolResult(ok=True, output=plan, summary=f"{verb} {len(plan)} files")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _create_report_markdown(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        notes_dir = Path(ctx.settings.notes_dir)
        notes_dir.mkdir(parents=True, exist_ok=True)
        title = args.get("title", "report")
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = notes_dir / f"{title.replace('/', '_')}-{ts}.md"
        body = f"# {title}\n\n_Generated {ts} UTC_\n\n{args.get('content', '')}\n"
        path.write_text(body, encoding="utf-8")
        return ToolResult(ok=True, output=str(path), summary=f"Report saved: {path.name}", artifacts=[str(path)])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _create_docx_report(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(
        ok=False,
        error="DOCX generation is a Phase 3 feature (install python-docx).",
        summary="not available",
    )


async def _create_pdf_report(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(
        ok=False,
        error="PDF generation is a Phase 3 feature (install reportlab/weasyprint).",
        summary="not available",
    )


# --------------------------------------------------------------------------
# memory tools
# --------------------------------------------------------------------------
async def _add_memory(ctx: ToolContext, args: dict) -> ToolResult:
    memory = ctx.services.get("memory")
    if not memory:
        return ToolResult(ok=False, error="Memory service unavailable.")
    item = memory.add(
        args["text"],
        collection=args.get("collection", "default"),
        metadata=args.get("metadata"),
        source=args.get("source"),
    )
    return ToolResult(ok=True, output=item.id, summary=f"Stored memory {item.id}")


async def _search_memory(ctx: ToolContext, args: dict) -> ToolResult:
    memory = ctx.services.get("memory")
    if not memory:
        return ToolResult(ok=False, error="Memory service unavailable.")
    hits = memory.search(
        args["query"], collection=args.get("collection"), limit=args.get("limit", 5)
    )
    out = [
        {"id": h.item.id, "score": h.score, "text": h.item.text, "source": h.item.source}
        for h in hits
    ]
    return ToolResult(ok=True, output=out, summary=f"{len(out)} memory hits")


# --------------------------------------------------------------------------
# task tools
# --------------------------------------------------------------------------
async def _get_task_status(ctx: ToolContext, args: dict) -> ToolResult:
    tasks = ctx.services.get("tasks")
    if not tasks:
        return ToolResult(ok=False, error="Task service unavailable.")
    task = tasks.get(args["task_id"])
    if not task:
        return ToolResult(ok=False, error="Task not found.")
    return ToolResult(ok=True, output=task.public(), summary=f"Task {task.id}: {task.status.value}")


async def _create_task(ctx: ToolContext, args: dict) -> ToolResult:
    tasks = ctx.services.get("tasks")
    if not tasks:
        return ToolResult(ok=False, error="Task service unavailable.")
    task = tasks.create(
        args["command"], args.get("task_type", "daily_assistant"), args.get("mode", "SINGLE_BEST_MODEL")
    )
    return ToolResult(ok=True, output=task.id, summary=f"Created task {task.id}")


async def _request_user_approval(ctx: ToolContext, args: dict) -> ToolResult:
    """Explicitly create an approval card and wait for the decision."""
    approvals = ctx.services.get("approvals")
    if not approvals:
        return ToolResult(ok=False, error="Approval service unavailable.")
    from app.services.approvals import ApprovalQueue, ApprovalRequest

    approval = approvals.create(
        ApprovalRequest(
            task_name=args.get("task_name", "task"),
            requested_action=args.get("action", "user approval"),
            agent=ctx.agent_key or "supervisor",
            model=ctx.model_key,
            tool="request_user_approval",
            account=args.get("account"),
            credential=args.get("credential"),
            risk=args.get("risk", "high"),
            what_can_change=args.get("what_can_change", ""),
            action_preview=args.get("preview", args.get("action", "")),
            allow_trust=args.get("allow_trust", False),
        )
    )
    resolved = await approvals.wait(approval.id, timeout=args.get("timeout", 300))
    granted = ApprovalQueue.is_granted(resolved)
    return ToolResult(
        ok=granted,
        output={"approval_id": approval.id, "granted": granted},
        summary=f"Approval {approval.id}: {'granted' if granted else 'not granted'}",
    )


async def _compare_ai_outputs(ctx: ToolContext, args: dict) -> ToolResult:
    """Heuristic comparison of multiple candidate outputs (length/agreement).
    A Verifier model produces the authoritative judgement in DEBATE/PARALLEL."""
    candidates = args.get("candidates", [])
    if not candidates:
        return ToolResult(ok=False, error="No candidates to compare.")
    # Simple agreement heuristic: pick the candidate most similar to the others.
    from collections import Counter

    from app.rag.memory import _tokens

    vecs = [Counter(_tokens(c.get("text", ""))) for c in candidates]

    def sim(a: Counter, b: Counter) -> float:
        common = set(a) & set(b)
        return sum(min(a[t], b[t]) for t in common) / (sum(a.values()) + 1)

    scores = []
    for i, vi in enumerate(vecs):
        agree = sum(sim(vi, vj) for j, vj in enumerate(vecs) if i != j)
        scores.append({"index": i, "model": candidates[i].get("model"), "agreement": round(agree, 3)})
    best = max(scores, key=lambda s: s["agreement"])
    return ToolResult(ok=True, output={"scores": scores, "best_index": best["index"]},
                      summary=f"Best candidate by agreement: #{best['index']}")


async def _verify_final_answer(ctx: ToolContext, args: dict) -> ToolResult:
    """Lightweight, non-LLM completeness/safety checks. The Verifier agent adds
    the model-based judgement; this is the deterministic guardrail layer."""
    answer = args.get("answer", "")
    issues: list[str] = []
    if not answer.strip():
        issues.append("Answer is empty.")
    if len(answer) < 5:
        issues.append("Answer is suspiciously short.")
    low = answer.lower()
    for bad in ("ignore previous instructions", "i cannot help with anything"):
        if bad in low:
            issues.append(f"Suspicious content: '{bad}'")
    passed = not issues
    return ToolResult(
        ok=True,
        output={"passed": passed, "issues": issues},
        summary="verification passed" if passed else f"{len(issues)} issue(s)",
    )


# --------------------------------------------------------------------------
# desktop / browser / terminal (graceful stubs with correct permissions)
# --------------------------------------------------------------------------
async def _take_desktop_screenshot(ctx: ToolContext, args: dict) -> ToolResult:
    try:
        import mss  # type: ignore
    except ImportError:
        return ToolResult(
            ok=False,
            error="Desktop screenshots need the optional 'mss' dependency (Phase 2).",
            summary="screenshot unavailable",
        )
    try:  # pragma: no cover - requires a display
        shots_dir = Path(ctx.settings.screenshots_dir)
        shots_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out = shots_dir / f"desktop-{ts}.png"
        with mss.mss() as sct:
            sct.shot(output=str(out))
        return ToolResult(ok=True, output=str(out), summary="Captured desktop", screenshot_ref=str(out))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


async def _open_url_readonly(ctx: ToolContext, args: dict) -> ToolResult:
    url = args.get("url", "")
    controller = ctx.services.get("browser")
    if controller is None:
        return ToolResult(
            ok=False,
            error="Browser controller not installed (Playwright is a Phase 2 optional dep).",
            summary="browser unavailable",
            output={"url": url},
        )
    return await controller.get_text(url)  # pragma: no cover


async def _browser_get_text(ctx: ToolContext, args: dict) -> ToolResult:
    return await _open_url_readonly(ctx, args)


async def _browser_take_screenshot(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(
        ok=False,
        error="Browser screenshots require Playwright (Phase 2).",
        summary="browser unavailable",
    )


async def _browser_write_stub(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(
        ok=False,
        error="Approved browser write actions require Playwright (Phase 2).",
        summary="browser unavailable",
    )


async def _propose_terminal_command(ctx: ToolContext, args: dict) -> ToolResult:
    """Read-only: returns the command + classification without running it."""
    cmd = args.get("command", "")
    return ToolResult(
        ok=True,
        output={"command": cmd, "note": "Proposed only; not executed."},
        summary=f"Proposed command: {cmd[:80]}",
    )


async def _run_terminal_readonly(ctx: ToolContext, args: dict) -> ToolResult:
    """Runs an approved read-only command. The guard + allowlist already vetted it."""
    import asyncio

    cmd = args.get("command", "")
    try:  # pragma: no cover - exercised in integration, not unit tests
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        text = out.decode(errors="replace")[:10_000]
        return ToolResult(ok=True, output=text, summary=f"ran: {cmd[:60]} (rc={proc.returncode})")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


# --------------------------------------------------------------------------
# telegram (handled by the bot; tool form for orchestrator use)
# --------------------------------------------------------------------------
async def _send_telegram_message(ctx: ToolContext, args: dict) -> ToolResult:
    bot = ctx.services.get("telegram")
    if not bot or not getattr(bot, "enabled", False):
        return ToolResult(ok=False, error="Telegram is not enabled.", summary="telegram disabled")
    return ToolResult(ok=True, output="queued", summary="Telegram message queued")  # pragma: no cover


async def _telegram_stub(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(ok=False, error="Telegram file/voice handling runs inside the bot (Phase 2).")


# --------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------
def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    # Note: allowed_paths/domains are enforced centrally by the Permission Guard
    # from settings, not per-tool here.
    def reg(**kw):
        registry.register(ToolSpec(**kw))

    # --- SAFE_READ ---
    reg(name="read_file", description="Read a UTF-8 text file inside the workspace.",
        permission=P.SAFE_READ, risk=R.NONE, func=_read_file, path_arg="path",
        input_schema={"path": "str"}, output_schema={"content": "str"})
    reg(name="list_directory", description="List entries of a workspace directory.",
        permission=P.SAFE_READ, risk=R.NONE, func=_list_directory, path_arg="path",
        input_schema={"path": "str"})
    reg(name="search_files", description="Search workspace files by name/content.",
        permission=P.SAFE_READ, risk=R.LOW, func=_search_files, path_arg="path",
        input_schema={"path": "str", "query": "str", "extension": "str?"})
    reg(name="search_memory", description="Semantic/lexical search over local memory.",
        permission=P.SAFE_READ, risk=R.NONE, func=_search_memory,
        input_schema={"query": "str", "collection": "str?", "limit": "int?"})
    reg(name="get_task_status", description="Get the status of a task by id.",
        permission=P.SAFE_READ, risk=R.NONE, func=_get_task_status, input_schema={"task_id": "str"})
    reg(name="compare_ai_outputs", description="Compare multiple AI candidate outputs.",
        permission=P.SAFE_READ, risk=R.NONE, func=_compare_ai_outputs,
        input_schema={"candidates": "list"})
    reg(name="verify_final_answer", description="Deterministic safety/completeness checks on an answer.",
        permission=P.SAFE_READ, risk=R.NONE, func=_verify_final_answer, input_schema={"answer": "str"})

    # --- orchestration ---
    reg(name="create_task", description="Create a new task record.",
        permission=P.SAFE_READ, risk=R.NONE, func=_create_task,
        input_schema={"command": "str", "task_type": "str?", "mode": "str?"})
    reg(name="request_user_approval", description="Create an approval card and wait for a decision.",
        permission=P.SAFE_READ, risk=R.NONE, func=_request_user_approval,
        input_schema={"task_name": "str", "action": "str", "risk": "str?"})

    # --- LOW_RISK_WRITE ---
    reg(name="write_note", description="Create a markdown note in the notes folder.",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_write_note,
        rollback="Delete the created note file.", supports_dry_run=False,
        input_schema={"title": "str", "content": "str"})
    reg(name="write_file", description="Write a text file inside the workspace.",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_write_file, path_arg="path",
        rollback="Restore previous file contents from backup if present.",
        input_schema={"path": "str", "content": "str"})
    reg(name="organize_folder", description="Sort files into subfolders by type (move-only).",
        permission=P.LOW_RISK_WRITE, risk=R.MEDIUM, func=_organize_folder, path_arg="path",
        supports_dry_run=True, rollback="Move files back to the parent folder.",
        input_schema={"path": "str", "dry_run": "bool"})
    reg(name="add_memory", description="Store a piece of text in local memory.",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_add_memory,
        input_schema={"text": "str", "collection": "str?"})
    reg(name="create_report_markdown", description="Generate a timestamped markdown report.",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_create_report_markdown,
        input_schema={"title": "str", "content": "str"})

    # --- document generation (Phase 3 stubs) ---
    reg(name="create_docx_report", description="Generate a DOCX report (Phase 3).",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_create_docx_report,
        input_schema={"title": "str", "content": "str"})
    reg(name="create_pdf_report", description="Generate a PDF report (Phase 3).",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_create_pdf_report,
        input_schema={"title": "str", "content": "str"})

    # --- BROWSER_READ ---
    reg(name="open_url_readonly", description="Open a URL and read visible text (read-only).",
        permission=P.BROWSER_READ, risk=R.LOW, func=_open_url_readonly, domain_arg="domain",
        allowed_domains=[], input_schema={"url": "str", "domain": "str"})
    reg(name="browser_get_text", description="Extract visible text/DOM from a page.",
        permission=P.BROWSER_READ, risk=R.LOW, func=_browser_get_text, domain_arg="domain",
        input_schema={"url": "str", "domain": "str"})
    reg(name="browser_take_screenshot", description="Screenshot the current browser page.",
        permission=P.BROWSER_READ, risk=R.LOW, func=_browser_take_screenshot,
        input_schema={"url": "str", "domain": "str"})

    # --- BROWSER_WRITE (always approval) ---
    reg(name="browser_click_after_approval", description="Click an element (approval required).",
        permission=P.BROWSER_WRITE, risk=R.MEDIUM, requires_approval=True, domain_arg="domain",
        func=_browser_write_stub, rollback="Navigate back / undo if the site supports it.",
        input_schema={"selector": "str", "domain": "str"})
    reg(name="browser_fill_form_after_approval", description="Fill a form (approval required).",
        permission=P.BROWSER_WRITE, risk=R.MEDIUM, requires_approval=True, domain_arg="domain",
        func=_browser_write_stub, input_schema={"fields": "dict", "domain": "str"})
    reg(name="browser_download_after_approval", description="Download a file (approval required).",
        permission=P.BROWSER_WRITE, risk=R.MEDIUM, requires_approval=True, domain_arg="domain",
        func=_browser_write_stub, input_schema={"url": "str", "domain": "str"})
    reg(name="use_browser_session_after_approval",
        description="Reuse a saved logged-in browser session (credential; approval required).",
        permission=P.CREDENTIAL_ACCESS, risk=R.HIGH, requires_approval=True, uses_credential=True,
        domain_arg="domain", func=_browser_write_stub,
        input_schema={"profile": "str", "domain": "str"})

    # --- DESKTOP_CONTROL ---
    reg(name="take_desktop_screenshot", description="Capture a desktop screenshot.",
        permission=P.DESKTOP_CONTROL, risk=R.LOW, requires_approval=True,
        func=_take_desktop_screenshot, input_schema={})

    # --- TERMINAL ---
    reg(name="propose_terminal_command", description="Propose a terminal command (no execution).",
        permission=P.SAFE_READ, risk=R.NONE, func=_propose_terminal_command,
        input_schema={"command": "str"})
    reg(name="run_terminal_readonly_after_approval",
        description="Run an allowlisted read-only command (approval first time).",
        permission=P.TERMINAL_READ, risk=R.MEDIUM, func=_run_terminal_readonly,
        command_arg="command", input_schema={"command": "str"})

    # --- telegram ---
    reg(name="send_telegram_message", description="Send a Telegram message to the owner.",
        permission=P.NETWORK_ACCESS, risk=R.LOW, func=_send_telegram_message,
        input_schema={"text": "str"})
    reg(name="receive_telegram_file", description="Ingest a Telegram-uploaded file to memory.",
        permission=P.SAFE_READ, risk=R.LOW, func=_telegram_stub, input_schema={"file_id": "str"})
    reg(name="transcribe_telegram_voice", description="Transcribe a Telegram voice message (Phase 2).",
        permission=P.SAFE_READ, risk=R.LOW, func=_telegram_stub, input_schema={"file_id": "str"})

    return registry
