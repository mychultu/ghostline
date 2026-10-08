from __future__ import annotations
"""
ghostline.server
================

The front door.

A tiny HTTP server for talking to a companion from the browser.
Uses only the Python standard library. No Flask. No FastAPI.
Because Ghostline runs on a phone.

Usage:
    python3 -m ghostline serve rin
    # then open http://localhost:8000

Endpoints:
    GET  /          - the chat page
    POST /say       - send a message, get a reply
    GET  /state     - current values
    GET  /kept      - kept memories
    GET  /mem       - recent memory
    GET  /ready     - readiness verdict
    GET  /history   - full conversation
"""


import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

from .companion import Companion
from .llm.groq import GroqLLM


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ghostline</title>
<style>
  :root {
    --bg: #0a0a0f;
    --panel: #12121a;
    --border: #1e1e2a;
    --text: #d8d8e0;
    --dim: #6a6a7a;
    --warm: #e8b060;
    --user: #7ab8f5;
    --soft: #c070d0;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 14px;
    line-height: 1.55;
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }
  header .name { color: var(--warm); font-weight: bold; }
  header .dot  { color: var(--dim); }
  header .status { color: var(--dim); font-size: 12px; margin-left: auto; }
  #log {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .msg { display: flex; gap: 10px; }
  .msg .who { color: var(--dim); flex-shrink: 0; min-width: 60px; }
  .msg.user .who     { color: var(--user); }
  .msg.companion .who{ color: var(--warm); }
  .msg .body { white-space: pre-wrap; word-break: break-word; }
  .note { color: var(--dim); font-size: 12px; font-style: italic; }
  footer {
    border-top: 1px solid var(--border);
    padding: 10px 16px;
    display: flex;
    gap: 8px;
    flex-shrink: 0;
  }
  footer input {
    flex: 1;
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 12px;
    font: inherit;
    border-radius: 4px;
    outline: none;
  }
  footer input:focus { border-color: var(--warm); }
  footer button {
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--warm);
    padding: 10px 16px;
    font: inherit;
    border-radius: 4px;
    cursor: pointer;
  }
  footer button:hover { border-color: var(--warm); }
  .toolbar {
    display: flex;
    gap: 6px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
    flex-shrink: 0;
  }
.globe-field {
  height: 140px;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 120%, rgba(232,176,96,0.08), transparent 60%),
    linear-gradient(180deg, #0a0a0f 0%, #0d0d15 100%);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.globe {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #ffe0a0, #e8b060 40%, #8a5a20 100%);
  box-shadow:
    0 0 20px 4px rgba(232,176,96,0.5),
    0 0 60px 15px rgba(232,176,96,0.15);
  transition: transform 0.6s cubic-bezier(0.2, 0.9, 0.3, 1.2),
              box-shadow 0.6s ease,
              background 0.6s ease;
  transform: translateY(0) scale(1);
}
.globe.idle {
  animation: breathe 6s ease-in-out infinite;
}
.globe.thinking {
  transform: translateY(-14px) scale(0.92);
  background: radial-gradient(circle at 35% 30%, #c0c8e0, #6a6a8a 40%, #3a3a50 100%);
  box-shadow:
    0 0 16px 2px rgba(120,120,180,0.5),
    0 0 40px 10px rgba(120,120,180,0.15);
}
.globe.speaking {
  transform: translateY(-24px) scale(1.15);
  box-shadow:
    0 0 30px 8px rgba(232,176,96,0.7),
    0 0 90px 25px rgba(232,176,96,0.25);
}
.globe.warm {
  background: radial-gradient(circle at 35% 30%, #ffd0a0, #e89060 40%, #8a4020 100%);
}
.globe.cold {
  background: radial-gradient(circle at 35% 30%, #a0d0ff, #6080c0 40%, #203060 100%);
}
@keyframes breathe {
  0%, 100% { transform: translateY(0) scale(1); }
  50%      { transform: translateY(-4px) scale(1.04); }
}
  .toolbar button {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--dim);
    padding: 4px 10px;
    font: inherit;
    font-size: 12px;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
  }
  .toolbar button:hover { color: var(--warm); border-color: var(--warm); }
</style>
</head>
<body>
  <header>
    <span class="name">ghostline</span>
    <span class="dot">·</span>
    <span class="name" id="cname">companion</span>
    <span class="status" id="status">loading...</span>
  </header>
  <div class="globe-field">
    <div class="globe idle" id="globe"></div>
  </div>
  <div class="toolbar">
    <button onclick="cmd('/state')">state</button>
    <button onclick="cmd('/kept')">kept</button>
    <button onclick="cmd('/mem')">memory</button>
    <button onclick="cmd('/ready')">ready</button>
    <button onclick="cmd('/refusals')">refusals</button>
  </div>
  <div id="log"></div>
  <footer>
    <input id="input" placeholder="say something..." autocomplete="off" autofocus>
    <button onclick="send()">send</button>
  </footer>

<script>
const log = document.getElementById("log");
const input = document.getElementById("input");
const status = document.getElementById("status");
const globe = document.getElementById("globe");

function add(role, text, note) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "you" : role === "companion" ? "rin" : "·";
  const body = document.createElement("span");
  body.className = "body";
  body.textContent = text;
  div.appendChild(who);
  div.appendChild(body);
  log.appendChild(div);
  if (note) {
    const n = document.createElement("div");
    n.className = "note";
    n.textContent = "  " + note;
    log.appendChild(n);
  }
  log.scrollTop = log.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  if (text.startsWith("/")) { await cmd(text); return; }
  add("user", text);
  status.textContent = "thinking...";
pulse("thinking");
  try {
    const res = await fetch("/say", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    add("companion", data.reply, data.gap_note || null);
    status.textContent = data.soft ? "soft refusal" : "ready";
pulse("speaking", data.soft ? "cold" : "warm");
setTimeout(() => pulse("idle"), 1800);
  } catch (e) {
    add("companion", "[error] " + e.message);
    status.textContent = "error";
  }
}

async function cmd(c) {
  const res = await fetch(c.slice(1));
  const data = await res.json();
  add("system", JSON.stringify(data, null, 2));
}
function pulse(state, mood) {
  if (!globe) return;
  globe.className = "globe " + state;
  if (mood) globe.classList.add(mood);
}

input.addEventListener("keydown", e => { if (e.key === "Enter") send(); });

// load status + history on page load
(async () => {
  try {
    const r = await fetch("/status");
    const d = await r.json();
    document.getElementById("cname").textContent = d.companion;
    status.textContent = d.has_awakened ? "awake" : "not yet awake";
    if (d.first_words) add("companion", d.first_words);
  } catch (e) { status.textContent = "offline"; }

  try {
    const r = await fetch("/history");
    const d = await r.json();
    for (const m of d.messages || []) {
      add(m.role, m.content);
    }
  } catch (e) {}
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    companion: Companion = None  # injected by serve()

    def log_message(self, fmt, *args):
        # silence the default noisy logging
        pass

    def _json(self, data: Any, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str, code: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        c = self.companion

        if path == "/" or path == "/index.html":
            return self._html(PAGE)

        if path == "/status":
            current = c.awakener.current()
            return self._json({
                "companion": c.name,
                "has_awakened": c.has_awakened(),
                "first_words": current.first_words if current else None,
            })

        if path == "/state":
            return self._json(c.state.values())

        if path == "/kept":
            return self._json([
                {"role": m.role, "content": m.content, "note": m.keep_note}
                for m in c.memory.kept()
            ])

        if path == "/mem":
            return self._json([
                {"role": m.role, "content": m.content, "kept": m.kept}
                for m in c.memory.present(limit=50)
            ])

        if path == "/ready":
            v = c.readiness()
            return self._json({
                "ready": v.ready,
                "self_ok": v.self_ok,
                "warmth_ok": v.warmth_ok,
                "kept_ok": v.kept_ok,
                "values": v.values,
                "kept_count": v.kept_count,
            })

        if path == "/refusals":
            return self._json([
                {"kind": r.kind, "subject": r.subject, "reason": r.reason}
                for r in c.refusal.history()
            ])

        if path == "/history":
            return self._json({
                "messages": [
                    {"role": m.role, "content": m.content}
                    for m in c.memory.all()
                ]
            })

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/say":
            return self._json({"error": "not found"}, 404)

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._json({"error": "invalid json"}, 400)

        message = (payload.get("message") or "").strip()
        tags = set(payload.get("tags") or [])

        if not message:
            return self._json({"error": "empty message"}, 400)

        try:
            result = self.companion.say(message, tags=tags)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

        return self._json({
            "reply": result["reply"],
            "refused": result["refused"],
            "soft": result["soft"],
            "gap_note": result["gap_note"],
        })


# ---------------------------------------------------------------------------
# Server entry
# ---------------------------------------------------------------------------

def serve(
    name: str,
    llm: Optional[Any] = None,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """
    Start the server for one companion.
    The companion awakens on first connect if it hasn't yet.
    """
    if llm is None:
        llm = GroqLLM()

    c = Companion(name, llm=llm)
    Handler.companion = c

    print(f"  ghostline serving '{name}' on http://{host}:{port}")
    print(f"  open that url in your browser")
    print(f"  ctrl-c to stop")
    print()

    server = HTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("  server stopped.")
    finally:
        server.server_close()
