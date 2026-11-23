"""Helpers for free-text search boxes."""

MAX_QUERY_LENGTH = 100


def like_pattern(query: str | None) -> str | None:
    """'12 main' -> '%12 main%' with LIKE wildcards in the user's text escaped. None when blank.

    Use with `... LIKE ? ESCAPE '\\'`. SQLite LIKE is case-insensitive for ASCII.
    """
    if not query:
        return None
    text = " ".join(query.split())[:MAX_QUERY_LENGTH]
    if not text:
        return None
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
