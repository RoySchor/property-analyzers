from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from database import get_db

router = APIRouter(tags=["watchlist"])


class WatchIn(BaseModel):
    listing_id: str | None = None
    parcel_id: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def needs_target(self):
        if not self.listing_id and not self.parcel_id:
            raise ValueError("listing_id or parcel_id is required")
        return self


@router.get("/watchlist")
def list_watchlist():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT w.*, l.address, l.zip, l.list_price, l.status, l.url, d.score, d.monthly_cashflow,
                   p.address AS parcel_address, p.last_sale_price, p.last_sale_date
            FROM watchlist w
            LEFT JOIN listings l ON l.listing_id = w.listing_id
            LEFT JOIN deal_scores d ON d.listing_id = w.listing_id
            LEFT JOIN parcels p ON p.parcel_id = COALESCE(w.parcel_id, l.parcel_id)
            ORDER BY w.created_at DESC
            """
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/watchlist", status_code=201)
def add_to_watchlist(body: WatchIn):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO watchlist (listing_id, parcel_id, notes) VALUES (?, ?, ?)",
            (body.listing_id, body.parcel_id, body.notes),
        )
        conn.commit()
    return {"id": cursor.lastrowid}


@router.delete("/watchlist/{item_id}")
def remove_from_watchlist(item_id: int):
    with get_db() as conn:
        deleted = conn.execute("DELETE FROM watchlist WHERE id = ?", (item_id,)).rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(404, "Watchlist item not found")
    return {"deleted": item_id}
