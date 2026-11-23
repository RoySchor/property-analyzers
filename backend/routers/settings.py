from fastapi import APIRouter, HTTPException

from database import get_db, get_settings
from services.analysis import compute_deal_scores, current_mortgage_rate
from services.rentcast import budget_status

router = APIRouter(tags=["settings"])

NUMERIC_KEYS = {
    "max_price", "min_price", "down_payment_pct", "investor_rate_premium_pct", "loan_years", "closing_cost_pct",
    "vacancy_pct", "maintenance_pct", "capex_pct", "management_pct", "insurance_annual", "fallback_tax_rate_pct",
}
OPTIONAL_NUMERIC_KEYS = {"interest_rate_pct"}


@router.get("/settings")
def read_settings():
    with get_db() as conn:
        settings = get_settings(conn)
        effective_rate = current_mortgage_rate(conn, settings)
    return {
        "settings": settings,
        "effective_interest_rate_pct": round(effective_rate, 3),
        "rentcast": budget_status(),
    }


@router.put("/settings")
def update_settings(values: dict[str, str]):
    unknown = set(values) - NUMERIC_KEYS - OPTIONAL_NUMERIC_KEYS
    if unknown:
        raise HTTPException(400, f"Unknown settings: {', '.join(sorted(unknown))}")
    for key, value in values.items():
        text = str(value).strip()
        if key in OPTIONAL_NUMERIC_KEYS and text == "":
            continue
        try:
            number = float(text)
        except ValueError as exc:
            raise HTTPException(400, f"{key} must be a number") from exc
        if number < 0:
            raise HTTPException(400, f"{key} cannot be negative")
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [(key, str(value).strip()) for key, value in values.items()],
        )
        settings = get_settings(conn)
        compute_deal_scores(conn, settings)
        conn.commit()
    return read_settings()
