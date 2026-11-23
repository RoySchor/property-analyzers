"""Post-sync analysis: link listings to parcels and compute deal math."""

import sqlite3
from datetime import date, datetime, timezone
from statistics import median

from database import get_db, get_settings, tracked_zips
from services.deal_math import DealInputs, analyze, deal_score

LATLON_MATCH_DEGREES = 0.0003  # roughly 30 m
RENTCAST_MAX_AGE_DAYS = 30
NO_MARKET_RENT_TYPES = ("land", "mobile", "farm", "other")


def recompute_all() -> None:
    with get_db() as conn:
        settings = get_settings(conn)
        match_listings_to_parcels(conn)
        compute_deal_scores(conn, settings)
        conn.commit()


# --- Listing <-> parcel ---------------------------------------------------------------------

def match_listings_to_parcels(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE listings SET
          parcel_id = (
            SELECT p.parcel_id FROM parcels p
            WHERE p.address_norm = listings.address_norm AND (p.zip = listings.zip OR p.zip IS NULL)
            ORDER BY (p.zip = listings.zip) DESC LIMIT 1
          ),
          match_method = 'address'
        WHERE address_norm IS NOT NULL
        """
    )
    conn.execute("UPDATE listings SET match_method = NULL WHERE parcel_id IS NULL")

    unmatched = conn.execute(
        "SELECT listing_id, lat, lon FROM listings WHERE parcel_id IS NULL AND lat IS NOT NULL AND lon IS NOT NULL"
    ).fetchall()
    for listing in unmatched:
        nearest = conn.execute(
            """
            SELECT parcel_id FROM parcels
            WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
            ORDER BY (lat - ?) * (lat - ?) + (lon - ?) * (lon - ?) LIMIT 1
            """,
            (
                listing["lat"] - LATLON_MATCH_DEGREES, listing["lat"] + LATLON_MATCH_DEGREES,
                listing["lon"] - LATLON_MATCH_DEGREES, listing["lon"] + LATLON_MATCH_DEGREES,
                listing["lat"], listing["lat"], listing["lon"], listing["lon"],
            ),
        ).fetchone()
        if nearest:
            conn.execute(
                "UPDATE listings SET parcel_id = ?, match_method = 'latlon' WHERE listing_id = ?",
                (nearest["parcel_id"], listing["listing_id"]),
            )


# --- Metric helpers -------------------------------------------------------------------------

def metric_series(conn: sqlite3.Connection, geo_id: str, metric: str, source: str | None = None) -> list[tuple[str, float]]:
    query = "SELECT period, value FROM market_metrics WHERE geo_id = ? AND metric = ?"
    params: list = [geo_id, metric]
    if source:
        query += " AND source = ?"
        params.append(source)
    return [(row["period"], row["value"]) for row in conn.execute(query + " ORDER BY period", params)]


def latest_value(conn: sqlite3.Connection, geo_id: str, metric: str) -> float | None:
    row = conn.execute(
        "SELECT value FROM market_metrics WHERE geo_id = ? AND metric = ? ORDER BY period DESC LIMIT 1",
        (geo_id, metric),
    ).fetchone()
    return row["value"] if row else None


def value_at(series: list[tuple[str, float]], period: str) -> float | None:
    """Last value at or before `period` (YYYY-MM-DD)."""
    found = None
    for series_period, value in series:
        if series_period > period:
            break
        found = value
    return found


def current_mortgage_rate(conn: sqlite3.Connection, settings: dict[str, str]) -> float:
    explicit = (settings.get("interest_rate_pct") or "").strip()
    if explicit:
        return float(explicit)
    market = latest_value(conn, "US", "mortgage_30y") or 6.5
    return market + float(settings.get("investor_rate_premium_pct") or 0)


# --- Deal scores ----------------------------------------------------------------------------

def _rent_for_listing(conn, listing, parcel, zori_by_zip) -> tuple[float | None, str | None]:
    cached = conn.execute(
        "SELECT rent, fetched_at FROM rent_estimates WHERE listing_id = ? AND source = 'rentcast'",
        (listing["listing_id"],),
    ).fetchone()
    if cached and (datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"])).days <= RENTCAST_MAX_AGE_DAYS:
        return cached["rent"], "RentCast estimate"

    is_multi = (parcel and parcel["property_class"] == "multi_family") or listing["property_type"] == "multi_family"
    units = (parcel["units"] if parcel and parcel["units"] and parcel["units"] >= 2 else 2) if is_multi else 1
    units_note = "" if not is_multi else (f" × {units} units" if parcel and parcel["units"] else " × 2 units (assumed)")
    beds_per_unit = max(0, min(4, round((listing["beds"] or 2) / units)))

    for geo_id in (listing["zip"], parcel["county_fips"] if parcel else None):
        if not geo_id:
            continue
        hud = latest_value(conn, geo_id, f"fmr_{beds_per_unit}br")
        if hud:
            return hud * units, f"HUD Fair Market Rent {beds_per_unit}BR{units_note}"

    zori = zori_by_zip.get(listing["zip"])
    if zori:
        return zori * units, f"Zillow ZIP typical rent{units_note}"
    return None, None


def _comp_price_per_sqft(conn, zip_code: str, property_class: str | None) -> float | None:
    since = date.today().replace(year=date.today().year - 1).isoformat()
    rows = conn.execute(
        """
        SELECT s.sale_price / p.sqft AS ppsf, p.property_class FROM sales s
        JOIN parcels p ON p.parcel_id = s.parcel_id
        WHERE s.source = 'county' AND s.is_valid = 1 AND s.zip = ? AND s.sale_date >= ? AND p.sqft > 300
        """,
        (zip_code, since),
    ).fetchall()
    same_class = [row["ppsf"] for row in rows if row["property_class"] == property_class]
    pool = same_class if len(same_class) >= 5 else [row["ppsf"] for row in rows]
    return median(pool) if len(pool) >= 5 else None


def compute_deal_scores(conn: sqlite3.Connection, settings: dict[str, str]) -> None:
    max_price = float(settings.get("max_price") or 250000)
    rate = current_mortgage_rate(conn, settings)
    fallback_tax_pct = float(settings.get("fallback_tax_rate_pct") or 2.2)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    zori_by_zip = {zip_code: latest_value(conn, zip_code, "zori") for zip_code in tracked_zips(conn)}
    zhvi_cache: dict[str, list] = {}
    comp_cache: dict[tuple, float | None] = {}

    conn.execute("DELETE FROM deal_scores")
    listings = conn.execute(
        """
        SELECT * FROM listings
        WHERE status IN ('for_sale', 'pending', 'contingent') AND list_price >= 10000 AND list_price <= ?
        """,
        (max_price,),
    ).fetchall()

    for listing in listings:
        parcel = conn.execute("SELECT * FROM parcels WHERE parcel_id = ?", (listing["parcel_id"],)).fetchone() \
            if listing["parcel_id"] else None
        price = listing["list_price"]

        prev_price, prev_date = listing["last_sold_price"], listing["last_sold_date"]
        if not prev_price and parcel and parcel["last_sale_valid"]:
            prev_price, prev_date = parcel["last_sale_price"], parcel["last_sale_date"]
        change_pct = (price / prev_price - 1) if prev_price else None

        zip_change = None
        if prev_date and listing["zip"]:
            series = zhvi_cache.setdefault(listing["zip"], metric_series(conn, listing["zip"], "zhvi"))
            then = value_at(series, prev_date[:7] + "-01")
            if then and series:
                zip_change = series[-1][1] / then - 1

        if parcel and parcel["annual_tax_est"]:
            annual_tax, tax_source = parcel["annual_tax_est"], "county_millage"
        else:
            annual_tax, tax_source = price * fallback_tax_pct / 100, "estimate"

        rent, rent_source = _rent_for_listing(conn, listing, parcel, zori_by_zip)
        if listing["property_type"] in NO_MARKET_RENT_TYPES and rent_source != "RentCast estimate":
            # ZIP-wide rents don't describe land, mobile homes on leased lots or bare garages; need a real estimate.
            rent, rent_source = None, "Needs a property-specific rent estimate"

        property_class = parcel["property_class"] if parcel else None
        sqft = listing["sqft"] or (parcel["sqft"] if parcel else None)
        price_per_sqft = price / sqft if sqft else None
        comp_key = (listing["zip"], property_class)
        if comp_key not in comp_cache:
            comp_cache[comp_key] = _comp_price_per_sqft(conn, listing["zip"], property_class)
        comp_ppsf = comp_cache[comp_key]
        comp_discount = (1 - price_per_sqft / comp_ppsf) if price_per_sqft and comp_ppsf else None
        days_on_market = (date.today() - date.fromisoformat(listing["list_date"][:10])).days if listing["list_date"] else None

        result = None
        if rent:
            result = analyze(DealInputs(
                price=price,
                monthly_rent=rent,
                annual_tax=annual_tax,
                annual_insurance=float(settings.get("insurance_annual") or 1500),
                monthly_hoa=listing["hoa_fee"] or 0,
                down_payment_pct=float(settings.get("down_payment_pct") or 25),
                interest_rate_pct=rate,
                loan_years=int(float(settings.get("loan_years") or 30)),
                closing_cost_pct=float(settings.get("closing_cost_pct") or 3),
                vacancy_pct=float(settings.get("vacancy_pct") or 0),
                maintenance_pct=float(settings.get("maintenance_pct") or 0),
                capex_pct=float(settings.get("capex_pct") or 0),
                management_pct=float(settings.get("management_pct") or 0),
            ))

        conn.execute(
            """
            INSERT INTO deal_scores (listing_id, computed_at, prev_sale_price, prev_sale_date, change_since_sale_pct,
              zip_change_same_period_pct, annual_tax, tax_source, rent, rent_source, monthly_piti, monthly_cashflow,
              cap_rate, cash_on_cash, price_per_sqft, comp_price_per_sqft, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing["listing_id"], now, prev_price, prev_date, change_pct, zip_change, round(annual_tax, 2),
                tax_source, rent, rent_source,
                result.monthly_piti if result else None, result.monthly_cashflow if result else None,
                result.cap_rate if result else None, result.cash_on_cash if result else None,
                price_per_sqft, comp_ppsf,
                deal_score(result.cap_rate, result.cash_on_cash, comp_discount, days_on_market) if result else None,
            ),
        )
