"""Top-k cosine search in pgvector. Every value goes in as a parameter, never into the SQL text."""

from config import STATEMENT_TIMEOUT_MS

from rag.db import connect

# SET cannot take parameters, set_config can. Stops a slow query before Cloud Run gives up.
STATEMENT_TIMEOUT_SQL = "SELECT set_config('statement_timeout', %s, false)"

SEARCH_SQL = """
SELECT doc_id, chunk, embedding <=> CAST(%s AS vector) AS distance
FROM chunks
WHERE CAST(%s AS text) IS NULL OR jurisdiction = CAST(%s AS text)
ORDER BY embedding <=> CAST(%s AS vector)
LIMIT %s
"""


def vector_literal(vector: list[float]) -> str:
    """pgvector reads '[0.1,0.2,...]'."""
    return "[" + ",".join(str(x) for x in vector) + "]"


def search_chunks(vector: list[float], top_k: int, jurisdiction: str | None = None) -> list[dict]:
    literal = vector_literal(vector)
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(STATEMENT_TIMEOUT_SQL, (str(STATEMENT_TIMEOUT_MS),))
        cursor.execute(SEARCH_SQL, (literal, jurisdiction, jurisdiction, literal, top_k))
        return [
            {"doc_id": doc_id, "chunk": text, "distance": float(distance)}
            for doc_id, text, distance in cursor.fetchall()
        ]
    finally:
        conn.close()
