from __future__ import annotations

from typing import Protocol

from inat.domain import ApplicationDraft


class ApplicationPageExtractor(Protocol):
    """Boundary for a future browser/LLM-backed job-page extractor."""

    def extract(self, url: str) -> ApplicationDraft: ...


class UrlDraftService:
    """Produces a draft only; a UI must confirm it before persistence."""

    def __init__(self, extractor: ApplicationPageExtractor):
        self.extractor = extractor

    def prepare(self, url: str) -> ApplicationDraft:
        draft = self.extractor.extract(url)
        if draft.career_page_url is None:
            return ApplicationDraft(
                company=draft.company,
                position=draft.position,
                start_at=draft.start_at,
                company_size_type=draft.company_size_type,
                career_page_url=url,
                notes=draft.notes,
            )
        return draft
