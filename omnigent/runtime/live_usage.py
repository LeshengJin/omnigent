"""Best-effort live usage snapshots for an external attempt recorder."""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
_ENV_VAR = "OMNIGENT_LIVE_USAGE_JSON"
_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "total_cost_usd",
)


def _numbers(raw: object) -> dict[str, int | float]:
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, int | float] = {}
    for field in _FIELDS:
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        result[field] = value
    return result


def publish_live_usage(session_id: str, usage: Mapping[str, object]) -> None:
    """Atomically publish one cumulative session-usage snapshot.

    The sidecar is opt-in through ``OMNIGENT_LIVE_USAGE_JSON`` and never
    affects the authoritative database write. Unknown counters and unpriced
    cost remain absent instead of being reported as zero.
    """
    raw_path = os.environ.get(_ENV_VAR)
    if not raw_path:
        return
    flat = _numbers(usage)
    raw_models = usage.get("by_model")
    models = {}
    if isinstance(raw_models, Mapping):
        for model, raw in raw_models.items():
            values = _numbers(raw)
            if values:
                models[str(model)] = values
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "updated_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "usage": flat,
        "models": models,
    }
    path = Path(raw_path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        logger.exception("failed to publish live usage snapshot at %s", path)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
