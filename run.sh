#!/usr/bin/env bash
# Run Replay: build offline snapshot, then serve on 127.0.0.1:4308.
#   ./run.sh           build + serve
#   ./run.sh --shots   build + screenshot + serve
set -euo pipefail
cd "$(dirname "$0")"
PORT=4308
python3 build.py
if [[ "${1:-}" == "--shots" ]]; then bash tests/screenshot.sh; fi
if ss -ltn | grep -q "127.0.0.1:$PORT "; then
  echo "already serving on http://127.0.0.1:$PORT/"
else
  nohup python3 server.py > /tmp/run-replay-$PORT.log 2>&1 &
  sleep 1
  echo "serving http://127.0.0.1:$PORT/ (pid $!)  ·  offline file: dist/run-replay.html"
fi
