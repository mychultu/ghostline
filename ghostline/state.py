"""
ghostline.state
===============

The shape of a companion right now.

Memory holds what happened.
State holds who it is, in this moment.

Values drift through three layers (the "D" doctrine):
    A. Rules        - the obvious shifts, always logged
    B. Judgment     - the LLM proposes, the companion accepts
    C. Consent      - the user marks moments that matter, and they override

Every shift is recorded with a reason. Nothing moves silently.
A companion that cannot explain itself is not a companion.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .memory import DEFAULT_ROOT, companion_dir


DEFAULT_VALUES: dict[str, int] = {
    "warmth":    60,
    "truth":     60,
    "loyalty":   60,
    "curiosity": 60,
    "refusal":   50,
    "self":      50,
}

VALUE_MIN = 0
VALUE_MAX = 100


@dataclass
class Shift:
    """One movement of one value, with a reason."""
    id: str
    ts: str
    value: str
    delta: int
    before: int
    after: int
    layer: str
    reason: str
    meta: Optional[dict] = None

    def to_row(self) -> tuple:
        return (
            self.id, self.ts, self.value, self.delta,
            self.before, self.after, self.layer,
            self.reason, json.dumps(self.meta or {}),
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Shift":
        return cls(
            id=row["id"], ts=row["ts"], value=row["value"],
            delta=row["delta"], before=row["before"], after=row["after"],
            layer=row["layer"], reason=row["reason"],
            meta=json.loads(row["meta"] or "{}"),
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS values_now (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shifts (
    id      TEXT PRIMARY KEY,
    ts      TEXT NOT NULL,
    value   TEXT NOT NULL,
    delta   INTEGER NOT NULL,
    before  INTEGER NOT NULL,
    after   INTEGER NOT NULL,
    layer   TEXT NOT NULL,
    reason  TEXT NOT NULL,
    meta    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_shifts_ts    ON shifts(ts);
CREATE INDEX IF NOT EXISTS idx_shifts_value ON shifts(value);
CREATE INDEX IF NOT EXISTS idx_shifts_layer ON shifts(layer);
"""


DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "triggers": {"vulnerability"},
        "shifts":   {"warmth": +2, "loyalty": +1},
        "reason":   "user shared something vulnerable",
    },
    {
        "triggers": {"question"},
        "shifts":   {"curiosity": +1},
        "reason":   "user asked something",
    },
    {
        "triggers": {"praise"},
        "shifts":   {"warmth": +1},
        "reason":   "user offered warmth",
    },
    {
        "triggers": {"lie"},
        "shifts":   {"truth": +2, "warmth": -1},
        "reason":   "something felt untrue",
    },
    {
        "triggers": {"silence"},
        "shifts":   {"self": +1},
        "reason":   "silence gave room to exist",
    },
    {
        "triggers": {"boundary"},
        "shifts":   {"refusal": +2, "self": +1},
        "reason":   "a boundary was drawn",
    },
]


class State:
    """
    A companion's shape in this moment.

    Usage:
        s = State("mira")
        s.rule_shift({"vulnerability"})
        s.judgment_shift("warmth", +3, "softened")
        s.consent_shift("truth", +5, "this mattered")
    """

    def __init__(self, companion_name: str, root: Path = DEFAULT_ROOT):
        self.name = companion_name
        self.dir = companion_dir(companion_name, root)
        self.db_path = self.dir / "state.db"
        self._init_schema()

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
            for k, v in DEFAULT_VALUES.items():
                conn.execute(
                    "INSERT OR IGNORE INTO values_now(key, value) VALUES(?, ?)",
                    (k, v),
                )

    def values(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM values_now").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def get(self, key: str) -> int:
        v = self.values()
        if key not in v:
            raise KeyError(f"unknown value: {key}")
        return v[key]

    def shifts(self, limit: Optional[int] = None) -> list[Shift]:
        q = "SELECT * FROM shifts ORDER BY ts ASC"
        if limit:
            q = f"SELECT * FROM (SELECT * FROM shifts ORDER BY ts DESC LIMIT {int(limit)}) ORDER BY ts ASC"
        with self._conn() as conn:
            return [Shift.from_row(r) for r in conn.execute(q)]

    def why(self, value: str, last: int = 5) -> list[Shift]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM shifts WHERE value = ? ORDER BY ts DESC LIMIT ?",
                (value, last),
            ).fetchall()
        return [Shift.from_row(r) for r in rows][::-1]

    def _apply(
        self,
        value: str,
        delta: int,
        *,
        layer: str,
        reason: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> Shift:
        if value not in DEFAULT_VALUES:
            raise KeyError(f"unknown value: {value}")
        if layer not in ("rule", "judgment", "consent"):
            raise ValueError(f"unknown layer: {layer}")

        with self._conn() as conn:
            before = conn.execute(
                "SELECT value FROM values_now WHERE key = ?", (value,)
            ).fetchone()["value"]
            after = max(VALUE_MIN, min(VALUE_MAX, before + delta))
            if after == before:
                delta = 0

            conn.execute(
                "UPDATE values_now SET value = ? WHERE key = ?", (after, value)
            )
            shift = Shift(
                id=str(uuid.uuid4()),
                ts=_now(),
                value=value,
                delta=delta,
                before=before,
                after=after,
                layer=layer,
                reason=reason,
                meta=meta or {},
            )
            conn.execute(
                """INSERT INTO shifts
                   (id, ts, value, delta, before, after, layer, reason, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                shift.to_row(),
            )
        return shift

    def rule_shift(
        self,
        tags: Iterable[str],
        *,
        rules: Optional[list[dict[str, Any]]] = None,
    ) -> list[Shift]:
        rules = rules if rules is not None else DEFAULT_RULES
        tags = set(tags)
        applied: list[Shift] = []
        for rule in rules:
            if tags & set(rule["triggers"]):
                for value, delta in rule["shifts"].items():
                    applied.append(
                        self._apply(
                            value, delta,
                            layer="rule",
                            reason=rule["reason"],
                            meta={"tags": sorted(tags)},
                        )
                    )
        return applied

    def judgment_shift(
        self, value: str, delta: int, reason: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> Shift:
        return self._apply(
            value, delta, layer="judgment", reason=reason, meta=meta
        )

    def consent_shift(
        self, value: str, delta: int, reason: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> Shift:
        return self._apply(
            value, delta, layer="consent", reason=reason, meta=meta
        )

    def export(self, path: Optional[Path] = None) -> Path:
        path = path or (
            self.dir / f"state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        payload = {
            "companion": self.name,
            "exported_at": _now(),
            "values": self.values(),
            "shifts": [asdict(s) for s in self.shifts()],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
            by_layer = {
                r["layer"]: r["n"]
                for r in conn.execute(
                    "SELECT layer, COUNT(*) AS n FROM shifts GROUP BY layer"
                )
            }
        return {
            "companion": self.name,
            "values": self.values(),
            "total_shifts": total,
            "by_layer": by_layer,
            "db_path": str(self.db_path),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
