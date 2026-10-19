#!/usr/bin/env bash
# Ein-Klick-Start (macOS/Linux): installiert beim ersten Mal alles, simuliert einen kompletten Zyklus
# ohne API-Kosten und öffnet das Control-Center im Browser.  Aufruf:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Erster Start: richte Python-Umgebung ein …"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/pip install -q -e .
fi
if [ ! -d data/demo ]; then
  .venv/bin/aicompany demo
fi
TOKEN_FILE=data/demo/owner_token
.venv/bin/aicompany --mode dry_run --data-dir data/demo serve &
SERVER=$!
sleep 2
URL="http://127.0.0.1:8765/#token=$(cat "$TOKEN_FILE")"
echo "Control-Center: $URL   (Beenden mit Strg+C)"
(command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL") || true
wait $SERVER
