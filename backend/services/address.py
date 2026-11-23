"""Address normalization so county parcels and listings can be matched on a common key."""

import re

SUFFIXES = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR", "LANE": "LN",
    "BOULEVARD": "BLVD", "COURT": "CT", "PLACE": "PL", "TERRACE": "TER", "CIRCLE": "CIR",
    "HIGHWAY": "HWY", "PARKWAY": "PKWY", "ALLEY": "ALY", "WAY": "WAY", "SQUARE": "SQ",
    "TRAIL": "TRL", "PIKE": "PIKE",
}
DIRECTIONS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
UNIT_PATTERN = re.compile(r"\s+(?:(?:APT|UNIT|STE|SUITE|FL|FLOOR)\b|#).*$")


def normalize_address(raw: str | None) -> str | None:
    """'485 West Cooper Street, Apt 2' -> '485 W COOPER ST'."""
    if not raw:
        return None
    street = raw.split(",")[0].upper()
    street = street.replace("#", " # ")
    street = UNIT_PATTERN.sub("", street)
    street = re.sub(r"[^A-Z0-9 ]", " ", street)
    words = [DIRECTIONS.get(word, SUFFIXES.get(word, word)) for word in street.split()]
    if not words or not words[0][0].isdigit():
        return None
    return " ".join(words)
