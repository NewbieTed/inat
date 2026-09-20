from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .enums import Season


@dataclass(frozen=True)
class ApplicationDraft:
    """Reviewable data produced manually now, or by a future URL extractor."""

    company: str | None = None
    position: str | None = None
    start_at: date | str | None = None
    company_size_type: str | None = None
    career_page_url: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Application:
    id: str
    company: str
    position: str
    start_at: str
    date_applied: date
    status: str
    status_updated_at: datetime
    application_season: Season
    application_year: int
    company_size_type: str | None
    career_page_url: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SearchMatch:
    application: Application
    score: float
    reason: str


@dataclass(frozen=True)
class StatusChange:
    application_id: str
    old_status: str | None
    new_status: str
    changed_at: datetime


@dataclass(frozen=True)
class VectorMatch:
    application_id: str
    similarity: float


@dataclass(frozen=True)
class VectorStatus:
    model_name: str
    model_cached: bool
    extension_available: bool
    total_applications: int
    indexed_applications: int
    stale_applications: int


@dataclass(frozen=True)
class VectorBuildResult:
    model_name: str
    total_applications: int
    embedded_applications: int
    skipped_applications: int
