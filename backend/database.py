import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def db_path() -> str:
    configured = os.getenv("DB_PATH")
    if not configured:
        return str(PROJECT_ROOT / "data" / "property.db")
    path = Path(configured)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def run_migrations():
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(migration.stem.split("_")[0])
            if version <= current:
                continue
            conn.executescript(migration.read_text())
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
            print(f"Applied migration {migration.name}")


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


def tracked_zips(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT rz.zip FROM region_zips rz
        JOIN regions r ON r.id = rz.region_id
        WHERE r.is_active = 1 ORDER BY rz.zip
        """
    ).fetchall()
    return [row["zip"] for row in rows]


def tracked_counties(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT rc.county_fips FROM region_counties rc
        JOIN regions r ON r.id = rc.region_id
        WHERE r.is_active = 1 ORDER BY rc.county_fips
        """
    ).fetchall()
    return [row["county_fips"] for row in rows]
