from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .sql_loader import read_sql


SCHEMA_VERSION = 6


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def connect(self, *, vectors: bool = False) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript(read_sql("connection.sql"))
        if vectors:
            self._load_vector_extension(connection)
        return connection

    @staticmethod
    def _load_vector_extension(connection: sqlite3.Connection) -> None:
        try:
            import sqlite_vec

            connection.enable_load_extension(True)
            sqlite_vec.load(connection)
            connection.enable_load_extension(False)
        except (ImportError, AttributeError, OSError, sqlite3.Error) as exc:
            try:
                connection.enable_load_extension(False)
            except (AttributeError, sqlite3.Error):
                pass
            raise RuntimeError("sqlite-vec is not available") from exc

    def initialize(self) -> None:
        """Initialize only core tables; vector tables are deliberately lazy."""
        with self.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database version {version} is newer than supported version "
                    f"{SCHEMA_VERSION}."
                )
            if version == 0:
                connection.executescript(read_sql("migrations", "001_initial.sql"))
                version = 1
            if version == 1:
                connection.executescript(
                    read_sql("migrations", "002_drop_deadline.sql")
                )
                version = 2
            if version == 2:
                connection.executescript(
                    read_sql("migrations", "003_drop_platform.sql")
                )
                version = 3
            if version == 3:
                connection.executescript(
                    read_sql("migrations", "004_custom_statuses.sql")
                )
                version = 4
            if version == 4:
                connection.executescript(
                    read_sql("migrations", "005_duplicate_guard.sql")
                )
                version = 5
            if version == 5:
                self._migrate_search_text(connection)
                connection.executescript(
                    read_sql("migrations", "006_company_position_search.sql")
                )

    @staticmethod
    def _migrate_search_text(connection: sqlite3.Connection) -> None:
        from inat.domain import normalize_search_text

        rows = connection.execute(
            "SELECT id, company, position FROM applications"
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE applications SET search_text = ? WHERE id = ?",
                (
                    normalize_search_text(
                        f"{str(row['company'])} {str(row['position'])}"
                    ),
                    row["id"],
                ),
            )

    def initialize_vectors(self) -> None:
        self.initialize()
        with self.connect(vectors=True) as connection:
            connection.executescript(read_sql("migrations", "vector_search.sql"))

    def vector_available(self) -> bool:
        try:
            with self.connect(vectors=True) as connection:
                connection.execute("SELECT vec_version()").fetchone()
            return True
        except (RuntimeError, sqlite3.Error):
            return False

    @contextmanager
    def transaction(self, *, vectors: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect(vectors=vectors)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
