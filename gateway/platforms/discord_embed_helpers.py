"""Discord embed builder for agent replies.

Agents can return structured payloads via ``metadata['embed'] = {...}``. This
module converts the dict spec into a :class:`discord.Embed` instance.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional

import discord

logger = logging.getLogger(__name__)


def build_embed_from_spec(spec: Dict[str, Any]) -> Optional[discord.Embed]:
    """Build a :class:`discord.Embed` from a dict ``spec``.

    Supported keys:
        title (str, <= 256)
        description (str, <= 4096)
        color (int, e.g. ``0x00B894`` for green)
        url (str)
        author: {name, icon_url, url}
        footer: {text, icon_url}
        thumbnail (str url)
        image (str url)
        fields: [{name, value, inline}]  (capped to 25 entries)
        timestamp (ISO str or ``'now'``)

    Returns ``None`` on any failure so the send path can fall back to plain text.
    """
    try:
        embed = discord.Embed()
        if "title" in spec:
            embed.title = str(spec["title"])[:256]
        if "description" in spec:
            embed.description = str(spec["description"])[:4096]
        if "color" in spec:
            try:
                embed.color = int(spec["color"])
            except (TypeError, ValueError):
                pass
        if "url" in spec:
            embed.url = str(spec["url"])
        if "thumbnail" in spec:
            embed.set_thumbnail(url=str(spec["thumbnail"]))
        if "image" in spec:
            embed.set_image(url=str(spec["image"]))
        if isinstance(spec.get("author"), dict):
            a = spec["author"]
            embed.set_author(
                name=str(a.get("name", ""))[:256],
                icon_url=str(a["icon_url"]) if a.get("icon_url") else None,
                url=str(a["url"]) if a.get("url") else None,
            )
        if isinstance(spec.get("footer"), dict):
            f = spec["footer"]
            embed.set_footer(
                text=str(f.get("text", ""))[:2048],
                icon_url=str(f["icon_url"]) if f.get("icon_url") else None,
            )
        if isinstance(spec.get("fields"), list):
            for fd in spec["fields"][:25]:
                if not isinstance(fd, dict):
                    continue
                name = str(fd.get("name", "​"))[:256]
                value = str(fd.get("value", "​"))[:1024]
                inline = bool(fd.get("inline", False))
                embed.add_field(name=name, value=value, inline=inline)
        if spec.get("timestamp"):
            if spec["timestamp"] == "now":
                embed.timestamp = datetime.datetime.utcnow()
            else:
                try:
                    embed.timestamp = datetime.datetime.fromisoformat(
                        str(spec["timestamp"]).replace("Z", "+00:00")
                    )
                except (TypeError, ValueError):
                    pass
        return embed
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to build embed from spec: %s", exc)
        return None


def color_for_agent(agent_key: str) -> int:
    """Return the canonical embed color for an agent key.

    Unknown agents return a neutral gray.
    """
    colors = {
        "maya":        0xFF5A5F,
        "olivia":      0x00B894,
        "henry":       0x2D3436,
        "mason":       0x6C5CE7,
        "ava":         0xFD79A8,
        "ralph":       0xFDCB6E,
        "watchdog":    0xE17055,
        "victor":      0xE17055,
        "spark":       0x0984E3,
        "drew":        0x0984E3,
        "iris":        0x00CEC9,
        "cole":        0x6C5CE7,
        "reid":        0xFF7675,
        "cron-router": 0x636E72,
    }
    return colors.get((agent_key or "").lower(), 0x95A5A6)
