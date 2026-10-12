"""Finds what to play for play_video: the first YouTube video for the user's words, read from
YouTube's own results page (no API key). The device then just opens it: the YouTube app on a
phone, BEKHI's browser window on the computer."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

log = logging.getLogger(__name__)

RESULTS_URL = "https://www.youtube.com/results?search_query={q}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept-Language": "mn,en;q=0.8",
}
# The first ordinary video in the results (Shorts and ads use other renderers), and its title.
FIRST_VIDEO = re.compile(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":("(?:[^"\\]|\\.)*")', re.S)


def first_video(html: str) -> tuple[str, str] | None:
    m = FIRST_VIDEO.search(html)
    if not m:
        return None
    try:
        title = json.loads(m.group(2))
    except ValueError:
        title = ""
    return f"https://www.youtube.com/watch?v={m.group(1)}", title


async def fill_video(args: dict[str, Any], http: httpx.AsyncClient) -> None:
    """Sets url and title on play_video's arguments. If YouTube cannot be read, the search page
    for the words is opened instead, and the reply names no song."""
    search = RESULTS_URL.format(q=quote_plus(args["query"]))
    try:
        r = await http.get(search, headers=HEADERS, timeout=8, follow_redirects=True)
        r.raise_for_status()
        found = first_video(r.text)
    except httpx.HTTPError as e:
        log.warning("youtube search failed: %s", type(e).__name__)
        found = None
    if found:
        args["url"], args["title"] = found[0], found[1][:200]
    else:
        args["url"] = search
