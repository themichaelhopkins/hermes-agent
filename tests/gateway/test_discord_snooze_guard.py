"""Tests for the Discord snooze guard in send()."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock

import pytest

import gateway.platforms.discord_ops_state as mod


@pytest.fixture(autouse=True)
def _reset_paths(tmp_path):
    """Redirect SNOOZE_PATH to tmp_path for every test."""
    orig_snooze = mod.SNOOZE_PATH
    mod.SNOOZE_PATH = tmp_path / "discord-snooze.json"
    yield tmp_path
    mod.SNOOZE_PATH = orig_snooze


def _is_user_initiated(metadata):
    """Mirror the expression from discord.py send() snooze guard."""
    return bool(metadata) and bool(
        metadata.get("reply_to")
        or metadata.get("is_command_response")
        or metadata.get("is_system_message")
    )


def test_snooze_suppresses_proactive_send(tmp_path):
    """When a channel is snoozed and metadata is None, the guard skips."""
    mod.set_snooze("ch1", 60)
    assert mod.is_snoozed("ch1") is True
    # metadata=None → _is_user_initiated is False → guard would skip
    assert _is_user_initiated(None) is False
    assert _is_user_initiated({}) is False


def test_snooze_passes_through_user_initiated(tmp_path):
    """When metadata indicates user-initiated, the guard lets it through."""
    mod.set_snooze("ch1", 60)
    assert mod.is_snoozed("ch1") is True
    # reply_to present → user-initiated → guard passes through
    assert _is_user_initiated({"reply_to": "msg-id"}) is True
    assert _is_user_initiated({"is_command_response": True}) is True
    assert _is_user_initiated({"is_system_message": True}) is True


def test_no_snooze_allows_all_metadata(tmp_path):
    """When not snoozed, all metadata shapes pass through."""
    # Clear snooze
    mod.SNOOZE_PATH.write_text("{}")
    assert mod.is_snoozed("ch1") is False
    assert _is_user_initiated(None) is False
    assert _is_user_initiated({"reply_to": "msg-id"}) is True
    assert _is_user_initiated({}) is False
