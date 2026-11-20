"""Send OpenTelemetry spans to Cloud Trace through the Telemetry API (OTLP)."""

import os

import google.auth
import google.auth.transport.requests
import grpc
from google.auth.transport.grpc import AuthMetadataPlugin
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

TELEMETRY_ENDPOINT = "telemetry.googleapis.com:443"


def setup_tracing() -> None:
    credentials, project_id = google.auth.default()
    channel_credentials = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.metadata_call_credentials(
            AuthMetadataPlugin(credentials=credentials, request=google.auth.transport.requests.Request())
        ),
    )
    resource = Resource.create(
        {
            "service.name": os.environ.get("K_SERVICE", "rag-api"),
            # Cloud Trace needs the project to file the spans.
            "gcp.project_id": os.environ.get("GOOGLE_CLOUD_PROJECT", project_id or ""),
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=TELEMETRY_ENDPOINT, credentials=channel_credentials)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
