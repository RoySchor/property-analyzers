from fastapi import APIRouter

from database import get_db
from services.sync_runner import SOURCES, progress, start_background_sync

router = APIRouter(tags=["sync"])


@router.post("/sync")
def trigger_sync(force: bool = False, source: str | None = None):
    started = start_background_sync(force=force, only=[source] if source else None)
    return {"started": started, "message": None if started else "A sync is already running"}


@router.get("/sync/status")
def sync_status():
    with get_db() as conn:
        rows = {row["source"]: dict(row) for row in conn.execute("SELECT * FROM source_sync")}
    sources = []
    for source in SOURCES:
        row = rows.get(source.name, {})
        sources.append({
            "source": source.name,
            "label": source.label,
            "status": row.get("status") or "never",
            "message": row.get("message"),
            "last_attempt_at": row.get("last_attempt_at"),
            "last_success_at": row.get("last_success_at"),
            "rows_upserted": row.get("rows_upserted"),
            "required_env": source.required_env,
        })
    analysis_row = rows.get("analysis", {})
    sources.append({
        "source": "analysis", "label": "Deal math", "status": analysis_row.get("status") or "never",
        "message": analysis_row.get("message"), "last_attempt_at": analysis_row.get("last_attempt_at"),
        "last_success_at": analysis_row.get("last_success_at"), "rows_upserted": None, "required_env": None,
    })
    return {"progress": progress(), "sources": sources}
