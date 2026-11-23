import json

from fastapi import APIRouter, HTTPException, Query

from database import get_db, get_settings
from services import rentcast
from services.analysis import compute_deal_scores, metric_series
from services.search import like_pattern

router = APIRouter(tags=["listings"])

SORTS = {
    "score": "d.score DESC NULLS LAST",
    "price": "l.list_price ASC",
    "cashflow": "d.monthly_cashflow DESC NULLS LAST",
    "cap_rate": "d.cap_rate DESC NULLS LAST",
    "newest": "l.list_date DESC",
    "change_since_sale": "d.change_since_sale_pct ASC NULLS LAST",
}


@router.get("/listings")
def list_listings(
    zips: str | None = None,
    property_type: str | None = None,
    garage_only: bool = False,
    status: str = Query("active", pattern="^(active|for_sale|pending|off_market|all)$"),
    sort: str = Query("score", pattern="^(" + "|".join(SORTS) + ")$"),
    max_price: float | None = None,
    q: str | None = Query(None, description="Address contains (case-insensitive)"),
    limit: int = Query(200, le=1000),
):
    with get_db() as conn:
        cap = max_price if max_price is not None else float(get_settings(conn).get("max_price") or 250000)
        where = ["l.list_price <= ?", "l.list_price >= 10000"]  # sub-$10k "sales" are mislabeled rentals
        params: list = [cap]
        if status == "active":
            where.append("l.status IN ('for_sale', 'pending', 'contingent')")
        elif status != "all":
            where.append("l.status = ?")
            params.append(status)
        if zips:
            zip_list = [z.strip() for z in zips.split(",") if z.strip()]
            where.append(f"l.zip IN ({','.join('?' * len(zip_list))})")
            params.extend(zip_list)
        else:
            where.append("l.zip IN (SELECT rz.zip FROM region_zips rz JOIN regions r ON r.id = rz.region_id WHERE r.is_active = 1)")
        if property_type:
            where.append("l.property_type = ?")
            params.append(property_type)
        pattern = like_pattern(q)
        if pattern:
            where.append("l.address LIKE ? ESCAPE '\\'")
            params.append(pattern)
        if garage_only:
            where.append("(l.has_garage = 1 OR p.property_class IN ('garage', 'parking', 'auto_garage'))")
        rows = conn.execute(
            f"""
            SELECT l.*, d.*, p.property_class, p.assessed_value, p.annual_tax_est, p.is_homestead, p.is_absentee
            FROM listings l
            LEFT JOIN deal_scores d ON d.listing_id = l.listing_id
            LEFT JOIN parcels p ON p.parcel_id = l.parcel_id
            WHERE {' AND '.join(where)}
            ORDER BY {SORTS[sort]}
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return {"max_price": cap, "listings": [dict(row) for row in rows]}


@router.get("/listings/{listing_id}")
def listing_detail(listing_id: str):
    with get_db() as conn:
        listing = conn.execute(
            """
            SELECT l.*, d.* FROM listings l LEFT JOIN deal_scores d ON d.listing_id = l.listing_id
            WHERE l.listing_id = ?
            """,
            (listing_id,),
        ).fetchone()
        if not listing:
            raise HTTPException(404, "Listing not found")
        listing = dict(listing)
        listing["photos"] = json.loads(listing["photos"]) if listing.get("photos") else []
        price_history = [dict(r) for r in conn.execute(
            "SELECT captured_at, list_price, status FROM listing_snapshots WHERE listing_id = ? ORDER BY captured_at",
            (listing_id,),
        )]
        parcel = None
        parcel_history: list = []
        sales_history: list = []
        if listing["parcel_id"]:
            parcel = dict(conn.execute("SELECT * FROM parcels WHERE parcel_id = ?", (listing["parcel_id"],)).fetchone())
            parcel_history = [dict(r) for r in conn.execute(
                "SELECT * FROM parcel_snapshots WHERE parcel_id = ? ORDER BY captured_at", (listing["parcel_id"],))]
        sales_history = [dict(r) for r in conn.execute(
            """
            SELECT sale_date, sale_price, is_valid, source FROM sales
            WHERE parcel_id = ? OR (parcel_id IS NULL AND address = ? AND zip = ?)
            ORDER BY sale_date
            """,
            (listing["parcel_id"], listing["address"], listing["zip"]),
        )]
        zip_values = metric_series(conn, listing["zip"], "zhvi") if listing["zip"] else []
        rent_estimates = [dict(r) for r in conn.execute(
            "SELECT * FROM rent_estimates WHERE listing_id = ?", (listing_id,))]
        comps = [dict(r) for r in conn.execute(
            """
            SELECT s.sale_date, s.sale_price, s.address, p.sqft, p.beds, p.property_class
            FROM sales s LEFT JOIN parcels p ON p.parcel_id = s.parcel_id
            WHERE s.zip = ? AND s.is_valid = 1 AND s.source = 'county' AND s.sale_date >= date('now', '-12 months')
              AND (? IS NULL OR p.property_class = ?)
            ORDER BY ABS(s.sale_price - ?) LIMIT 12
            """,
            (listing["zip"], parcel["property_class"] if parcel else None,
             parcel["property_class"] if parcel else None, listing["list_price"] or 0),
        )]
    return {
        "listing": listing,
        "price_history": price_history,
        "parcel": parcel,
        "parcel_history": parcel_history,
        "sales_history": sales_history,
        "zip_value_series": [{"period": p, "value": v} for p, v in zip_values if p >= "2000-01-01"],
        "rent_estimates": rent_estimates,
        "comps": comps,
        "rentcast": rentcast.budget_status(),
    }


@router.post("/listings/{listing_id}/rent-estimate")
def fetch_rent_estimate(listing_id: str):
    try:
        estimate = rentcast.estimate_rent(listing_id)
    except rentcast.RentcastUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    with get_db() as conn:
        compute_deal_scores(conn, get_settings(conn))
        conn.commit()
    return estimate
