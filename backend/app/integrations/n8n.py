"""n8n integration (Phase 3): trigger n8n workflows via webhooks.

Pure payload building is tested; the HTTP trigger uses lazy httpx and is
NETWORK_ACCESS (approval per policy). JARVIS can hand off trusted automations to
n8n while keeping the approval/audit trail on its side.
"""
from __future__ import annotations


def build_webhook_payload(workflow: str, data: dict | None = None) -> dict:
    return {"source": "jarvis", "workflow": workflow, "data": data or {}}


class N8nClient:
    def __init__(self, base_url: str | None) -> None:
        self.base_url = (base_url or "").rstrip("/")

    def configured(self) -> bool:
        return bool(self.base_url)

    async def trigger(self, webhook_path: str, data: dict | None = None) -> dict:  # pragma: no cover
        if not self.configured():
            raise RuntimeError("n8n base URL is not configured.")
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("httpx required for n8n integration.") from exc
        url = f"{self.base_url}/webhook/{webhook_path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=build_webhook_payload(webhook_path, data))
            resp.raise_for_status()
            return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"status": resp.status_code}
