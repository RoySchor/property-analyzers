"""The RentCast budget must never allow more than 45 calls in any 31-day window, under any conditions."""

import json
import multiprocessing
import threading
from datetime import datetime, timedelta, timezone

import pytest

from services import rentcast


@pytest.fixture
def ledger(tmp_path, monkeypatch, temp_db):
    path = tmp_path / "rentcast_ledger.jsonl"
    monkeypatch.setattr(rentcast, "LEDGER_PATH", path)
    monkeypatch.setenv("RENTCAST_API_KEY", "test-key")
    monkeypatch.delenv("RENTCAST_MONTHLY_CAP", raising=False)
    return path


@pytest.fixture
def listing(ledger):
    from database import get_db

    with get_db() as conn:
        conn.executemany(
            """
            INSERT INTO listings (listing_id, address, city, zip, beds, sqft, first_seen_at, last_seen_at)
            VALUES (?, '1 Main St', 'Easton', '18042', 3, 1200, '2026-01-01', '2026-01-01')
            """,
            [(f"L{i}",) for i in range(120)],
        )
        conn.commit()


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"rent": 1800}

    def json(self):
        return self._payload


@pytest.fixture
def http(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(kwargs.get("params"))
        return FakeResponse()

    monkeypatch.setattr(rentcast.requests, "get", fake_get)
    return calls


def _write_entries(path, timestamps):
    with open(path, "a") as handle:
        for ts in timestamps:
            handle.write(json.dumps({"at": ts.isoformat(), "listing_id": "x"}) + "\n")


def test_hard_stop_at_45_real_http_calls(listing, http):
    successes = 0
    for i in range(100):
        try:
            rentcast.estimate_rent(f"L{i}")
            successes += 1
        except rentcast.RentcastUnavailable:
            pass
    assert successes == 45
    assert len(http) == 45  # the network was touched exactly 45 times, never more


def test_env_var_can_lower_but_never_raise_the_cap(listing, http, monkeypatch):
    monkeypatch.setenv("RENTCAST_MONTHLY_CAP", "500")
    assert rentcast.monthly_cap() == 45
    monkeypatch.setenv("RENTCAST_MONTHLY_CAP", "10")
    assert rentcast.monthly_cap() == 10
    monkeypatch.setenv("RENTCAST_MONTHLY_CAP", "-5")
    assert rentcast.monthly_cap() == 0
    monkeypatch.setenv("RENTCAST_MONTHLY_CAP", "lots")
    with pytest.raises(rentcast.RentcastUnavailable):
        rentcast.estimate_rent("L0")
    assert http == []


def test_rolling_window_blocks_across_calendar_month_boundary(ledger, listing, http):
    # 45 calls made 5 days ago (e.g. late last month). A calendar-month counter would reset; this must not.
    _write_entries(ledger, [datetime.now(timezone.utc) - timedelta(days=5)] * 45)
    with pytest.raises(rentcast.RentcastUnavailable):
        rentcast.estimate_rent("L0")
    assert http == []


def test_calls_older_than_31_days_free_up_budget(ledger, listing, http):
    _write_entries(ledger, [datetime.now(timezone.utc) - timedelta(days=32)] * 45)
    rentcast.estimate_rent("L0")
    assert len(http) == 1


def test_failed_requests_still_count(ledger, listing, monkeypatch):
    attempts = []

    def failing_get(*args, **kwargs):
        attempts.append(1)
        return FakeResponse(status=500)

    monkeypatch.setattr(rentcast.requests, "get", failing_get)
    for i in range(60):
        with pytest.raises(rentcast.RentcastUnavailable):
            rentcast.estimate_rent(f"L{i}")
    assert len(attempts) == 45


def test_network_exception_counts_and_is_not_retried(ledger, listing, monkeypatch):
    attempts = []

    def raising_get(*args, **kwargs):
        attempts.append(1)
        raise rentcast.requests.ConnectionError("down")

    monkeypatch.setattr(rentcast.requests, "get", raising_get)
    with pytest.raises(rentcast.RentcastUnavailable):
        rentcast.estimate_rent("L0")
    assert len(attempts) == 1
    assert rentcast.calls_last_31_days() == 1


def test_cached_estimate_does_not_spend_budget(listing, http):
    rentcast.estimate_rent("L0")
    rentcast.estimate_rent("L0")
    rentcast.estimate_rent("L0")
    assert len(http) == 1


def test_corrupt_ledger_fails_closed(ledger, listing, http):
    ledger.write_text("not json\n")
    with pytest.raises(rentcast.RentcastUnavailable):
        rentcast.estimate_rent("L0")
    assert http == []
    assert rentcast.budget_status()["used"] == 45  # UI shows it as exhausted


def test_missing_key_never_calls(ledger, listing, http, monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "")
    with pytest.raises(rentcast.RentcastUnavailable):
        rentcast.estimate_rent("L0")
    assert http == []


def test_concurrent_threads_cannot_exceed_cap(ledger):
    successes = []
    lock = threading.Lock()

    def worker(i):
        try:
            rentcast._reserve_call(f"T{i}")
            with lock:
                successes.append(i)
        except rentcast.RentcastUnavailable:
            pass

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(successes) == 45
    assert rentcast.calls_last_31_days() == 45


def _process_worker(ledger_path, start, results):
    from services import rentcast as rc

    rc.LEDGER_PATH = ledger_path
    for i in range(start, start + 25):
        try:
            rc._reserve_call(f"P{i}")
            results.put(1)
        except rc.RentcastUnavailable:
            results.put(0)


def test_concurrent_processes_cannot_exceed_cap(ledger):
    context = multiprocessing.get_context("fork")
    results = context.Queue()
    processes = [context.Process(target=_process_worker, args=(ledger, n * 25, results)) for n in range(8)]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    granted = sum(results.get() for _ in range(200))
    assert granted == 45
    assert len([line for line in ledger.read_text().splitlines() if line.strip()]) == 45
