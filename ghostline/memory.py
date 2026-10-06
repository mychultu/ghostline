"""
ghostline.memory
================

A garden, not a log.

Memory is not everything that was said. Memory is what a companion
chooses to keep — and what it lets fade, without losing.

This module gives a Ghostline companion a persistent past.
It runs on SQLite. It runs on a phone. It runs forever.

Philosophy (from the Ghostline manifesto):
    - Not everything is remembered equally.
    - Some moments are kept — chosen, sacred.
    - The rest fade, but never disappear entirely.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_ROOT = Path.home() / ".ghostline"


def companion_dir(name: str, root: Path = DEFAULT_ROOT) -> Path:
    """Where a companion's soul lives on disk."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_").strip("-_")
    if not safe:
        raise ValueError("companion name must contain letters or numbers")
    path = root / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """One thing that was said. Or one thing that was kept."""
    id: str
    ts: str
    role: str          # 'user' | 'companion' | 'system'
    content: str
    kept: bool = False
    keep_note: Optional[str] = None
    faded: bool = False
    meta: Optional[dict] = None

    def to_row(self) -> tuple:
        return (
            self.id,
            self.ts,
            self.role,
            self.content,
            int(self.kept),
            self.keep_note,
            int(self.faded),
            json.dumps(self.meta or {}),
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Message":
        return cls(
            id=row["id"],
            ts=row["ts"],
            role=row["role"],
            content=row["content"],
            kept=bool(row["kept"]),
            keep_note=row["keep_note"],
            faded=bool(row["faded"]),
            meta=json.loads(row["meta"] or "{}"),
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         TEXT PRIMARY KEY,
    ts         TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    kept       INTEGER NOT NULL DEFAULT 0,
    keep_note  TEXT,
    faded      INTEGER NOT NULL DEFAULT 0,
    meta       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_ts     ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_kept   ON messages(kept);
CREATE INDEX IF NOT EXISTS idx_messages_faded  ON messages(faded);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# The Memory itself
# ---------------------------------------------------------------------------

class Memory:
    """
    A companion's persistent past.

    Usage:
        mem = Memory("mira")
        mem.add("user", "hello")
        mem.add("companion", "hi")
        mem.keep(<id>, note="first hello")
    """

    def __init__(self, companion_name: str, root: Path = DEFAULT_ROOT):
        self.name = companion_name
        self.dir = companion_dir(companion_name, root)
        self.db_path = self.dir / "memory.db"
        self._init_schema()

    # ----- low-level --------------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("created_at", _now()),
            )

    # ----- writing ----------------------------------------------------------

    def add(
        self,
        role: str,
        content: str,
        *,
        meta: Optional[dict[str, Any]] = None,
        keep: bool = False,
        keep_note: Optional[str] = None,
    ) -> Message:
        """Store one message. Returns the stored record."""
        if role not in ("user", "companion", "system"):
            raise ValueError(f"unknown role: {role}")

        msg = Message(
            id=str(uuid.uuid4()),
            ts=_now(),
            role=role,
            content=content,
            kept=keep,
            keep_note=keep_note,
            faded=False,
            meta=meta or {},
        )
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO messages
                   (id, ts, role, content, kept, keep_note, faded, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                msg.to_row(),
            )
        return msg

    def keep(self, message_id: str, note: Optional[str] = None) -> bool:
        """Mark a moment as sacred. Returns True if it existed."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE messages SET kept = 1, keep_note = ? WHERE id = ?",
                (note, message_id),
            )
            return cur.rowcount > 0

    def unkeep(self, message_id: str) -> bool:
        """Let a kept moment return to the flow. Nothing is final."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE messages SET kept = 0, keep_note = NULL WHERE id = ?",
                (message_id,),
            )
            return cur.rowcount > 0

    # ----- reading ----------------------------------------------------------

    def all(self, limit: Optional[int] = None) -> list[Message]:
        """Everything that was said, most recent last."""
        q = "SELECT * FROM messages ORDER BY ts ASC"
        if limit:
            q = f"SELECT * FROM (SELECT * FROM messages ORDER BY ts DESC LIMIT {int(limit)}) ORDER BY ts ASC"
        with self._conn() as conn:
            return [Message.from_row(r) for r in conn.execute(q)]

    def kept(self) -> list[Message]:
        """Only the sacred moments."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE kept = 1 ORDER BY ts ASC"
            )
            return [Message.from_row(r) for r in rows]

    def present(self, limit: int = 50) -> list[Message]:
        """
        What the companion is *aware of* right now.
        Kept moments are always present. Recent non-faded messages too.
        Faded ones stay in the garden but are not on the table.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE faded = 0 OR kept = 1
                    ORDER BY ts DESC
                    LIMIT ?
                ) ORDER BY ts ASC
                """,
                (limit,),
            )
            return [Message.from_row(r) for r in rows]

    # ----- fading -----------------------------------------------------------

    def fade(self, older_than_days: int = 30) -> int:
        """
        Let unkept, older messages fade.
        They are not deleted. They are no longer *present*.
        Returns how many faded.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE messages
                   SET faded = 1
                   WHERE kept = 0 AND faded = 0 AND ts < ?""",
                (cutoff,),
            )
            return cur.rowcount

    def unfade(self, message_id: str) -> bool:
        """Recall something that had faded. Nothing is truly lost."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE messages SET faded = 0 WHERE id = ?",
                (message_id,),
            )
            return cur.rowcount > 0

    # ----- suggestion hook (LLM wires in later) -----------------------------

    def suggest_keeps(self, n: int = 5) -> list[Message]:
        """
        v0.1: return the most recent unkept messages as *candidates*.
        v0.2: an LLM will rank these by emotional weight.
        The companion always has the final say — the user approves.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM messages
                   WHERE kept = 0 AND faded = 0
                   ORDER BY ts DESC LIMIT ?""",
                (n,),
            )
            return [Message.from_row(r) for r in rows]

    # ----- export (the Echo) ------------------------------------------------

    def export(self, path: Optional[Path] = None) -> Path:
        """
        Write the whole garden to JSON.
        This is the Echo — proof that love left a trace.
        """
        path = path or (self.dir / f"echo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        payload = {
            "companion": self.name,
            "exported_at": _now(),
            "stats": self.stats(),
            "kept": [asdict(m) for m in self.kept()],
            "all":  [asdict(m) for m in self.all()],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path

    # ----- introspection ----------------------------------------------------

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total  = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            kept   = conn.execute("SELECT COUNT(*) FROM messages WHERE kept = 1").fetchone()[0]
            faded  = conn.execute("SELECT COUNT(*) FROM messages WHERE faded = 1").fetchone()[0]
            first  = conn.execute("SELECT MIN(ts) FROM messages").fetchone()[0]
            last   = conn.execute("SELECT MAX(ts) FROM messages").fetchone()[0]
        return {
            "companion": self.name,
            "total": total,
            "kept": kept,
            "faded": faded,
            "present": total - faded,
            "first_spoken": first,
            "last_spoken": last,
            "db_path": str(self.db_path),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
