"""ToolExecutor — the single chokepoint for running any tool.

Flow for every call:
  1. Look up the ToolSpec.
  2. Build a GuardRequest (pulling path/domain/command from args).
  3. Ask the Permission Guard.
     - DENY              -> return a denied ToolResult (audited).
     - REQUIRES_APPROVAL -> create an Approval, wait; if not granted, abort.
     - AUTO_ALLOW        -> proceed.
  4. Run the tool function with a timeout.
  5. Audit the outcome (with redaction).

This is the only place tools run, so the guard cannot be bypassed.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app.audit.logger import AuditLog
from app.security.permissions import (
    Decision,
    GuardRequest,
    PermissionGuard,
)
from app.services.approvals import ApprovalQueue, ApprovalRequest
from app.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec


@dataclass
class ExecutionOutcome:
    result: ToolResult
    decision: Decision
    approval_id: str | None = None
    audited_id: str | None = None


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        guard: PermissionGuard,
        approvals: ApprovalQueue,
        audit: AuditLog,
        *,
        approval_timeout: float | None = 300.0,
    ) -> None:
        self.registry = registry
        self.guard = guard
        self.approvals = approvals
        self.audit = audit
        self.approval_timeout = approval_timeout

    @staticmethod
    def _resolve_path(workspace_root: str, value: str) -> str:
        """Resolve a tool's path arg against the workspace root so the guard
        evaluates the concrete target. Uses normpath (not realpath) to stay
        consistent with the configured allowlist roots and still collapse '..'."""
        import os

        return os.path.normpath(os.path.join(workspace_root, value))

    def _guard_request(self, spec: ToolSpec, args: dict, ctx: ToolContext) -> GuardRequest:
        raw_path = args.get(spec.path_arg) if spec.path_arg else None
        resolved_path = (
            self._resolve_path(ctx.workspace_root, raw_path) if raw_path is not None else None
        )
        return GuardRequest(
            tool_name=spec.name,
            permission=spec.permission,
            risk=spec.risk,
            path=resolved_path,
            domain=args.get(spec.domain_arg) if spec.domain_arg else None,
            command=args.get(spec.command_arg) if spec.command_arg else None,
            uses_credential=spec.uses_credential,
            is_irreversible=spec.is_irreversible,
            private_mode=ctx.private_mode,
        )

    async def execute(
        self, name: str, args: dict, ctx: ToolContext, *, task_name: str = "task"
    ) -> ExecutionOutcome:
        spec = self.registry.get(name)
        if spec is None:
            res = ToolResult(ok=False, error=f"Unknown tool: {name}", summary="unknown tool")
            return ExecutionOutcome(result=res, decision=Decision.DENY)

        guard_req = self._guard_request(spec, args, ctx)
        verdict = self.guard.evaluate(guard_req)

        if verdict.decision == Decision.DENY:
            entry = self.audit.record(
                user_command=ctx.user_command,
                agent=ctx.agent_key,
                model=ctx.model_key,
                tool=name,
                input_summary=_summarize_args(args),
                output_summary=f"DENIED: {verdict.reason}",
                risk=spec.risk.value,
                approval_status="denied",
                error=verdict.reason,
            )
            return ExecutionOutcome(
                result=ToolResult(ok=False, error=verdict.reason, summary="denied by guard"),
                decision=Decision.DENY,
                audited_id=entry.id,
            )

        approval_id: str | None = None
        if verdict.decision == Decision.REQUIRES_APPROVAL:
            approval = self.approvals.create(
                ApprovalRequest(
                    task_name=task_name,
                    requested_action=spec.description,
                    agent=ctx.agent_key or "unknown",
                    model=ctx.model_key,
                    tool=name,
                    account=args.get("account"),
                    credential=args.get("credential"),
                    risk=spec.risk.value,
                    what_can_change=spec.rollback or "See action preview.",
                    action_preview=_preview(name, args),
                    allow_trust=not spec.is_irreversible and not spec.uses_credential,
                )
            )
            approval_id = approval.id
            resolved = await self.approvals.wait(approval.id, timeout=self.approval_timeout)
            if not ApprovalQueue.is_granted(resolved):
                status = resolved.status.value if resolved else "expired"
                entry = self.audit.record(
                    user_command=ctx.user_command,
                    agent=ctx.agent_key,
                    model=ctx.model_key,
                    tool=name,
                    input_summary=_summarize_args(args),
                    output_summary=f"Not approved ({status}).",
                    risk=spec.risk.value,
                    approval_status=status,
                )
                return ExecutionOutcome(
                    result=ToolResult(
                        ok=False, error=f"Action not approved ({status}).", summary="not approved"
                    ),
                    decision=Decision.REQUIRES_APPROVAL,
                    approval_id=approval_id,
                    audited_id=entry.id,
                )

        # Run the tool.
        if spec.func is None:
            res = ToolResult(ok=False, error=f"Tool '{name}' has no implementation.")
        else:
            start = time.perf_counter()
            try:
                res = await asyncio.wait_for(spec.func(ctx, args), timeout=spec.timeout_s)
            except TimeoutError:
                res = ToolResult(ok=False, error=f"Tool '{name}' timed out after {spec.timeout_s}s")
            except Exception as exc:  # noqa: BLE001
                res = ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")
            res.duration_ms = int((time.perf_counter() - start) * 1000)

        entry = self.audit.record(
            user_command=ctx.user_command,
            agent=ctx.agent_key,
            model=ctx.model_key,
            tool=name,
            input_summary=_summarize_args(args),
            output_summary=(res.summary or str(res.output))[:500] if res.ok else (res.error or ""),
            risk=spec.risk.value,
            approval_status="approved" if approval_id else "auto",
            screenshot_ref=res.screenshot_ref,
            error=res.error,
        )
        return ExecutionOutcome(
            result=res,
            decision=verdict.decision,
            approval_id=approval_id,
            audited_id=entry.id,
        )


def _summarize_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        sval = str(v)
        if len(sval) > 80:
            sval = sval[:77] + "..."
        parts.append(f"{k}={sval}")
    return ", ".join(parts)[:500]


def _preview(name: str, args: dict) -> str:
    return f"{name}({_summarize_args(args)})"
