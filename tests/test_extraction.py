from inat.domain import ApplicationDraft
from inat.services import UrlDraftService


class FakeExtractor:
    def extract(self, url):
        return ApplicationDraft(
            company="Future Co",
            position="AI Intern",
        )


def test_url_extraction_produces_unpersisted_reviewable_draft():
    draft = UrlDraftService(FakeExtractor()).prepare("https://example.com/job")

    assert draft.company == "Future Co"
    assert draft.career_page_url == "https://example.com/job"
