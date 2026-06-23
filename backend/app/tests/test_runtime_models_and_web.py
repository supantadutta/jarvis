"""Connect-any-model at runtime + real web tools + self-learning loop."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.main import create_app
from app.tools.base import ToolContext


@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c, brain


# --- runtime "connect any model" ---
def test_add_model_at_runtime(client):
    c, brain = client
    before = len(brain.registry.all())
    r = c.post("/api/models", json={
        "provider": "deepseek", "model_name": "deepseek-chat", "kind": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1", "api_key": "sk-xxx",
        "reasoning_level": 5, "coding_level": 5,
    })
    assert r.status_code == 200
    assert r.json()["added"]["key"] == "deepseek/deepseek-chat"
    assert len(brain.registry.all()) == before + 1
    # The new model is usable: it appears in the registry and is bound.
    assert brain.registry.get("deepseek/deepseek-chat").enabled
    assert "deepseek" in brain.providers


@pytest.mark.asyncio
async def test_add_model_then_used_by_orchestrator(brain):
    # Add a custom model and confirm the router/orchestrator can select it.
    from app.agents.orchestrator import Orchestrator

    for s in brain.registry.all():
        s.enabled = False
    brain.add_model_source(provider="myllm", model_name="m1", reasoning_level=5,
                           privacy_level=2, cost_type="free")
    result = await Orchestrator(brain).run("hello there")
    assert any("myllm" in m for m in result.models)


def test_delete_model(client):
    c, brain = client
    c.post("/api/models", json={"provider": "tmp", "model_name": "x"})
    r = c.delete("/api/models/tmp/x")
    assert r.status_code == 200 and r.json()["removed"] == "tmp/x"
    assert brain.registry.get("tmp/x") is None


def test_secret_not_leaked_in_providers_endpoint(client):
    c, _ = client
    c.post("/api/models", json={"provider": "p", "model_name": "m", "api_key": "sk-super-secret"})
    body = c.get("/api/providers").json()
    assert "sk-super-secret" not in c.get("/api/providers").text
    assert body["configs"]["p"]["has_key"] is True


# --- real web tools (mocked network) ---
@pytest.fixture
def mock_web(monkeypatch):
    from app.tools.builtin import web

    monkeypatch.setattr(web, "do_search", lambda q, **k: [
        {"title": "Result A", "url": "https://example.com/a", "snippet": ""},
        {"title": "Result B", "url": "https://example.com/b", "snippet": ""},
    ])
    pages = {
        "https://example.com/a": "Python is a programming language created by Guido.",
        "https://example.com/b": "Python is widely used for AI and data science.",
    }
    monkeypatch.setattr(web, "do_fetch", lambda url, max_chars=20000: pages.get(url, ""))


def test_html_to_text():
    from app.tools.builtin.web import html_to_text

    out = html_to_text("<html><body><script>x=1</script><p>Hello &amp; world</p></body></html>")
    assert "Hello & world" in out
    assert "x=1" not in out


@pytest.mark.asyncio
async def test_web_search_tool(brain, mock_web):
    ctx = ToolContext(settings=brain.settings, workspace_root=brain.settings.workspace_root,
                      services=brain.service_bundle(), agent_key="research")
    out = await brain.executor.execute("web_search", {"query": "python", "domain": "x"}, ctx)
    # NETWORK_ACCESS auto-allows by default policy; tool returns results.
    assert out.result.ok
    assert len(out.result.output["results"]) == 2


@pytest.mark.asyncio
async def test_web_fetch_wraps_untrusted(brain, mock_web):
    ctx = ToolContext(settings=brain.settings, workspace_root=brain.settings.workspace_root,
                      services=brain.service_bundle(), agent_key="research")
    out = await brain.executor.execute(
        "web_fetch", {"url": "https://example.com/a", "domain": "example.com"}, ctx)
    assert out.result.ok
    assert "untrusted_external_data" in out.result.output


@pytest.mark.asyncio
async def test_web_tools_blocked_in_private_mode(brain, mock_web):
    ctx = ToolContext(settings=brain.settings, workspace_root=brain.settings.workspace_root,
                      services=brain.service_bundle(), agent_key="research", private_mode=True)
    out = await brain.executor.execute("web_search", {"query": "x"}, ctx)
    assert out.decision.value == "deny"


# --- self-learning loop ---
@pytest.mark.asyncio
async def test_learn_topic_stores_to_memory(brain, mock_web):
    result = await brain.learner.learn("python", max_sources=2)
    assert result["sources_used"] == 2
    assert result["memory_id"]
    assert result["summary"]  # mock model produced a summary
    # The learned knowledge is now retrievable from memory.
    hits = brain.memory.search("python programming language", collection="learned")
    assert hits


def test_learn_endpoint(client, mock_web):
    c, _ = client
    r = c.post("/api/learn", json={"topic": "python", "max_sources": 2})
    assert r.status_code == 200
    assert r.json()["sources_used"] == 2
