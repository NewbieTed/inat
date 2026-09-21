from __future__ import annotations

import re
import unicodedata
from datetime import date

from .enums import Season


ID_LENGTH = 8
ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def default_application_season(today: date | None = None) -> tuple[int, Season]:
    """Return the upcoming summer, using June 1 as the year cutoff."""
    reference = today or date.today()
    year = reference.year + (reference >= date(reference.year, 6, 1))
    return year, Season.SUMMER


def normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())
