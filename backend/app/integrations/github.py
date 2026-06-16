"""GitHub automation (Phase 3).

README/scaffold generation is pure (tested). Repo mutations (create repo, push,
open PR) are HIGH_RISK and approval-gated; the client is a lazy-httpx scaffold.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectInfo:
    name: str
    description: str = ""
    features: list[str] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    install_cmds: list[str] = field(default_factory=list)
    usage: str = ""
    license: str = "MIT"


def build_readme(info: ProjectInfo) -> str:
    """Render a clean README.md from project info (deterministic)."""
    lines = [f"# {info.name}", ""]
    if info.description:
        lines += [info.description, ""]
    if info.features:
        lines += ["## Features", ""]
        lines += [f"- {f}" for f in info.features]
        lines.append("")
    if info.tech_stack:
        lines += ["## Tech Stack", "", ", ".join(info.tech_stack), ""]
    if info.install_cmds:
        lines += ["## Installation", "", "```bash"]
        lines += info.install_cmds
        lines += ["```", ""]
    if info.usage:
        lines += ["## Usage", "", info.usage, ""]
    lines += ["## License", "", f"{info.license}", ""]
    return "\n".join(lines)


class GitHubClient:
    """Approval-gated GitHub REST client scaffold."""

    def __init__(self, token: str | None) -> None:
        self.token = token
        self.base_url = "https://api.github.com"

    def configured(self) -> bool:
        return bool(self.token)

    async def get_repo(self, owner: str, repo: str) -> dict:  # pragma: no cover - network
        if not self.configured():
            raise RuntimeError("GitHub token is not configured.")
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("httpx required for GitHub integration.") from exc
        headers = {"Authorization": f"Bearer {self.token}",
                   "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.base_url}/repos/{owner}/{repo}", headers=headers)
            resp.raise_for_status()
            return resp.json()
