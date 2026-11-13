"""Log lines carry the trace_id and span_id of the active span, and neither outside a span."""

from __future__ import annotations

import json
import re

import structlog
from opentelemetry.sdk.trace import TracerProvider

from taskboard12_api.logging_config import configure_logging


def _lines(capsys) -> list[dict]:
    return [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.strip()]


def test_log_line_in_span_carries_span_ids(capsys) -> None:
    configure_logging("INFO")
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("work") as span:
        structlog.get_logger().info("inside")
        ctx = span.get_span_context()
    (line,) = _lines(capsys)
    assert line["trace_id"] == format(ctx.trace_id, "032x")
    assert line["span_id"] == format(ctx.span_id, "016x")
    assert re.fullmatch(r"[0-9a-f]{32}", line["trace_id"])
    assert re.fullmatch(r"[0-9a-f]{16}", line["span_id"])


def test_log_line_outside_span_has_no_ids(capsys) -> None:
    configure_logging("INFO")
    structlog.get_logger().info("outside")
    (line,) = _lines(capsys)
    assert "trace_id" not in line
    assert "span_id" not in line
