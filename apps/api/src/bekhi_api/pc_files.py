"""The user's own files on this computer, for the agent (find_files, open_file, read_file).

Only the user's folders are searched (Downloads, Documents, Desktop, Pictures, Music, Videos/Movies),
only documents and media are listed, and a file can be opened or read only by the id find_files
gave it, so the model can never name a path, a program or a system file.
"""

from __future__ import annotations

import html
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import system
from .models import ActionResult

FOLDERS = ("downloads", "documents", "desktop", "pictures", "music", "videos")
FOLDER_MN = {"downloads": "Downloads", "documents": "Documents", "desktop": "Desktop", "pictures": "Pictures",
             "music": "Music", "videos": "Movies" if system.IS_MAC else "Videos"}
KINDS = {
    "pdf": {".pdf"},
    "document": {".doc", ".docx", ".odt", ".rtf", ".txt", ".md"},
    "spreadsheet": {".xls", ".xlsx", ".csv", ".ods"},
    "presentation": {".ppt", ".pptx", ".odp"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp"},
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm"},
    "audio": {".mp3", ".m4a", ".wav", ".flac", ".ogg"},
    "text": {".txt", ".md", ".csv", ".json", ".html", ".htm"},
}
OPENABLE = set().union(*KINDS.values())
READABLE = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".docx"}
SKIP_DIRS = {"node_modules", "appdata", "$recycle.bin", "__pycache__", ".git", ".venv"}
# Mac folders that are really one item (an app, the Photos or Music library): never searched inside.
PACKAGES = {".app", ".photoslibrary", ".musiclibrary", ".tvlibrary", ".imovielibrary", ".fcpbundle"}
MAX_DEPTH = 4
MAX_ENTRIES = 30_000  # stop a search in a huge folder rather than keep the user waiting
MAX_TEXT = 8_000  # characters of a file the model gets
MAX_IDS = 300

CYRILLIC = dict(zip("абвгдеёжзийклмноөпрстуүфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "i", "k", "l", "m", "n", "o", "o", "p", "r",
                     "s", "t", "u", "u", "f", "h", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya"]))

_found: dict[str, Path] = {}
_next_id = 0


def _latin(text: str) -> str:
    """A rough Latin key, so "тайлан" finds "Tailan_2026.pdf" (as contact names are matched)."""
    s = "".join(CYRILLIC.get(c, c) for c in text.casefold())
    return re.sub(r"[^a-z0-9]", "", s.replace("kh", "h").replace("y", "i").replace("o", "u"))


def _matches(name: str, words: list[str]) -> bool:
    plain, latin = name.casefold(), _latin(name)
    return all(w in plain or (_latin(w) and _latin(w) in latin) for w in words)


def _folder_path(folder: str) -> Path:
    return Path(system.controls().known_folder(folder))


def _walk(root: Path, exts: set[str], words: list[str], budget: list[int]) -> list[tuple[float, Path]]:
    found: list[tuple[float, Path]] = []
    stack = [(root, 0)]
    while stack and budget[0] > 0:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            budget[0] -= 1
            name = e.name
            if name.startswith((".", "~$")):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if (depth < MAX_DEPTH and name.casefold() not in SKIP_DIRS
                            and Path(name).suffix.casefold() not in PACKAGES):
                        stack.append((Path(e.path), depth + 1))
                elif Path(name).suffix.casefold() in exts and _matches(name, words):
                    found.append((e.stat().st_mtime, Path(e.path)))
            except OSError:
                continue
    return found


def _register(path: Path) -> str:
    global _next_id
    _next_id += 1
    file_id = f"f{_next_id}"
    _found[file_id] = path
    while len(_found) > MAX_IDS:
        _found.pop(next(iter(_found)))
    return file_id


def _ok(action_id: str, tool: str, summary: str, **data: Any) -> ActionResult:
    return ActionResult(action_id=action_id, tool=tool, status="succeeded", executed_via="backend", error_code=None,
                        data={**data, "summary_mn": summary})


def _fail(action_id: str, tool: str, code: str) -> ActionResult:
    return ActionResult(action_id=action_id, tool=tool, status="failed", executed_via="backend", error_code=code, data=None)


def find_files(action_id: str, args: dict[str, Any]) -> ActionResult:
    folders = [args["folder"]] if args.get("folder") else list(FOLDERS)
    kind = args.get("kind") or "any"
    exts = OPENABLE if kind == "any" else KINDS[kind]
    words = [w for w in re.split(r"\s+", str(args.get("query") or "").casefold()) if w]
    budget = [MAX_ENTRIES]
    hits: list[tuple[float, Path, str]] = []
    seen: set[Path] = set()
    for folder in folders:
        try:
            root = _folder_path(folder)
        except OSError:
            continue
        for mtime, path in _walk(root, exts, words, budget):
            if path not in seen:  # Desktop may sit inside Documents (OneDrive)
                seen.add(path)
                hits.append((mtime, path, folder))
    hits.sort(key=lambda h: h[0], reverse=True)
    files = [
        {
            "id": _register(path),
            "name": path.name,
            "folder": FOLDER_MN[folder],
            "modified": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            "size_kb": max(1, round(path.stat().st_size / 1024)) if path.exists() else None,
        }
        for mtime, path, folder in hits[: int(args.get("limit") or 5)]
    ]
    if not files:
        return _ok(action_id, "find_files", "Тийм файл олдсонгүй.", files=[])
    names = ", ".join(f["name"] for f in files[:3])
    return _ok(action_id, "find_files", f"{len(files)} файл олдлоо: {names}.", files=files)


def open_file(action_id: str, args: dict[str, Any]) -> ActionResult:
    path = _found.get(args["file"])
    if path is None or not path.is_file():
        return _fail(action_id, "open_file", "FILE_NOT_FOUND")
    if path.suffix.casefold() not in OPENABLE:
        return _fail(action_id, "open_file", "FILE_NOT_ALLOWED")
    system.open_path(path)
    return _ok(action_id, "open_file", f"За, '{path.name}'-ийг нээлээ.", name=path.name)


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def read_file(action_id: str, args: dict[str, Any]) -> ActionResult:
    path = _found.get(args["file"])
    if path is None or not path.is_file():
        return _fail(action_id, "read_file", "FILE_NOT_FOUND")
    ext = path.suffix.casefold()
    if ext not in READABLE:
        return _fail(action_id, "read_file", "FILE_UNREADABLE")
    try:
        if ext == ".docx":
            text = _docx_text(path)
        else:
            text = path.read_bytes()[:400_000].decode("utf-8", "replace")
            if ext in (".html", ".htm"):
                from .webpage import page_text

                text = page_text(text)[1]
    except (OSError, zipfile.BadZipFile, KeyError):
        return _fail(action_id, "read_file", "FILE_UNREADABLE")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return _ok(action_id, "read_file", f"'{path.name}'-ийг уншлаа.", name=path.name, text=text[:MAX_TEXT],
               truncated=len(text) > MAX_TEXT)


PC_TOOLS = {"find_files": find_files, "open_file": open_file, "read_file": read_file}
