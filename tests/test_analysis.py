from datetime import datetime, timezone

from services.analysis import value_at

SERIES = [("2020-01-01", 100.0), ("2021-01-01", 110.0), ("2025-01-01", 150.0), ("2026-01-01", 165.0)]


def test_value_at_uses_last_known_value():
    assert value_at(SERIES, "2021-06-01") == 110.0
    assert value_at(SERIES, "2019-01-01") is None


def test_off_market_listings_get_deal_math(temp_db):
    from database import get_connection, get_settings
    from services.analysis import compute_deal_scores

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO listings (listing_id, address, zip, property_type, status, list_price, first_seen_at, last_seen_at)
        VALUES ('L1', '1 Test St', '18015', 'single_family', 'off_market', 150000, '2026-01-01', '2026-01-01')
        """
    )
    conn.execute(
        "INSERT INTO rent_estimates (listing_id, source, rent, fetched_at) VALUES ('L1', 'rentcast', 1500, ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
    compute_deal_scores(conn, get_settings(conn))

    row = conn.execute("SELECT rent, monthly_piti, tax_source FROM deal_scores WHERE listing_id = 'L1'").fetchone()
    assert row is not None
    assert row["rent"] == 1500
    assert row["monthly_piti"] is not None
    assert row["tax_source"] == "estimate"
