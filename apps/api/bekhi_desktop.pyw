"""Starts BEKHI on this computer. The Windows desktop shortcut (install-desktop.ps1) runs this file
with uv's pythonw.exe, so there is no console window; the project's packages come from .venv. On a
Mac, BEKHI.app (install-desktop.sh) runs it with .venv's own Python."""

import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path[:0] = [str(here / "src"), str(here / ".venv" / "Lib" / "site-packages")]

from bekhi_api.desktop_app import main  # noqa: E402

main()
