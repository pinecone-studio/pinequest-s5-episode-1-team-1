"""Tavily web search (https://tavily.com): built for AI agents, 1,000 free searches a month,
no credit card. Results go to Gemini, which answers the user in Mongolian."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import SearchError

log = logging.getLogger(__name__)

URL = "https://api.tavily.com/search"
MAX_RESULTS = 5
SNIPPET_CHARS = 600
# Duud's users are in Mongolia: "Pinecone Academy" should find the one in Ulaanbaatar, not a namesake abroad.
COUNTRY = "mongolia"

# HTTP status -> web_search error code (compose.FAILED_BY_CODE has the Mongolian wording).
ERRORS = {
    401: "WEB_SEARCH_KEY_INVALID",
    429: "WEB_SEARCH_FAILED",  # rate limited: a later search can work
    432: "WEB_SEARCH_LIMIT",  # the plan's monthly credits are used up
    433: "WEB_SEARCH_LIMIT",
}


class TavilyWebSearch:
    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._key = api_key

    async def search(self, query: str) -> dict[str, Any]:
        r = await self._http.post(
            URL,
            headers={"Authorization": f"Bearer {self._key}"},
            # basic depth costs 1 credit; the short answer saves the model reading every page
            json={
                "query": query,
                "search_depth": "basic",
                "include_answer": "basic",
                "max_results": MAX_RESULTS,
                "country": COUNTRY,
            },
            timeout=20,
        )
        if r.status_code != 200:
            log.warning("tavily search failed: http=%s", r.status_code)  # never the query
            raise SearchError(ERRORS.get(r.status_code, "WEB_SEARCH_FAILED"))
        body = r.json()
        results = [
            {"title": x.get("title") or "", "url": x.get("url") or "", "content": (x.get("content") or "")[:SNIPPET_CHARS]}
            for x in (body.get("results") or [])[:MAX_RESULTS]
        ]
        return {
            "answer": (body.get("answer") or "").strip(),
            "results": results,
            "sources": [{"title": x["title"], "url": x["url"]} for x in results],
        }
