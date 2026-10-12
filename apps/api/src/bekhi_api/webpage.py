"""Reads a public web page for the agent (read_webpage): its title and readable text, which the
model answers from ("энэ сайтад юу бичсэн байна"). Only public https addresses are fetched, never
this machine or its network, also after redirects."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from .models import ActionResult

log = logging.getLogger(__name__)

MAX_BYTES = 3_000_000
MAX_TEXT = 8_000
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept-Language": "mn,en;q=0.8",
}
BLOCKS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer"}
HIDDEN = {"script", "style", "noscript", "svg", "template", "iframe"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._hidden = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in HIDDEN:
            self._hidden += 1
        elif tag == "title":
            self._in_title = True
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in HIDDEN and self._hidden:
            self._hidden -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._hidden:
            self.parts.append(data)


def page_text(markup: str) -> tuple[str, str]:
    """(title, readable text) of an HTML page."""
    parser = _Text()
    parser.feed(markup)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return re.sub(r"\s+", " ", parser.title).strip(), text


async def _public(host: str | None) -> bool:
    if not host:
        return False
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, 443)
    except OSError:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def _fail(action_id: str, code: str) -> ActionResult:
    return ActionResult(action_id=action_id, tool="read_webpage", status="failed", executed_via="backend",
                        error_code=code, data=None)


async def read_webpage(action_id: str, args: dict[str, Any], http: httpx.AsyncClient) -> ActionResult:
    url = str(args["url"])
    for _ in range(5):  # follow redirects by hand, checking each address
        if urlparse(url).scheme != "https" or not await _public(urlparse(url).hostname):
            return _fail(action_id, "URL_NOT_ALLOWED")
        try:
            r = await http.get(url, headers=HEADERS, timeout=10, follow_redirects=False)
        except httpx.HTTPError as e:
            log.warning("read_webpage failed: %s", type(e).__name__)
            return _fail(action_id, "PAGE_UNREACHABLE")
        if r.is_redirect and r.headers.get("location"):
            url = str(r.url.join(r.headers["location"]))
            continue
        break
    else:
        return _fail(action_id, "PAGE_UNREACHABLE")
    if r.status_code >= 400:
        return _fail(action_id, "PAGE_UNREACHABLE")
    kind = r.headers.get("content-type", "")
    if "html" not in kind and "text" not in kind:
        return _fail(action_id, "PAGE_NOT_TEXT")
    title, text = page_text(r.text[:MAX_BYTES]) if "html" in kind else ("", r.text[:MAX_BYTES])
    return ActionResult(
        action_id=action_id, tool="read_webpage", status="succeeded", executed_via="backend", error_code=None,
        data={"url": url, "title": title, "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT,
              "summary_mn": f"'{title or url}' хуудсыг уншлаа."},
    )
