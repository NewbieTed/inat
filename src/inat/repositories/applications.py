from __future__ import annotations

import sqlite3
from datetime import date, datetime

from inat.domain import Application, Season


class ApplicationRepository:
    @staticmethod
    def _application(row: sqlite3.Row) -> Application:
        return Application(
            id=str(row["public_id"]),
            company=str(row["company"]),
            position=str(row["position"]),
            start_at=str(row["start_at"]),
            date_applied=date.fromisoformat(str(row["date_applied"])),
            status=str(row["status"]),
            status_updated_at=datetime.fromisoformat(str(row["status_updated_at"])),
            application_season=Season(str(row["application_season"])),
            application_year=int(row["application_year"]),
            company_size_type=row["company_size_type"],
            career_page_url=str(row["career_page_url"]),
            notes=row["notes"],
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def public_id_exists(self, connection: sqlite3.Connection, public_id: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM applications WHERE public_id = ?", (public_id,)
        ).fetchone()
        return row is not None

    def create(
        self,
        connection: sqlite3.Connection,
        *,
        public_id: str,
        company: str,
        position: str,
        start_at: str,
        date_applied: date,
        status: str,
        status_updated_at: datetime,
        application_season: Season,
        application_year: int,
        company_size_type: str | None,
        career_page_url: str,
        notes: str | None,
        search_text: str,
    ) -> None:
        timestamp = status_updated_at.isoformat()
        cursor = connection.execute(
            """
            INSERT INTO applications (
                public_id, company, position, start_at,
                date_applied, status, status_updated_at, application_season,
                application_year, company_size_type, career_page_url, notes,
                search_text, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                public_id,
                company,
                position,
                start_at,
                date_applied.isoformat(),
                status,
                timestamp,
                application_season.value,
                application_year,
                company_size_type,
                career_page_url,
                notes,
                search_text,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO status_history (application_id, old_status, new_status, changed_at)
            VALUES (?, NULL, ?, ?)
            """,
            (cursor.lastrowid, status, timestamp),
        )

    def get(self, connection: sqlite3.Connection, public_id: str) -> Application | None:
        row = connection.execute(
            "SELECT * FROM applications WHERE public_id = ?", (public_id.upper(),)
        ).fetchone()
        return self._application(row) if row is not None else None

    def get_by_internal_id(
        self, connection: sqlite3.Connection, application_id: int
    ) -> Application | None:
        row = connection.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        return self._application(row) if row is not None else None

    def list(
        self,
        connection: sqlite3.Connection,
        *,
        status: str | None = None,
        year: int | None = None,
        season: Season | None = None,
    ) -> list[Application]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if year is not None:
            clauses.append("application_year = ?")
            params.append(year)
        if season is not None:
            clauses.append("application_season = ?")
            params.append(season.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"SELECT * FROM applications{where} "
            "ORDER BY start_at, company COLLATE NOCASE, position COLLATE NOCASE",
            params,
        ).fetchall()
        return [self._application(row) for row in rows]

    def update_status(
        self,
        connection: sqlite3.Connection,
        *,
        public_id: str,
        old_status: str,
        new_status: str,
        changed_at: datetime,
        company_size_type: str | None,
        notes: str | None,
        search_text: str,
    ) -> None:
        row = connection.execute(
            "SELECT id FROM applications WHERE public_id = ?", (public_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Application {public_id!r} does not exist.")
        timestamp = changed_at.isoformat()
        connection.execute(
            """
            UPDATE applications
            SET status = ?, status_updated_at = ?, company_size_type = ?,
                notes = ?, search_text = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_status,
                timestamp,
                company_size_type,
                notes,
                search_text,
                timestamp,
                row["id"],
            ),
        )
        if new_status != old_status:
            connection.execute(
                """
                INSERT INTO status_history
                    (application_id, old_status, new_status, changed_at)
                VALUES (?, ?, ?, ?)
                """,
                (row["id"], old_status, new_status, timestamp),
            )

    def statuses(self, connection: sqlite3.Connection) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT name, is_builtin
            FROM application_statuses
            ORDER BY is_builtin DESC,
                CASE lower(name)
                    WHEN 'applied' THEN 1
                    WHEN 'oa' THEN 2
                    WHEN 'interview' THEN 3
                    WHEN 'offer' THEN 4
                    WHEN 'rejected' THEN 5
                    WHEN 'withdrawn' THEN 6
                    ELSE 100
                END,
                name COLLATE NOCASE
            """
        ).fetchall()

    def status(self, connection: sqlite3.Connection, name: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT name, is_builtin
            FROM application_statuses
            WHERE name = ? COLLATE NOCASE
            """,
            (name,),
        ).fetchone()

    def add_status(self, connection: sqlite3.Connection, name: str) -> None:
        connection.execute(
            "INSERT INTO application_statuses (name, is_builtin) VALUES (?, 0)",
            (name,),
        )

    def rename_status(
        self, connection: sqlite3.Connection, old_name: str, new_name: str
    ) -> None:
        connection.execute(
            "UPDATE application_statuses SET name = ? WHERE name = ? COLLATE NOCASE",
            (new_name, old_name),
        )

    def delete_status(self, connection: sqlite3.Connection, name: str) -> None:
        connection.execute(
            "DELETE FROM application_statuses WHERE name = ? COLLATE NOCASE",
            (name,),
        )

    def status_use_count(self, connection: sqlite3.Connection, name: str) -> int:
        row = connection.execute(
            "SELECT count(*) FROM applications WHERE status = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        return int(row[0])

    def history(
        self, connection: sqlite3.Connection, public_id: str
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT h.old_status, h.new_status, h.changed_at
            FROM status_history AS h
            JOIN applications AS a ON a.id = h.application_id
            WHERE a.public_id = ?
            ORDER BY h.changed_at, h.id
            """,
            (public_id,),
        ).fetchall()
