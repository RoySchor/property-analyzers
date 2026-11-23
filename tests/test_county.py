from database import get_db
from services.sources.county import classify_lehigh, classify_northampton, store_parcels


def test_classification():
    assert classify_northampton("110", 90_000) == "single_family"
    assert classify_northampton("120", 90_000) == "multi_family"
    assert classify_northampton("180", 5_000) == "garage"
    assert classify_northampton("568", 0) == "parking"          # parking lots have no building but are kept
    assert classify_lehigh("1101", 1, 90_000) == "single_family"
    assert classify_lehigh("1101", 3, 90_000) == "multi_family"
    assert classify_lehigh("1110", 0, 8_000) == "garage"


def test_mobile_homes_and_land_are_classified_for_exclusion():
    for code in ("171", "172", "173", "175", "176", "177"):
        assert classify_northampton(code, 40_000) == "mobile_home"
    assert classify_lehigh("1220", 1, 40_000) == "mobile_home"
    assert classify_lehigh("1221", 3, 9_000) == "mobile_home"   # park parcel with several units is still mobile
    assert classify_northampton("90", None) == "land"
    assert classify_northampton("110", 0) == "land"             # house code but no building = vacant lot
    assert classify_northampton("110", None) == "single_family"  # unknown building value is not assumed vacant
    assert classify_lehigh("2101", 0, 0) == "land"
    assert classify_lehigh("1110", 0, 0) == "land"


def _parcel(**overrides):
    parcel = {
        "parcel_id": "42095:X1", "county_fips": "42095", "address": "1 MAIN ST", "address_norm": "1 MAIN ST",
        "zip": "18042", "muni": "10", "land_use_code": "110", "property_class": "single_family", "units": None,
        "beds": 3, "baths": 1.0, "sqft": 1200, "year_built": 1920, "lat": None, "lon": None,
        "owner_name": "A", "owner_mail": None, "is_homestead": 1, "is_absentee": 0, "assessed_value": 50_000,
        "market_value": 100_000, "last_sale_price": 150_000, "last_sale_date": "2019-05-01", "last_sale_valid": 1,
        "annual_tax_est": 5452.0,
    }
    parcel.update(overrides)
    return parcel


def test_snapshots_only_on_change_and_sale_history_accumulates(temp_db):
    with get_db() as conn:
        assert store_parcels(conn, [_parcel()]) == (1, 1)
        assert store_parcels(conn, [_parcel()]) == (1, 0)  # unchanged: no new snapshot
        store_parcels(conn, [_parcel(last_sale_price=240_000, last_sale_date="2026-03-01", owner_name="B")])
        sales = conn.execute("SELECT sale_date, sale_price FROM sales ORDER BY sale_date").fetchall()
        snapshots = conn.execute("SELECT COUNT(*) FROM parcel_snapshots").fetchone()[0]
        current = conn.execute("SELECT last_sale_price FROM parcels").fetchone()[0]
    # The prior sale survives even though the county now only reports the new one.
    assert [tuple(s) for s in sales] == [("2019-05-01", 150_000), ("2026-03-01", 240_000)]
    assert snapshots == 2
    assert current == 240_000
