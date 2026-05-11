"""
Optional web-search retrieval skill for the tutor agent.

The tool uses Tavily's HTTP API directly so the project does not need another
Python SDK dependency. It is only meant as a fallback when local course
retrieval finds no useful context.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass
class WebSearchResult:
    """One external web result returned by the web-search skill."""

    title: str
    url: str
    content: str
    score: float


def search_web(query: str, max_results: int = 3) -> tuple[list[WebSearchResult], str | None]:
    """
    Search the web for external context.

    Returns a pair of (results, reason). The reason is populated when the search
    was skipped or failed, so the main loop can explain what happened.
    """

    if not _web_search_enabled():
        return [], "web search is disabled"

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return [], "TAVILY_API_KEY is not set"

    payload = {
        "query": query,
        "search_depth": os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    request = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore")
        return [], f"web search failed with HTTP {error.code}: {details}"
    except urllib.error.URLError as error:
        return [], f"web search failed: {error}"

    results = []
    for item in data.get("results", []):
        results.append(
            WebSearchResult(
                title=item.get("title", "Untitled result"),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=float(item.get("score", 0.0) or 0.0),
            )
        )

    if not results:
        return [], "web search returned no results"

    return results, None


def format_web_results_for_prompt(results: list[WebSearchResult]) -> str:
    """Render external web results into a prompt-friendly context block."""

    parts = []
    for index, result in enumerate(results, start=1):
        parts.append(
            f"[W{index}] External source: {result.title}\n"
            f"URL: {result.url}\n"
            f"Score: {result.score:.4f}\n"
            f"{result.content}"
        )
    return "\n\n".join(parts)


def _web_search_enabled() -> bool:
    configured = os.getenv("WEB_SEARCH_ENABLED")
    if configured is None:
        return bool(os.getenv("TAVILY_API_KEY"))

    return configured.strip().lower() not in FALSE_VALUES
