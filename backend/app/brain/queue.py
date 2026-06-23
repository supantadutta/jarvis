"""Processing Queue + background worker (Cognitive Processing Engine v2).

An async, in-process job queue with a worker that runs coroutine jobs and tracks
status, logs, artifacts, and errors. States: queued, running, waiting_for_approval,
paused, completed, failed, cancelled. Supports cancel + retry. This is the
local-first default; a Redis/Arq backend can replace the queue transport later
without changing callers (same Job API).
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

JobFn = Callable[["Job"], Awaitable[object]]


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    kind: str
    payload: dict
    status: JobStatus = JobStatus.QUEUED
    logs: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    result: object = None
    error: str | None = None
    retries: int = 0
    max_retries: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    _cancel: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def log(self, msg: str) -> None:
        self.logs.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}")
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_status(self, status: JobStatus) -> None:
        self.status = status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def public(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "status": self.status.value,
            "logs": self.logs[-50:], "artifacts": self.artifacts,
            "error": self.error, "retries": self.retries,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "result": self.result if isinstance(self.result, (dict, list, str, int, float, bool, type(None))) else str(self.result),
        }


class ProcessingQueue:
    def __init__(self, concurrency: int = 2) -> None:
        self.concurrency = concurrency
        self._handlers: dict[str, JobFn] = {}
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False

    def register(self, kind: str, fn: JobFn) -> None:
        self._handlers[kind] = fn

    def enqueue(self, kind: str, payload: dict, *, max_retries: int = 1) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, payload=payload, max_retries=max_retries)
        self._jobs[job.id] = job
        self._queue.put_nowait(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all(self, limit: int = 100) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return False
        job._cancel.set()
        if job.status == JobStatus.QUEUED:
            job.set_status(JobStatus.CANCELLED)
        return True

    def retry(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if not job or job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
            return None
        job.error = None
        job._cancel = asyncio.Event()
        job.set_status(JobStatus.QUEUED)
        self._queue.put_nowait(job.id)
        return job

    async def _run_job(self, job: Job) -> None:
        handler = self._handlers.get(job.kind)
        if handler is None:
            job.set_status(JobStatus.FAILED)
            job.error = f"no handler for kind '{job.kind}'"
            return
        if job.cancelled:
            job.set_status(JobStatus.CANCELLED)
            return
        job.set_status(JobStatus.RUNNING)
        job.log(f"running ({job.kind})")
        try:
            job.result = await handler(job)
            job.set_status(JobStatus.COMPLETED if not job.cancelled else JobStatus.CANCELLED)
            job.log("completed")
        except asyncio.CancelledError:
            job.set_status(JobStatus.CANCELLED)
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            if job.retries < job.max_retries and not job.cancelled:
                job.retries += 1
                job.log(f"error: {exc} -> retry {job.retries}")
                job.set_status(JobStatus.QUEUED)  # so the worker picks it up again
                self._queue.put_nowait(job.id)
            else:
                job.set_status(JobStatus.FAILED)
                job.log(f"failed: {exc}")

    async def _worker(self) -> None:
        while self._running:
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.QUEUED,):
                await self._run_job(job)
            self._queue.task_done()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]

    async def stop(self) -> None:
        self._running = False
        for w in self._workers:
            w.cancel()
        self._workers = []

    async def drain(self, timeout: float = 5.0) -> None:
        """Wait until all queued jobs are processed (for tests/shutdown)."""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
