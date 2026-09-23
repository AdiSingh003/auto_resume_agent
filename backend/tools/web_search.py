"""Web Search tool — Tavily when an API key is configured, DuckDuckGo otherwise."""

import asyncio
import logging

logger = logging.getLogger(__name__)

MAX_SNIPPET_CHARS = 600


def _snippet(title: str, body: str) -> str:
    # Collapse whitespace so each result is a single paragraph (results are "\n\n"-separated).
    return f"[{' '.join((title or '').split())}] {' '.join((body or '').split())[:MAX_SNIPPET_CHARS]}"


def _tavily_search(api_key: str, job_title: str, company_name: str) -> list[str]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    query = f"{job_title} job requirements skills typical responsibilities"
    if company_name:
        query += f" at {company_name} company culture engineering tech stack"

    response = client.search(query, search_depth="basic", max_results=4)
    return [_snippet(r.get("title", ""), r.get("content", "")) for r in response.get("results", [])]


def _duckduckgo_search(job_title: str, company_name: str) -> list[str]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    results_text = []
    with DDGS() as ddgs:
        query = f"{job_title} job requirements skills typical responsibilities"
        for r in ddgs.text(query, max_results=3):
            results_text.append(_snippet(r.get("title", ""), r.get("body", "")))

        if company_name:
            query = f"{company_name} company culture engineering tech stack"
            for r in ddgs.text(query, max_results=2):
                results_text.append(_snippet(r.get("title", ""), r.get("body", "")))
    return results_text


async def search_role_info(job_title: str, company_name: str = "") -> str:
    """Search for role and company information. Returns "\\n\\n"-separated result snippets."""
    from backend.config import settings

    # Both clients are synchronous; run them off the event loop so WebSocket traffic keeps flowing.
    if settings.tavily_api_key:
        try:
            results = await asyncio.to_thread(_tavily_search, settings.tavily_api_key, job_title, company_name)
            if results:
                return "\n\n".join(results)
        except Exception as e:
            logger.warning("Tavily search failed, falling back to DuckDuckGo: %s", e)

    try:
        results = await asyncio.to_thread(_duckduckgo_search, job_title, company_name)
        return "\n\n".join(results)
    except Exception as e:
        logger.warning("Web search failed: %s", e)
        return ""
