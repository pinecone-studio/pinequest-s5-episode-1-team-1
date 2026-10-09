@echo off
rem BEKHI's PC agent: runs this PC's actions (reminders, alarms, notes, apps, volume) for the
rem BEKHI web app at https://bekhi.pages.dev. Keep this window open while you use BEKHI.
cd /d "%~dp0"
if not exist .venv (
  set UV_LINK_MODE=copy
  uv sync --frozen --no-dev || exit /b 1
)
rem The base interpreter with the project's packages: Windows Smart App Control can block the
rem launchers inside .venv\Scripts, but not uv's own Python.
for /f "delims=" %%p in ('uv python find --system 3.12') do set "BEKHI_PY=%%p"
set "PYTHONPATH=%~dp0src;%~dp0.venv\Lib\site-packages"
"%BEKHI_PY%" -m bekhi_api.agent
