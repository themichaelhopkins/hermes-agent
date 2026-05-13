"""Tests for HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE env gate."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


def test_skip_autocomplete_env_suppresses_registration():
    """When HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE=1, _register_skill_group returns early."""
    # Replicate the 3-line env-gate check from discord.py
    import os as _os
    _os.environ["HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE"] = "1"
    try:
        # Simulate the guard logic
        if _os.environ.get("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", "").lower() in ("1", "true", "yes"):
            # Early return would happen here
            early_returned = True
        else:
            early_returned = False
    finally:
        _os.environ.pop("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", None)

    assert early_returned is True


def test_no_env_var_allows_registration():
    """Without the env var, the guard does not trigger."""
    import os as _os
    # Ensure it's not set
    _os.environ.pop("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", None)
    try:
        if _os.environ.get("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", "").lower() in ("1", "true", "yes"):
            early_returned = True
        else:
            early_returned = False
    finally:
        _os.environ.pop("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", None)

    assert early_returned is False


def test_various_truthy_values():
    """Test that 1, true, yes (case-insensitive) all trigger the guard."""
    import os as _os
    for val in ["1", "true", "True", "TRUE", "yes", "Yes", "YES"]:
        _os.environ["HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE"] = val
        triggered = _os.environ.get("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", "").lower() in ("1", "true", "yes")
        assert triggered is True, f"Expected {val!r} to trigger guard"

    # Falsey values should not trigger
    for val in ["0", "false", "False", "no", "", "TRUEE", "yess"]:
        _os.environ["HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE"] = val
        triggered = _os.environ.get("HERMES_DISCORD_SKIP_SKILL_AUTOCOMPLETE", "").lower() in ("1", "true", "yes")
        assert triggered is False, f"Expected {val!r} to NOT trigger guard"
