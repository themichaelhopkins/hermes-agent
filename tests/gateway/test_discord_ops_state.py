"""Tests for gateway/platforms/discord_ops_state."""
from __future__ import annotations
import json
import time
from pathlib import Path
from unittest import mock

import pytest

import gateway.platforms.discord_ops_state as mod


@pytest.fixture(autouse=True)
def _reset_paths(tmp_path):
    """Redirect SNOOZE_PATH and FIX_LOG_PATH to tmp_path for every test."""
    orig_snooze = mod.SNOOZE_PATH
    orig_fix = mod.FIX_LOG_PATH
    mod.SNOOZE_PATH = tmp_path / "discord-snooze.json"
    mod.FIX_LOG_PATH = tmp_path / "fix-log.jsonl"
    yield tmp_path
    mod.SNOOZE_PATH = orig_snooze
    mod.FIX_LOG_PATH = orig_fix


def test_snooze_set_and_check(tmp_path):
    """set_snooze writes state; is_snoozed returns True with correct epoch."""
    epoch = mod.set_snooze("123", 5)
    assert isinstance(epoch, int)
    assert epoch > int(time.time())
    assert epoch <= int(time.time()) + 305  # 5*60 + small margin

    assert mod.is_snoozed("123") is True

    # Verify file contents
    data = json.loads((tmp_path / "discord-snooze.json").read_text())
    assert data["123"] == epoch


def test_snooze_expired_returns_false(tmp_path):
    """A snooze with a past epoch_until is considered expired and pruned."""
    # Write a snooze entry with epoch 1 second ago
    past = int(time.time()) - 1
    mod.SNOOZE_PATH.write_text(json.dumps({"999": past}), encoding="utf-8")

    # First call: detects expired, prunes, returns False
    assert mod.is_snoozed("999") is False

    data = json.loads(mod.SNOOZE_PATH.read_text())
    assert "999" not in data


def test_log_fix_appends_jsonl(tmp_path):
    """log_fix appends a valid JSON line with expected fields."""
    mod.log_fix("ava", "999", "test")
    lines = mod.FIX_LOG_PATH.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["user"] == "ava"
    assert record["channel"] == "999"
    assert record["description"] == "test"
    assert "ts" in record
    assert "Z" in record["ts"]
