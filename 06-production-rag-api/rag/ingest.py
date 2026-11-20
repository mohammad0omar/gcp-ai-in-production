"""Ingest job: chunk, embed and replace every document in docs/.

Runs as the ingest database user, which can write `chunks` but cannot change the schema.
Embeddings are computed first, so no database transaction waits on Gemini. Each run makes
the table match docs/ exactly: changed documents are replaced, removed documents are deleted.
"""

import sys
from pathlib import Path

from rag.chunk import chunk
from rag.db import connect
from rag.embed import embed_documents
from rag.search import vector_literal

ROOT = Path(__file__).resolve().parents[1]
DELETE_DOC_SQL = "DELETE FROM chunks WHERE doc_id = %s"
DELETE_REMOVED_SQL = "DELETE FROM chunks WHERE doc_id <> ALL(%s)"
INSERT_SQL = """
INSERT INTO chunks (id, doc_id, jurisdiction, chunk, embedding)
VALUES (%s, %s, %s, %s, CAST(%s AS vector))
"""


def read_document(path: Path) -> tuple[str, str]:
    """First line may be `jurisdiction: <name>`. Returns (jurisdiction, body)."""
    first, _, rest = path.read_text().partition("\n")
    if first.lower().startswith("jurisdiction:"):
        return first.split(":", 1)[1].strip(), rest.strip()
    return "all", path.read_text().strip()


def prepare(docs_dir: Path) -> list[dict]:
    """Read and embed everything. No database connection is open yet."""
    prepared = []
    for path in sorted(docs_dir.glob("*.txt")):
        jurisdiction, body = read_document(path)
        parts = chunk(body)
        vectors = embed_documents(parts)
        prepared.append(
            {"doc_id": path.stem, "jurisdiction": jurisdiction, "parts": parts, "vectors": vectors}
        )
    return prepared


def write(cursor, prepared: list[dict]) -> int:
    """Replace each document's rows. The caller commits, so the swap is one transaction."""
    count = 0
    for doc in prepared:
        cursor.execute(DELETE_DOC_SQL, (doc["doc_id"],))
        for n, (text, vector) in enumerate(zip(doc["parts"], doc["vectors"], strict=True)):
            cursor.execute(
                INSERT_SQL,
                (f"{doc['doc_id']}-{n}", doc["doc_id"], doc["jurisdiction"], text, vector_literal(vector)),
            )
            count += 1
    cursor.execute(DELETE_REMOVED_SQL, ([doc["doc_id"] for doc in prepared],))
    return count


def main() -> int:
    prepared = prepare(ROOT / "docs")
    if not prepared:
        print("no documents found, refusing to empty the table")
        return 1
    conn = connect()
    try:
        count = write(conn.cursor(), prepared)
        conn.commit()
    finally:
        conn.close()
    print(f"ingested {count} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
