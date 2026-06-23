"""Real web access + autonomous learning tools.

These actually use the internet (httpx) when the host has network access. They
are NETWORK_ACCESS (so PRIVATE_MODE blocks them, and policy may require
approval). All fetched content is treated as UNTRUSTED: wrapped + injection
scanned before it can reach a model.

`learn_topic` is the self-learning loop: search → fetch → summarize with the
model → store into memory (RAG), so the assistant builds its own knowledge from
the web over time.
"""
from __future__ import annotations

import re

from app.security.permissions import PermissionLevel as P
from app.security.permissions import RiskLevel as R
from app.security.prompt_injection import scan_for_injection, wrap_untrusted
from app.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(html: str) -> str:
    """Strip scripts/styles/tags to readable text (no external dep)."""
    text = _TAG.sub(" ", html)
    text = _HTML.sub(" ", text)
    # Unescape a few common entities.
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&nbsp;", " ")):
        text = text.replace(a, b)
    return _WS.sub(" ", text).strip()


def _client(timeout: float = 20.0):
    import httpx

    return httpx.Client(
        timeout=timeout, follow_redirects=True,
        headers={"User-Agent": "JarvisBot/1.0 (+local-assistant)"},
    )


def do_fetch(url: str, max_chars: int = 20000) -> str:
    """Fetch a URL and return readable text. Shared by the tool + the learner;
    tests monkeypatch this to avoid real network."""
    with _client() as client:
        resp = client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        text = html_to_text(resp.text) if "html" in ctype else resp.text
    return text[:max_chars]


def do_search(query: str, *, search_url: str | None = None, limit: int = 6) -> list[dict]:
    """Search the web; shared by the tool + the learner. Tests monkeypatch this."""
    with _client() as client:
        if search_url:
            resp = client.get(search_url, params={"q": query, "format": "json"})
            resp.raise_for_status()
            return [
                {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content", "")}
                for r in resp.json().get("results", [])[:limit]
            ]
        resp = client.get("https://duckduckgo.com/html/", params={"q": query})
        resp.raise_for_status()
        return _parse_ddg(resp.text)[:limit]


async def _web_fetch(ctx: ToolContext, args: dict) -> ToolResult:
    url = args.get("url", "")
    if not url.startswith(("http://", "https://")):
        return ToolResult(ok=False, error="URL must start with http:// or https://")
    try:
        text = do_fetch(url, args.get("max_chars", 20000))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"fetch failed: {exc}")
    scan = scan_for_injection(text)
    return ToolResult(
        ok=True,
        output=wrap_untrusted(text, source=f"web:{url}"),
        summary=f"fetched {len(text)} chars from {url}"
        + (" [injection-flagged]" if scan.flagged else ""),
        injection_flagged=scan.flagged,
    )


async def _web_search(ctx: ToolContext, args: dict) -> ToolResult:
    """Search the web. Uses a configurable SearXNG/JSON endpoint if set
    (SEARCH_API_URL), else DuckDuckGo's HTML endpoint. Returns titles + links."""
    query = args.get("query", "")
    if not query.strip():
        return ToolResult(ok=False, error="empty query")
    search_url = getattr(ctx.settings, "search_api_url", None)
    try:
        results = do_search(query, search_url=search_url, limit=args.get("limit", 6))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"search failed: {exc}")
    return ToolResult(ok=True, output={"query": query, "results": results},
                      summary=f"{len(results)} results for '{query}'")


_DDG = re.compile(r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _parse_ddg(html: str) -> list[dict]:
    out = []
    for href, title in _DDG.findall(html):
        out.append({"title": html_to_text(title), "url": href, "snippet": ""})
    return out


async def _learn_topic(ctx: ToolContext, args: dict) -> ToolResult:
    """Autonomous research: search the web, fetch top pages, summarize with the
    configured model, and store the summary into memory (RAG). The assistant
    teaches itself about `topic` and remembers it for future tasks."""
    topic = args.get("topic", "")
    if not topic.strip():
        return ToolResult(ok=False, error="empty topic")
    learner = ctx.services.get("learner")
    if learner is None:
        return ToolResult(ok=False, error="learner service unavailable")
    try:
        result = await learner.learn(topic, max_sources=args.get("max_sources", 3))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"learning failed: {exc}")
    return ToolResult(ok=True, output=result,
                      summary=f"learned '{topic}' from {result.get('sources_used', 0)} sources")


def register_web_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="web_fetch", description="Fetch a web page and return readable text (untrusted).",
        permission=P.NETWORK_ACCESS, risk=R.LOW, func=_web_fetch, domain_arg="domain",
        input_schema={"url": "str", "max_chars": "int?"}))
    registry.register(ToolSpec(
        name="web_search", description="Search the web and return titles + links.",
        permission=P.NETWORK_ACCESS, risk=R.LOW, func=_web_search,
        input_schema={"query": "str", "limit": "int?"}))
    registry.register(ToolSpec(
        name="learn_topic",
        description="Autonomously research a topic from the web and store it in memory.",
        permission=P.NETWORK_ACCESS, risk=R.MEDIUM, func=_learn_topic,
        input_schema={"topic": "str", "max_sources": "int?"}))
