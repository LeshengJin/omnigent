"""Live session-usage sidecar tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnigent.stores.conversation_store.sqlalchemy_store import (
    SqlAlchemyConversationStore,
)


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def test_set_session_usage_publishes_opt_in_snapshot(
    conversation_store: SqlAlchemyConversationStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state/live-usage.json"
    monkeypatch.setenv("OMNIGENT_LIVE_USAGE_JSON", str(path))
    conversation = conversation_store.create_conversation()

    conversation_store.set_session_usage(
        conversation.id,
        {
            "input_tokens": 12,
            "output_tokens": 3,
            "cache_read_input_tokens": 40,
            "total_tokens": 55,
            "total_cost_usd": 0.25,
            "by_model": {
                "databricks-glm-5-3": {
                    "input_tokens": 12,
                    "output_tokens": 3,
                    "total_cost_usd": 0.25,
                }
            },
        },
    )

    snapshot = read(path)
    assert snapshot["session_id"] == conversation.id
    assert snapshot["usage"]["cache_read_input_tokens"] == 40
    assert snapshot["usage"]["total_cost_usd"] == 0.25
    assert snapshot["models"]["databricks-glm-5-3"]["input_tokens"] == 12


def test_increment_replaces_snapshot_and_preserves_unknown_cost(
    conversation_store: SqlAlchemyConversationStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "live-usage.json"
    monkeypatch.setenv("OMNIGENT_LIVE_USAGE_JSON", str(path))
    conversation = conversation_store.create_conversation()

    conversation_store.increment_session_usage(conversation.id, {"input_tokens": 10})
    first = read(path)
    assert first["usage"] == {"input_tokens": 10}
    assert "total_cost_usd" not in first["usage"]

    conversation_store.increment_session_usage(
        conversation.id,
        {"input_tokens": 5, "output_tokens": 2, "total_cost_usd": 0.1},
    )
    second = read(path)
    assert second["usage"] == {
        "input_tokens": 15,
        "output_tokens": 2,
        "total_cost_usd": 0.1,
    }
    assert second["updated_at"] >= first["updated_at"]


def test_snapshot_is_disabled_without_environment(
    conversation_store: SqlAlchemyConversationStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNIGENT_LIVE_USAGE_JSON", raising=False)
    unexpected = tmp_path / "live-usage.json"
    conversation = conversation_store.create_conversation()
    conversation_store.set_session_usage(conversation.id, {"input_tokens": 1})
    assert not unexpected.exists()
