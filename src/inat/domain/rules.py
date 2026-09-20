from __future__ import annotations

import re
import unicodedata
from datetime import date

from .enums import Season


ID_LENGTH = 8
ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def default_application_season(today: date | None = None) -> tuple[int, Season]:
    """Internship applications default to next year's summer season."""
    reference = today or date.today()
    return reference.year + 1, Season.SUMMER


def normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())

