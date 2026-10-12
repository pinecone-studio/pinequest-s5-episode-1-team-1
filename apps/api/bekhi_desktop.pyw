"""Starts BEKHI on this computer. The desktop shortcut (install-desktop.ps1) runs this file with uv's
pythonw.exe, so there is no console window; the project's packages come from .venv."""

import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path[:0] = [str(here / "src"), str(here / ".venv" / "Lib" / "site-packages")]

from bekhi_api.desktop_app import main  # noqa: E402

main()
