"""Live harness-event sidecar tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from omnigent.runtime.harnesses._scaffold import HarnessApp, TurnContext
from omnigent.runtime.live_activity import publish_live_activity
from omnigent.server.schemas import CreateResponseRequest, OutputTextDeltaEvent


def test_live_activity_is_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "activity.jsonl"
    monkeypatch.delenv("OMNIGENT_LIVE_ACTIVITY_JSONL", raising=False)
    publish_live_activity(
        "session-1",
        "response-1",
        OutputTextDeltaEvent(type="response.output_text.delta", delta="working"),
    )
    assert not path.exists()


def test_live_activity_appends_timestamped_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "activity.jsonl"
    monkeypatch.setenv("OMNIGENT_LIVE_ACTIVITY_JSONL", str(path))

    publish_live_activity(
        "session-1",
        "response-1",
        OutputTextDeltaEvent(type="response.output_text.delta", delta="first"),
    )
    publish_live_activity(
        "session-1",
        "response-1",
        OutputTextDeltaEvent(type="response.output_text.delta", delta="second"),
    )

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["event"]["delta"] for row in rows] == ["first", "second"]
    assert all(row["schema_version"] == 1 for row in rows)
    assert all(row["session_id"] == "session-1" for row in rows)
    assert all(row["response_id"] == "response-1" for row in rows)
    assert all(row["observed_at"].endswith("Z") for row in rows)
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_harness_exports_full_stream_including_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "activity.jsonl"
    monkeypatch.setenv("OMNIGENT_LIVE_ACTIVITY_JSONL", str(path))

    class _ActivityHarness(HarnessApp):
        async def run_turn(self, request: CreateResponseRequest, ctx: TurnContext) -> None:
            del request
            ctx.emit(OutputTextDeltaEvent(type="response.output_text.delta", delta="working"))

    app = _ActivityHarness()
    ctx = TurnContext(
        response_id="response-1",
        event_queue=asyncio.Queue(),
        cancelled=asyncio.Event(),
        session_id="session-1",
    )
    request = CreateResponseRequest(model="test-agent", input="work")

    _ = [frame async for frame in app._stream_turn(request, ctx, "test-agent")]

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["event"]["type"] for row in rows] == [
        "response.created",
        "response.in_progress",
        "response.output_text.delta",
        "response.completed",
    ]
    assert [row["event"]["sequence_number"] for row in rows] == [0, 1, 2, 3]
