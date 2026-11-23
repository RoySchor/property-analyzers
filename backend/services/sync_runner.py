"""Runs every source independently, records status, then recomputes analysis.

Triggered on app startup (background thread) and by POST /api/sync. Each source is skipped when it was
refreshed recently and the tracked ZIPs/counties are unchanged, or when its remote file is unchanged.
"""

import hashlib
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from database import get_db, get_settings, tracked_counties, tracked_zips
from services import analysis
from services.exclusions import purge_excluded
from services.http_fetch import SourceError
from services.sources.base import Source, SourceOutcome, SourceState, SyncContext
from services.sources.county import LEHIGH, NORTHAMPTON, make_county_runner
from services.sources.government import run_census, run_hud
from services.sources.listings import run_listings
from services.sources.market import make_zillow_runner, run_fred, run_realtor_zip

logger = logging.getLogger(__name__)

SOURCES: list[Source] = [
    Source("fred", "FRED (30-year mortgage rate)", timedelta(hours=12), run_fred, scoped_by=()),
    Source("zillow_zhvi_zip", "Zillow home values by ZIP", timedelta(hours=12), make_zillow_runner("zillow_zhvi_zip")),
    Source("zillow_zhvi_bottom_zip", "Zillow bottom-tier home values by ZIP", timedelta(hours=12), make_zillow_runner("zillow_zhvi_bottom_zip")),
    Source("zillow_zori_zip", "Zillow rents by ZIP", timedelta(hours=12), make_zillow_runner("zillow_zori_zip")),
    Source("realtor_zip", "Realtor.com inventory by ZIP", timedelta(hours=12), run_realtor_zip),
    Source("census_acs", "Census ACS (rent, vacancy, income)", timedelta(days=30), run_census, required_env="CENSUS_API_KEY"),
    Source("hud_fmr", "HUD Fair Market Rents", timedelta(days=30), run_hud, required_env="HUD_API_TOKEN", scoped_by=("zips", "counties")),
    Source("county_northampton", "Northampton County parcels & sales", timedelta(days=7), make_county_runner(NORTHAMPTON), scoped_by=("counties",)),
    Source("county_lehigh", "Lehigh County parcels & sales", timedelta(days=7), make_county_runner(LEHIGH), scoped_by=("counties",)),
    Source("listings", "Realtor.com listings (HomeHarvest)", timedelta(hours=1), run_listings, scoped_by=("zips", "settings")),
]
SOURCES_BY_NAME = {source.name: source for source in SOURCES}

_lock = threading.Lock()
_progress: dict = {"running": False, "current": None, "started_at": None, "finished_at": None}


def progress() -> dict:
    return dict(_progress)


def start_background_sync(force: bool = False, only: list[str] | None = None) -> bool:
    """Returns False when a sync is already running."""
    if _lock.locked():
        return False
    thread = threading.Thread(target=run_all, kwargs={"force": force, "only": only}, daemon=True)
    thread.start()
    return True


def run_all(force: bool = False, only: list[str] | None = None) -> None:
    if not _lock.acquire(blocking=False):
        return
    try:
        _progress.update(running=True, started_at=_now(), finished_at=None, current=None)
        with get_db() as conn:
            ctx = SyncContext(
                zips=tracked_zips(conn), counties=tracked_counties(conn), settings=get_settings(conn), force=force
            )
        for source in SOURCES:
            if only and source.name not in only:
                continue
            _progress["current"] = source.label
            _run_source(source, ctx)
        _progress["current"] = "Analysis"
        _run_analysis()
    finally:
        _progress.update(running=False, current=None, finished_at=_now())
        _lock.release()


def _run_source(source: Source, ctx: SyncContext) -> None:
    scope_key = _scope_key(source, ctx)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM source_sync WHERE source = ?", (source.name,)).fetchone()

    if source.required_env and not os.getenv(source.required_env):
        _record(source.name, "needs_key", f"Add {source.required_env} to .env (see README → Getting started)")
        return

    if not ctx.force and row and row["last_success_at"] and row["scope_key"] == scope_key:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["last_success_at"])
        if age < source.min_interval:
            _record(source.name, "skipped_fresh", f"Refreshed {_humanize(age)} ago", keep_success=True)
            return

    # A changed scope (new ZIPs) must re-download even if the remote file is unchanged.
    state = SourceState(
        etag=row["etag"] if row and row["scope_key"] == scope_key and not ctx.force else None,
        last_modified=row["last_modified"] if row and row["scope_key"] == scope_key and not ctx.force else None,
    )
    _record(source.name, "running", None, keep_success=True)
    try:
        outcome: SourceOutcome = source.run(ctx, state)
    except SourceError as exc:
        logger.error("Source %s failed: %s", source.name, exc)
        _record(source.name, "error", str(exc), keep_success=True)
        return
    except Exception as exc:  # unexpected bug: report the type only, never details that might hold secrets
        logger.error("Source %s crashed: %s", source.name, type(exc).__name__)
        _record(source.name, "error", f"Unexpected {type(exc).__name__}; see server log", keep_success=True)
        return

    status = "skipped_unchanged" if outcome.unchanged else "ok"
    message = outcome.message or ("Remote data unchanged" if outcome.unchanged else f"{outcome.rows:,} rows")
    _record(
        source.name, status, message, success=True, etag=outcome.etag, last_modified=outcome.last_modified,
        scope_key=scope_key, rows=outcome.rows,
    )


def _run_analysis() -> None:
    try:
        with get_db() as conn:
            purge_excluded(conn)  # mobile homes and land never reach scoring or the UI
        analysis.recompute_all()
        _record("analysis", "ok", "Scores recomputed", success=True)
    except Exception as exc:
        logger.exception("Analysis failed")  # no secrets involved in local computation
        _record("analysis", "error", f"{type(exc).__name__}: {exc}")


def _record(name: str, status: str, message: str | None, *, success: bool = False, keep_success: bool = False,
            etag: str | None = None, last_modified: str | None = None, scope_key: str | None = None,
            rows: int | None = None) -> None:
    now = _now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO source_sync (source, last_attempt_at, status, message) VALUES (?, ?, ?, ?)
            ON CONFLICT (source) DO UPDATE SET last_attempt_at = excluded.last_attempt_at,
              status = excluded.status, message = excluded.message
            """,
            (name, now, status, message),
        )
        if success:
            conn.execute(
                """
                UPDATE source_sync SET last_success_at = ?, etag = ?, last_modified = ?, scope_key = ?,
                  rows_upserted = ? WHERE source = ?
                """,
                (now, etag, last_modified, scope_key, rows, name),
            )
        conn.commit()


def _scope_key(source: Source, ctx: SyncContext) -> str:
    parts = []
    if "zips" in source.scoped_by:
        parts.append(",".join(ctx.zips))
    if "counties" in source.scoped_by:
        parts.append(",".join(ctx.counties))
    if "settings" in source.scoped_by:
        parts.append(f"{ctx.settings.get('min_price')}-{ctx.settings.get('max_price')}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _humanize(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 48 * 60:
        return f"{minutes // 60}h"
    return f"{minutes // 1440}d"
