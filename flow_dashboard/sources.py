#!/usr/bin/env python3
"""Source registry — maps a signal's source to its board label / color / enabled.

Color = source/strategy is the board's organizing idea: a new experiment is just
a new colored lane, an old one is parked with ``enabled: false`` without losing
its history. The registry lives in ``sources.yaml`` so adding/retiring a strategy
is a one-line data edit, never a code change.

Tags are the SHORT source slugs (swing / grade / gex / flow) that appear in the
signal_id. Signals on disk carry the LONG name (``directional_grader``); this
module accepts either and normalizes via ``signal_log.SOURCE_TAGS``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml

from signal_log import SOURCE_TAGS  # long source name → short tag

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "sources.yaml")

# Fallback for an unregistered source — surface it (grey) rather than crash, so a
# brand-new generator's signals still show up before you add them to the yaml.
_DEFAULT_COLOR = "#9ca3af"


@dataclass(frozen=True)
class Source:
    tag: str          # short slug, e.g. "grade"
    label: str        # human label, e.g. "Directional Grade"
    color: str        # hex, drives card color
    enabled: bool     # parked strategies surface no new cards


def _short_tag(source: str) -> str:
    """Normalize a long source name or short tag to the short tag."""
    if source in SOURCE_TAGS:            # long name → short
        return SOURCE_TAGS[source]
    return source                        # already short (or unknown)


def load_registry(path: str | None = None) -> dict[str, Source]:
    """Read sources.yaml → {short_tag: Source}. Missing file → empty registry."""
    path = path or REGISTRY_PATH
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    reg: dict[str, Source] = {}
    for tag, cfg in raw.items():
        cfg = cfg or {}
        reg[tag] = Source(
            tag=tag,
            label=cfg.get("label", tag.title()),
            color=cfg.get("color", _DEFAULT_COLOR),
            enabled=bool(cfg.get("enabled", True)),
        )
    return reg


def source_for(source: str, registry: dict[str, Source] | None = None) -> Source:
    """Resolve a source (long or short) to its Source, with a grey fallback."""
    reg = registry if registry is not None else load_registry()
    tag = _short_tag(source)
    if tag in reg:
        return reg[tag]
    return Source(tag=tag, label=tag.title(), color=_DEFAULT_COLOR, enabled=True)


def is_enabled(source: str, registry: dict[str, Source] | None = None) -> bool:
    return source_for(source, registry).enabled


def ansi_swatch(hex_color: str) -> str:
    """A truecolor terminal block for the given hex — so the CLI shows the color."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "  "
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"\x1b[48;2;{r};{g};{b}m  \x1b[0m"


if __name__ == "__main__":
    reg = load_registry()
    print(f"Registry: {REGISTRY_PATH}")
    for tag, s in reg.items():
        state = "on " if s.enabled else "off"
        print(f"  {ansi_swatch(s.color)} {tag:6} {s.color}  [{state}]  {s.label}")
    # normalization sanity
    assert source_for("directional_grader", reg).tag == "grade"
    assert source_for("swing", reg).label == "Swing Persistence"
    print("sources registry ✅")
