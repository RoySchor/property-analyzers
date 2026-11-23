"""County parcel adapters (ArcGIS REST). Each returns normalized parcel dicts; `store_parcels` handles snapshots."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from database import PROJECT_ROOT, get_db
from services.address import normalize_address
from services.exclusions import purge_parcels
from services.http_fetch import SourceError, get_json
from services.sources.base import SourceOutcome, SourceState, SyncContext, to_float

PAGE_SIZE = 1000
WORKERS = 4

NORTHAMPTON = "42095"
LEHIGH = "42077"
NORTHAMPTON_URL = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer"
LEHIGH_URL = "https://services1.arcgis.com/XWDNR4PQlDQwrRCL/ArcGIS/rest/services/ATestParcel/FeatureServer"

SUPPORTED_COUNTIES = {NORTHAMPTON: "Northampton", LEHIGH: "Lehigh"}

# Sales under this are transfers (family, $1 deeds) rather than market sales.
MIN_MARKET_SALE = 10_000


def _load_millage() -> dict:
    path = PROJECT_ROOT / "config" / "millage.json"
    return json.loads(Path(path).read_text())


def fetch_layer(layer_url: str, out_fields: list[str], where: str = "1=1") -> list[dict]:
    """Page through an ArcGIS layer in parallel. Fails loudly if any page fails so a partial pull never lands."""
    count = get_json(f"{layer_url}/query", params={"where": where, "returnCountOnly": "true", "f": "json"})
    if "count" not in count:
        raise SourceError(f"Unexpected count response from {layer_url}")
    offsets = range(0, count["count"], PAGE_SIZE)

    def fetch_page(offset: int) -> list[dict]:
        payload = get_json(
            f"{layer_url}/query",
            params={
                "where": where,
                "outFields": ",".join(out_fields),
                "returnGeometry": "false",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            },
        )
        if "error" in payload:
            raise SourceError(f"ArcGIS error from {layer_url}: {payload['error'].get('message')}")
        return [feature["attributes"] for feature in payload.get("features", [])]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pages = list(pool.map(fetch_page, offsets))
    records = [record for page in pages for record in page]
    if len(records) < count["count"] * 0.98:
        raise SourceError(f"Incomplete pull from {layer_url}: {len(records)} of {count['count']}")
    return records


# --- Classification -------------------------------------------------------------------------

# Out of scope for this tool (not investment targets); parcels in these classes are never stored.
EXCLUDED_CLASSES = {"mobile_home", "land"}

# Northampton: 171-173 mobile home (owned land / rented land / in park), 175-177 mobile home parks.
# Lehigh: 1220 mobile home on own land, 1221 in a park (inferred from the data; no official code table found).
MOBILE_HOME_CODES_NORTHAMPTON = {"171", "172", "173", "175", "176", "177"}
MOBILE_HOME_CODES_LEHIGH = {"1220", "1221"}
VACANT_CODES_NORTHAMPTON = {"90", "92", "93", "94", "95", "96", "97", "98", "99", "200"}


def _no_building(building_value: float | None) -> bool:
    """Vacant land = the county puts $0 on the building. Unknown (None) is not treated as vacant."""
    return building_value is not None and building_value <= 0


def classify_northampton(luc: str | None, building_value: float | None = None) -> str:
    code = (luc or "").strip()
    # Garages, parking and storage first: a parking lot has no building but is wanted on the Garages page.
    if code in MOBILE_HOME_CODES_NORTHAMPTON:
        return "mobile_home"
    if code == "180":
        return "garage"          # auxiliary improvements: detached garages / outbuildings on their own parcel
    if code in ("567", "568"):
        return "parking"
    if code == "562":
        return "auto_garage"     # commercial repair shop or garage
    if code == "710":
        return "storage"
    if code in VACANT_CODES_NORTHAMPTON or _no_building(building_value):
        return "land"
    if code in ("110", "210"):
        return "single_family"
    if code in ("120", "300", "301", "302", "303"):
        return "multi_family"
    if code in ("160", "402", "502", "505"):
        return "mixed_use"
    if code in ("151", "152"):
        return "condo"
    if code[:1] in ("3", "4", "5", "7"):
        return "commercial"
    return "other"


def classify_lehigh(use_code: str | None, units: int | None, building_value: float | None = None) -> str:
    code = (use_code or "").strip()
    if code in MOBILE_HOME_CODES_LEHIGH:   # checked first: a park parcel can carry several units
        return "mobile_home"
    if code == "1110":
        # Residential with no living units; 478 of 495 carry a building, so treated as garages/outbuildings.
        return "land" if _no_building(building_value) else "garage"
    if _no_building(building_value):
        return "land"
    if units and units >= 2 and code.startswith("1"):
        return "multi_family"
    if code in ("1101", "1102", "1103", "1104"):
        return "single_family"
    if code in ("1108",) or code.startswith("114"):
        return "multi_family"
    if code.startswith("119"):
        return "condo"
    if code[:1] in ("2", "3", "4", "5"):
        return "commercial"
    return "other"


# --- Northampton ----------------------------------------------------------------------------

NORTHAMPTON_PARCEL_FIELDS = [
    "CAMA_ID", "MUNI", "SCHDIST", "LOCATION", "LUC", "TOTAL_VALUE", "TOTAL_ASSESSED_VALUE",
    "SALE_PRICE", "SALE_DATE", "SALE_VALIDITY_CODE", "SQFT_LIVING_AREA", "OWNERS_NAME_1",
    "MAIL_ADDRESS_1", "MAIL_ADDRESS_3", "FLAG_3_HMSTD", "YEAR_BUILT", "RES_YEAR_BUILT",
    "NUMBER_OF_BEDROOMS", "NUMBER_OF_BATHS", "NUMBER_HALF_BATHS", "BLDG_VALUE",
]


def _clean_id(value: str | None) -> str | None:
    return " ".join(value.split()) if value else None


def fetch_northampton() -> list[dict]:
    address_points = fetch_layer(f"{NORTHAMPTON_URL}/6", ["CAMAID", "Zip"])
    zip_by_cama = {}
    for point in address_points:
        cama_id = _clean_id(point.get("CAMAID"))
        if cama_id and point.get("Zip"):
            zip_by_cama.setdefault(cama_id, point["Zip"].strip()[:5])

    millage = _load_millage().get(NORTHAMPTON, {}).get("muni_total_mills", {})
    parcels = []
    for record in fetch_layer(f"{NORTHAMPTON_URL}/0", NORTHAMPTON_PARCEL_FIELDS):
        cama_id = _clean_id(record.get("CAMA_ID"))
        if not cama_id:
            continue
        address = (record.get("LOCATION") or "").strip() or None
        sale_price = to_float(record.get("SALE_PRICE"))
        sale_date = _epoch_ms_to_date(record.get("SALE_DATE"))
        assessed = to_float(record.get("TOTAL_ASSESSED_VALUE"))
        market = to_float(record.get("TOTAL_VALUE"))
        muni = (record.get("MUNI") or "").strip()
        mills = millage.get(muni, {}).get("mills")
        baths = to_float(record.get("NUMBER_OF_BATHS"))
        half_baths = to_float(record.get("NUMBER_HALF_BATHS"))
        address_norm = normalize_address(address)
        parcels.append({
            "parcel_id": f"{NORTHAMPTON}:{cama_id}",
            "county_fips": NORTHAMPTON,
            "address": address,
            "address_norm": address_norm,
            "zip": zip_by_cama.get(cama_id),
            "muni": muni,
            "land_use_code": record.get("LUC"),
            "property_class": classify_northampton(record.get("LUC"), to_float(record.get("BLDG_VALUE"))),
            "units": None,
            "beds": record.get("NUMBER_OF_BEDROOMS") or None,
            "baths": (baths or 0) + 0.5 * (half_baths or 0) if baths is not None else None,
            "sqft": record.get("SQFT_LIVING_AREA") or None,
            "year_built": record.get("RES_YEAR_BUILT") or record.get("YEAR_BUILT") or None,
            "lat": None,
            "lon": None,
            "owner_name": record.get("OWNERS_NAME_1"),
            "owner_mail": " ".join(filter(None, [record.get("MAIL_ADDRESS_1"), record.get("MAIL_ADDRESS_3")])) or None,
            "is_homestead": 1 if record.get("FLAG_3_HMSTD") else 0,
            "is_absentee": _is_absentee(address_norm, record.get("MAIL_ADDRESS_1")),
            "assessed_value": assessed,
            "market_value": market,
            "last_sale_price": sale_price,
            "last_sale_date": sale_date,
            "last_sale_valid": _is_valid_sale(sale_price, record.get("SALE_VALIDITY_CODE") == "0"),
            "annual_tax_est": round(assessed * mills / 1000, 2) if assessed and mills else None,
        })
    return parcels


# --- Lehigh ---------------------------------------------------------------------------------

LEHIGH_OWNER_FIELDS = [
    "PIN", "ADDRESS", "USELAND", "UNITS", "SMON", "SYEAR", "SPRICE", "NAMOWN", "AD1OWN", "ZIPOWN",
    "TOTAPR", "TOTASMT", "LAT", "LONG", "DIST", "TAXBLD",
]


def fetch_lehigh() -> list[dict]:
    boundaries = fetch_layer(f"{LEHIGH_URL}/1", ["PIN", "SITUS_ZIP"])
    zip_by_pin = {row["PIN"]: (row.get("SITUS_ZIP") or "").strip()[:5] or None for row in boundaries if row.get("PIN")}

    parcels = []
    for record in fetch_layer(f"{LEHIGH_URL}/0", LEHIGH_OWNER_FIELDS):
        pin = (record.get("PIN") or "").strip()
        if not pin:
            continue
        address = (record.get("ADDRESS") or "").strip() or None
        address_norm = normalize_address(address)
        units = _to_int(record.get("UNITS"))
        sale_price = to_float(record.get("SPRICE"))
        sale_date = _lehigh_sale_date(record.get("SYEAR"), record.get("SMON"))
        market = to_float(record.get("TOTAPR"))
        parcels.append({
            "parcel_id": f"{LEHIGH}:{pin}",
            "county_fips": LEHIGH,
            "address": address,
            "address_norm": address_norm,
            "zip": zip_by_pin.get(pin),
            "muni": (record.get("DIST") or "").strip() or None,
            "land_use_code": record.get("USELAND"),
            "property_class": classify_lehigh(record.get("USELAND"), units, to_float(record.get("TAXBLD"))),
            "units": units,
            "beds": None,
            "baths": None,
            "sqft": None,
            "year_built": None,
            "lat": to_float(record.get("LAT")),
            "lon": to_float(record.get("LONG")),
            "owner_name": record.get("NAMOWN"),
            "owner_mail": " ".join(filter(None, [record.get("AD1OWN"), record.get("ZIPOWN")])) or None,
            "is_homestead": None,
            "is_absentee": _is_absentee(address_norm, record.get("AD1OWN")),
            "assessed_value": to_float(record.get("TOTASMT")),
            "market_value": market,
            "last_sale_price": sale_price,
            "last_sale_date": sale_date,
            "last_sale_valid": _is_valid_sale(sale_price, True),
            "annual_tax_est": None,   # Lehigh millage not yet configured; deal math falls back to the estimate rate
        })
    return parcels


# --- Storage --------------------------------------------------------------------------------

PARCEL_COLUMNS = [
    "parcel_id", "county_fips", "address", "address_norm", "zip", "muni", "land_use_code", "property_class",
    "units", "beds", "baths", "sqft", "year_built", "lat", "lon", "owner_name", "owner_mail", "is_homestead",
    "is_absentee", "assessed_value", "market_value", "last_sale_price", "last_sale_date", "last_sale_valid",
    "annual_tax_est",
]
SNAPSHOT_FIELDS = ("last_sale_price", "last_sale_date", "assessed_value", "market_value", "owner_name")


def store_parcels(conn: sqlite3.Connection, parcels: list[dict]) -> tuple[int, int]:
    """Upsert parcels; append a snapshot and a sale only when something changed. Returns (parcels, changes)."""
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")  # snapshot PK; must not collide
    previous = {
        row["parcel_id"]: row
        for row in conn.execute(
            f"SELECT parcel_id, {', '.join(SNAPSHOT_FIELDS)} FROM parcels WHERE county_fips = ?",
            (parcels[0]["county_fips"],),
        )
    } if parcels else {}

    placeholders = ", ".join("?" for _ in PARCEL_COLUMNS)
    updates = ", ".join(f"{column} = excluded.{column}" for column in PARCEL_COLUMNS[1:])
    conn.executemany(
        f"""
        INSERT INTO parcels ({', '.join(PARCEL_COLUMNS)}, updated_at) VALUES ({placeholders}, ?)
        ON CONFLICT (parcel_id) DO UPDATE SET {updates}, updated_at = excluded.updated_at
        """,
        [tuple(parcel[column] for column in PARCEL_COLUMNS) + (now,) for parcel in parcels],
    )

    snapshots, sales = [], []
    for parcel in parcels:
        before = previous.get(parcel["parcel_id"])
        if before is not None and all(before[field] == parcel[field] for field in SNAPSHOT_FIELDS):
            continue
        snapshots.append((
            parcel["parcel_id"], now, parcel["last_sale_price"], parcel["last_sale_date"],
            parcel["last_sale_valid"], parcel["assessed_value"], parcel["market_value"], parcel["owner_name"],
        ))
        if parcel["last_sale_date"] and parcel["last_sale_price"]:
            sales.append((
                parcel["parcel_id"], parcel["address"], parcel["zip"], parcel["last_sale_date"],
                parcel["last_sale_price"], parcel["last_sale_valid"], parcel["address_norm"],
            ))
    conn.executemany(
        """
        INSERT OR IGNORE INTO parcel_snapshots
          (parcel_id, captured_at, sale_price, sale_date, sale_valid, assessed_value, market_value, owner_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        snapshots,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO sales (parcel_id, address, zip, sale_date, sale_price, is_valid, address_norm, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'county')
        """,
        sales,
    )
    conn.commit()
    return len(parcels), len(snapshots)


def make_county_runner(county_fips: str):
    fetcher = {NORTHAMPTON: fetch_northampton, LEHIGH: fetch_lehigh}[county_fips]

    def run(ctx: SyncContext, state: SourceState) -> SourceOutcome:
        if county_fips not in ctx.counties:
            return SourceOutcome(unchanged=True, message="No active region uses this county")
        fetched = fetcher()
        parcels = [parcel for parcel in fetched if parcel["property_class"] not in EXCLUDED_CLASSES]
        excluded_ids = [parcel["parcel_id"] for parcel in fetched if parcel["property_class"] in EXCLUDED_CLASSES]
        with get_db() as conn:
            total, changed = store_parcels(conn, parcels)
            removed = purge_parcels(conn, excluded_ids)  # drops any stored before they were reclassified
            conn.commit()
        return SourceOutcome(
            rows=total,
            message=f"{total:,} parcels, {changed:,} new or changed; {removed:,} mobile-home/land parcels skipped",
        )

    return run


# --- Helpers --------------------------------------------------------------------------------

def _epoch_ms_to_date(value) -> str | None:
    if value in (None, 0):
        return None
    try:
        return _not_future(datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat())
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def _lehigh_sale_date(year, month) -> str | None:
    year_int = _to_int(year)
    month_int = _to_int(month) or 1
    if not year_int or year_int < 1900:
        return None
    return _not_future(f"{year_int:04d}-{min(max(month_int, 1), 12):02d}-01")


def _not_future(iso_date: str) -> str | None:
    """County data occasionally carries keying errors with future sale dates; drop them."""
    return iso_date if iso_date <= datetime.now(timezone.utc).date().isoformat() else None


def _to_int(value) -> int | None:
    try:
        return int(str(value).strip()) if value not in (None, "") else None
    except ValueError:
        return None


def _is_absentee(site_norm: str | None, mail_line: str | None) -> int | None:
    mail_norm = normalize_address(mail_line)
    if not site_norm or not mail_norm:
        return None
    return 0 if site_norm == mail_norm else 1


def _is_valid_sale(price: float | None, county_says_valid: bool) -> int:
    if not price or price < MIN_MARKET_SALE or not county_says_valid:
        return 0
    return 1
