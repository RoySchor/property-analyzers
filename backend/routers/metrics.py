from fastapi import APIRouter, HTTPException, Query

from database import get_db

router = APIRouter(tags=["metrics"])

MAX_SERIES = 40


@router.get("/metrics")
def get_metrics(
    geo_ids: str = Query(..., description="Comma-separated ZIPs, or 'US' for the mortgage rate"),
    metrics: str = Query(..., description="Comma-separated metric names, e.g. zhvi,zori"),
    start: str | None = Query(None, description="YYYY-MM-DD"),
):
    geo_list = [g.strip() for g in geo_ids.split(",") if g.strip()]
    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]
    if not geo_list or not metric_list or len(geo_list) * len(metric_list) > MAX_SERIES:
        raise HTTPException(400, f"Provide 1–{MAX_SERIES} geo/metric combinations")
    query = f"""
        SELECT source, geo_type, geo_id, metric, period, value FROM market_metrics
        WHERE geo_id IN ({','.join('?' * len(geo_list))}) AND metric IN ({','.join('?' * len(metric_list))})
    """
    params: list = [*geo_list, *metric_list]
    if start:
        query += " AND period >= ?"
        params.append(start)
    with get_db() as conn:
        rows = conn.execute(query + " ORDER BY period", params).fetchall()
    series: dict[str, dict] = {}
    for row in rows:
        key = f"{row['geo_id']}:{row['metric']}"
        entry = series.setdefault(key, {
            "geo_id": row["geo_id"], "geo_type": row["geo_type"], "metric": row["metric"],
            "source": row["source"], "points": [],
        })
        entry["points"].append({"period": row["period"], "value": row["value"]})
    return {"series": list(series.values())}


@router.get("/metrics/catalog")
def metric_catalog():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT metric, source, geo_type, COUNT(DISTINCT geo_id) AS geos, MIN(period) AS first_period,
                   MAX(period) AS last_period
            FROM market_metrics GROUP BY metric, source, geo_type ORDER BY metric
            """
        ).fetchall()
    return {"metrics": [dict(row) for row in rows]}


@router.get("/metrics/sales-trend")
def sales_trend(zips: str, max_price: float | None = None):
    """Monthly median valid county sale price and count, from parcel data (for under-cap trend lines)."""
    zip_list = [z.strip() for z in zips.split(",") if z.strip()]
    if not zip_list:
        raise HTTPException(400, "zips is required")
    query = f"""
        SELECT substr(sale_date, 1, 7) AS month, sale_price FROM sales
        WHERE source = 'county' AND is_valid = 1 AND zip IN ({','.join('?' * len(zip_list))})
          AND sale_date >= '2000-01-01'
    """
    params: list = list(zip_list)
    if max_price:
        query += " AND sale_price <= ?"
        params.append(max_price)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    by_month: dict[str, list[float]] = {}
    for row in rows:
        by_month.setdefault(row["month"], []).append(row["sale_price"])
    points = []
    for month in sorted(by_month):
        prices = sorted(by_month[month])
        points.append({"period": f"{month}-01", "median": prices[len(prices) // 2], "count": len(prices)})
    return {"points": points}
