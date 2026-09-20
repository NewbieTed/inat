from __future__ import annotations

import sqlite3


class VectorRepository:
    def embedding_applications(
        self, connection: sqlite3.Connection, model_name: str
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT a.id, a.public_id, a.search_text,
                   s.model_name, s.content_hash
            FROM applications AS a
            LEFT JOIN application_embedding_state AS s
                ON s.application_id = a.id AND s.model_name = ?
            ORDER BY a.id
            """,
            (model_name,),
        ).fetchall()

    def ensure_model(
        self, connection: sqlite3.Connection, model_name: str, dimensions: int
    ) -> None:
        connection.execute(
            """
            INSERT INTO embedding_models (model_name, dimensions)
            VALUES (?, ?)
            ON CONFLICT(model_name) DO UPDATE SET dimensions = excluded.dimensions
            """,
            (model_name, dimensions),
        )

    def replace_embedding(
        self,
        connection: sqlite3.Connection,
        *,
        application_id: int,
        model_name: str,
        content_hash: str,
        embedding: object,
    ) -> None:
        connection.execute(
            "DELETE FROM vec_application_embeddings WHERE rowid = ?",
            (application_id,),
        )
        connection.execute(
            "INSERT INTO vec_application_embeddings(rowid, embedding) VALUES (?, ?)",
            (application_id, embedding),
        )
        connection.execute(
            """
            INSERT INTO application_embedding_state
                (application_id, model_name, content_hash)
            VALUES (?, ?, ?)
            ON CONFLICT(application_id) DO UPDATE SET
                model_name = excluded.model_name,
                content_hash = excluded.content_hash,
                generated_at = CURRENT_TIMESTAMP
            """,
            (application_id, model_name, content_hash),
        )

    def finish_build(self, connection: sqlite3.Connection, model_name: str) -> None:
        connection.execute(
            """
            DELETE FROM vec_application_embeddings
            WHERE rowid NOT IN (SELECT id FROM applications)
            """
        )
        connection.execute(
            "UPDATE embedding_models SET indexed_at = CURRENT_TIMESTAMP WHERE model_name = ?",
            (model_name,),
        )

    def knn(
        self, connection: sqlite3.Connection, embedding: object, limit: int
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT rowid AS application_id, distance
            FROM vec_application_embeddings
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
            """,
            (embedding, limit),
        ).fetchall()

    def vector_state(
        self, connection: sqlite3.Connection, application_id: int
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT a.public_id, a.search_text, s.model_name, s.content_hash
            FROM applications AS a
            JOIN application_embedding_state AS s ON s.application_id = a.id
            WHERE a.id = ?
            """,
            (application_id,),
        ).fetchone()

