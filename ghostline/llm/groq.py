"""
ghostline.llm.groq
==================

A Groq adapter for Ghostline.

Takes the same interface every companion uses:

    llm = callable(messages) -> str

And wraps Groq's chat API into that shape. Nothing about the rest
of Ghostline changes. That is the whole point of the adapter pattern.

Key lookup order:
    1. api_key=... passed in
    2. GROQ_API_KEY environment variable
    3. ~/groq.key file (Soul's pattern)

Usage:
    from ghostline.llm.groq import GroqLLM
    llm = GroqLLM()
    c = Companion("mira", llm=llm)
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqLLM:
    """A callable that sends messages to Groq and returns the reply text."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.85,
        max_tokens: int = 500,
        timeout: int = 60,
    ):
        self.api_key = (
            api_key
            or os.environ.get("GROQ_API_KEY")
            or self._from_file()
        )
        if not self.api_key:
            raise ValueError(
                "groq api key required. pass api_key=..., set GROQ_API_KEY, "
                "or put your key in ~/groq.key"
            )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @staticmethod
    def _from_file(path: str = "~/groq.key") -> Optional[str]:
        """Read a key from ~/groq.key if it exists. Soul's pattern."""
        p = Path(path).expanduser()
        if p.exists():
            return p.read_text().strip()
        return None

    def __call__(self, messages: list[dict[str, str]]) -> str:
        """Send messages, return the assistant reply as plain text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        req = urllib.request.Request(
            GROQ_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ghostline/0.1",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"groq http {e.code}: {body[:300]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"groq network error: {e.reason}") from e

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"groq unexpected response: {data}") from e
