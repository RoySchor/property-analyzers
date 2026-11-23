"""Common pieces for data source adapters."""

import sqlite3
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class SyncContext:
    zips: list[str]
    counties: list[str]
    settings: dict[str, str]
    force: bool = False


@dataclass
class SourceState:
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class SourceOutcome:
    rows: int = 0
    unchanged: bool = False
    message: str = ""
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class Source:
    """A named sync step. `run` does its own HTTP outside DB transactions and writes in short batches."""

    name: str
    label: str
    min_interval: timedelta
    run: callable
    required_env: str | None = None
    scoped_by: tuple[str, ...] = field(default=("zips",))   # which context fields force a reload when they change


def upsert_metrics(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (source, geo_type, geo_id, metric, period, value)."""
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO market_metrics (source, geo_type, geo_id, metric, period, value)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, geo_type, geo_id, metric, period) DO UPDATE SET value = excluded.value
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def to_float(value) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if text in ("", ".", "NA", "nan", "None"):
            return None
        return float(text)
    except ValueError:
        return None
