"""Lightweight JSON-backed state for Discord ops slash commands.

Provides snooze-window tracking and append-only fix-log writes. Keep IO minimal
and synchronous — these are called from slash handlers, not the hot path.
"""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SNOOZE_PATH = Path(os.environ.get("HERMES_DISCORD_SNOOZE_PATH", str(Path.home() / ".hermes" / "discord-snooze.json")))
FIX_LOG_PATH = Path(os.environ.get("HERMES_DISCORD_FIX_LOG", str(Path.home() / "fabric" / "fleet" / "fix-log.jsonl")))


def _load_snooze() -> dict:
    try:
        return json.loads(SNOOZE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def set_snooze(channel_id: str, minutes: int) -> int:
    """Snooze a channel for *minutes* minutes. Returns the epoch_until value."""
    minutes = max(1, min(int(minutes), 1440))
    epoch_until = int(time.time()) + minutes * 60
    data = _load_snooze()
    data[str(channel_id)] = epoch_until
    SNOOZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNOOZE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return epoch_until


def is_snoozed(channel_id: str) -> bool:
    """Return True if *channel_id* has a future snooze window."""
    data = _load_snooze()
    until = data.get(str(channel_id))
    if not until:
        return False
    if int(until) <= int(time.time()):
        # Expired — prune lazily.
        try:
            del data[str(channel_id)]
            SNOOZE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
        return False
    return True


def log_fix(user: str, channel_id: str, description: str) -> None:
    """Append a single JSONL fix record to FIX_LOG_PATH."""
    import datetime as _dt
    record = {
        "ts": _dt.datetime.utcnow().isoformat() + "Z",
        "user": str(user),
        "channel": str(channel_id),
        "description": str(description)[:500],
    }
    try:
        FIX_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FIX_LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.warning("Failed to write fix log: %s", exc)
