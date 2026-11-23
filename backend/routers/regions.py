import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from database import get_db
from services.sources.county import SUPPORTED_COUNTIES
from services.sync_runner import start_background_sync

router = APIRouter(tags=["regions"])


class RegionIn(BaseModel):
    name: str
    zips: list[str]
    counties: list[str] = []
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("zips")
    @classmethod
    def valid_zips(cls, value: list[str]) -> list[str]:
        cleaned = sorted({zip_code.strip() for zip_code in value if zip_code.strip()})
        if not cleaned:
            raise ValueError("At least one ZIP is required")
        bad = [zip_code for zip_code in cleaned if not re.fullmatch(r"\d{5}", zip_code)]
        if bad:
            raise ValueError(f"Invalid ZIP codes: {', '.join(bad)}")
        return cleaned

    @field_validator("counties")
    @classmethod
    def supported_counties(cls, value: list[str]) -> list[str]:
        unsupported = [fips for fips in value if fips not in SUPPORTED_COUNTIES]
        if unsupported:
            raise ValueError(f"No parcel adapter for counties: {', '.join(unsupported)}")
        return sorted(set(value))


def _load_regions(conn) -> list[dict]:
    regions = [dict(row) for row in conn.execute("SELECT * FROM regions ORDER BY is_default DESC, name")]
    for region in regions:
        region["zips"] = [r["zip"] for r in conn.execute(
            "SELECT zip FROM region_zips WHERE region_id = ? ORDER BY zip", (region["id"],))]
        region["counties"] = [r["county_fips"] for r in conn.execute(
            "SELECT county_fips FROM region_counties WHERE region_id = ? ORDER BY county_fips", (region["id"],))]
        region["is_active"] = bool(region["is_active"])
        region["is_default"] = bool(region["is_default"])
    return regions


@router.get("/regions")
def list_regions():
    with get_db() as conn:
        return {"regions": _load_regions(conn), "supported_counties": SUPPORTED_COUNTIES}


def _save_children(conn, region_id: int, body: RegionIn) -> None:
    conn.execute("DELETE FROM region_zips WHERE region_id = ?", (region_id,))
    conn.execute("DELETE FROM region_counties WHERE region_id = ?", (region_id,))
    conn.executemany("INSERT INTO region_zips (region_id, zip) VALUES (?, ?)", [(region_id, z) for z in body.zips])
    conn.executemany(
        "INSERT INTO region_counties (region_id, county_fips) VALUES (?, ?)", [(region_id, c) for c in body.counties]
    )


@router.post("/regions", status_code=201)
def create_region(body: RegionIn):
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM regions WHERE name = ?", (body.name,)).fetchone():
            raise HTTPException(409, f"A region named {body.name!r} already exists")
        cursor = conn.execute("INSERT INTO regions (name, is_active) VALUES (?, ?)", (body.name, int(body.is_active)))
        _save_children(conn, cursor.lastrowid, body)
        conn.commit()
    start_background_sync()  # pull data for the new ZIPs right away
    return {"id": cursor.lastrowid}


@router.put("/regions/{region_id}")
def update_region(region_id: int, body: RegionIn):
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM regions WHERE id = ?", (region_id,)).fetchone():
            raise HTTPException(404, "Region not found")
        conn.execute("UPDATE regions SET name = ?, is_active = ? WHERE id = ?", (body.name, int(body.is_active), region_id))
        _save_children(conn, region_id, body)
        conn.commit()
    start_background_sync()
    return {"id": region_id}


@router.delete("/regions/{region_id}")
def delete_region(region_id: int):
    with get_db() as conn:
        region = conn.execute("SELECT is_default FROM regions WHERE id = ?", (region_id,)).fetchone()
        if not region:
            raise HTTPException(404, "Region not found")
        if region["is_default"]:
            raise HTTPException(400, "Default regions can be deactivated but not deleted")
        conn.execute("DELETE FROM regions WHERE id = ?", (region_id,))
        conn.commit()
    return {"deleted": region_id}
