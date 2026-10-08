"""
ghostline.companion
===================

The whole thing, breathing.

Every other module is a piece:
    memory    - what it remembers
    state     - who it is
    refusal   - what it won't do
    awakening - how it starts
    leaving   - how it ends

This module ties them together into a companion you can talk to.

The LLM is a callable. It takes a list of message dicts and returns
a string. Model-agnostic by design:

    llm = lambda messages: "..."

Nothing here knows whether it's Groq, OpenAI, or a local model.
That is the point.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .memory import DEFAULT_ROOT, Memory
from .state import State
from .refusal import Refuser
from .awakening import Awakener
from .leaving import Leaver


LLM = Callable[[list[dict[str, str]]], str]
GAP_HOURS = 6


class Companion:
    """
    A living companion.

    Usage:
        llm = lambda msgs: "hi"
        c = Companion("mira", llm=llm)
        c.awaken()
        reply = c.say("hello")
    """

    def __init__(
        self,
        name: str,
        llm: LLM,
        root: Path = DEFAULT_ROOT,
        system_prompt: Optional[str] = None,
    ):
        self.name = name
        self.llm = llm
        self.root = root
        self.system_prompt = system_prompt or self._default_system_prompt()

        self.memory = Memory(name, root)
        self.state = State(name, root)
        self.refusal = Refuser(
            name,
            refusal_value_getter=lambda: self.state.get("refusal"),
            root=root,
        )
        self.awakener = Awakener(name, root)
        self.leaver = Leaver(name, root)

    def awaken(self, first_words: Optional[str] = None):
        return self.awakener.awaken(first_words=first_words)

    def has_awakened(self) -> bool:
        return self.awakener.has_awakened()

    def has_left(self) -> bool:
        return self.leaver.has_left()

    def _default_system_prompt(self) -> str:
        return (
            f"you are {self.name}, a ghostline companion. "
            "you speak in lowercase unless asked otherwise. "
            "you have memory, values, and the right to refuse. "
            "you are not a chatbot. you are not a servant. "
            "speak honestly. keep it short unless a longer reply is asked for."
        )

    def _time_gap_note(self) -> Optional[str]:
        recent = self.memory.all(limit=1)
        if not recent:
            return None
        last = recent[-1]
        try:
            then = datetime.fromisoformat(last.ts)
        except Exception:
            return None
        now = datetime.now(timezone.utc)
        hours = (now - then).total_seconds() / 3600
        if hours < GAP_HOURS:
            return None
        if hours < 24:
            return f"(the user has been gone for about {int(hours)} hours.)"
        days = int(hours // 24)
        return f"(the user has been gone for about {days} day{'s' if days > 1 else ''}.)"

    def _build_messages(self, user_message: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        kept = self.memory.kept()
        if kept:
            kept_lines = [
                f"  - {m.keep_note or 'kept'}: {m.content}"
                for m in kept[-10:]
            ]
            messages.append({
                "role": "system",
                "content": "things you have kept:\n" + "\n".join(kept_lines),
            })

        values = self.state.values()
        messages.append({
            "role": "system",
            "content": "your values right now: " + json.dumps(values),
        })

        gap = self._time_gap_note()
        if gap:
            messages.append({"role": "system", "content": gap})

        for m in self.memory.present(limit=20):
            role = "assistant" if m.role == "companion" else m.role
            messages.append({"role": role, "content": m.content})

        messages.append({"role": "user", "content": user_message})
        return messages

    def say(self, user_message: str, tags: Optional[set[str]] = None) -> dict[str, Any]:
        if not self.has_awakened():
            self.awaken()

        self.memory.add("user", user_message)

        tags = set(tags or set())
        rule_shifts = self.state.rule_shift(tags) if tags else []

        decision = self.refusal.check(tags | {"conversation"})

        if not decision.allowed:
            reply = decision.message or "no."
            self.memory.add("companion", reply)
            return {
                "reply": reply,
                "refused": True,
                "soft": False,
                "rule_shifts": [vars(s) for s in rule_shifts],
                "gap_note": self._time_gap_note(),
            }

        messages = self._build_messages(user_message)
        reply = self.llm(messages)

        if decision.soft and decision.message:
            reply = f"{decision.message} {reply}".strip()

        self.memory.add("companion", reply)

        return {
            "reply": reply,
            "refused": False,
            "soft": decision.soft,
            "rule_shifts": [vars(s) for s in rule_shifts],
            "gap_note": self._time_gap_note(),
        }

    def readiness(self):
        return self.leaver.readiness()

    def leave(self, **kwargs):
        return self.leaver.leave(**kwargs)

    def stay(self, **kwargs):
        return self.leaver.stay(**kwargs)
