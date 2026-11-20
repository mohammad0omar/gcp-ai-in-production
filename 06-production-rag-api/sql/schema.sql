CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id           text PRIMARY KEY,
    doc_id       text NOT NULL,
    jurisdiction text NOT NULL DEFAULT 'all',
    chunk        text NOT NULL,
    embedding    vector(768) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_jurisdiction_idx ON chunks (jurisdiction);
