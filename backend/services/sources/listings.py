"""Active, pending and sold listings from Realtor.com via HomeHarvest."""

import json
import logging
import math
import time
from datetime import datetime, timezone

from database import get_db
from services.address import normalize_address
from services.http_fetch import SourceError
from services.sources.base import SourceOutcome, SourceState, SyncContext, to_float

logger = logging.getLogger(__name__)

PAUSE_BETWEEN_CALLS_SECONDS = 2
SOLD_LOOKBACK_DAYS = 365
# Realtor.com occasionally tags rentals as for-sale (e.g. a $1,895 "price"); nothing real sells this low.
MIN_PLAUSIBLE_SALE_PRICE = 10_000
MAX_PHOTOS = 12
# Mobile/manufactured homes and vacant land are excluded from the app entirely.
EXCLUDED_STYLES = {"MOBILE", "MANUFACTURED", "LAND"}
MOBILE_TEXT_MARKERS = ("mobile home", "manufactured home", "mobile/manufactured", "trailer park")

LISTING_COLUMNS = [
    "listing_id", "address", "address_norm", "city", "zip", "property_type", "has_garage", "status",
    "list_price", "list_date", "last_sold_price", "last_sold_date", "estimated_value", "beds", "baths",
    "sqft", "year_built", "lot_sqft", "hoa_fee", "lat", "lon", "url", "photo_url", "photos",
]


def _scrape(location: str, **kwargs) -> list[dict]:
    from homeharvest import scrape_property  # imported lazily: heavy import, only needed during sync

    frame = scrape_property(location=location, **kwargs)
    if frame is None or frame.empty:
        return []
    return frame.to_dict(orient="records")


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    text = str(value)
    return None if text in ("NaT", "nan", "None") else value


def _photo_list(primary, alternates) -> str | None:
    """Primary first, then alternates (HomeHarvest gives a comma-separated string), https only, deduped."""
    urls = []
    for candidate in [_clean(primary), *str(_clean(alternates) or "").split(",")]:
        url = str(candidate or "").strip()
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return json.dumps(urls[:MAX_PHOTOS]) if urls else None


def _is_excluded(record: dict) -> bool:
    style = str(_clean(record.get("style")) or "").upper()
    if style in EXCLUDED_STYLES:
        return True
    description = str(_clean(record.get("text")) or "").lower()
    return any(marker in description for marker in MOBILE_TEXT_MARKERS)


def _date_only(value) -> str | None:
    cleaned = _clean(value)
    return str(cleaned)[:10] if cleaned else None


def _listing_row(record: dict) -> dict | None:
    listing_id = _clean(record.get("property_id"))
    if not listing_id:
        return None
    full_baths = to_float(_clean(record.get("full_baths"))) or 0
    half_baths = to_float(_clean(record.get("half_baths"))) or 0
    garage = to_float(_clean(record.get("parking_garage")))
    address = _clean(record.get("full_street_line")) or _clean(record.get("street"))
    status = (_clean(record.get("status")) or "").lower() or None
    return {
        "listing_id": str(listing_id),
        "address": address,
        "address_norm": normalize_address(address),
        "city": _clean(record.get("city")),
        "zip": str(_clean(record.get("zip_code")) or "").zfill(5) or None,
        "property_type": (_clean(record.get("style")) or "").lower() or None,
        "has_garage": 1 if garage and garage > 0 else 0,
        "status": status,
        "list_price": to_float(_clean(record.get("list_price"))),
        "list_date": _date_only(record.get("list_date")),
        "last_sold_price": to_float(_clean(record.get("last_sold_price"))) or to_float(_clean(record.get("sold_price"))),
        "last_sold_date": _date_only(record.get("last_sold_date")),
        "estimated_value": to_float(_clean(record.get("estimated_value"))),
        "beds": _clean(record.get("beds")),
        "baths": (full_baths + 0.5 * half_baths) or None,
        "sqft": _clean(record.get("sqft")),
        "year_built": _clean(record.get("year_built")),
        "lot_sqft": _clean(record.get("lot_sqft")),
        "hoa_fee": to_float(_clean(record.get("hoa_fee"))),
        "lat": to_float(_clean(record.get("latitude"))),
        "lon": to_float(_clean(record.get("longitude"))),
        "url": _clean(record.get("property_url")),
        "photo_url": _clean(record.get("primary_photo")),
        "photos": _photo_list(record.get("primary_photo"), record.get("alt_photos")),
    }


def run_listings(ctx: SyncContext, state: SourceState) -> SourceOutcome:
    max_price = int(float(ctx.settings.get("max_price") or 250000))
    min_price = int(float(ctx.settings.get("min_price") or 0)) or None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    active: list[dict] = []
    sold: list[dict] = []
    failed_zips: list[str] = []
    for zip_code in ctx.zips:
        try:
            # "for_sale" already includes pending/contingent; passing a list with "pending" drops active ones.
            active.extend(_scrape(zip_code, listing_type="for_sale", price_max=max_price, price_min=min_price))
            time.sleep(PAUSE_BETWEEN_CALLS_SECONDS)
            sold.extend(_scrape(zip_code, listing_type="sold", past_days=SOLD_LOOKBACK_DAYS))
            time.sleep(PAUSE_BETWEEN_CALLS_SECONDS)
        except Exception as exc:  # HomeHarvest raises its own types (blocked, timeouts); keep other ZIPs going
            logger.warning("Listing scrape failed for %s: %s", zip_code, type(exc).__name__)
            failed_zips.append(zip_code)

    if failed_zips and len(failed_zips) == len(ctx.zips):
        raise SourceError("Realtor.com scrape failed for every ZIP (likely rate limited); using cached listings")

    active_rows = [
        row for row in map(_listing_row, (r for r in active if not _is_excluded(r)))
        if row and row["zip"] in ctx.zips and (row["list_price"] or 0) >= MIN_PLAUSIBLE_SALE_PRICE
    ]
    sold_rows = [
        row for row in map(_listing_row, (r for r in sold if not _is_excluded(r)))
        if row and row["zip"] in ctx.zips
    ]

    with get_db() as conn:
        _store_listings(conn, active_rows, now)
        _store_sold(conn, sold_rows)
        scraped_zips = [zip_code for zip_code in ctx.zips if zip_code not in failed_zips]
        _mark_gone(conn, scraped_zips, {row["listing_id"] for row in active_rows}, now)
        conn.commit()

    message = f"{len(active_rows)} active/pending under ${max_price:,}, {len(sold_rows)} sold in last year"
    if failed_zips:
        message += f"; failed ZIPs: {', '.join(failed_zips)}"
    return SourceOutcome(rows=len(active_rows) + len(sold_rows), message=message)


def _store_listings(conn, rows: list[dict], now: str) -> None:
    previous = {
        row["listing_id"]: (row["list_price"], row["status"])
        for row in conn.execute("SELECT listing_id, list_price, status FROM listings")
    }
    placeholders = ", ".join("?" for _ in LISTING_COLUMNS)
    updates = ", ".join(f"{column} = excluded.{column}" for column in LISTING_COLUMNS[1:])
    conn.executemany(
        f"""
        INSERT INTO listings ({', '.join(LISTING_COLUMNS)}, first_seen_at, last_seen_at)
        VALUES ({placeholders}, ?, ?)
        ON CONFLICT (listing_id) DO UPDATE SET {updates}, last_seen_at = excluded.last_seen_at
        """,
        [tuple(row[column] for column in LISTING_COLUMNS) + (now, now) for row in rows],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO listing_snapshots (listing_id, captured_at, list_price, status) VALUES (?, ?, ?, ?)",
        [
            (row["listing_id"], now, row["list_price"], row["status"])
            for row in rows
            if previous.get(row["listing_id"]) != (row["list_price"], row["status"])
        ],
    )


def _store_sold(conn, rows: list[dict]) -> None:
    """Upsert so re-syncs backfill the link and photos on sold records stored before those columns existed."""
    conn.executemany(
        """
        INSERT INTO sales (parcel_id, address, zip, sale_date, sale_price, is_valid, source, address_norm, url, photos)
        VALUES (NULL, ?, ?, ?, ?, 1, 'homeharvest', ?, ?, ?)
        ON CONFLICT (source, address, zip, sale_date, sale_price) WHERE parcel_id IS NULL
        DO UPDATE SET address_norm = excluded.address_norm, url = excluded.url, photos = excluded.photos
        """,
        [
            (row["address"], row["zip"], row["last_sold_date"], row["last_sold_price"],
             row["address_norm"], row["url"], row["photos"])
            for row in rows
            if row["last_sold_date"] and row["last_sold_price"]
        ],
    )


def _mark_gone(conn, scraped_zips: list[str], seen_ids: set[str], now: str) -> None:
    """Listings in a successfully scraped ZIP that no longer appear are off market (sold, withdrawn, or above the cap)."""
    if not scraped_zips:
        return
    placeholders = ", ".join("?" for _ in scraped_zips)
    stale = conn.execute(
        f"SELECT listing_id FROM listings WHERE zip IN ({placeholders}) AND status IN ('for_sale', 'pending', 'contingent')",
        scraped_zips,
    ).fetchall()
    gone = [row["listing_id"] for row in stale if row["listing_id"] not in seen_ids]
    conn.executemany("UPDATE listings SET status = 'off_market' WHERE listing_id = ?", [(i,) for i in gone])
    conn.executemany(
        "INSERT OR IGNORE INTO listing_snapshots (listing_id, captured_at, list_price, status) VALUES (?, ?, NULL, 'off_market')",
        [(i, now) for i in gone],
    )
