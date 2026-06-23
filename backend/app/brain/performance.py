"""Local Performance Optimizer (Cognitive Processing Engine v2).

Adds caching + resource awareness for faster, leaner local execution:
- ResponseCache: LRU+TTL cache for (model, prompt) -> completion, to skip repeat
  LLM calls (deterministic, opt-in; PRIVATE_MODE-safe since it's local-only).
- EmbeddingCache / chunk cache: avoid recomputing embeddings.
- ResourceMonitor: CPU/RAM/GPU detection -> recommended max parallel jobs and a
  graceful-degradation flag when resources are low.
- OllamaTuner: health check + keep-alive/warmup payload helpers.

All optional deps (psutil, torch) are imported lazily; nothing here calls the
network except the explicit Ollama health check.
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from app.llm.base import CompletionRequest, CompletionResponse, LLMProvider


def prompt_key(model: str, request: CompletionRequest) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    for m in request.messages:
        h.update(b"\x00")
        h.update(m.role.value.encode())
        h.update(m.content.encode())
    h.update(f"|t={request.temperature}|j={request.json_mode}".encode())
    return h.hexdigest()


class ResponseCache:
    def __init__(self, max_size: int = 512, ttl: float = 3600.0) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self._data: OrderedDict[str, tuple[float, CompletionResponse]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> CompletionResponse | None:
        item = self._data.get(key)
        if item is None:
            self.misses += 1
            return None
        ts, resp = item
        if time.monotonic() - ts > self.ttl:
            self._data.pop(key, None)
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return resp

    def set(self, key: str, resp: CompletionResponse) -> None:
        self._data[key] = (time.monotonic(), resp)
        self._data.move_to_end(key)
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"size": len(self._data), "hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0}


async def cached_complete(provider: LLMProvider, request: CompletionRequest,
                          cache: ResponseCache) -> CompletionResponse:
    """Complete with response caching. Skips the model on a cache hit."""
    key = prompt_key(request.model, request)
    cached = cache.get(key)
    if cached is not None:
        return cached
    resp = await provider.complete(request)
    cache.set(key, resp)
    return resp


class EmbeddingCache:
    def __init__(self, max_size: int = 4096) -> None:
        self.max_size = max_size
        self._data: OrderedDict[str, list[float]] = OrderedDict()

    def get_or_compute(self, text: str, embed) -> list[float]:
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        vec = embed(text)
        self._data[key] = vec
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)
        return vec


class ResourceMonitor:
    def snapshot(self) -> dict:
        import os

        cpu = os.cpu_count() or 1
        ram_gb = self._ram_gb()
        gpu = self._has_gpu()
        # Recommend parallelism: bounded by CPUs, reduced if RAM is low.
        max_parallel = max(1, min(cpu, 8))
        degraded = ram_gb is not None and ram_gb < 2.0
        if degraded:
            max_parallel = 1
        return {
            "cpu_count": cpu, "ram_gb": ram_gb, "gpu": gpu,
            "max_parallel_jobs": max_parallel, "degraded": degraded,
        }

    @staticmethod
    def _ram_gb() -> float | None:
        try:
            import psutil  # type: ignore

            return round(psutil.virtual_memory().total / 1e9, 1)
        except Exception:  # noqa: BLE001
            try:
                import os

                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return round(pages * page_size / 1e9, 1)
            except (ValueError, OSError, AttributeError):
                return None

    @staticmethod
    def _has_gpu() -> bool:
        import shutil

        if shutil.which("nvidia-smi"):
            return True
        try:
            import torch  # type: ignore

            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            return False

    def gpu_aware_model_filter(self, specs: list, snapshot: dict | None = None) -> list:
        """When no GPU and RAM is low, prefer smaller/faster local models."""
        snap = snapshot or self.snapshot()
        if snap["gpu"] or not snap["degraded"]:
            return specs
        # Degraded + CPU-only: prefer faster models.
        return sorted(specs, key=lambda s: -getattr(s, "speed_level", 3))


class OllamaTuner:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def health(self) -> bool:  # pragma: no cover - network
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5) as c:
                return (await c.get(f"{self.base_url}/api/tags")).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def keep_alive_payload(model: str, keep_alive: str = "10m") -> dict:
        """Body to warm/keep a model resident in Ollama."""
        return {"model": model, "keep_alive": keep_alive, "prompt": "", "stream": False}
