from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("deepfrida.inference")
    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


LOGGER = _build_logger()


def log_inference_event(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": _utc_now(),
        "event": event,
        **fields,
    }
    LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
