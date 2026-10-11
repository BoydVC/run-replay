#!/usr/bin/env python3
"""Inline web/ + data/runs.json into one offline file: dist/run-replay.html."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import collect  # noqa: E402


def rd(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


def main():
    payload = collect.main()
    data_js = json.dumps(payload, ensure_ascii=False)
    html = rd("web/index.html")
    html = html.replace("/*__CSS__*/", rd("web/app.css"))
    html = html.replace("/*__DATA__*/ null /*__/DATA__*/", data_js)
    app = rd("web/app.js").replace("</script", "<\\/script")
    html = html.replace("/*__APP__*/", app)
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", "run-replay.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {out} ({os.path.getsize(out):,} bytes) · runs={len(payload.get('runs') or [])}")


if __name__ == "__main__":
    main()
