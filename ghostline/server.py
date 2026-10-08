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
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

from .companion import Companion
from .llm.groq import GroqLLM


UI_DIR = Path(__file__).parent / "ui"


def read_ui(filename: str) -> str:
    """Read a file from ghostline/ui/ and return its text."""
    return (UI_DIR / filename).read_text(encoding="utf-8")





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
            return self._html(read_ui("index.html"))

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
