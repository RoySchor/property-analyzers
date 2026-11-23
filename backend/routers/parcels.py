import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from database import get_db, get_settings
from services.address import normalize_address
from services.analysis import metric_series, value_at
from services.search import like_pattern

router = APIRouter(tags=["parcels"])


@router.get("/sales")
def recent_sales(
    zips: str | None = None,
    months: int = Query(12, ge=1, le=600),
    valid_only: bool = True,
    under_cap: bool = True,
    property_class: str | None = None,
    q: str | None = Query(None, description="Address contains (case-insensitive)"),
    limit: int = Query(500, le=5000),
):
    with get_db() as conn:
        cap = float(get_settings(conn).get("max_price") or 250000)
        where = ["s.source = 'county'", "s.sale_date >= date('now', ?)"]
        params: list = [f"-{months} months"]
        if zips:
            zip_list = [z.strip() for z in zips.split(",") if z.strip()]
            where.append(f"s.zip IN ({','.join('?' * len(zip_list))})")
            params.extend(zip_list)
        else:
            where.append("s.zip IN (SELECT rz.zip FROM region_zips rz JOIN regions r ON r.id = rz.region_id WHERE r.is_active = 1)")
        if valid_only:
            where.append("s.is_valid = 1")
        if under_cap:
            where.append("s.sale_price <= ?")
            params.append(cap)
        if property_class:
            where.append("p.property_class = ?")
            params.append(property_class)
        pattern = like_pattern(q)
        if pattern:
            where.append("s.address LIKE ? ESCAPE '\\'")
            params.append(pattern)
        rows = conn.execute(
            f"""
            SELECT s.*, p.property_class, p.sqft, p.beds, p.year_built, p.assessed_value, p.annual_tax_est,
                   p.is_homestead, p.is_absentee, p.owner_name
            FROM sales s LEFT JOIN parcels p ON p.parcel_id = s.parcel_id
            WHERE {' AND '.join(where)}
            ORDER BY s.sale_date DESC LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return {"sales": [dict(row) for row in rows]}


COUNTY_RECORD_SEARCH = {
    "42095": ("Northampton County property record", "https://www.ncpub.org/_web/search/commonsearch.aspx?mode=parid"),
    "42077": ("Lehigh County property record", "https://home.lehighcounty.org/ORA.UI/Public/PropertySearch"),
}
COMP_WINDOW_MONTHS = 6
FALLBACK_COMP_MONTHS = 36


@router.get("/sales/{sale_id}")
def sale_detail(sale_id: int):
    """Everything known about one recorded sale: the property, its full sale history, value since, comps, links."""
    with get_db() as conn:
        sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if not sale:
            raise HTTPException(404, "Sale not found")
        sale = dict(sale)
        parcel_row = conn.execute("SELECT * FROM parcels WHERE parcel_id = ?", (sale["parcel_id"],)).fetchone() \
            if sale["parcel_id"] else None
        return _property_payload(conn, sale=sale, parcel=dict(parcel_row) if parcel_row else None)


def _property_payload(conn, *, sale: dict | None, parcel: dict | None) -> dict:
    """Shared by the sale page and the parcel page. `sale` is the sale in focus (None if the parcel never sold)."""
    parcel_id = (parcel or {}).get("parcel_id") or (sale or {}).get("parcel_id")
    zip_code = (sale or {}).get("zip") or (parcel or {}).get("zip")
    address = (sale or {}).get("address") or (parcel or {}).get("address")
    address_key = (sale or {}).get("address_norm") or (parcel or {}).get("address_norm") or normalize_address(address)

    # Same property = same parcel, or (no parcel) same normalized address in the same ZIP.
    history = [dict(r) for r in conn.execute(
        """
        SELECT id, sale_date, sale_price, is_valid, source, url FROM sales
        WHERE (parcel_id IS NOT NULL AND parcel_id = ?) OR (zip = ? AND address_norm IS NOT NULL AND address_norm = ?)
        ORDER BY sale_date
        """,
        (parcel_id, zip_code, address_key),
    )]
    snapshots = [dict(r) for r in conn.execute(
        "SELECT * FROM parcel_snapshots WHERE parcel_id = ? ORDER BY captured_at", (parcel_id,))] if parcel_id else []
    listing = conn.execute(
        """
        SELECT listing_id, status, list_price, list_date, url, photos, beds, baths, sqft, year_built, lot_sqft
        FROM listings
        WHERE (parcel_id IS NOT NULL AND parcel_id = ?) OR (zip = ? AND address_norm = ?)
        ORDER BY last_seen_at DESC LIMIT 1
        """,
        (parcel_id, zip_code, address_key),
    ).fetchone()
    listing = dict(listing) if listing else None
    realtor_sold = conn.execute(
        """
        SELECT url, photos FROM sales
        WHERE source = 'homeharvest' AND zip = ? AND address_norm = ? AND (url IS NOT NULL OR photos IS NOT NULL)
        ORDER BY sale_date DESC LIMIT 1
        """,
        (zip_code, address_key),
    ).fetchone()

    photos_json = (listing or {}).get("photos") or (realtor_sold["photos"] if realtor_sold else None)
    zip_series = metric_series(conn, zip_code, "zhvi") if zip_code else []
    zip_change = None
    if sale and zip_series:
        value_then = value_at(zip_series, sale["sale_date"][:7] + "-01")
        zip_change = (zip_series[-1][1] / value_then - 1) if value_then else None

    property_class = (parcel or {}).get("property_class")

    def find_comps(window_sql: str, window_params: list) -> list[dict]:
        return [dict(r) for r in conn.execute(
            f"""
            SELECT s.id, s.sale_date, s.sale_price, s.address, p.sqft, p.beds, p.property_class FROM sales s
            LEFT JOIN parcels p ON p.parcel_id = s.parcel_id
            WHERE s.source = 'county' AND s.is_valid = 1 AND s.zip = ? AND s.id != ?
              AND (? IS NULL OR p.property_class = ?) AND (s.parcel_id IS NULL OR s.parcel_id != ?)
              {window_sql} LIMIT 12
            """,
            [zip_code, (sale or {}).get("id", -1), property_class, property_class, parcel_id or "", *window_params],
        )]

    comps, comps_note = [], ""
    if sale:  # sales around the same time, closest in price
        comps = find_comps(
            "AND s.sale_date BETWEEN date(?, ?) AND date(?, ?) ORDER BY ABS(s.sale_price - ?)",
            [sale["sale_date"], f"-{COMP_WINDOW_MONTHS} months", sale["sale_date"], f"+{COMP_WINDOW_MONTHS} months",
             sale["sale_price"]],
        )
        comps_note = f"within {COMP_WINDOW_MONTHS} months of this sale, closest in price"
    if not comps:  # never sold, or a rare type (garages): the most recent similar sales in the ZIP
        comps = find_comps(f"AND s.sale_date >= date('now', '-{FALLBACK_COMP_MONTHS} months') ORDER BY s.sale_date DESC", [])
        comps_note = f"most recent in the last {FALLBACK_COMP_MONTHS // 12} years"
    max_price = float(get_settings(conn).get("max_price") or 250000)

    full_address = ", ".join(filter(None, [address, f"PA {zip_code}" if zip_code else None]))
    county_label, county_url = COUNTY_RECORD_SEARCH.get((parcel or {}).get("county_fips"), (None, None))
    links = [
        {"label": "Google Maps", "url": f"https://www.google.com/maps/search/?api=1&query={quote(full_address)}"},
        {"label": "Zillow", "url": f"https://www.zillow.com/homes/{quote(full_address.replace(',', ''))}_rb/"},
    ]
    realtor_url = (listing or {}).get("url") or (realtor_sold["url"] if realtor_sold else None)
    if realtor_url:
        links.insert(0, {"label": "Realtor.com", "url": realtor_url})
    if county_url:
        links.append({"label": county_label, "url": county_url})

    chart_start = f"{int(sale['sale_date'][:4]) - 1}-01-01" if sale else f"{int(zip_series[-1][0][:4]) - 5}-01-01" if zip_series else ""
    return {
        "address": address,
        "zip": zip_code,
        "sale": sale,
        "parcel": parcel,
        "parcel_number": parcel_id.split(":", 1)[1] if parcel_id else None,
        "history": history,
        "snapshots": snapshots,
        "listing": {k: v for k, v in listing.items() if k != "photos"} if listing else None,
        "photos": json.loads(photos_json) if photos_json else [],
        "zip_value_series": [{"period": p, "value": v} for p, v in zip_series if p >= chart_start],
        "zip_change_since_sale": zip_change,
        "estimated_value_today": round(sale["sale_price"] * (1 + zip_change))
        if sale and zip_change is not None and sale["is_valid"] else None,
        "comps": comps,
        "comps_note": comps_note,
        "under_cap": sale["sale_price"] <= max_price if sale else None,
        "links": links,
    }


@router.get("/parcels")
def search_parcels(
    zips: str | None = None,
    property_class: str | None = None,
    address: str | None = None,
    q: str | None = Query(None, description="Address or owner contains (case-insensitive)"),
    limit: int = Query(500, le=2000),
):
    where, params = [], []
    if zips:
        zip_list = [z.strip() for z in zips.split(",") if z.strip()]
        where.append(f"zip IN ({','.join('?' * len(zip_list))})")
        params.extend(zip_list)
    if property_class:
        where.append("property_class = ?")
        params.append(property_class)
    if address:
        where.append("address_norm LIKE ?")
        params.append(f"%{address.upper().strip()}%")
    pattern = like_pattern(q)
    if pattern:
        where.append("(address LIKE ? ESCAPE '\\' OR owner_name LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    if not where:
        raise HTTPException(400, "Provide zips, property_class, address or q")
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM parcels WHERE {' AND '.join(where)} ORDER BY last_sale_date DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return {"parcels": [dict(row) for row in rows]}


@router.get("/parcels/{parcel_id:path}")
def parcel_detail(parcel_id: str):
    """Property page for a county parcel (e.g. a garage), focused on its most recent recorded sale if any."""
    with get_db() as conn:
        parcel = conn.execute("SELECT * FROM parcels WHERE parcel_id = ?", (parcel_id,)).fetchone()
        if not parcel:
            raise HTTPException(404, "Parcel not found")
        latest_sale = conn.execute(
            """
            SELECT * FROM sales WHERE parcel_id = ? AND source = 'county'
            ORDER BY is_valid DESC, sale_date DESC LIMIT 1
            """,
            (parcel_id,),
        ).fetchone()
        return _property_payload(conn, sale=dict(latest_sale) if latest_sale else None, parcel=dict(parcel))
