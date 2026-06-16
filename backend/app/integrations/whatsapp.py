"""WhatsApp Cloud API integration (Phase 3).

OFFICIAL WhatsApp Business Cloud API only — no unofficial scraping/automation.
The payload builder is pure (tested); sending is approval-gated (NETWORK +
HIGH_RISK) and uses lazy httpx. Inbound webhook content is untrusted external
data and never issues commands.
"""
from __future__ import annotations


def build_text_message(to: str, body: str) -> dict:
    """Build a WhatsApp Cloud API text message payload."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }


def build_template_message(to: str, template: str, lang: str = "en_US") -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template, "language": {"code": lang}},
    }


class WhatsAppCloudClient:
    """Official Cloud API client. Sending requires an approved HIGH_RISK action."""

    def __init__(self, phone_number_id: str | None, access_token: str | None) -> None:
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.base_url = "https://graph.facebook.com/v18.0"

    def configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    async def send_text(self, to: str, body: str) -> dict:  # pragma: no cover - network
        if not self.configured():
            raise RuntimeError("WhatsApp Cloud API is not configured.")
        try:
            import httpx
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("httpx required for WhatsApp Cloud API.") from exc
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=build_text_message(to, body), headers=headers)
            resp.raise_for_status()
            return resp.json()
