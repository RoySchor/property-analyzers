"""On-demand RentCast rent estimates with a hard, fail-closed request budget.

RentCast bills per successful request beyond 50 per *billing period* (anchored to the plan's activation day,
not the calendar month) and offers no server-side hard cap. So this module enforces its own:

- At most HARD_CAP requests in ANY rolling 31-day window. Every billing period is at most 31 days, so no
  billing period can ever contain more than HARD_CAP calls, regardless of which day it starts.
- Every attempt is recorded BEFORE the HTTP request, and counted even if it fails (conservative).
- The ledger is an append-only file outside the database, so `make db-reset` cannot wipe it.
- Reserve-then-call happens under an exclusive OS file lock, so concurrent requests (threads or processes)
  cannot both slip under the cap.
- Exactly one HTTP request per reservation: no retries.
- Any doubt (unreadable ledger, bad config) blocks the call rather than allowing it.
- A cached estimate younger than 30 days is returned without calling the API.

This is the ONLY code path that talks to RentCast. Sync never calls it.
"""

import fcntl
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from database import PROJECT_ROOT, get_db

RENTCAST_URL = "https://api.rentcast.io/v1/avm/rent/long-term"
HARD_CAP = 45                      # 5 below the free 50, as margin; the env var can lower this but never raise it
WINDOW = timedelta(days=31)        # longest possible billing period
CACHE_DAYS = 30
REQUEST_TIMEOUT_SECONDS = 30

LEDGER_PATH = PROJECT_ROOT / "data" / "rentcast_ledger.jsonl"


class RentcastUnavailable(Exception):
    pass


def monthly_cap() -> int:
    raw = (os.getenv("RENTCAST_MONTHLY_CAP") or "").strip()
    if not raw:
        return HARD_CAP
    try:
        configured = int(raw)
    except ValueError as exc:
        raise RentcastUnavailable("RENTCAST_MONTHLY_CAP is not a whole number; refusing to call RentCast") from exc
    return max(0, min(configured, HARD_CAP))


def _read_ledger(handle) -> list[datetime]:
    handle.seek(0)
    calls = []
    for line_number, line in enumerate(handle, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            calls.append(datetime.fromisoformat(json.loads(line)["at"]))
        except (ValueError, KeyError, TypeError) as exc:
            # A corrupt ledger means we can't prove we're under the cap: fail closed.
            raise RentcastUnavailable(f"RentCast ledger line {line_number} is unreadable; refusing to call") from exc
    return calls


def _calls_in_window(calls: list[datetime], now: datetime) -> int:
    return sum(1 for called_at in calls if called_at > now - WINDOW)


def budget_status() -> dict:
    """For display only. Never raises; a bad config shows as an exhausted budget."""
    try:
        cap = monthly_cap()
    except RentcastUnavailable:
        cap = 0
    return {"used": calls_last_31_days(), "cap": cap, "window_days": WINDOW.days}


def calls_last_31_days() -> int:
    """Calls in the trailing 31 days (the figure the cap is enforced against)."""
    path = Path(LEDGER_PATH)
    if not path.exists():
        return 0
    try:
        with open(path, "r") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            try:
                return _calls_in_window(_read_ledger(handle), datetime.now(timezone.utc))
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    except RentcastUnavailable:
        return HARD_CAP  # report as exhausted so the UI disables the button


def _reserve_call(listing_id: str) -> None:
    """Atomically check the rolling-window budget and record the call. Raises if the budget is spent."""
    cap = monthly_cap()
    path = Path(LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)  # held until the entry is durably written
        try:
            now = datetime.now(timezone.utc)
            used = _calls_in_window(_read_ledger(handle), now)
            if used >= cap:
                raise RentcastUnavailable(
                    f"RentCast budget reached: {used} of {cap} calls used in the last 31 days. "
                    "Blocked to avoid overage charges."
                )
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps({"at": now.isoformat(), "listing_id": listing_id}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _cached_estimate(listing_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT rent, fetched_at FROM rent_estimates WHERE listing_id = ? AND source = 'rentcast'", (listing_id,)
        ).fetchone()
    if not row:
        return None
    age = datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])
    return {"rent": row["rent"], "cached": True} if age.days < CACHE_DAYS else None


def estimate_rent(listing_id: str) -> dict:
    api_key = (os.getenv("RENTCAST_API_KEY") or "").strip()
    if not api_key:
        raise RentcastUnavailable("RENTCAST_API_KEY is not set (see README → Getting started)")

    with get_db() as conn:
        listing = conn.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,)).fetchone()
    if not listing:
        raise RentcastUnavailable("Listing not found")

    cached = _cached_estimate(listing_id)
    if cached:
        return cached

    params = {"address": f"{listing['address']}, {listing['city']}, PA {listing['zip']}"}
    if listing["beds"]:
        params["bedrooms"] = listing["beds"]
    if listing["sqft"]:
        params["squareFootage"] = listing["sqft"]

    _reserve_call(listing_id)  # raises before any network activity if the budget is spent

    try:
        response = requests.get(
            RENTCAST_URL, params=params, headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RentcastUnavailable(f"RentCast request failed ({type(exc).__name__}); it still counts toward the budget") from exc
    if response.status_code != 200:
        raise RentcastUnavailable(f"RentCast returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RentcastUnavailable("RentCast returned a non-JSON response") from exc
    rent = payload.get("rent") if isinstance(payload, dict) else None
    if not rent:
        raise RentcastUnavailable("RentCast returned no estimate for this address")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO rent_estimates (listing_id, source, rent, value_est, fetched_at) VALUES (?, 'rentcast', ?, NULL, ?)
            ON CONFLICT (listing_id, source) DO UPDATE SET rent = excluded.rent, fetched_at = excluded.fetched_at
            """,
            (listing_id, rent, now),
        )
        conn.commit()
    return {"rent": rent, "range_low": payload.get("rentRangeLow"), "range_high": payload.get("rentRangeHigh")}
