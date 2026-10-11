"""JSON diagnostics on stderr; CLI results remain available on stdout."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "context": getattr(record, "context", {}),
        }
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        return json.dumps(event, default=str)


def configure_logging(level: str | None = None) -> None:
    """Configure our namespace once, including under Streamlit reruns."""
    logger = logging.getLogger("supplysignal")
    level = (level or os.environ.get("SUPPLYSIGNAL_LOG_LEVEL", "INFO")).upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Invalid SUPPLYSIGNAL_LOG_LEVEL")
    logger.setLevel(level)
    logger.propagate = False
    if not any(getattr(handler, "supplysignal_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.supplysignal_handler = True
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


def run_cli(main) -> None:
    configure_logging()
    logger = logging.getLogger("supplysignal.cli")
    started = perf_counter()
    context = {"stage": Path(main.__code__.co_filename).stem}
    logger.info("stage_started", extra={"context": context})
    try:
        main()
    except Exception:
        logger.exception("stage_failed", extra={"context": context})
        raise
    logger.info("stage_completed", extra={"context": {
        **context, "elapsed_seconds": round(perf_counter() - started, 3),
    }})
