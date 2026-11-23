from services.address import normalize_address


def test_listing_and_county_formats_match():
    assert normalize_address("485 West Cooper Street, Easton, PA") == "485 W COOPER ST"
    assert normalize_address("485 W COOPER ST ") == "485 W COOPER ST"


def test_units_are_stripped():
    assert normalize_address("12 Main Ave Apt 3B") == "12 MAIN AVE"
    assert normalize_address("12 Main Ave #3") == "12 MAIN AVE"


def test_non_street_values_are_rejected():
    assert normalize_address(None) is None
    assert normalize_address("PO BOX 55") is None
