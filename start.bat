@echo off
REM Ein-Klick-Start (Windows): Doppelklick genügt. Installiert beim ersten Mal alles, simuliert einen
REM kompletten Zyklus ohne API-Kosten und öffnet das Control-Center im Browser.
cd /d "%~dp0"
if not exist .venv (
  echo Erster Start: richte Python-Umgebung ein ...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
  .venv\Scripts\pip install -q -e .
)
if not exist data\demo .venv\Scripts\aicompany demo
set /p TOKEN=<data\demo\owner_token
start "" "http://127.0.0.1:8765/#token=%TOKEN%"
.venv\Scripts\aicompany --mode dry_run --data-dir data\demo serve
