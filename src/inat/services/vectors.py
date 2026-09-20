from __future__ import annotations

import hashlib

from inat.adapters import BgeM3Embedder, EmbeddingModelError
from inat.adapters.embeddings import EMBEDDING_DIMENSIONS
from inat.domain import VectorBuildResult, VectorMatch, VectorStatus
from inat.infrastructure import Database
from inat.repositories import VectorRepository


class VectorUnavailableError(RuntimeError):
    pass


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class VectorService:
    def __init__(
        self,
        database: Database,
        repository: VectorRepository | None = None,
        embedder: BgeM3Embedder | None = None,
    ):
        self.database = database
        self.repository = repository or VectorRepository()
        self.embedder = embedder or BgeM3Embedder()

    def setup(self) -> int:
        try:
            self.database.initialize_vectors()
        except RuntimeError as exc:
            raise VectorUnavailableError(
                "sqlite-vec is unavailable. Install the 'vectors' extra first."
            ) from exc
        model = self.embedder.load(allow_download=not self.embedder.is_cached)
        dimensions = int(model.get_sentence_embedding_dimension())
        if dimensions != EMBEDDING_DIMENSIONS:
            raise EmbeddingModelError(
                f"Expected {EMBEDDING_DIMENSIONS} dimensions, received {dimensions}."
            )
        return dimensions

    def status(self) -> VectorStatus:
        self.database.initialize()
        if not self.database.vector_available():
            with self.database.connect() as connection:
                total = int(connection.execute("SELECT count(*) FROM applications").fetchone()[0])
            return VectorStatus(
                self.embedder.model_name,
                self.embedder.is_cached,
                False,
                total,
                0,
                total,
            )
        self.database.initialize_vectors()
        with self.database.connect(vectors=True) as connection:
            rows = self.repository.embedding_applications(
                connection, self.embedder.model_name
            )
        indexed = sum(
            row["content_hash"] == _content_hash(str(row["search_text"]))
            for row in rows
        )
        return VectorStatus(
            self.embedder.model_name,
            self.embedder.is_cached,
            True,
            len(rows),
            indexed,
            len(rows) - indexed,
        )

    def rebuild(self, *, show_progress: bool = False) -> VectorBuildResult:
        if not self.database.vector_available():
            raise VectorUnavailableError(
                "sqlite-vec is unavailable. Install the 'vectors' extra first."
            )
        if not self.embedder.is_cached:
            raise VectorUnavailableError(
                "BGE-M3 is not downloaded. Run `inat vectors setup` first."
            )
        self.database.initialize_vectors()
        with self.database.connect(vectors=True) as connection:
            rows = self.repository.embedding_applications(
                connection, self.embedder.model_name
            )
        pending = [
            row
            for row in rows
            if row["content_hash"] != _content_hash(str(row["search_text"]))
        ]
        if pending:
            embeddings = self.embedder.encode(
                [str(row["search_text"]) for row in pending],
                show_progress=show_progress,
            )
            with self.database.transaction(vectors=True) as connection:
                self.repository.ensure_model(
                    connection, self.embedder.model_name, EMBEDDING_DIMENSIONS
                )
                for row, embedding in zip(pending, embeddings, strict=True):
                    self.repository.replace_embedding(
                        connection,
                        application_id=int(row["id"]),
                        model_name=self.embedder.model_name,
                        content_hash=_content_hash(str(row["search_text"])),
                        embedding=embedding,
                    )
                self.repository.finish_build(connection, self.embedder.model_name)
        return VectorBuildResult(
            self.embedder.model_name,
            len(rows),
            len(pending),
            len(rows) - len(pending),
        )

    def search(self, query: str, *, limit: int = 20) -> list[VectorMatch]:
        try:
            if not self.database.vector_available() or not self.embedder.is_cached:
                return []
            self.database.initialize_vectors()
            query_embedding = self.embedder.encode([query])[0]
            matches: list[VectorMatch] = []
            with self.database.connect(vectors=True) as connection:
                for row in self.repository.knn(connection, query_embedding, limit):
                    state = self.repository.vector_state(
                        connection, int(row["application_id"])
                    )
                    if state is None:
                        continue
                    if (
                        state["model_name"] != self.embedder.model_name
                        or state["content_hash"]
                        != _content_hash(str(state["search_text"]))
                    ):
                        continue
                    similarity = max(-1.0, min(1.0, 1.0 - float(row["distance"])))
                    matches.append(VectorMatch(str(state["public_id"]), similarity))
            return matches
        except Exception:
            # Vector search is optional; hybrid search still returns text matches.
            return []
