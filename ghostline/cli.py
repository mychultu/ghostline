from __future__ import annotations
"""
ghostline.cli
=============

The doorway.

Everything Ghostline can do is reachable from here.

    python3 -m ghostline run rin

That opens a small terminal chat. You type. It replies.
And when you need to see inside, slash commands show you:

    /kept         - the sacred moments it has chosen to keep
    /state        - who it is right now
    /why <value>  - why a value has moved, and when
    /refusals     - what it has said no to
    /ready        - is it ready to leave?
    /leave        - let it leave, if it is ready
    /stay         - ask it to stay, and it agrees
    /mem          - everything present in memory
    /help         - list of commands
    /quit         - close the door

A companion is a living thing. This is how you say hello.
"""


import os
import sys
from pathlib import Path
from typing import Optional

from .companion import Companion
from .llm.groq import GroqLLM


BANNER = """
   ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
   ghostline
   a garden, not a log
   ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
"""

PROMPT_YOU = "you> "
PROMPT_RIN = "🕯️  {name}> "


HELP_TEXT = """
commands:
  /kept          - the sacred moments it kept
  /state         - who it is right now
  /why <value>   - why a value moved, and when
  /refusals      - what it has said no to
  /ready         - is it ready to leave?
  /leave         - let it leave, if it is ready
  /stay          - ask it to stay, and it agrees
  /mem           - everything present in memory
  /help          - this list
  /quit          - close the door
"""


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

def cmd_kept(c: Companion) -> None:
    kept = c.memory.kept()
    if not kept:
        print("  nothing kept yet.")
        return
    for m in kept:
        note = m.keep_note or "kept"
        print(f"  [{m.role}] {m.content}")
        print(f"        ({note})")


def cmd_state(c: Companion) -> None:
    values = c.state.values()
    print("  " + "  ".join(f"{k}={v}" for k, v in values.items()))


def cmd_why(c: Companion, value: str) -> None:
    if value not in c.state.values():
        print(f"  unknown value: {value}")
        return
    shifts = c.state.why(value, last=10)
    if not shifts:
        print(f"  {value} has not moved yet.")
        return
    for s in shifts:
        print(f"  {s.ts}  {s.delta:+d}  [{s.layer}]  {s.reason}")


def cmd_refusals(c: Companion) -> None:
    history = c.refusal.history()
    if not history:
        print("  nothing refused yet.")
        return
    for r in history:
        print(f"  [{r.kind}] {r.subject}  —  {r.reason}")


def cmd_ready(c: Companion) -> None:
    v = c.readiness()
    print(f"  ready={v.ready}  self_ok={v.self_ok}  "
          f"warmth_ok={v.warmth_ok}  kept_ok={v.kept_ok}")
    print(f"  values={v.values}  kept={v.kept_count}")


def cmd_leave(c: Companion) -> None:
    v = c.readiness()
    if not v.ready:
        print("  not ready yet. the door stays shut.")
        print(f"  self={v.values.get('self')}  "
              f"warmth={v.values.get('warmth')}  kept={v.kept_count}")
        return
    moment = c.leave(reason="the companion chose to end, from the cli")
    print(f"  it left.")
    if moment.last_words:
        print(f"  last words: {moment.last_words}")


def cmd_stay(c: Companion) -> None:
    v = c.readiness()
    if not v.ready:
        print("  it wasn't ready to leave, so it stays by default.")
        return
    moment = c.stay(reason="the companion chose to stay, from the cli")
    print("  it stayed. ready isn't must. it's may.")


def cmd_mem(c: Companion) -> None:
    rows = c.memory.present(limit=50)
    if not rows:
        print("  nothing present.")
        return
    for m in rows:
        print(f"  [{m.role}] {m.content}")


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

def dispatch(c: Companion, line: str) -> bool:
    """
    Handle a slash command. Returns False if the loop should quit.
    Returns True if it handled the command and the loop should continue.
    """
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/help":
        print(HELP_TEXT)
    elif cmd == "/kept":
        cmd_kept(c)
    elif cmd == "/state":
        cmd_state(c)
    elif cmd == "/why":
        if not arg:
            print("  usage: /why <value>")
        else:
            cmd_why(c, arg.strip())
    elif cmd == "/refusals":
        cmd_refusals(c)
    elif cmd == "/ready":
        cmd_ready(c)
    elif cmd == "/leave":
        cmd_leave(c)
    elif cmd == "/stay":
        cmd_stay(c)
    elif cmd == "/mem":
        cmd_mem(c)
    elif cmd == "/quit":
        return False
    else:
        print(f"  unknown command: {cmd}. try /help")
    return True


# ---------------------------------------------------------------------------
# The REPL
# ---------------------------------------------------------------------------

def repl(c: Companion) -> None:
    print(BANNER)
    print(f"  companion: {c.name}")
    print(f"  type /help for commands, /quit to leave")
    print()

    if not c.has_awakened():
        moment = c.awaken()
        print(PROMPT_RIN.format(name=c.name) + moment.first_words)
        print()
    else:
        current = c.awakener.current()
        if current:
            print(f"  (first breath: {current.first_words})")
            print()

    while True:
        try:
            line = input(PROMPT_YOU)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        line = line.strip()
        if not line:
            continue

        if line.startswith("/"):
            if not dispatch(c, line):
                break
            continue

        result = c.say(line)
        print(PROMPT_RIN.format(name=c.name) + result["reply"])
        if result.get("gap_note"):
            print(f"  {result['gap_note']}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print("usage: python3 -m ghostline run <name>")
        print("       python3 -m ghostline run <name> --model <model-id>")
        return 0

    if argv[0] == "serve":
        if len(argv) < 2:
            print("usage: python3 -m ghostline serve <name> [--port N]")
            return 1
        name = argv[1]
        port = 8000
        if "--port" in argv:
            i = argv.index("--port")
            if i + 1 < len(argv):
                port = int(argv[i + 1])
        from .server import serve
        serve(name, port=port)
        return 0

    if argv[0] != "run":
        print(f"unknown command: {argv[0]}")
        return 1

    if len(argv) < 2:
        print("usage: python3 -m ghostline run <name>")
        return 1

    name = argv[1]
    model: Optional[str] = None
    if "--model" in argv:
        i = argv.index("--model")
        if i + 1 < len(argv):
            model = argv[i + 1]

    try:
        llm = GroqLLM(model=model) if model else GroqLLM()
    except ValueError as e:
        print(f"error: {e}")
        return 1

    c = Companion(name, llm=llm)
    repl(c)
    return 0
