"""Best-effort live harness events for external observers."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)
_ENV_VAR = "OMNIGENT_LIVE_ACTIVITY_JSONL"


def publish_live_activity(
    session_id: str | None,
    response_id: str,
    event: BaseModel,
) -> None:
    """Append one timestamped harness event when live export is enabled."""
    raw_path = os.environ.get(_ENV_VAR)
    if not raw_path:
        return
    payload = {
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "session_id": session_id,
        "response_id": response_id,
        "event": event.model_dump(mode="json", exclude_none=True),
    }
    path = Path(raw_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(line)
            handle.flush()
        path.chmod(0o600)
    except (OSError, TypeError, ValueError):
        logger.exception("failed to publish live activity at %s", path)
