"""Removes property types the owner doesn't invest in (mobile homes, vacant land) from every table.

Import already skips them; this purges rows stored before a rule existed or before a parcel was reclassified.
"""

import sqlite3

EXCLUDED_LISTING_TYPES = ("mobile", "manufactured", "land")
CHUNK = 500


def _chunks(values: list[str]):
    for start in range(0, len(values), CHUNK):
        yield values[start:start + CHUNK]


def purge_listings(conn: sqlite3.Connection, listing_ids: list[str]) -> int:
    for chunk in _chunks(listing_ids):
        marks = ",".join("?" * len(chunk))
        for table in ("watchlist", "deal_scores", "listing_snapshots", "rent_estimates"):
            conn.execute(f"DELETE FROM {table} WHERE listing_id IN ({marks})", chunk)
        conn.execute(f"DELETE FROM listings WHERE listing_id IN ({marks})", chunk)
    return len(listing_ids)


def purge_parcels(conn: sqlite3.Connection, parcel_ids: list[str]) -> int:
    for chunk in _chunks(parcel_ids):
        marks = ",".join("?" * len(chunk))
        # Realtor.com sold records for the same address (they carry no parcel id).
        conn.execute(
            f"""
            DELETE FROM sales WHERE parcel_id IS NULL AND EXISTS (
              SELECT 1 FROM parcels p WHERE p.parcel_id IN ({marks})
                AND p.zip = sales.zip AND p.address_norm IS NOT NULL AND p.address_norm = sales.address_norm)
            """,
            chunk,
        )
        conn.execute(f"DELETE FROM watchlist WHERE parcel_id IN ({marks})", chunk)
        conn.execute(f"UPDATE listings SET parcel_id = NULL, match_method = NULL WHERE parcel_id IN ({marks})", chunk)
        for table in ("sales", "parcel_snapshots", "tax_history", "distressed_sales"):
            conn.execute(f"DELETE FROM {table} WHERE parcel_id IN ({marks})", chunk)
        conn.execute(f"DELETE FROM parcels WHERE parcel_id IN ({marks})", chunk)
    return len(parcel_ids)


def purge_excluded(conn: sqlite3.Connection) -> dict[str, int]:
    """Purge everything currently identifiable as excluded. Safe to run repeatedly."""
    listing_ids = [r[0] for r in conn.execute(
        f"""
        SELECT listing_id FROM listings
        WHERE property_type IN ({','.join('?' * len(EXCLUDED_LISTING_TYPES))})
           OR parcel_id IN (SELECT parcel_id FROM parcels WHERE property_class IN ('mobile_home', 'land'))
        """,
        EXCLUDED_LISTING_TYPES,
    )]
    parcel_ids = [r[0] for r in conn.execute(
        "SELECT parcel_id FROM parcels WHERE property_class IN ('mobile_home', 'land')"
    )]
    counts = {"listings": purge_listings(conn, listing_ids), "parcels": purge_parcels(conn, parcel_ids)}
    conn.commit()
    return counts
