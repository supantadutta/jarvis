"""CSV data-analysis tool (stdlib-only, guard-gated SAFE_READ)."""
from __future__ import annotations

import pytest

from app.security.permissions import Decision
from app.tools.base import ToolContext


def _ctx(brain):
    return ToolContext(settings=brain.settings, workspace_root=brain.settings.workspace_root,
                       services=brain.service_bundle(), agent_key="data")


@pytest.mark.asyncio
async def test_analyze_csv_summarizes(brain):
    ctx = _ctx(brain)
    csv_content = "name,age,score\nalice,30,9.5\nbob,25,8.0\ncarol,35,7.5\n"
    await brain.executor.execute("write_file", {"path": "data.csv", "content": csv_content}, ctx)
    out = await brain.executor.execute("analyze_csv", {"path": "data.csv"}, ctx)
    assert out.decision == Decision.AUTO_ALLOW and out.result.ok
    res = out.result.output
    assert res["rows"] == 3
    assert res["columns"] == ["name", "age", "score"]
    assert res["stats"]["age"]["type"] == "numeric"
    assert res["stats"]["age"]["min"] == 25.0 and res["stats"]["age"]["max"] == 35.0
    assert res["stats"]["age"]["mean"] == 30.0
    assert res["stats"]["name"]["type"] == "text"


@pytest.mark.asyncio
async def test_analyze_csv_outside_workspace_denied(brain):
    out = await brain.executor.execute("analyze_csv", {"path": "/etc/passwd"}, _ctx(brain))
    assert out.decision == Decision.DENY


@pytest.mark.asyncio
async def test_analyze_csv_missing_file(brain):
    out = await brain.executor.execute("analyze_csv", {"path": "nope.csv"}, _ctx(brain))
    assert not out.result.ok
