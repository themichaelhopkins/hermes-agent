"""Unit tests for gateway.platforms.discord_embed_helpers.

The shared ``tests/gateway/conftest.py`` installs a small ``_FakeEmbed`` shim
into ``sys.modules['discord']`` when the real library has not been imported
yet.  These tests exercise the full Embed surface (set_thumbnail / set_image /
set_author / set_footer / add_field), so we restore the real library before
importing the helper module.
"""
from __future__ import annotations

import sys

# Restore the real discord library (shim is incompatible with the embed builder).
sys.modules.pop("discord", None)
sys.modules.pop("gateway.platforms.discord_embed_helpers", None)
import discord  # noqa: E402,F401  (force real import)
from gateway.platforms.discord_embed_helpers import (  # noqa: E402
    build_embed_from_spec,
    color_for_agent,
)


def test_build_embed_minimal():
    embed = build_embed_from_spec({"title": "Hello", "description": "World"})
    assert embed is not None
    assert embed.title == "Hello"
    assert embed.description == "World"


def test_build_embed_full():
    spec = {
        "title": "T",
        "description": "D",
        "color": 0xFF0000,
        "url": "https://example.com",
        "thumbnail": "https://example.com/thumb.png",
        "image": "https://example.com/img.png",
        "author": {"name": "Tester", "icon_url": "https://example.com/a.png"},
        "footer": {"text": "Foot", "icon_url": "https://example.com/f.png"},
        "fields": [{"name": f"k{i}", "value": f"v{i}", "inline": False} for i in range(30)],
        "timestamp": "now",
    }
    embed = build_embed_from_spec(spec)
    assert embed is not None
    assert embed.title == "T"
    assert embed.description == "D"
    assert int(embed.color) == 0xFF0000
    assert embed.url == "https://example.com"
    assert embed.thumbnail.url == "https://example.com/thumb.png"
    assert embed.image.url == "https://example.com/img.png"
    assert embed.author.name == "Tester"
    assert embed.footer.text == "Foot"
    assert embed.timestamp is not None
    # fields list must be capped at 25
    assert len(embed.fields) == 25


def test_color_for_agent_known_and_unknown():
    assert color_for_agent("maya") == 0xFF5A5F
    assert color_for_agent("Maya") == 0xFF5A5F  # case-insensitive
    assert color_for_agent("zzz_unknown") == 0x95A5A6
    assert color_for_agent("") == 0x95A5A6
