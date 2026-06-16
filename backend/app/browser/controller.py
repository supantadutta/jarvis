"""Playwright browser controller (Phase 2).

Read actions (open/get_text/screenshot) are exposed here; the *permission* and
*approval* decisions are made by the Permission Guard before any of this runs.
Playwright is imported lazily so the backend boots and tests run without it.

The domain-allowlist and URL helpers are pure and unit-tested; live navigation
is integration-only.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.tools.base import ToolResult


def domain_of(url: str) -> str:
    """Return the lowercased hostname of a URL (no port)."""
    netloc = urlparse(url if "://" in url else f"//{url}", scheme="http").netloc
    host = netloc.split("@")[-1].split(":")[0]
    return host.lower()


def is_domain_allowed(url: str, allowed: list[str]) -> bool:
    """Exact host or subdomain match against the allowlist."""
    host = domain_of(url)
    if not host or not allowed:
        return False
    for a in allowed:
        a = a.lower().strip()
        if host == a or host.endswith("." + a):
            return True
    return False


class BrowserController:
    """Persistent-profile, domain-allowlisted browser. Headed by default so a
    human can solve MFA/CAPTCHA; the controller never solves them itself."""

    def __init__(
        self,
        allowed_domains: list[str],
        *,
        headless: bool = False,
        storage_state: str | None = None,
        screenshots_dir: str = "data/screenshots",
    ) -> None:
        self.allowed_domains = allowed_domains
        self.headless = headless
        self.storage_state = storage_state
        self.screenshots_dir = screenshots_dir
        self._pw = None
        self._browser = None
        self._context = None

    async def _ensure(self):  # pragma: no cover - needs Playwright + browsers
        if self._context is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError(
                "Playwright not installed. `pip install playwright && playwright install chromium`."
            ) from exc
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        kwargs = {}
        if self.storage_state:
            kwargs["storage_state"] = self.storage_state
        self._context = await self._browser.new_context(**kwargs)

    async def get_text(self, url: str, domain: str | None = None) -> ToolResult:
        if not is_domain_allowed(url, self.allowed_domains):
            return ToolResult(
                ok=False,
                error=f"Domain '{domain or domain_of(url)}' not in browser allowlist.",
                summary="domain blocked",
            )
        try:  # pragma: no cover - integration
            await self._ensure()
            page = await self._context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            text = await page.inner_text("body")
            await page.close()
            from app.security.prompt_injection import wrap_untrusted

            return ToolResult(
                ok=True,
                output=wrap_untrusted(text[:200_000], source=f"web:{domain_of(url)}"),
                summary=f"read {len(text)} chars from {domain_of(url)}",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=str(exc))

    async def save_session(self, profile: str) -> str | None:  # pragma: no cover - integration
        """Persist the current context's storage_state (cookies/localStorage)."""
        if self._context is None:
            return None
        state = await self._context.storage_state()
        return state if isinstance(state, dict) else None

    async def close(self) -> None:  # pragma: no cover
        for closer in (self._context, self._browser):
            if closer:
                await closer.close()
        if self._pw:
            await self._pw.stop()
        self._context = self._browser = self._pw = None


class SessionStore:
    """Encrypts Playwright `storage_state` at rest via a vault backend, so
    'log in once, reuse session' never persists cookies in plaintext. The DB
    only holds a `storage_state_ref` pointer (see BrowserProfile)."""

    def __init__(self, vault) -> None:
        self.vault = vault

    @staticmethod
    def _ref(profile: str) -> str:
        return f"browser_session:{profile}"

    def save(self, profile: str, storage_state: dict) -> str:
        import json

        ref = self._ref(profile)
        self.vault.set(ref, json.dumps(storage_state))
        return ref

    def load(self, profile: str) -> dict | None:
        import json

        raw = self.vault.get(self._ref(profile))
        return json.loads(raw) if raw else None

    def delete(self, profile: str) -> None:
        self.vault.delete(self._ref(profile))
