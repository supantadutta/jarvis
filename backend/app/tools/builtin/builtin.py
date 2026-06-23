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
from app.security.prompt_injection import scan_for_injection, wrap_untrusted
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
        # File contents are untrusted external data — scan + wrap.
        scan = scan_for_injection(text)
        return ToolResult(
            ok=True,
            output=wrap_untrusted(text, source=f"file:{args['path']}"),
            summary=f"Read {len(text)} chars from {args['path']}"
            + (" [injection-flagged]" if scan.flagged else ""),
            injection_flagged=scan.flagged,
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


def _doc_model(args: dict):
    """Build a DocumentModel from tool args (title + content + optional table)."""
    from app.documents.generators import DocumentModel, Section

    return DocumentModel(
        title=args.get("title", "report"),
        sections=[Section(heading="Content", body=args.get("content", ""))],
        table_headers=args.get("table_headers", []),
        table_rows=args.get("table_rows", []),
    )


def _doc_path(ctx: ToolContext, title: str, ext: str) -> str:
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = title.replace("/", "_")
    return f"{ctx.settings.notes_dir}/{safe}-{ts}.{ext}"


async def _create_docx_report(ctx: ToolContext, args: dict) -> ToolResult:
    from app.documents.generators import write_docx

    try:
        path = write_docx(_doc_model(args), _doc_path(ctx, args.get("title", "report"), "docx"))
        return ToolResult(ok=True, output=path, summary=f"DOCX saved: {path}", artifacts=[path])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc), summary="docx generation failed")


async def _create_pdf_report(ctx: ToolContext, args: dict) -> ToolResult:
    from app.documents.generators import write_pdf

    try:
        path = write_pdf(_doc_model(args), _doc_path(ctx, args.get("title", "report"), "pdf"))
        return ToolResult(ok=True, output=path, summary=f"PDF saved: {path}", artifacts=[path])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc), summary="pdf generation failed")


async def _create_xlsx_report(ctx: ToolContext, args: dict) -> ToolResult:
    from app.documents.generators import write_xlsx

    try:
        path = write_xlsx(_doc_model(args), _doc_path(ctx, args.get("title", "report"), "xlsx"))
        return ToolResult(ok=True, output=path, summary=f"XLSX saved: {path}", artifacts=[path])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc), summary="xlsx generation failed")


async def _analyze_csv(ctx: ToolContext, args: dict) -> ToolResult:
    """Read a workspace CSV and return summary stats (stdlib only, no pandas)."""
    import csv
    import statistics

    try:
        path = _safe_join(ctx.workspace_root, args["path"])
        if not path.exists() or not path.is_file():
            return ToolResult(ok=False, error="CSV file not found.")
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            headers = reader.fieldnames or []
        if not headers:
            return ToolResult(ok=False, error="CSV has no header row.")

        columns: dict[str, dict] = {}
        for col in headers:
            values = [r.get(col, "") for r in rows]
            nums: list[float] = []
            for v in values:
                try:
                    nums.append(float(v))
                except (TypeError, ValueError):
                    pass
            is_numeric = len(nums) == len([v for v in values if v not in ("", None)]) and bool(nums)
            info: dict = {"type": "numeric" if is_numeric else "text",
                          "non_empty": len([v for v in values if v not in ("", None)])}
            if is_numeric:
                info.update({
                    "min": min(nums), "max": max(nums),
                    "mean": round(statistics.fmean(nums), 4), "sum": round(sum(nums), 4),
                })
            columns[col] = info

        return ToolResult(
            ok=True,
            output={"rows": len(rows), "columns": headers, "stats": columns},
            summary=f"Analyzed CSV: {len(rows)} rows × {len(headers)} columns",
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


# --------------------------------------------------------------------------
# Phase 3 integration tools (defensive SOC / docs / comms)
# --------------------------------------------------------------------------
async def _build_soc_query(ctx: ToolContext, args: dict) -> ToolResult:
    from app.soc.defensive import DetectionSpec, build_logscale_query, build_splunk_spl

    spec = DetectionSpec(
        index=args.get("index", "*"), event_id=args.get("event_id"),
        field_filters=args.get("field_filters", {}), threshold=args.get("threshold"),
        by_fields=args.get("by_fields", []),
    )
    return ToolResult(
        ok=True,
        output={"spl": build_splunk_spl(spec), "logscale": build_logscale_query(spec)},
        summary="Built defensive SOC queries.",
    )


async def _generate_readme(ctx: ToolContext, args: dict) -> ToolResult:
    from app.integrations.github import ProjectInfo, build_readme

    readme = build_readme(ProjectInfo(
        name=args.get("name", "project"), description=args.get("description", ""),
        features=args.get("features", []), tech_stack=args.get("tech_stack", []),
        install_cmds=args.get("install_cmds", []), usage=args.get("usage", ""),
        license=args.get("license", "MIT"),
    ))
    return ToolResult(ok=True, output=readme, summary="Generated README.")


async def _compose_email_draft(ctx: ToolContext, args: dict) -> ToolResult:
    from app.integrations.email_calendar import compose_email_draft

    draft = compose_email_draft(
        to=args.get("to", []), subject=args.get("subject", ""),
        body=args.get("body", ""), cc=args.get("cc"), signature=args.get("signature"),
    )
    return ToolResult(ok=True, output=draft.public(), summary="Composed email draft (not sent).")


async def _create_calendar_event(ctx: ToolContext, args: dict) -> ToolResult:
    from datetime import datetime

    from app.integrations.email_calendar import build_ics_event

    try:
        start = datetime.fromisoformat(args["start"])
        end = datetime.fromisoformat(args["end"])
    except (KeyError, ValueError) as exc:
        return ToolResult(ok=False, error=f"start/end must be ISO datetimes: {exc}")
    ics = build_ics_event(summary=args.get("summary", "Event"), start=start, end=end,
                          description=args.get("description", ""), location=args.get("location", ""))
    from pathlib import Path

    notes = Path(ctx.settings.notes_dir)
    notes.mkdir(parents=True, exist_ok=True)
    path = notes / f"{args.get('summary', 'event').replace('/', '_')}.ics"
    path.write_text(ics, encoding="utf-8")
    return ToolResult(ok=True, output=str(path), summary="Created ICS event.", artifacts=[str(path)])


async def _send_email_after_approval(ctx: ToolContext, args: dict) -> ToolResult:
    # Guard already required approval (HIGH_RISK). Real SMTP/OAuth send is Phase 3+.
    return ToolResult(
        ok=False,
        error="Email sending requires a configured provider (Gmail/Graph OAuth) — Phase 3+.",
        summary="send not configured",
    )


async def _send_whatsapp_after_approval(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(
        ok=False,
        error="WhatsApp Cloud API send requires WHATSAPP_* configuration.",
        summary="whatsapp not configured",
    )


async def _trigger_n8n_after_approval(ctx: ToolContext, args: dict) -> ToolResult:
    return ToolResult(
        ok=False, error="n8n trigger requires N8N_BASE_URL configuration.",
        summary="n8n not configured",
    )


# --------------------------------------------------------------------------
# memory tools
# --------------------------------------------------------------------------
async def _index_file(ctx: ToolContext, args: dict) -> ToolResult:
    """Read a workspace file, chunk it, and store chunks into semantic memory."""
    from app.rag.chunking import chunk_text

    memory = ctx.services.get("layered_memory") or ctx.services.get("memory")
    if not memory:
        return ToolResult(ok=False, error="Memory service unavailable.")
    try:
        path = _safe_join(ctx.workspace_root, args["path"])
        if not path.exists() or not path.is_file():
            return ToolResult(ok=False, error="File not found.")
        text = path.read_text(encoding="utf-8", errors="replace")[:500_000]
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))
    chunks = chunk_text(text, size=args.get("chunk_size", 800), overlap=args.get("overlap", 120))
    for i, c in enumerate(chunks):
        if hasattr(memory, "remember"):
            memory.remember("semantic", c, source=f"file:{args['path']}#chunk{i}",
                            metadata={"chunk_index": i})
        else:
            memory.add(c, collection="semantic", source=f"file:{args['path']}#chunk{i}")
    return ToolResult(ok=True, output={"chunks": len(chunks)},
                      summary=f"Indexed {len(chunks)} chunks from {args['path']}")


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
    reg(name="analyze_csv", description="Summarize a workspace CSV (rows, columns, numeric stats).",
        permission=P.SAFE_READ, risk=R.NONE, func=_analyze_csv, path_arg="path",
        input_schema={"path": "str"})
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
    reg(name="index_file", description="Chunk a workspace file into semantic memory (RAG).",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_index_file, path_arg="path",
        input_schema={"path": "str", "chunk_size": "int?", "overlap": "int?"})
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
    reg(name="create_xlsx_report", description="Generate an XLSX spreadsheet report (Phase 3).",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_create_xlsx_report,
        input_schema={"title": "str", "table_headers": "list", "table_rows": "list"})

    # --- Phase 3 integrations ---
    reg(name="build_soc_query", description="Build defensive Splunk/LogScale detection queries.",
        permission=P.SAFE_READ, risk=R.NONE, func=_build_soc_query,
        input_schema={"index": "str?", "event_id": "int?", "by_fields": "list?", "threshold": "int?"})
    reg(name="generate_readme", description="Generate a project README from structured info.",
        permission=P.SAFE_READ, risk=R.NONE, func=_generate_readme,
        input_schema={"name": "str", "description": "str?", "features": "list?"})
    reg(name="compose_email_draft", description="Compose an email draft (not sent).",
        permission=P.SAFE_READ, risk=R.NONE, func=_compose_email_draft,
        input_schema={"to": "list", "subject": "str", "body": "str"})
    reg(name="create_calendar_event", description="Create an ICS calendar event file.",
        permission=P.LOW_RISK_WRITE, risk=R.LOW, func=_create_calendar_event,
        input_schema={"summary": "str", "start": "str", "end": "str"})
    reg(name="send_email_after_approval", description="Send an email (HIGH_RISK; approval required).",
        permission=P.HIGH_RISK, risk=R.HIGH, requires_approval=True, uses_credential=True,
        func=_send_email_after_approval, is_irreversible=True,
        input_schema={"to": "list", "subject": "str", "body": "str"})
    reg(name="send_whatsapp_after_approval",
        description="Send a WhatsApp message via the official Cloud API (approval required).",
        permission=P.HIGH_RISK, risk=R.HIGH, requires_approval=True, uses_credential=True,
        func=_send_whatsapp_after_approval, is_irreversible=True,
        input_schema={"to": "str", "body": "str"})
    reg(name="trigger_n8n_after_approval", description="Trigger an n8n workflow webhook (approval).",
        permission=P.NETWORK_ACCESS, risk=R.MEDIUM, requires_approval=True,
        func=_trigger_n8n_after_approval, input_schema={"webhook": "str", "data": "dict?"})

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
