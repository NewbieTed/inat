from inat.infrastructure import Database
from inat.infrastructure.sql_loader import read_sql


def test_existing_database_drops_deadline_without_losing_application(tmp_path):
    database = Database(tmp_path / "inat.db")
    with database.connect() as connection:
        connection.executescript(read_sql("migrations", "001_initial.sql"))
        connection.execute(
            """
            INSERT INTO applications (
                public_id, company, position, deadline, start_at, platform,
                date_applied, status, status_updated_at, application_season,
                application_year, company_size_type, career_page_url, notes,
                search_text, created_at, updated_at
            ) VALUES (
                'ABCDEFGH', 'Acme', 'Intern', '2026-10-15', '2027-06-01',
                'Handshake', '2026-09-19', 'assessment',
                '2026-09-19T12:00:00+00:00', 'summer', 2027, NULL,
                'https://example.com/job', NULL, 'acme intern handshake',
                '2026-09-19T12:00:00+00:00', '2026-09-19T12:00:00+00:00'
            )
            """
        )

    database.initialize()

    with database.connect() as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(applications)")
        }
        row = connection.execute(
            "SELECT public_id, company, status FROM applications"
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        statuses = {
            row[0] for row in connection.execute("SELECT name FROM application_statuses")
        }
    assert "deadline" not in columns
    assert "platform" not in columns
    assert tuple(row) == ("ABCDEFGH", "Acme", "OA")
    assert statuses >= {"applied", "OA", "interview", "offer", "rejected", "withdrawn"}
    assert version == 4
