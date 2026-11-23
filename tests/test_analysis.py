from services.analysis import value_at

SERIES = [("2020-01-01", 100.0), ("2021-01-01", 110.0), ("2025-01-01", 150.0), ("2026-01-01", 165.0)]


def test_value_at_uses_last_known_value():
    assert value_at(SERIES, "2021-06-01") == 110.0
    assert value_at(SERIES, "2019-01-01") is None
