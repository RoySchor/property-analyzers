from database import get_db
from services.exclusions import purge_excluded
from services.sources.listings import _is_excluded


def test_listing_filter_drops_mobile_manufactured_and_land():
    assert _is_excluded({"style": "MOBILE"})
    assert _is_excluded({"style": "LAND"})
    assert _is_excluded({"style": "SINGLE_FAMILY", "text": "Charming manufactured home on a large lot"})
    assert not _is_excluded({"style": "SINGLE_FAMILY", "text": "Brick twin near Lafayette"})


def test_purge_removes_excluded_rows_everywhere(temp_db):
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO parcels (parcel_id, county_fips, address, address_norm, zip, property_class, updated_at) VALUES (?, '42095', ?, ?, '18042', ?, 'now')",
            [("42095:M", "1 PARK LN", "1 PARK LN", "mobile_home"), ("42095:L", "2 LOT RD", "2 LOT RD", "land"),
             ("42095:H", "3 MAIN ST", "3 MAIN ST", "single_family")],
        )
        conn.executemany(
            "INSERT INTO sales (parcel_id, address, address_norm, zip, sale_date, sale_price, is_valid, source) VALUES (?, ?, ?, '18042', '2026-01-01', 50000, 1, ?)",
            [("42095:M", "1 PARK LN", "1 PARK LN", "county"), ("42095:H", "3 MAIN ST", "3 MAIN ST", "county"),
             (None, "1 Park Ln", "1 PARK LN", "homeharvest")],
        )
        conn.executemany(
            "INSERT INTO listings (listing_id, address, zip, property_type, parcel_id, first_seen_at, last_seen_at) VALUES (?, ?, '18042', ?, ?, 'now', 'now')",
            [("A", "9 Lot Rd", "land", None), ("B", "1 Park Ln", "single_family", "42095:M"), ("C", "3 Main St", "single_family", "42095:H")],
        )
        conn.execute("INSERT INTO watchlist (listing_id) VALUES ('A')")
        conn.execute("INSERT INTO watchlist (parcel_id) VALUES ('42095:M')")
        conn.commit()

        purge_excluded(conn)

        assert [r[0] for r in conn.execute("SELECT parcel_id FROM parcels")] == ["42095:H"]
        assert [r[0] for r in conn.execute("SELECT listing_id FROM listings")] == ["C"]
        assert [r[0] for r in conn.execute("SELECT address FROM sales")] == ["3 MAIN ST"]
        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 0
