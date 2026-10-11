#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${RUN_REPLAY_PORT:-4308}"
CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
mkdir -p screenshots dist
if [[ ! -f dist/run-replay.html ]]; then python3 build.py; fi
if ! ss -ltn | grep -q "127.0.0.1:$PORT "; then
  nohup python3 server.py > /tmp/run-replay-$PORT.log 2>&1 &
  sleep 1
fi
shot() {
  local url="$1" out="$2" size="$3"; shift 3 || true
  local prof; prof="$(mktemp -d /tmp/rrshot.XXXX)"
  "$CHROME" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --run-all-compositor-stages-before-draw --virtual-time-budget=32000 \
    --window-size="$size" --user-data-dir="$prof" --screenshot="$out" "$@" "$url" >/dev/null 2>&1
  rm -rf "$prof"; echo "  $out ($(wc -c < "$out") bytes)"
}
U="http://127.0.0.1:$PORT"
# Best hero: replay of the DEMO escape-room crash (deep-link)
shot "file://$PWD/dist/run-replay.html#replay/demo-escape-room-crash-oct8" screenshots/00-best-home.png 1440,1100
shot "$U/#runs" screenshots/00-desktop-runs.png 1440,1000
shot "$U/#replay/demo-escape-room-crash-oct8" screenshots/01-replay-demo.png 1440,1100
shot "$U/#about" screenshots/02-about.png 1440,1000
shot "$U/#runs" screenshots/03-phone.png 390,844 --user-agent="Mozilla/5.0 (iPhone)"
echo "screenshots done"
