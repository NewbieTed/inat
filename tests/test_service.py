from datetime import date, datetime, timezone

import pytest

from inat.domain import (
    ApplicationDraft,
    ID_LENGTH,
    SearchMode,
    Season,
    VectorMatch,
)
from inat.infrastructure import Database
from inat.services import ApplicationService


def draft(**overrides):
    values = {
        "company": "Acme",
        "position": "Software Engineering Intern",
        "start_at": date(2027, 6, 1),
        "career_page_url": "https://example.com/jobs/123",
    }
    values.update(overrides)
    return ApplicationDraft(**values)


def service(tmp_path, semantic_search=None):
    result = ApplicationService(
        Database(tmp_path / "inat.db"), semantic_search=semantic_search
    )
    result.initialize()
    return result


def test_add_autofills_dates_and_next_summer(tmp_path):
    tracker = service(tmp_path)
    now = datetime(2026, 9, 19, 12, 30, tzinfo=timezone.utc)

    item = tracker.add(draft(), today=date(2026, 9, 19), now=now)

    assert item.date_applied == date(2026, 9, 19)
    assert item.application_year == 2027
    assert item.application_season is Season.SUMMER
    assert item.start_at == "2027-06-01"
    assert item.status == "applied"
    assert item.status_updated_at == now


def test_add_accepts_an_explicit_applied_date_without_changing_default_season(tmp_path):
    tracker = service(tmp_path)

    item = tracker.add(
        draft(),
        date_applied=date(2025, 12, 31),
        today=date(2026, 9, 20),
    )

    assert item.date_applied == date(2025, 12, 31)
    assert item.application_year == 2027
    assert item.application_season is Season.SUMMER


def test_every_application_id_has_same_length_and_is_unique(tmp_path):
    tracker = service(tmp_path)

    identifiers = {
        tracker.add(draft(position=f"Intern {index}")).id for index in range(25)
    }

    assert len(identifiers) == 25
    assert {len(identifier) for identifier in identifiers} == {ID_LENGTH}


def test_add_rejects_exact_duplicate_and_reports_existing_id(tmp_path):
    tracker = service(tmp_path)
    existing = tracker.add(draft(), today=date(2026, 9, 20))

    with pytest.raises(ValueError, match=existing.id):
        tracker.add(
            draft(start_at="N/A", notes="Different non-key details"),
            status="offer",
            date_applied=date(2026, 1, 1),
            today=date(2026, 9, 20),
        )

    assert len(tracker.list()) == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"company": "Acme Labs"},
        {"position": "Research Intern"},
        {"career_page_url": "https://example.com/jobs/456"},
    ],
)
def test_add_allows_a_difference_in_any_duplicate_key_field(tmp_path, changed):
    tracker = service(tmp_path)
    tracker.add(draft(), today=date(2026, 9, 20))

    tracker.add(draft(**changed), today=date(2026, 9, 20))

    assert len(tracker.list()) == 2


def test_same_details_are_allowed_in_a_different_application_season(tmp_path):
    tracker = service(tmp_path)
    tracker.add(draft(), today=date(2026, 9, 20))

    tracker.add(draft(), today=date(2027, 6, 1))

    assert {item.application_year for item in tracker.list()} == {2027, 2028}


def test_remove_deletes_application_and_status_history(tmp_path):
    tracker = service(tmp_path)
    item = tracker.add(draft())
    tracker.update_status(item.id, "interview")

    removed = tracker.remove(item.id.lower())

    assert removed.id == item.id
    assert tracker.list() == []
    with pytest.raises(ValueError, match="does not exist"):
        tracker.get(item.id)
    with tracker.database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM status_history").fetchone()[0] == 0


def test_remove_rejects_unknown_id(tmp_path):
    tracker = service(tmp_path)

    with pytest.raises(ValueError, match="does not exist"):
        tracker.remove("ABCDEFGH")


def test_optional_company_size_and_notes_are_blank(tmp_path):
    tracker = service(tmp_path)

    item = tracker.add(draft(company_size_type="  ", notes=""))

    assert item.company_size_type is None
    assert item.notes is None


def test_start_at_defaults_to_next_summer_and_accepts_na(tmp_path):
    tracker = service(tmp_path)

    defaulted = tracker.add(draft(start_at=None), today=date(2026, 9, 19))
    unavailable = tracker.add(draft(position="Research Intern", start_at="n/a"))

    assert defaulted.start_at == "summer 2027"
    assert unavailable.start_at == "N/A"


class SearchMustNotRun:
    def search(self, query, *, limit=20):
        raise AssertionError("add must not perform vector search")


def test_add_never_uses_semantic_search_or_creates_vector_tables(tmp_path):
    tracker = service(tmp_path, SearchMustNotRun())

    tracker.add(draft())

    with tracker.database.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
    assert "embedding_models" not in names
    assert "vec_application_embeddings" not in names


def test_update_changes_status_timestamp_and_history(tmp_path):
    tracker = service(tmp_path)
    item = tracker.add(
        draft(),
        now=datetime(2026, 9, 19, 12, tzinfo=timezone.utc),
    )
    changed_at = datetime(2026, 9, 21, 8, 15, tzinfo=timezone.utc)

    change = tracker.update_status(
        item.id,
        "interview",
        company_size_type="startup / 50-100",
        notes="Technical interview",
        now=changed_at,
    )

    updated = tracker.get(item.id.lower())
    assert change.old_status == "applied"
    assert change.new_status == "interview"
    assert updated.status == "interview"
    assert updated.status_updated_at == changed_at
    assert updated.company_size_type == "startup / 50-100"
    assert updated.notes == "Technical interview"
    assert [entry.new_status for entry in tracker.history(item.id)] == [
        "applied",
        "interview",
    ]
    assert tracker.history(item.id)[0].old_status is None


class FakeVectors:
    def __init__(self):
        self.calls = 0
        self.result = []

    def search(self, query, *, limit=20):
        self.calls += 1
        return self.result


def test_text_search_does_not_use_vectors(tmp_path):
    vectors = FakeVectors()
    tracker = service(tmp_path, vectors)
    tracker.add(draft(notes="distributed systems"))

    matches = tracker.search("Acme", mode=SearchMode.TEXT)

    assert matches[0].reason == "exact"
    assert vectors.calls == 0


def test_search_only_compares_company_and_position_text(tmp_path):
    tracker = service(tmp_path)
    tracker.add(
        draft(
            company_size_type="quantum banana collective",
            notes="purple observatory marmalade",
        )
    )

    assert tracker.search("quantum banana", mode=SearchMode.TEXT) == []
    assert tracker.search("purple observatory", mode=SearchMode.TEXT) == []
    assert tracker.search("Software Engineering", mode=SearchMode.TEXT)


def test_status_and_season_filters_work_without_query_or_vectors(tmp_path):
    vectors = FakeVectors()
    tracker = service(tmp_path, vectors)
    tracker.add(draft(), status="applied", today=date(2026, 9, 20))
    tracker.add(
        draft(position="Research Intern"),
        status="interview",
        today=date(2027, 6, 1),
    )

    by_status = tracker.search(None, status="interview", all_years=True)
    by_season = tracker.search(None, year=2027, season=Season.SUMMER)

    assert [match.application.position for match in by_status] == ["Research Intern"]
    assert [match.application.company for match in by_season] == ["Acme"]
    assert {match.reason for match in by_status + by_season} == {"filter"}
    assert vectors.calls == 0


def test_search_without_query_defaults_to_current_application_year(tmp_path):
    tracker = service(tmp_path)
    tracker.add(draft(), today=date(2026, 9, 20))
    tracker.add(draft(position="Future Intern"), today=date(2027, 6, 1))

    matches = tracker.search(None, today=date(2026, 9, 20))

    assert [match.application.position for match in matches] == [
        "Software Engineering Intern"
    ]


def test_search_year_all_disables_default_year_filter(tmp_path):
    tracker = service(tmp_path)
    tracker.add(draft(), today=date(2026, 9, 20))
    tracker.add(draft(position="Future Intern"), today=date(2027, 6, 1))

    matches = tracker.search(None, all_years=True)

    assert {match.application.application_year for match in matches} == {2027, 2028}


def test_search_returns_all_filtered_matches_for_pagination(tmp_path):
    tracker = service(tmp_path)
    for index in range(25):
        tracker.add(draft(position=f"Intern {index:02d}"))

    matches = tracker.search(None, status="applied")

    assert len(matches) == 25
    assert tracker.count(status="applied") == 25


def test_vector_and_hybrid_modes_use_vectors(tmp_path):
    vectors = FakeVectors()
    tracker = service(tmp_path, vectors)
    item = tracker.add(draft())
    vectors.result = [VectorMatch(item.id, 0.94)]

    vector = tracker.search("backend", mode=SearchMode.VECTOR)
    hybrid = tracker.search("Acme", mode=SearchMode.HYBRID)

    assert vectors.calls == 2
    assert vector[0].reason == "vector"
    assert hybrid[0].reason == "hybrid"


def test_builtin_and_custom_statuses(tmp_path):
    tracker = service(tmp_path)

    assert [name for name, built_in in tracker.statuses() if built_in] == [
        "applied",
        "OA",
        "interview",
        "offer",
        "rejected",
        "withdrawn",
    ]
    tracker.add_status("phone screen")
    item = tracker.add(draft(), status="PHONE SCREEN")
    assert item.status == "phone screen"

    assert tracker.rename_status("phone screen", "recruiter call") == "recruiter call"
    assert tracker.get(item.id).status == "recruiter call"
    with pytest.raises(ValueError, match="used by 1 application"):
        tracker.remove_status("recruiter call")


def test_unknown_status_must_be_added_first(tmp_path):
    tracker = service(tmp_path)

    with pytest.raises(ValueError, match="statuses add"):
        tracker.add(draft(), status="custom")


def test_unused_custom_status_can_be_removed(tmp_path):
    tracker = service(tmp_path)
    tracker.add_status("on hold")

    assert tracker.remove_status("ON HOLD") == "on hold"
    assert "on hold" not in {name for name, _ in tracker.statuses()}


@pytest.mark.parametrize(
    "replacement, message",
    [
        ({"company": ""}, "Company cannot be blank"),
        ({"start_at": "sometime"}, "YYYY-MM-DD or N/A"),
        ({"career_page_url": "not-a-url"}, "must be an http"),
    ],
)
def test_add_validates_required_fields(tmp_path, replacement, message):
    with pytest.raises(ValueError, match=message):
        service(tmp_path).add(draft(**replacement))
