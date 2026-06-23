"""Performance optimizer + learning loop + processing queue."""
from __future__ import annotations

import asyncio

import pytest

from app.brain.learning import FeedbackLoop, TaskFeedback
from app.brain.performance import (
    EmbeddingCache,
    ResourceMonitor,
    ResponseCache,
    cached_complete,
    prompt_key,
)
from app.brain.queue import JobStatus, ProcessingQueue
from app.eval.evaluations import EvaluationStore
from app.llm.base import ChatMessage, CompletionRequest, Role
from app.llm.mock_provider import MockProvider


# --- performance: response cache ---
@pytest.mark.asyncio
async def test_response_cache_skips_second_model_call():
    provider = MockProvider()
    cache = ResponseCache()
    req = CompletionRequest(model="m", messages=[ChatMessage(Role.USER, "hello")])
    r1 = await cached_complete(provider, req, cache)
    r2 = await cached_complete(provider, req, cache)
    assert r1.text == r2.text
    assert len(provider.calls) == 1  # second call served from cache
    assert cache.stats()["hits"] == 1


def test_prompt_key_stable_and_distinct():
    a = CompletionRequest(model="m", messages=[ChatMessage(Role.USER, "x")])
    b = CompletionRequest(model="m", messages=[ChatMessage(Role.USER, "y")])
    assert prompt_key("m", a) == prompt_key("m", a)
    assert prompt_key("m", a) != prompt_key("m", b)


def test_response_cache_lru_eviction():
    cache = ResponseCache(max_size=2)
    from app.llm.base import CompletionResponse

    for i in range(3):
        cache.set(f"k{i}", CompletionResponse(text=str(i), model="m", provider="mock"))
    assert cache.get("k0") is None  # evicted
    assert cache.get("k2") is not None


def test_embedding_cache_computes_once():
    calls = {"n": 0}

    def embed(t):
        calls["n"] += 1
        return [1.0, 2.0]

    ec = EmbeddingCache()
    ec.get_or_compute("hi", embed)
    ec.get_or_compute("hi", embed)
    assert calls["n"] == 1


def test_resource_monitor_snapshot():
    snap = ResourceMonitor().snapshot()
    assert snap["cpu_count"] >= 1
    assert snap["max_parallel_jobs"] >= 1
    assert isinstance(snap["gpu"], bool)


# --- learning loop ---
def test_feedback_updates_router_performance():
    loop = FeedbackLoop(EvaluationStore())
    loop.record(TaskFeedback(task_id="1", model_key="ollama/llama3.1", task_type="coding",
                             verifier_score=0.9, completeness=0.9, factuality=0.9))
    loop.record(TaskFeedback(task_id="2", model_key="ollama/llama3.1", task_type="coding",
                             verifier_score=0.2, completeness=0.2, user_corrected=True))
    perf = loop.to_router_performance()
    from app.llm.registry import TaskType

    assert (("ollama/llama3.1", TaskType.CODING) in perf)
    # one pass, one fail -> 0.5 success rate
    assert perf[("ollama/llama3.1", TaskType.CODING)] == 0.5


def test_feedback_composite_and_pass():
    good = TaskFeedback(task_id="x", model_key="m", task_type="research",
                        verifier_score=0.9, completeness=0.9, factuality=0.9,
                        user_satisfied=True)
    assert good.passed() is True
    bad = TaskFeedback(task_id="y", model_key="m", task_type="research",
                       verifier_score=0.9, user_corrected=True)
    assert bad.passed() is False


def test_leaderboard_sorted():
    loop = FeedbackLoop(EvaluationStore())
    loop.record(TaskFeedback(task_id="1", model_key="good", task_type="coding",
                             verifier_score=1, completeness=1, factuality=1))
    loop.record(TaskFeedback(task_id="2", model_key="bad", task_type="coding",
                             verifier_score=0, completeness=0, user_corrected=True))
    board = loop.leaderboard("coding")
    assert board[0]["model"] == "good"


# --- processing queue ---
@pytest.mark.asyncio
async def test_queue_runs_job_to_completion():
    q = ProcessingQueue(concurrency=2)

    async def handler(job):
        job.log("working")
        return {"echo": job.payload.get("x")}

    q.register("echo", handler)
    await q.start()
    job = q.enqueue("echo", {"x": 42})
    await q.drain()
    await q.stop()
    assert q.get(job.id).status == JobStatus.COMPLETED
    assert q.get(job.id).result == {"echo": 42}


@pytest.mark.asyncio
async def test_queue_failure_retries_then_fails():
    q = ProcessingQueue(concurrency=1)
    attempts = {"n": 0}

    async def boom(job):
        attempts["n"] += 1
        raise RuntimeError("boom")

    q.register("boom", boom)
    await q.start()
    job = q.enqueue("boom", {}, max_retries=2)
    await q.drain()
    await asyncio.sleep(0.05)
    await q.stop()
    assert q.get(job.id).status == JobStatus.FAILED
    assert attempts["n"] == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_queue_cancel_before_run():
    q = ProcessingQueue(concurrency=1)

    async def slow(job):
        await asyncio.sleep(1)
        return "done"

    q.register("slow", slow)
    job = q.enqueue("slow", {})
    assert q.cancel(job.id) is True
    await q.start()
    await asyncio.sleep(0.05)
    await q.stop()
    assert q.get(job.id).status == JobStatus.CANCELLED
