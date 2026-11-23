from database import get_db
from routers.parcels import recent_sales, search_parcels
from services.search import like_pattern


def test_like_pattern_escapes_wildcards_and_blank():
    assert like_pattern("  12   main ") == "%12 main%"
    assert like_pattern("50%_off") == "%50\\%\\_off%"
    assert like_pattern("") is None
    assert like_pattern("   ") is None


def _seed(conn):
    conn.executemany(
        "INSERT INTO parcels (parcel_id, county_fips, address, zip, property_class, owner_name, updated_at) VALUES (?, '42095', ?, '18042', 'garage', ?, 'now')",
        [("42095:A", "726 WASHINGTON CT", "SMITH JOHN"), ("42095:B", "15 MAIN ST", "WASHINGTON HOLDINGS LLC"), ("42095:C", "9 OAK ST", "DOE JANE")],
    )
    conn.executemany(
        "INSERT INTO sales (parcel_id, address, zip, sale_date, sale_price, is_valid, source) VALUES (?, ?, '18042', date('now', '-10 days'), ?, 1, 'county')",
        [("42095:A", "726 WASHINGTON CT", 90000), ("42095:C", "9 OAK ST", 120000)],
    )
    conn.commit()


def test_garage_search_matches_address_or_owner_case_insensitive(temp_db):
    with get_db() as conn:
        _seed(conn)
    found = {p["parcel_id"] for p in search_parcels(zips="18042", property_class="garage", address=None, q="washington", limit=50)["parcels"]}
    assert found == {"42095:A", "42095:B"}  # A by address, B by owner


def test_sales_search_by_address(temp_db):
    with get_db() as conn:
        _seed(conn)
    sales = recent_sales(zips="18042", months=12, valid_only=True, under_cap=True, property_class=None, q="oak", limit=50)["sales"]
    assert [s["address"] for s in sales] == ["9 OAK ST"]
