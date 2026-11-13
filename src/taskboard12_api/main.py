"""FastAPI entry point for taskboard12-api."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks import InMemoryTaskStore
from .tasks import router as tasks_router
from .tracing import configure_tracing, tracing_enabled

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()


class HealthResponse(BaseModel):
    status: str


def create_app() -> FastAPI:
    """Build the application with its own in-memory task store."""
    app = FastAPI(title="taskboard12-api", version=__version__)
    app.add_middleware(MetricsMiddleware)
    if tracing_enabled():
        FastAPIInstrumentor.instrument_app(app)
    app.state.task_store = InMemoryTaskStore()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Liveness probe — returns 200 as long as the process is responding."""
        return HealthResponse(status="ok")

    @app.get("/ready", response_model=HealthResponse)
    def ready() -> HealthResponse:
        """Readiness probe — returns 200 when the service is ready to accept traffic."""
        return HealthResponse(status="ready")

    @app.get("/ping")
    def ping() -> dict[str, str]:
        """Simple ping endpoint."""
        return {"pong": "taskboard12-api"}

    @app.get("/metrics")
    def metrics() -> Response:
        """Prometheus scrape endpoint."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(tasks_router)
    return app


app = create_app()
