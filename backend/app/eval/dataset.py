"""Local fine-tuning dataset export (Phase 4).

Exports completed tasks / chat pairs to JSONL in the common chat-messages
("OpenAI") format for local fine-tuning or evaluation. Pure transformation +
file write; secrets are redacted on the way out. Local-first: data never leaves
the machine.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.security.prompt_injection import redact_secrets
from app.services.tasks import Task


def task_to_example(task: Task, *, system: str | None = None) -> dict:
    """Convert a completed task into a chat fine-tuning example."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": redact_secrets(task.command)})
    messages.append({"role": "assistant", "content": redact_secrets(task.result)})
    return {"messages": messages, "meta": {"task_type": task.task_type, "mode": task.mode}}


def export_tasks_jsonl(tasks: list[Task], path: str, *, system: str | None = None,
                       only_completed: bool = True) -> int:
    """Write tasks to a JSONL dataset; returns the number of rows written."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with Path(path).open("w", encoding="utf-8") as fh:
        for task in tasks:
            if only_completed and task.status.value != "completed":
                continue
            if not task.result.strip():
                continue
            fh.write(json.dumps(task_to_example(task, system=system)) + "\n")
            n += 1
    return n
