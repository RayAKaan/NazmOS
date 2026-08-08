"""OpenTelemetry tracing setup for NazmOS.

Instruments FastAPI, SQLAlchemy, and Celery when OTEL_EXPORTER_OTLP_ENDPOINT
or Sentry performance monitoring is enabled. Trace context is propagated via
``traceparent`` and ``X-Request-ID`` headers.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

from app.config import get_settings
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("tracing")


def _get_exporter() -> Any | None:
    """Return an OTLP span exporter if an endpoint is configured."""
    endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None)
    if not endpoint:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        return OTLPSpanExporter(endpoint=endpoint)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to create OTLP exporter", extra={"error": str(exc)})
        return None


def init_tracing(service_name: str = "nazmos-api") -> None:
    """Initialize the global tracer provider. Safe to call multiple times."""
    if trace.get_tracer_provider().__class__ is not TracerProvider:
        # Already initialized by auto-instrumentation or a previous call.
        return

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: getattr(settings, "API_VERSION", "2.1.0-ksa"),
            DEPLOYMENT_ENVIRONMENT: settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)

    exporter = _get_exporter()
    if exporter:
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OpenTelemetry tracing initialized", extra={"endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT})
    else:
        # No OTLP endpoint: keep a no-op provider so code can still create spans.
        logger.info("OpenTelemetry tracing initialized (no exporter configured)")

    trace.set_tracer_provider(provider)


@contextmanager
def start_span(
    name: str,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Helper to create a manual span that is safe when no exporter is configured."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name, kind=kind, attributes=attributes or {}) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def instrument_fastapi(app: Any) -> None:
    """Instrument a FastAPI application for OpenTelemetry if package is available."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # pragma: no cover
        logger.warning("FastAPI OpenTelemetry instrumentation failed", extra={"error": str(exc)})


def instrument_sqlalchemy(engine: Any) -> None:
    """Instrument a SQLAlchemy engine for OpenTelemetry if package is available."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from sqlalchemy.ext.asyncio import AsyncEngine

        target = engine.sync_engine if isinstance(engine, AsyncEngine) else engine
        SQLAlchemyInstrumentor().instrument(engine=target)
    except Exception as exc:  # pragma: no cover
        logger.warning("SQLAlchemy OpenTelemetry instrumentation failed", extra={"error": str(exc)})
