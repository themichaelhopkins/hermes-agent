"""Discord webhook-based per-agent identity helper.

Loads per-channel webhook identity maps from a JSON file and provides
async helpers to post messages via Discord webhooks with chunking,
429 retry, and token-redacting logging.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity map loading
# ---------------------------------------------------------------------------

# Use a mutable container to avoid UnboundLocalError in Python 3.14+
_CACHE_STATE: Dict[str, Any] = {
    "data": {},
    "time": 0.0,
}
_IDENTITY_MAP_TTL: float = 30.0  # seconds


def _redact_token(url: str) -> str:
    """Return a redacted version of a webhook URL showing only the last 6 chars."""
    if not url:
        return url
    # Discord webhook URL pattern: https://discord.com/api/webhooks/<id>/<token>
    match = re.search(r"/([a-f0-9]+)/([a-zA-Z0-9_\-\.]+)$", url)
    if match:
        token = match.group(2)
        return url[: match.start()] + f"/...{token[-6:]}"
    return url


def load_identity_map(identity_path: Optional[str] = None) -> Dict[str, Any]:
    """Load the per-channel identity map from disk.

    Uses HERMES_DISCORD_IDENTITIES env var as the path, falling back to
    ``/Users/michael/.hermes/discord-agent-identities.json``.
    Results are cached for 30 s to avoid repeated disk reads.
    """
    env_path = os.environ.get("HERMES_DISCORD_IDENTITIES")
    if identity_path is None:
        identity_path = env_path or "/Users/michael/.hermes/discord-agent-identities.json"

    now = time.time()
    if now - _CACHE_STATE["time"] < _IDENTITY_MAP_TTL:
        return _CACHE_STATE["data"]

    try:
        data = json.loads(Path(identity_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load Discord identity map from %s: %s", identity_path, exc)
        return {}

    _CACHE_STATE["data"].clear()
    _CACHE_STATE["data"].update(data)
    _CACHE_STATE["time"] = now
    return _CACHE_STATE["data"]


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def resolve_for_channel(
    channel_id: str,
    agent_override: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a webhook identity for *channel_id*.

    Supports two on-disk schemas:

    1. v1 (production, ``discord-agent-identities.json``)::

           {
             "agents":   {"airbnb": {"username": ..., "avatar_url": ...}, ...},
             "channels": {"<channel_id>": {"default_agent": "airbnb",
                                            "webhook_url": "...",
                                            "name": "airbnb-chat"}, ...}
           }

    2. Flat schema (used in tests)::

           {"<channel_id>": {"webhook_url": ..., "username": ...,
                              "avatar_url": ..., "agent_key": ...}}

    Returns a dict with keys ``webhook_url``, ``username``, ``avatar_url``,
    ``agent_key`` or ``None`` when no mapping exists.
    """
    identity_map = load_identity_map()
    if not identity_map:
        return None

    agents = identity_map.get("agents") if isinstance(identity_map.get("agents"), dict) else {}
    channels = identity_map.get("channels") if isinstance(identity_map.get("channels"), dict) else None

    if channels is not None:
        # v1 schema
        channel_map = channels.get(str(channel_id))
        if not channel_map:
            return None
        webhook_url = channel_map.get("webhook_url")
        if not webhook_url:
            return None
        agent_key = agent_override or channel_map.get("default_agent") or "ava"
        agent_meta = agents.get(agent_key, {}) if isinstance(agents, dict) else {}
        result: Dict[str, Any] = {
            "webhook_url": webhook_url,
            "username": agent_meta.get("username", agent_key.title()),
            "avatar_url": agent_meta.get("avatar_url"),
            "agent_key": agent_key,
        }
        return result

    # Flat schema fallback (test fixture shape)
    channel_map = identity_map.get(str(channel_id))
    if not channel_map or not channel_map.get("webhook_url"):
        return None

    result = {
        "webhook_url": channel_map["webhook_url"],
        "username": channel_map.get("username", "Ava"),
        "avatar_url": channel_map.get("avatar_url"),
        "agent_key": channel_map.get("agent_key", str(channel_id)),
    }

    if agent_override:
        agent_map = channel_map.get("agents", {}).get(agent_override)
        if agent_map:
            result["username"] = agent_map.get("username", result["username"])
            result["avatar_url"] = agent_map.get("avatar_url", result["avatar_url"])
            if "webhook_url" in agent_map:
                result["webhook_url"] = agent_map["webhook_url"]
            result["agent_key"] = agent_override

    return result


# ---------------------------------------------------------------------------
# Webhook sending
# ---------------------------------------------------------------------------

_WEBHOOK_TOKEN_RE = re.compile(r"/([a-zA-Z0-9_\-\.]+)$")


async def edit_via_webhook(
    webhook_url: str,
    message_id: str,
    content: str,
) -> Optional[Dict[str, Any]]:
    """Edit a previously posted webhook message.

    Endpoint: ``PATCH /webhooks/{webhook_id}/{webhook_token}/messages/{message_id}``.
    The supplied ``webhook_url`` already contains the ``{id}/{token}`` segment.
    Returns the decoded response dict on 200, ``{"status": 204}`` on 204, or
    ``None`` on failure.
    """
    if not content:
        return None
    edit_url = f"{webhook_url}/messages/{message_id}"
    payload = {"content": content[:2000]}
    async with aiohttp.ClientSession() as session:
        for attempt in range(2):
            try:
                async with session.patch(edit_url, json=payload) as resp:
                    if resp.status in (200, 204):
                        if resp.status == 200:
                            return await resp.json()
                        return {"status": 204}
                    if resp.status == 429:
                        retry_after = 1.0
                        hdr = resp.headers.get("Retry-After")
                        if hdr:
                            try:
                                retry_after = float(hdr)
                            except ValueError:
                                pass
                        else:
                            try:
                                body = await resp.json()
                                retry_after = float(body.get("retry_after", 1.0))
                            except Exception:
                                pass
                        logger.debug(
                            "Discord webhook PATCH 429, retrying after %.1fs (attempt %d)",
                            retry_after,
                            attempt + 1,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    logger.error(
                        "Discord webhook PATCH failed: %d %s",
                        resp.status,
                        _redact_token(webhook_url),
                    )
                    return None
            except Exception as exc:
                logger.error(
                    "Discord webhook PATCH error: %s %s",
                    _redact_token(webhook_url),
                    exc,
                )
                return None
    return None


async def send_via_webhook(
    webhook_url: str,
    username: str,
    avatar_url: Optional[str] = None,
    content: str = "",
    thread_id: Optional[str] = None,
    allowed_mentions: Optional[Dict[str, Any]] = None,
    wait: bool = False,
) -> Optional[Dict[str, Any]]:
    """Post *content* to Discord via a webhook URL.

    Handles content chunking (>2000 chars), HTTP 429 retry (once),
    and returns the final posted message dict (or ``None`` on failure).
    """
    if not content:
        return None

    # Chunk if needed
    chunks: list[str] = []
    if len(content) > 2000:
        # Split on newlines first, then by whitespace
        parts = content.split("\n")
        current = ""
        for part in parts:
            if len(current) + len(part) + 1 <= 2000:
                current = current + ("\n" if current else "") + part
            else:
                if current:
                    chunks.append(current)
                # Try to fit the part
                if len(part) > 2000:
                    # Word-level split
                    words = part.split(" ")
                    current = ""
                    for word in words:
                        if len(current) + len(word) + 1 <= 2000:
                            current = current + (" " if current else "") + word
                        else:
                            if current:
                                chunks.append(current)
                            current = word
                    current = part  # fallback
                else:
                    current = part
        if current:
            chunks.append(current)
    else:
        chunks = [content]

    if not chunks:
        return None

    params: list[str] = []
    if wait:
        params.append("wait=1")
    if thread_id:
        params.append(f"thread_id={thread_id}")
    url = f"{webhook_url}?{'&'.join(params)}" if params else webhook_url

    # Build payload
    payload: Dict[str, Any] = {"content": chunks[0]}
    if username:
        payload["username"] = username
    if avatar_url:
        payload["avatar_url"] = avatar_url
    if allowed_mentions:
        payload["allowed_mentions"] = allowed_mentions

    last_msg: Optional[Dict[str, Any]] = None

    async with aiohttp.ClientSession() as session:
        for idx, chunk in enumerate(chunks):
            msg = {"content": chunk}
            if username:
                msg["username"] = username
            if avatar_url:
                msg["avatar_url"] = avatar_url
            if allowed_mentions:
                msg["allowed_mentions"] = allowed_mentions

            # Retry on 429 (once)
            for attempt in range(2):
                try:
                    async with session.post(url, json=msg) as resp:
                        if resp.status in (200, 204):
                            # 204 = success with no body (Discord returns it when wait=False).
                            if wait and resp.status == 200:
                                last_msg = await resp.json()
                            else:
                                last_msg = {"status": resp.status}
                            break
                        elif resp.status == 429:
                            retry_after = 1.0
                            hdr = resp.headers.get("Retry-After")
                            if hdr:
                                try:
                                    retry_after = float(hdr)
                                except ValueError:
                                    pass
                            else:
                                try:
                                    body = await resp.json()
                                    retry_after = float(body.get("retry_after", 1.0))
                                except Exception:
                                    pass
                            logger.debug(
                                "Discord webhook 429, retrying after %.1fs (attempt %d)",
                                retry_after,
                                attempt + 1,
                            )
                            await asyncio.sleep(retry_after)
                            continue  # retry once
                        else:
                            logger.error(
                                "Discord webhook POST failed: %d %s",
                                resp.status,
                                _redact_token(webhook_url),
                            )
                            break
                except Exception as exc:
                    logger.error(
                        "Discord webhook POST error: %s %s",
                        _redact_token(webhook_url),
                        exc,
                    )
                    break

    return last_msg
