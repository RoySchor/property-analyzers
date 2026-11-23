"""Census ACS and HUD Fair Market Rents. Both need free keys; the runner skips them until keys are set."""

import os
from datetime import date

from database import get_db
from services.http_fetch import SourceError, get_json
from services.sources.base import SourceOutcome, SourceState, SyncContext, to_float, upsert_metrics

ACS_VARIABLES = {
    "B25064_001E": "median_gross_rent",
    "B25077_001E": "median_home_value",
    "B19013_001E": "median_household_income",
    "B01003_001E": "population",
    "B25002_001E": "housing_units",
    "B25002_003E": "vacant_units",
    "B25003_001E": "occupied_units",
    "B25003_003E": "renter_occupied_units",
}
ACS_FIRST_YEAR = 2015


def run_census(ctx: SyncContext, state: SourceState) -> SourceOutcome:
    api_key = os.environ["CENSUS_API_KEY"]
    rows: list[tuple] = []
    years_loaded = []
    # ACS 5-year data is released each December for the year two years prior.
    for year in range(ACS_FIRST_YEAR, date.today().year):
        params = {
            "get": ",".join(ACS_VARIABLES),
            "for": f"zip code tabulation area:{','.join(ctx.zips)}",
            "key": api_key,
        }
        if year <= 2019:
            params["in"] = "state:42"  # older vintages nest ZCTAs under state
        try:
            payload = get_json(f"https://api.census.gov/data/{year}/acs/acs5", params=params, retries=1)
        except SourceError:
            continue  # vintage not published yet
        if not isinstance(payload, list) or len(payload) < 2:
            continue
        header = payload[0]
        zcta_index = header.index("zip code tabulation area")
        for record in payload[1:]:
            zip_code = record[zcta_index]
            values = {ACS_VARIABLES[var]: to_float(record[header.index(var)]) for var in ACS_VARIABLES}
            values = {k: v for k, v in values.items() if v is not None and v >= 0}  # Census uses negatives for N/A
            if values.get("housing_units") and "vacant_units" in values:
                values["vacancy_rate"] = values["vacant_units"] / values["housing_units"]
            if values.get("occupied_units") and "renter_occupied_units" in values:
                values["renter_share"] = values["renter_occupied_units"] / values["occupied_units"]
            for metric, value in values.items():
                rows.append(("census", "zip", zip_code, metric, f"{year}-01-01", value))
        years_loaded.append(year)
    if not years_loaded:
        raise SourceError("No ACS vintages returned; check CENSUS_API_KEY")
    with get_db() as conn:
        count = upsert_metrics(conn, rows)
    return SourceOutcome(rows=count, message=f"ACS {years_loaded[0]}–{years_loaded[-1]}")


HUD_BASE = "https://www.huduser.gov/hudapi/public/fmr"
HUD_BEDROOM_FIELDS = {
    "Efficiency": "fmr_0br", "One-Bedroom": "fmr_1br", "Two-Bedroom": "fmr_2br",
    "Three-Bedroom": "fmr_3br", "Four-Bedroom": "fmr_4br",
}


def run_hud(ctx: SyncContext, state: SourceState) -> SourceOutcome:
    headers = {"Authorization": f"Bearer {os.environ['HUD_API_TOKEN']}"}
    rows: list[tuple] = []
    wanted = set(ctx.zips)
    for county_fips in ctx.counties:
        payload = get_json(f"{HUD_BASE}/data/{county_fips}99999", headers=headers)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        year = str(data.get("year") or date.today().year)
        period = f"{year}-01-01"
        basic = data.get("basicdata")
        entries = basic if isinstance(basic, list) else [basic] if isinstance(basic, dict) else []
        for entry in entries:
            zip_code = str(entry.get("zip_code") or "")
            if zip_code.isdigit():
                if zip_code not in wanted:
                    continue
                geo_type, geo_id = "zip", zip_code
            else:
                geo_type, geo_id = "county", county_fips  # county/metro-wide FMR when no ZIP-level SAFMR
            for field, metric in HUD_BEDROOM_FIELDS.items():
                value = to_float(entry.get(field))
                if value is not None:
                    rows.append(("hud", geo_type, geo_id, metric, period, value))
    with get_db() as conn:
        count = upsert_metrics(conn, rows)
    return SourceOutcome(rows=count, message=f"{len(ctx.counties)} counties")
