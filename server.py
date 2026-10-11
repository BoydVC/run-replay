#!/usr/bin/env python3
"""Run Replay server — 127.0.0.1:4308. Serves live page + read-only /api/runs."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 4308))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)


def rd(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


def load_payload(refresh=False):
    path = os.path.join(HERE, "data", "runs.json")
    if refresh or not os.path.isfile(path):
        import collect

        return collect.main()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def data_js():
    p = os.path.join(HERE, "data", "runs.json")
    if os.path.isfile(p):
        return open(p, encoding="utf-8").read()
    return "null"


def page():
    html = rd("web/index.html")
    html = html.replace("/*__CSS__*/", rd("web/app.css"))
    html = html.replace("/*__DATA__*/ null /*__/DATA__*/", data_js())
    html = html.replace(
        "/*__APP__*/", rd("web/app.js").replace("</script", "<\\/script")
    )
    return html


class H(BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        try:
            if path in ("/", "/index.html", "/run-replay.html"):
                self.send(200, page(), "text/html; charset=utf-8")
            elif path == "/api/runs":
                # list without full event payloads for lightness
                payload = load_payload(refresh=False)
                light = {
                    "generatedAt": payload.get("generatedAt"),
                    "timezone": payload.get("timezone"),
                    "source": payload.get("source"),
                    "liveCount": payload.get("liveCount"),
                    "runs": [
                        {k: v for k, v in r.items() if k != "events"}
                        for r in (payload.get("runs") or [])
                    ],
                }
                self.send(200, json.dumps(light), "application/json")
            elif path.startswith("/api/runs/"):
                rid = path[len("/api/runs/") :].strip("/")
                payload = load_payload(refresh=False)
                for r in payload.get("runs") or []:
                    if r.get("id") == rid:
                        self.send(200, json.dumps(r), "application/json")
                        return
                self.send(404, json.dumps({"error": "run not found"}), "application/json")
            elif path == "/api/refresh":
                payload = load_payload(refresh=True)
                self.send(
                    200,
                    json.dumps(
                        {
                            "ok": True,
                            "liveCount": payload.get("liveCount"),
                            "runs": len(payload.get("runs") or []),
                        }
                    ),
                    "application/json",
                )
            elif path == "/health":
                self.send(
                    200,
                    json.dumps({"ok": True, "port": PORT, "app": "run-replay"}),
                    "application/json",
                )
            else:
                self.send(404, "not found", "text/plain")
        except Exception as ex:
            self.send(500, f"error: {ex}", "text/plain")

    def log_message(self, fmt, *args):
        print(f"[run-replay] {args[0]}")


if __name__ == "__main__":
    # ensure snapshot exists
    if not os.path.isfile(os.path.join(HERE, "data", "runs.json")):
        import collect

        collect.main()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Run Replay http://127.0.0.1:{PORT}/")
    httpd.serve_forever()
