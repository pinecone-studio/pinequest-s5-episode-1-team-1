"""BEKHI's PC agent: this API on 127.0.0.1, for the PC's own actions while the user talks to BEKHI
in the cloud (https://bekhi.pages.dev).

    bekhi-agent.cmd                    (Windows, from apps/api)
    python -m bekhi_api.agent          (or: uv run python -m bekhi_api.agent)

The web app sends the PC's actions here: reminders, alarms and timers as Windows toasts, notes,
opening apps and folders, the volume and the lock screen (desktop.py). Alarms and timers set on
the user's other devices are pulled from the cloud API and ring here too. Only this PC can ask
(desktop actions accept local requests only); no API keys are needed.
"""

from __future__ import annotations

import os

import uvicorn

from . import config  # noqa: F401  (loads apps/api/.env first, so its settings are kept)

CLOUD_API = "https://bekhi-api.onrender.com"
CLOUD_WEB = "https://bekhi.pages.dev"
PORT = 8000  # where the web app looks for the agent (apps/mobile connect.ts)


def main() -> None:
    os.environ.setdefault("DESKTOP_ACTIONS", "true")
    os.environ.setdefault("SYNC_API_URL", CLOUD_API)
    origins = [o for o in (os.getenv("CORS_ORIGINS") or "").split(",") if o.strip()]
    os.environ["CORS_ORIGINS"] = ",".join(dict.fromkeys([*origins, CLOUD_WEB, "http://localhost:8081"]))
    print(f"BEKHI agent: this PC's actions for {CLOUD_WEB}. Keep this window open; Ctrl+C stops it.")
    uvicorn.run("bekhi_api.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
