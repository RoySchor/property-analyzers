"""Market-level time series: Zillow Research, Realtor.com Research, FRED."""

import csv
from collections.abc import Iterable

import requests

from database import get_db
from services.http_fetch import conditional_stream, get_text, iter_lines
from services.sources.base import SourceOutcome, SourceState, SyncContext, to_float, upsert_metrics

ZILLOW_BASE = "https://files.zillowstatic.com/research/public_csvs/"
REALTOR_BASE = "https://econdata.s3-us-west-2.amazonaws.com/Reports/Core/"
REALTOR_ZIP_FILE = "RDC_Inventory_Core_Metrics_Zip_History.csv"

# ZIP-level only: metro-wide and national aggregates are intentionally not synced.
ZILLOW_FILES = {
    "zillow_zhvi_zip": ("zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv", "zhvi"),
    "zillow_zhvi_bottom_zip": ("zhvi/Zip_zhvi_uc_sfrcondo_tier_0.0_0.33_sm_sa_month.csv", "zhvi_bottom_tier"),
    "zillow_zori_zip": ("zori/Zip_zori_uc_sfrcondomfr_sm_month.csv", "zori"),
}

REALTOR_METRICS = (
    "median_listing_price",
    "active_listing_count",
    "median_days_on_market",
    "new_listing_count",
    "price_reduced_share",
    "pending_listing_count",
    "median_listing_price_per_square_foot",
    "pending_ratio",
)

FRED_SERIES = {
    "MORTGAGE30US": ("mortgage_30y", "national", "US"),      # Freddie Mac weekly 30-year fixed
}


def make_zillow_runner(source_name: str):
    path, metric = ZILLOW_FILES[source_name]

    def run(ctx: SyncContext, state: SourceState) -> SourceOutcome:
        result = conditional_stream(ZILLOW_BASE + path, state.etag, state.last_modified)
        if result.unchanged:
            return SourceOutcome(unchanged=True, etag=result.etag, last_modified=result.last_modified)
        wanted = set(ctx.zips)
        rows: list[tuple] = []
        with result.response as response:
            reader = csv.reader(iter_lines(response))
            header = next(reader)
            date_columns = [(index, name) for index, name in enumerate(header) if name[:2] in ("19", "20")]
            name_index = header.index("RegionName")
            for record in reader:
                zip_code = record[name_index].zfill(5)
                if zip_code in wanted:
                    rows.extend(_wide_to_rows("zillow", "zip", zip_code, metric, record, date_columns))
        with get_db() as conn:
            count = upsert_metrics(conn, rows)
        return SourceOutcome(rows=count, etag=result.etag, last_modified=result.last_modified)

    return run


def _wide_to_rows(source: str, geo_type: str, geo_id: str, metric: str, record: list[str], date_columns) -> Iterable[tuple]:
    for index, period in date_columns:
        if index >= len(record):
            continue
        value = to_float(record[index])
        if value is not None:
            yield (source, geo_type, geo_id, metric, period[:7] + "-01", value)


def run_realtor_zip(ctx: SyncContext, state: SourceState) -> SourceOutcome:
    result = conditional_stream(REALTOR_BASE + REALTOR_ZIP_FILE, state.etag, state.last_modified)
    if result.unchanged:
        return SourceOutcome(unchanged=True, etag=result.etag, last_modified=result.last_modified)
    wanted = set(ctx.zips)
    rows: list[tuple] = []
    with result.response as response:
        reader = csv.reader(iter_lines(response))
        header = next(reader)
        month_index = header.index("month_date_yyyymm")
        key_index = header.index("postal_code")
        metric_indexes = [(header.index(m), m) for m in REALTOR_METRICS if m in header]
        for record in reader:
            if len(record) <= key_index:
                continue
            geo_id = record[key_index].strip().zfill(5)
            if geo_id not in wanted:
                continue
            month = record[month_index].strip()
            if len(month) != 6 or not month.isdigit():
                continue  # the file ends with a footnote row
            period = f"{month[:4]}-{month[4:]}-01"
            for index, metric in metric_indexes:
                value = to_float(record[index]) if index < len(record) else None
                if value is not None:
                    rows.append(("realtor", "zip", geo_id, metric, period, value))
    with get_db() as conn:
        count = upsert_metrics(conn, rows)
    return SourceOutcome(rows=count, etag=result.etag, last_modified=result.last_modified)


def run_fred(ctx: SyncContext, state: SourceState) -> SourceOutcome:
    rows: list[tuple] = []
    for series_id, (metric, geo_type, geo_id) in FRED_SERIES.items():
        # FRED stalls requests that send a custom User-Agent, so use the library default here.
        text = get_text(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
            headers={"User-Agent": requests.utils.default_user_agent()},
        )
        reader = csv.reader(text.splitlines())
        next(reader, None)
        for record in reader:
            if len(record) < 2:
                continue
            value = to_float(record[1])
            if value is not None:
                rows.append(("fred", geo_type, geo_id, metric, record[0], value))
    with get_db() as conn:
        count = upsert_metrics(conn, rows)
    return SourceOutcome(rows=count, message=f"{len(FRED_SERIES)} series")
