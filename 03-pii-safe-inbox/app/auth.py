"""Verify the OIDC token Pub/Sub attaches to a push request.

We check the signature, expiry and audience (google-auth), then the caller's email
and email_verified. Fail closed: with no settings, every request is refused.
"""

import os

from config import AUTH_TIMEOUT_S
from fastapi import HTTPException
from google.auth import exceptions as auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class _Request(google_requests.Request):
    """google-auth fetches signing certificates with a 120 s default timeout. Shorten it."""

    def __call__(
        self,
        url,
        method="GET",
        body=None,
        headers=None,
        timeout=AUTH_TIMEOUT_S,
        **kwargs,
    ):
        return super().__call__(url, method, body, headers, timeout, **kwargs)


_REQUEST = (
    _Request()
)  # certificates are fetched per request; add a cached session if that matters


def verify_push(authorization: str | None) -> None:
    audience = os.environ.get("PUSH_AUDIENCE")
    expected_email = os.environ.get("PUSH_SERVICE_ACCOUNT")
    if not audience or not expected_email:
        raise HTTPException(status_code=500, detail="push auth not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        claims = id_token.verify_oauth2_token(
            authorization.removeprefix("Bearer "), _REQUEST, audience=audience
        )
    except auth_exceptions.TransportError:
        # Could not fetch Google's certificates: not the caller's fault, let Pub/Sub retry.
        raise HTTPException(status_code=503, detail="cannot verify token now") from None
    except (ValueError, auth_exceptions.GoogleAuthError):
        raise HTTPException(status_code=401, detail="invalid token") from None
    if claims.get("email") != expected_email or not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="wrong caller")
