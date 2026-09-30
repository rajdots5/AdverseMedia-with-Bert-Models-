import os
from contextlib import contextmanager
from urllib.request import urlopen
from opentelemetry.trace import Status, StatusCode

PHOENIX_URL = os.getenv("PHOENIX_UI_URL", "http://localhost:6006").rstrip("/")
_tracer = None

try:
    from phoenix.otel import register

    tracer_provider = register(
        project_name="adverse-media-scanner",
        auto_instrument=False,
    )
    _tracer = tracer_provider.get_tracer("adverse-media-scanner")
except ImportError:
    pass


@contextmanager
def traced_span(name, kind="CHAIN", attributes=None):
    if _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as span:
        span.set_attribute("openinference.span.kind", kind)
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as error:
            if span.status.status_code == StatusCode.UNSET:
                span.record_exception(error)
                span.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise
        else:
            if span.status.status_code == StatusCode.UNSET:
                span.set_status(Status(StatusCode.OK))


def mark_span_error(span, stage, error_type):
    if span is None:
        return

    span.set_status(Status(StatusCode.ERROR, stage))
    span.set_attribute("error.stage", stage)
    span.set_attribute("error.type", error_type)
    span.set_attribute("workflow.outcome", "error")


def phoenix_status():
    try:
        with urlopen(PHOENIX_URL, timeout=0.6):
            reachable = True
    except Exception:
        reachable = False

    return {
        "instrumentation_enabled": _tracer is not None,
        "server_reachable": reachable,
        "url": PHOENIX_URL,
    }