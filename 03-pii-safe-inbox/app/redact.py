"""Redact personal data with Sensitive Data Protection (DLP) before any model call."""

import os
import re
from functools import lru_cache

from config import DLP_LOCATION, DLP_TIMEOUT_S, INFO_TYPES
from google.cloud import dlp_v2

# Fail-closed check after DLP: anything that still looks like an email address or a
# 13 to 19 digit card number (spaces or dashes allowed) means DLP missed something.
LEFTOVER = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|(?:\d[ -]?){13,19}")


def looks_unredacted(text: str) -> bool:
    return LEFTOVER.search(text) is not None


@lru_cache(maxsize=1)
def get_dlp_client() -> dlp_v2.DlpServiceClient:
    return dlp_v2.DlpServiceClient()


def redact(text: str) -> str:
    """Return `text` with each match replaced by its info type, e.g. [EMAIL_ADDRESS]."""
    types = [{"name": name} for name in INFO_TYPES]
    response = get_dlp_client().deidentify_content(
        request={
            "parent": f"projects/{os.environ['GOOGLE_CLOUD_PROJECT']}/locations/{DLP_LOCATION}",
            # Listing the types keeps DLP from scanning for everything.
            "inspect_config": {"info_types": types},
            "deidentify_config": {
                "info_type_transformations": {
                    "transformations": [
                        {
                            "info_types": types,
                            "primitive_transformation": {
                                "replace_with_info_type_config": {}
                            },
                        }
                    ]
                }
            },
            "item": {"value": text},
        },
        retry=None,  # the default retries for up to 300 s; Pub/Sub redelivery is our retry
        timeout=DLP_TIMEOUT_S,
    )
    return response.item.value
