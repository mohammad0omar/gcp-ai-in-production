"""Bootstrap job: create the extension, table and indexes, then grant each identity its rights.

Run it once as the admin database user (a member of cloudsqlsuperuser; only that role can
CREATE EXTENSION on Cloud SQL). Safe to run again.
"""

import os
import sys
from pathlib import Path

from rag.db import connect

SCHEMA = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
# quote_ident() makes PostgreSQL quote the role name, so a hostile name cannot escape. The
# GRANT text is assembled on the server from our constant; the name travels as a parameter.
GRANT_API_SQL = "SELECT 'GRANT SELECT ON chunks TO ' || quote_ident(CAST(%s AS text))"
GRANT_INGEST_SQL = (
    "SELECT 'GRANT SELECT, INSERT, UPDATE, DELETE ON chunks TO ' || quote_ident(CAST(%s AS text))"
)


def apply_schema(cursor, schema_path: Path = SCHEMA) -> None:
    # One statement per execute: the driver does not take several at once.
    for statement in schema_path.read_text().split(";"):
        if statement.strip():
            cursor.execute(statement)


def grant(cursor, grant_sql: str, role: str) -> None:
    cursor.execute(grant_sql, (role,))
    cursor.execute(cursor.fetchone()[0])


def main() -> int:
    conn = connect()
    try:
        cursor = conn.cursor()
        apply_schema(cursor)
        grant(cursor, GRANT_API_SQL, os.environ["API_DB_USER"])
        grant(cursor, GRANT_INGEST_SQL, os.environ["INGEST_DB_USER"])
        conn.commit()
    finally:
        conn.close()
    print("schema and grants applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
