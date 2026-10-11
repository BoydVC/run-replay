#!/usr/bin/env python3
"""Read-only collector: join routine runs + audit tool events into replay traces.

Writes ONLY data/runs.json inside this folder. Metadata only — no prompts,
full shell commands, secrets, or message bodies.
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = "/home/box/agent-data/agents"
ET = ZoneInfo("America/New_York")
MAX_RUNS = 80
MAX_EVENTS_PER_RUN = 120
SLACK_MS = 90_000  # join window pad after finishedAt

SERVER_LABELS = {
    "user-Gmail": "Gmail",
    "user-Gmail--miranda": "Gmail (Miranda)",
    "user-Google-calendar": "Calendar",
    "user-Google-drive": "Drive",
    "user-Notion": "Notion",
    "user-X": "X",
    "user-Slack": "Slack",
    "user-Composio": "Composio",
    "user-Finance-xai": "Finance",
    "user-Agentmail": "Agentmail",
    "user-Linear": "Linear",
    "cursor-github": "GitHub",
    "cursor-origin": "Origin",
    "x": "X public",
}

SAFE_PATH_RE = re.compile(
    r"(/workspace/tokenmax/[A-Za-z0-9._/-]+|/home/box/agent-data/agents/[a-f0-9-]+/(?:attachments|assets)/[A-Za-z0-9._/-]+)"
)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return default


def iso_ms(ms):
    if ms is None:
        return None
    try:
        n = float(ms)
        if n > 1e12:
            n /= 1000.0
        return datetime.fromtimestamp(n, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except Exception:
        return None


def et_label(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
        return dt.strftime("%a %b %-d · %-I:%M %p ET")
    except Exception:
        return iso


def bot_name(aid):
    prof = read_json(os.path.join(AGENTS, aid, "profile.json"), {}) or {}
    return prof.get("name") or prof.get("displayName") or aid[:8]


def sanitize_shell(cmd):
    """Return a short, non-sensitive shell summary — never the full command."""
    if not cmd:
        return "shell"
    s = str(cmd).strip()
    # drop obvious secret-ish fragments
    if re.search(r"(password|secret|token|api[_-]?key|Bearer\s)", s, re.I):
        return "shell (redacted)"
    first = s.split(None, 1)[0]
    first = os.path.basename(first)
    paths = SAFE_PATH_RE.findall(s)
    hint = ""
    if paths:
        # keep only basename of first safe path
        hint = " → " + os.path.basename(paths[0].rstrip("/"))[:40]
    return f"{first}{hint}"[:72]


def extract_file_hints(cmd):
    out = []
    if not cmd:
        return out
    if re.search(r"(password|secret|token|api[_-]?key)", str(cmd), re.I):
        return out
    for m in SAFE_PATH_RE.findall(str(cmd)):
        # only treat as write-ish if redirect / write verbs nearby
        if re.search(r"(>|>>|tee\b|cp\s|mv\s|install\b|touch\b|mkdir\b|cat\s*>)", str(cmd)):
            out.append(
                {
                    "path": m[:120],
                    "name": os.path.basename(m.rstrip("/"))[:64] or m[-40:],
                }
            )
    return out[:4]


def summarize_audit(d):
    t = d.get("type")
    ev = {
        "id": d.get("eventId") or d.get("toolCallId") or f"e-{d.get('ts')}",
        "ts": d.get("ts"),
        "kind": "tool",
        "type": t,
        "status": d.get("status") or "ok",
    }
    if d.get("durationMs") is not None:
        ev["ms"] = int(d["durationMs"])
    if t == "mcp_tool_call":
        srv = d.get("serverIdentifier") or ""
        tool = d.get("toolName") or ""
        short = tool[len(srv) + 1 :] if srv and tool.startswith(srv + "-") else tool
        ev["app"] = SERVER_LABELS.get(srv, srv.replace("user-", "") or "tool")
        ev["label"] = short[:56] or "mcp"
        ev["kind"] = "tool"
    elif t == "shell_command":
        ev["app"] = "Shell" if d.get("target") != "user_machine" else "Boyd's PC"
        ev["label"] = sanitize_shell(d.get("command"))
        ev["kind"] = "shell"
        hints = extract_file_hints(d.get("command"))
        if hints:
            ev["files"] = hints
    elif t == "browser_navigation":
        host = ""
        try:
            host = urlparse(d.get("url") or "").hostname or ""
        except Exception:
            pass
        ev["app"] = "Browser"
        ev["label"] = host[:60] or "navigate"
        ev["kind"] = "browser"
    elif t == "computer_use_session":
        ev["app"] = "Computer use"
        ev["label"] = "session"
        ev["kind"] = "computer"
    else:
        ev["app"] = t or "event"
        ev["label"] = t or "event"
    if ev.get("status") and ev["status"] != "ok":
        ev["kind"] = "error"
        ev["error"] = True
    return ev


def load_audit_index(aid):
    path = os.path.join(AGENTS, aid, "audit.jsonl")
    rows = []
    if not os.path.isfile(path):
        return rows
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts = d.get("ts")
                if not ts:
                    continue
                try:
                    ms = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
                except Exception:
                    continue
                rows.append((ms, d))
    except OSError:
        return []
    rows.sort(key=lambda x: x[0])
    return rows


def file_events_in_window(aid, start_ms, end_ms):
    """Attachments/assets touched during the run window (basename only)."""
    out = []
    for sub in ("attachments", "assets"):
        root = os.path.join(AGENTS, aid, sub)
        if not os.path.isdir(root):
            continue
        for dp, _dn, fnames in os.walk(root):
            for name in fnames:
                fp = os.path.join(dp, name)
                try:
                    m = os.path.getmtime(fp) * 1000
                    sz = os.path.getsize(fp)
                except OSError:
                    continue
                if start_ms <= m <= end_ms + SLACK_MS:
                    out.append(
                        {
                            "id": f"file-{int(m)}-{name[:20]}",
                            "ts": iso_ms(m),
                            "kind": "file",
                            "type": "file_write",
                            "app": "Files",
                            "label": name[:64],
                            "status": "ok",
                            "bytes": sz,
                            "ext": os.path.splitext(name)[1][:8].lower(),
                        }
                    )
            # shallow
            if dp.count(os.sep) - root.count(os.sep) > 2:
                break
    out.sort(key=lambda e: e.get("ts") or "")
    return out[:40]


def collect_runs():
    audit_cache = {}
    runs = []
    for runs_path in glob.glob(os.path.join(AGENTS, "*", "automations", "*", "runs.json")):
        aid = runs_path.split(os.sep)[-4]
        slug = runs_path.split(os.sep)[-2]
        auto = read_json(os.path.join(os.path.dirname(runs_path), "automation.json"), {}) or {}
        for r in read_json(runs_path, []) or []:
            started = r.get("startedAt")
            if not started:
                continue
            finished = r.get("finishedAt") or started
            status = r.get("status") or "unknown"
            if status == "ok":
                pass
            elif status in ("error", "failed", "fail"):
                status = "error"
            elif status in ("running", "in_progress"):
                status = "running"
            else:
                status = str(status)

            start_iso = iso_ms(started)
            end_iso = iso_ms(finished)
            duration_ms = None
            try:
                if finished and started and finished >= started:
                    duration_ms = int(finished - started)
            except Exception:
                pass

            if aid not in audit_cache:
                audit_cache[aid] = load_audit_index(aid)
            events = []
            # bookends
            events.append(
                {
                    "id": f"start-{r.get('id')}",
                    "ts": start_iso,
                    "kind": "start",
                    "type": "run_start",
                    "app": "Run",
                    "label": "run started",
                    "status": "ok",
                }
            )
            end_pad = (finished or started) + SLACK_MS
            for ms, d in audit_cache[aid]:
                if ms < started:
                    continue
                if ms > end_pad:
                    break
                events.append(summarize_audit(d))
                if len(events) >= MAX_EVENTS_PER_RUN - 2:
                    break

            # files from shell hints
            for ev in list(events):
                for fh in ev.get("files") or []:
                    events.append(
                        {
                            "id": f"hint-{ev['id']}-{fh['name']}",
                            "ts": ev.get("ts"),
                            "kind": "file",
                            "type": "file_hint",
                            "app": "Files",
                            "label": fh["name"],
                            "path": fh.get("path"),
                            "status": "ok",
                        }
                    )
                ev.pop("files", None)

            events.extend(file_events_in_window(aid, started, finished or started))

            events.append(
                {
                    "id": f"end-{r.get('id')}",
                    "ts": end_iso,
                    "kind": "end" if status != "error" else "error",
                    "type": "run_end",
                    "app": "Run",
                    "label": f"run {status}",
                    "status": status,
                    "error": status == "error",
                }
            )

            # sort + cap
            events.sort(key=lambda e: e.get("ts") or "")
            # dedupe by id
            seen = set()
            deduped = []
            for e in events:
                i = e.get("id")
                if i in seen:
                    continue
                seen.add(i)
                deduped.append(e)
            events = deduped[:MAX_EVENTS_PER_RUN]

            tool_n = sum(1 for e in events if e.get("kind") in ("tool", "shell", "browser", "computer"))
            err_n = sum(1 for e in events if e.get("error") or e.get("kind") == "error")
            file_n = sum(1 for e in events if e.get("kind") == "file")

            runs.append(
                {
                    "id": r.get("id") or f"{aid}-{started}",
                    "demo": False,
                    "botId": aid,
                    "bot": bot_name(aid),
                    "routine": auto.get("name") or slug,
                    "slug": slug,
                    "trigger": r.get("trigger") or "schedule",
                    "status": status,
                    "startedAt": start_iso,
                    "finishedAt": end_iso,
                    "startedLabel": et_label(start_iso),
                    "finishedLabel": et_label(end_iso),
                    "durationMs": duration_ms,
                    "requestId": r.get("requestId"),
                    "counts": {
                        "events": len(events),
                        "tools": tool_n,
                        "files": file_n,
                        "errors": err_n,
                    },
                    "events": events,
                    "sparse": tool_n < 2,
                }
            )

    runs.sort(key=lambda r: r.get("startedAt") or "", reverse=True)
    return runs[:MAX_RUNS]


def load_demo():
    path = os.path.join(HERE, "data", "demo-trace.json")
    return read_json(path, None)


def main():
    live = collect_runs()
    demo = load_demo()
    payload = {
        "generatedAt": datetime.now(ET).isoformat(timespec="seconds"),
        "timezone": "America/New_York",
        "source": "agent-data automations/*/runs.json + audit.jsonl (read-only)",
        "liveCount": len(live),
        "runs": ([demo] if demo else []) + live,
    }
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    out = os.path.join(HERE, "data", "runs.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(
        f"collected {len(live)} live runs"
        + (f" + demo '{demo.get('routine')}'" if demo else "")
        + f" → {out} ({os.path.getsize(out):,} bytes)"
    )
    return payload


if __name__ == "__main__":
    main()
