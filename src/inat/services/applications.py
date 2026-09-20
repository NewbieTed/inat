from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Protocol
from urllib.parse import urlparse

from inat.domain import (
    Application,
    ApplicationDraft,
    ApplicationStatus,
    ID_LENGTH,
    SearchMatch,
    SearchMode,
    Season,
    StatusChange,
    VectorMatch,
    default_application_season,
    normalize_search_text,
)
from inat.domain.rules import ID_ALPHABET
from inat.infrastructure import Database
from inat.repositories import ApplicationRepository


class SemanticSearch(Protocol):
    def search(self, query: str, *, limit: int = 20) -> list[VectorMatch]: ...


UNSET = object()
MAX_STATUS_LENGTH = 40


class ApplicationService:
    def __init__(
        self,
        database: Database,
        repository: ApplicationRepository | None = None,
        semantic_search: SemanticSearch | None = None,
    ):
        self.database = database
        self.repository = repository or ApplicationRepository()
        self.semantic_search = semantic_search

    def initialize(self) -> None:
        self.database.initialize()

    @staticmethod
    def _clean_required(value: str | None, label: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError(f"{label} cannot be blank.")
        return cleaned

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None

    @staticmethod
    def _validate_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Career/application page URL must be an http(s) URL.")
        return value

    @staticmethod
    def _search_text(
        *,
        company: str,
        position: str,
        company_size_type: str | None,
        notes: str | None,
    ) -> str:
        return normalize_search_text(
            " ".join(
                part
                for part in (company, position, company_size_type, notes)
                if part
            )
        )

    @staticmethod
    def _start_at(
        value: date | str | None, *, year: int, season: Season
    ) -> str:
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"{season.value} {year}"
        if isinstance(value, date):
            return value.isoformat()
        cleaned = value.strip()
        if cleaned.casefold().replace(".", "") in {"n/a", "na"}:
            return "N/A"
        try:
            return date.fromisoformat(cleaned).isoformat()
        except ValueError:
            raise ValueError("Start At must use YYYY-MM-DD or N/A.") from None

    @staticmethod
    def _new_id() -> str:
        return "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))

    @staticmethod
    def _status_name(status: str | ApplicationStatus) -> str:
        value = status.value if isinstance(status, ApplicationStatus) else status
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Status cannot be blank.")
        if len(cleaned) > MAX_STATUS_LENGTH:
            raise ValueError(
                f"Status cannot be longer than {MAX_STATUS_LENGTH} characters."
            )
        if any(ord(character) < 32 for character in cleaned):
            raise ValueError("Status cannot contain control characters.")
        return cleaned

    def _resolve_status(self, connection, status: str | ApplicationStatus) -> str:
        requested = self._status_name(status)
        row = self.repository.status(connection, requested)
        if row is None:
            raise ValueError(
                f"Unknown status {requested!r}. Add it with "
                f"`inat statuses add {requested!r}` first."
            )
        return str(row["name"])

    def add(
        self,
        draft: ApplicationDraft,
        *,
        status: str | ApplicationStatus = ApplicationStatus.APPLIED,
        date_applied: date | None = None,
        today: date | None = None,
        now: datetime | None = None,
    ) -> Application:
        """Add directly from confirmed fields; semantic search is never invoked."""
        company = self._clean_required(draft.company, "Company")
        position = self._clean_required(draft.position, "Position")
        url = self._validate_url(
            self._clean_required(draft.career_page_url, "Career/application page URL")
        )
        current_date = today or date.today()
        applied_on = date_applied or current_date
        changed_at = now or datetime.now(timezone.utc)
        year, season = default_application_season(current_date)
        start_at = self._start_at(draft.start_at, year=year, season=season)
        company_size_type = self._clean_optional(draft.company_size_type)
        notes = self._clean_optional(draft.notes)
        search_text = self._search_text(
            company=company,
            position=position,
            company_size_type=company_size_type,
            notes=notes,
        )
        with self.database.transaction() as connection:
            canonical_status = self._resolve_status(connection, status)
            for _ in range(20):
                public_id = self._new_id()
                if not self.repository.public_id_exists(connection, public_id):
                    break
            else:
                raise RuntimeError("Could not allocate a unique application ID.")
            self.repository.create(
                connection,
                public_id=public_id,
                company=company,
                position=position,
                start_at=start_at,
                date_applied=applied_on,
                status=canonical_status,
                status_updated_at=changed_at,
                application_season=season,
                application_year=year,
                company_size_type=company_size_type,
                career_page_url=url,
                notes=notes,
                search_text=search_text,
            )
            result = self.repository.get(connection, public_id)
        if result is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("Application was not saved.")
        return result

    def get(self, application_id: str) -> Application:
        clean_id = application_id.strip().upper()
        if len(clean_id) != ID_LENGTH:
            raise ValueError(f"Application IDs are exactly {ID_LENGTH} characters.")
        with self.database.connect() as connection:
            result = self.repository.get(connection, clean_id)
        if result is None:
            raise ValueError(f"Application {clean_id!r} does not exist.")
        return result

    def list(
        self,
        *,
        status: str | None = None,
        year: int | None = None,
        season: Season | None = None,
    ) -> list[Application]:
        with self.database.connect() as connection:
            canonical_status = (
                self._resolve_status(connection, status) if status is not None else None
            )
            return self.repository.list(
                connection, status=canonical_status, year=year, season=season
            )

    def update_status(
        self,
        application_id: str,
        status: str | ApplicationStatus,
        *,
        company_size_type: str | None | object = UNSET,
        notes: str | None | object = UNSET,
        now: datetime | None = None,
    ) -> StatusChange:
        current = self.get(application_id)
        changed_at = now or datetime.now(timezone.utc)
        new_size = (
            current.company_size_type
            if company_size_type is UNSET
            else self._clean_optional(company_size_type)  # type: ignore[arg-type]
        )
        new_notes = (
            current.notes
            if notes is UNSET
            else self._clean_optional(notes)  # type: ignore[arg-type]
        )
        search_text = self._search_text(
            company=current.company,
            position=current.position,
            company_size_type=new_size,
            notes=new_notes,
        )
        with self.database.transaction() as connection:
            canonical_status = self._resolve_status(connection, status)
            self.repository.update_status(
                connection,
                public_id=current.id,
                old_status=current.status,
                new_status=canonical_status,
                changed_at=changed_at,
                company_size_type=new_size,
                notes=new_notes,
                search_text=search_text,
            )
        return StatusChange(current.id, current.status, canonical_status, changed_at)

    def statuses(self) -> list[tuple[str, bool]]:
        with self.database.connect() as connection:
            rows = self.repository.statuses(connection)
        return [(str(row["name"]), bool(row["is_builtin"])) for row in rows]

    def add_status(self, name: str) -> str:
        cleaned = self._status_name(name)
        with self.database.transaction() as connection:
            if self.repository.status(connection, cleaned) is not None:
                raise ValueError(f"Status {cleaned!r} already exists.")
            self.repository.add_status(connection, cleaned)
        return cleaned

    def rename_status(self, old_name: str, new_name: str) -> str:
        replacement = self._status_name(new_name)
        with self.database.transaction() as connection:
            current = self.repository.status(connection, old_name.strip())
            if current is None:
                raise ValueError(f"Status {old_name.strip()!r} does not exist.")
            if bool(current["is_builtin"]):
                raise ValueError("Built-in statuses cannot be renamed.")
            collision = self.repository.status(connection, replacement)
            if (
                collision is not None
                and str(collision["name"]).casefold()
                != str(current["name"]).casefold()
            ):
                raise ValueError(f"Status {replacement!r} already exists.")
            self.repository.rename_status(
                connection, str(current["name"]), replacement
            )
        return replacement

    def remove_status(self, name: str) -> str:
        with self.database.transaction() as connection:
            current = self.repository.status(connection, name.strip())
            if current is None:
                raise ValueError(f"Status {name.strip()!r} does not exist.")
            canonical = str(current["name"])
            if bool(current["is_builtin"]):
                raise ValueError("Built-in statuses cannot be removed.")
            uses = self.repository.status_use_count(connection, canonical)
            if uses:
                raise ValueError(
                    f"Status {canonical!r} is used by {uses} application(s). "
                    "Update them before removing it."
                )
            self.repository.delete_status(connection, canonical)
        return canonical

    def history(self, application_id: str) -> list[StatusChange]:
        current = self.get(application_id)
        with self.database.connect() as connection:
            rows = self.repository.history(connection, current.id)
        return [
            StatusChange(
                application_id=current.id,
                old_status=str(row["old_status"]) if row["old_status"] else None,
                new_status=str(row["new_status"]),
                changed_at=datetime.fromisoformat(str(row["changed_at"])),
            )
            for row in rows
        ]

    def _text_matches(
        self, query: str, applications: list[Application]
    ) -> list[SearchMatch]:
        key = normalize_search_text(query)
        if not key:
            return []
        matches: list[SearchMatch] = []
        for application in applications:
            fields = [
                normalize_search_text(application.company),
                normalize_search_text(application.position),
                normalize_search_text(application.id),
            ]
            haystack = self._search_text(
                company=application.company,
                position=application.position,
                company_size_type=application.company_size_type,
                notes=application.notes,
            )
            if key in fields:
                score = 100.0
                reason = "exact"
            elif key in haystack:
                score = 92.0
                reason = "text"
            else:
                score = max(
                    [SequenceMatcher(None, key, field).ratio() * 100 for field in fields]
                    + [SequenceMatcher(None, key, haystack).ratio() * 100]
                )
                reason = "fuzzy"
            if score >= 35:
                matches.append(SearchMatch(application, score, reason))
        return sorted(
            matches,
            key=lambda match: (
                -match.score,
                match.application.company.casefold(),
                match.application.position.casefold(),
            ),
        )

    def search(
        self,
        query: str,
        *,
        mode: SearchMode = SearchMode.HYBRID,
        limit: int = 20,
        status: str | None = None,
        year: int | None = None,
        season: Season | None = None,
    ) -> list[SearchMatch]:
        if limit < 1:
            raise ValueError("Limit must be at least 1.")
        applications = self.list(status=status, year=year, season=season)
        allowed = {application.id: application for application in applications}
        text_matches = (
            self._text_matches(query, applications)
            if mode in {SearchMode.TEXT, SearchMode.HYBRID}
            else []
        )
        vector_matches = (
            self.semantic_search.search(query, limit=max(limit * 3, 20))
            if mode in {SearchMode.VECTOR, SearchMode.HYBRID}
            and self.semantic_search is not None
            else []
        )
        vector_matches = [
            match for match in vector_matches if match.application_id in allowed
        ]
        if mode is SearchMode.TEXT:
            return text_matches[:limit]
        if mode is SearchMode.VECTOR:
            return [
                SearchMatch(
                    allowed[item.application_id], item.similarity * 100, "vector"
                )
                for item in vector_matches[:limit]
            ]

        text_rank = {
            item.application.id: rank for rank, item in enumerate(text_matches, 1)
        }
        vector_rank = {
            item.application_id: rank
            for rank, item in enumerate(vector_matches, 1)
        }
        text_by_id = {item.application.id: item for item in text_matches}
        vector_by_id = {item.application_id: item for item in vector_matches}
        ranked: list[tuple[float, SearchMatch]] = []
        for application_id in text_rank.keys() | vector_rank.keys():
            fusion = 0.0
            if application_id in text_rank:
                fusion += 1 / (60 + text_rank[application_id])
            if application_id in vector_rank:
                fusion += 1 / (60 + vector_rank[application_id])
            text_match = text_by_id.get(application_id)
            vector_match = vector_by_id.get(application_id)
            if text_match is not None and vector_match is not None:
                score = max(text_match.score, vector_match.similarity * 100)
                reason = "hybrid"
            elif text_match is not None:
                score = text_match.score
                reason = text_match.reason
            else:
                score = vector_match.similarity * 100  # type: ignore[union-attr]
                reason = "vector"
            ranked.append(
                (fusion, SearchMatch(allowed[application_id], score, reason))
            )
        ranked.sort(key=lambda item: (-item[0], -item[1].score))
        return [item[1] for item in ranked[:limit]]
