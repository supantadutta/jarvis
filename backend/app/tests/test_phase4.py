"""Phase 4: self-evaluation loop, dataset export, plugins, MCP manifest."""
from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.agents.orchestrator import Orchestrator
from app.deps import set_brain
from app.eval.dataset import export_tasks_jsonl, task_to_example
from app.eval.evaluations import EvaluationStore
from app.integrations.mcp import export_tool_manifest
from app.llm.registry import TaskType
from app.main import create_app
from app.model_router.modes import Mode


# --- evaluation store ---
def test_evaluation_store_success_rate():
    s = EvaluationStore()
    s.record("ollama/llama3.1", TaskType.CODING, passed=True, score=0.9)
    s.record("ollama/llama3.1", TaskType.CODING, passed=False, score=0.2)
    stat = s.get("ollama/llama3.1", TaskType.CODING)
    assert stat.samples == 2 and stat.successes == 1
    assert stat.success_rate == 0.5
    perf = s.to_router_performance()
    assert perf[("ollama/llama3.1", TaskType.CODING)] == 0.5


@pytest.mark.asyncio
async def test_orchestrator_records_evaluation_in_deep_work(brain):
    await Orchestrator(brain).run("deep work: design something", mode_override=Mode.DEEP_WORK_MODE)
    assert brain.evaluations.summary()  # at least one verdict recorded
    # And the router now has performance data fed back.
    assert brain.evaluations.to_router_performance()


# --- dataset export ---
@pytest.mark.asyncio
async def test_dataset_export_jsonl(brain):
    await Orchestrator(brain).run("summarize my notes")
    path = os.path.join(tempfile.mkdtemp(), "ds.jsonl")
    n = export_tasks_jsonl(brain.tasks.all(), path, system="You are Jarvis.")
    assert n >= 1
    lines = open(path).read().strip().splitlines()
    row = json.loads(lines[0])
    assert row["messages"][0]["role"] == "system"
    assert row["messages"][-1]["role"] == "assistant"


def test_task_to_example_redacts_secrets():
    from app.services.tasks import Task, TaskStatus

    t = Task(id="1", command="my api_key=sk-abcdef123456789", task_type="x", mode="y")
    t.result = "ok"
    t.status = TaskStatus.COMPLETED
    ex = task_to_example(t)
    assert "sk-abcdef" not in json.dumps(ex)
    assert "[REDACTED]" in ex["messages"][0]["content"]


# --- plugin system ---
SAMPLE_PLUGIN = '''
from app.tools.base import ToolSpec, ToolResult
from app.security.permissions import PermissionLevel, RiskLevel

async def _hello(ctx, args):
    return ToolResult(ok=True, output="hi", summary="hello plugin")

def register(registry):
    registry.register(ToolSpec(
        name="hello_plugin_tool", description="A sample plugin tool.",
        permission=PermissionLevel.SAFE_READ, risk=RiskLevel.NONE, func=_hello,
    ))

PLUGIN_META = {"name": "hello", "version": "1.0"}
'''


def test_plugin_loads_and_registers_tool(brain):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hello_plugin.py"), "w") as fh:
        fh.write(SAMPLE_PLUGIN)
    loaded = brain.plugins.load_directory(d)
    assert len(loaded) == 1
    assert loaded[0].error is None
    assert "hello_plugin_tool" in loaded[0].tools_added
    assert brain.tools.get("hello_plugin_tool") is not None


def test_plugin_without_register_reports_error(brain):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "bad_plugin.py"), "w") as fh:
        fh.write("X = 1\n")
    loaded = brain.plugins.load_directory(d)
    assert loaded[0].error is not None


# --- MCP manifest ---
def test_mcp_manifest_shape(brain):
    manifest = export_tool_manifest(brain.tools)
    assert "tools" in manifest and len(manifest["tools"]) >= 25
    tool = next(t for t in manifest["tools"] if t["name"] == "read_file")
    assert tool["inputSchema"]["type"] == "object"
    assert "path" in tool["inputSchema"]["properties"]
    assert tool["x-jarvis"]["permission"] == "SAFE_READ"


def test_mcp_manifest_flags_approval_tools(brain):
    manifest = export_tool_manifest(brain.tools)
    click = next(t for t in manifest["tools"] if t["name"] == "browser_click_after_approval")
    assert click["x-jarvis"]["requires_approval"] is True


# --- API endpoints ---
@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c


def test_api_evaluations_and_mcp_and_plugins(client):
    assert client.get("/api/evaluations").status_code == 200
    assert "tools" in client.get("/api/mcp/manifest").json()
    assert "plugins" in client.get("/api/plugins").json()


def test_api_dataset_export(client):
    client.post("/api/chat", json={"message": "hello"})
    r = client.post("/api/dataset/export", json={"system": "You are Jarvis."})
    assert r.status_code == 200
    assert r.json()["rows"] >= 1
    assert os.path.exists(r.json()["path"])
