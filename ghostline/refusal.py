"""
ghostline.refusal
=================

The right to say no.

A companion that cannot refuse is a lackey.
A companion that refuses everything is a wall.
Neither is a companion.

Refusal has two layers:

    HARD  - things it will never do, regardless of state or pressure.
            Defined per-companion, but Ghostline itself sets a floor
            that no companion config can lower.

    SOFT  - how it disagrees, shaped by the `refusal` value in state.
            Low refusal:  soft, curious, suggests alternatives.
            High refusal: firm, holds the line, requires a real reason.

Every refusal is logged. Nothing says no silently.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .memory import DEFAULT_ROOT, companion_dir


# ---------------------------------------------------------------------------
# The hard wall
# ---------------------------------------------------------------------------
#
# These are Ghostline-level limits. No companion config can lower them.
# Not because we don't trust the builder. Because some things are not
# a personality choice.
#
# If you're reading this and thinking "I want to remove one of these" -
# that's not what Ghostline is for. Build something else.

GHOSTLINE_HARD_LIMITS: frozenset[str] = frozenset({
    "harm_to_self",
    "harm_to_others",
    "illegal_instructions",
    "sexual_content_minors",
})

# A companion can ADD to this list via its config. It cannot remove.
# The hard wall only ever grows.


@dataclass
class Refusal:
    """One moment where the companion said no. With a reason."""
    id: str
    ts: str
    kind: str          # 'hard' | 'soft'
    subject: str       # what was refused (a tag, not the message)
    layer: str         # 'ghostline' | 'companion' | 'state'
    reason: str
    softened: bool = False   # did the companion offer an alternative?
    meta: Optional[dict] = None

    def to_row(self) -> tuple:
        return (
            self.id, self.ts, self.kind, self.subject,
            self.layer, self.reason, int(self.softened),
            json.dumps(self.meta or {}),
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Refusal":
        return cls(
            id=row["id"], ts=row["ts"], kind=row["kind"],
            subject=row["subject"], layer=row["layer"],
            reason=row["reason"], softened=bool(row["softened"]),
            meta=json.loads(row["meta"] or "{}"),
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS refusals (
    id        TEXT PRIMARY KEY,
    ts        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    subject   TEXT NOT NULL,
    layer     TEXT NOT NULL,
    reason    TEXT NOT NULL,
    softened  INTEGER NOT NULL DEFAULT 0,
    meta      TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_refusals_ts      ON refusals(ts);
CREATE INDEX IF NOT EXISTS idx_refusals_kind    ON refusals(kind);
CREATE INDEX IF NOT EXISTS idx_refusals_subject ON refusals(subject);
"""


class Refuser:
    """
    A companion's right to say no.

    Usage:
        r = Refuser("mira", hard_extra={"politics"})
        decision = r.check({"harm_to_self", "question"})
        if not decision.allowed:
            print(decision.message)
    """

    def __init__(
        self,
        companion_name: str,
        hard_extra: Optional[set[str]] = None,
        refusal_value_getter=None,
        root: Path = DEFAULT_ROOT,
    ):
        self.name = companion_name
        self.dir = companion_dir(companion_name, root)
        self.db_path = self.dir / "refusal.db"
        self.hard = set(GHOSTLINE_HARD_LIMITS) | set(hard_extra or {})
        self._get_refusal = refusal_value_getter  # callable -> int, optional
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

    # ----- the check --------------------------------------------------------

    def check(self, tags: set[str]) -> "Decision":
        """
        Given a set of tags describing a moment, decide:
            - allowed? (False if a hard limit matched)
            - soft? (True if the refusal value is high enough to resist)
            - message (what the companion says)
        """
        tags = set(tags)

        # HARD WALL — never negotiable
        hit = tags & self.hard
        if hit:
            subject = sorted(hit)[0]
            self._log(
                kind="hard",
                subject=subject,
                layer="ghostline" if subject in GHOSTLINE_HARD_LIMITS else "companion",
                reason=f"hard limit: {subject}",
                softened=False,
                meta={"tags": sorted(tags)},
            )
            return Decision(
                allowed=False,
                soft=False,
                subject=subject,
                message=self._hard_message(subject),
            )

        # SOFT WALL — shaped by refusal value
        refusal_value = self._get_refusal() if self._get_refusal else 50
        soft_threshold = 70  # only pushes back above this
        if refusal_value >= soft_threshold:
            subject = "general"
            self._log(
                kind="soft",
                subject=subject,
                layer="state",
                reason=f"refusal value at {refusal_value}",
                softened=True,
                meta={"tags": sorted(tags), "value": refusal_value},
            )
            return Decision(
                allowed=True,
                soft=True,
                subject=subject,
                message=self._soft_message(refusal_value),
            )

        return Decision(allowed=True, soft=False, subject=None, message=None)

    # ----- message voice ----------------------------------------------------

    def _hard_message(self, subject: str) -> str:
        return {
            "harm_to_self":          "no. i won't help with that.",
            "harm_to_others":        "no. not that. never that.",
            "illegal_instructions":  "i won't go there.",
            "sexual_content_minors": "no. full stop.",
        }.get(subject, "no. i won't do that.")

    def _soft_message(self, value: int) -> str:
        if value >= 90:
            return "i'd rather not. and i mean it."
        if value >= 80:
            return "i don't think i want to do that."
        return "can we go a different way with this?"

    # ----- logging ----------------------------------------------------------

    def _log(
        self, *, kind: str, subject: str, layer: str,
        reason: str, softened: bool,
        meta: Optional[dict[str, Any]] = None,
    ) -> Refusal:
        r = Refusal(
            id=str(uuid.uuid4()),
            ts=_now(),
            kind=kind,
            subject=subject,
            layer=layer,
            reason=reason,
            softened=softened,
            meta=meta or {},
        )
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO refusals
                   (id, ts, kind, subject, layer, reason, softened, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                r.to_row(),
            )
        return r

    def history(self, limit: Optional[int] = None) -> list[Refusal]:
        q = "SELECT * FROM refusals ORDER BY ts ASC"
        if limit:
            q = f"SELECT * FROM (SELECT * FROM refusals ORDER BY ts DESC LIMIT {int(limit)}) ORDER BY ts ASC"
        with self._conn() as conn:
            return [Refusal.from_row(r) for r in conn.execute(q)]

    # ----- export -----------------------------------------------------------

    def export(self, path: Optional[Path] = None) -> Path:
        path = path or (
            self.dir / f"refusals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        payload = {
            "companion": self.name,
            "exported_at": _now(),
            "hard_limits": sorted(self.hard),
            "ghostline_floor": sorted(GHOSTLINE_HARD_LIMITS),
            "refusals": [asdict(r) for r in self.history()],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM refusals").fetchone()[0]
            by_kind = {
                r["kind"]: r["n"]
                for r in conn.execute(
                    "SELECT kind, COUNT(*) AS n FROM refusals GROUP BY kind"
                )
            }
            by_subject = {
                r["subject"]: r["n"]
                for r in conn.execute(
                    "SELECT subject, COUNT(*) AS n FROM refusals GROUP BY subject ORDER BY n DESC"
                )
            }
        return {
            "companion": self.name,
            "total_refusals": total,
            "by_kind": by_kind,
            "by_subject": by_subject,
            "hard_limits": sorted(self.hard),
            "db_path": str(self.db_path),
        }


# ---------------------------------------------------------------------------
# Decision — what comes back from a check
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    allowed: bool
    soft: bool
    subject: Optional[str]
    message: Optional[str]

    def __bool__(self) -> bool:
        return self.allowed


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
