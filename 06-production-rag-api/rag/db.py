"""Connect to Cloud SQL for PostgreSQL with the Cloud SQL Python connector.

No password: the connector logs in with the runtime service account (IAM database
authentication) over private IP.
"""

import os
from functools import lru_cache

import pg8000.dbapi
from config import CONNECT_TIMEOUT_SECONDS
from google.cloud.sql.connector import Connector, exceptions


@lru_cache(maxsize=1)
def _connector() -> Connector:
    # "lazy" refresh suits Cloud Run, where CPU can be throttled between requests.
    return Connector(ip_type="private", enable_iam_auth=True, timeout=CONNECT_TIMEOUT_SECONDS, refresh_strategy="lazy")


# The connector has no common error base class, so list what it can raise at connect time.
CONNECT_ERRORS = (
    exceptions.CloudSQLConnectionError,
    exceptions.CloudSQLIPTypeError,
    exceptions.RefreshNotValidError,
    exceptions.ConnectorLoopError,
    exceptions.ClosedConnectorError,
    exceptions.DnsResolutionError,
    TimeoutError,
    OSError,
)


def connect() -> pg8000.dbapi.Connection:
    try:
        return _connector().connect(
            os.environ["INSTANCE_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["DB_USER"],
            db=os.environ["DB_NAME"],
            enable_iam_auth=True,
            timeout=CONNECT_TIMEOUT_SECONDS,  # socket timeout, passed on to pg8000
        )
    except CONNECT_ERRORS as exc:
        # One error type for callers: the API turns it into a 503.
        raise pg8000.dbapi.InterfaceError("cannot connect to the database") from exc
