CREATE TABLE IF NOT EXISTS embedding_models (
    model_name TEXT PRIMARY KEY,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    indexed_at TEXT
);

CREATE TABLE IF NOT EXISTS application_embedding_state (
    application_id INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL REFERENCES embedding_models(model_name) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS vec_application_embeddings USING vec0(
    embedding float[1024] distance_metric=cosine
);

