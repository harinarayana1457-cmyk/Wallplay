"""Shared helpers: state directory, errors, colour parsing."""
from __future__ import annotations

import colorsys
import json
import os
import random
from pathlib import Path

from PIL import ImageColor

STATE_DIR = Path(os.environ.get("WALLPLAY_HOME", str(Path.home() / ".wallplay")))


class WallplayError(Exception):
    """A friendly, user-facing error."""


def ensure_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def read_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    ensure_dir()
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def random_color() -> str:
    r, g, b = colorsys.hsv_to_rgb(random.random(), random.uniform(0.55, 0.9), random.uniform(0.85, 1.0))
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def parse_color(value, alpha: int | None = None) -> tuple:
    """Parse 'hotpink', '#ff8800', 'ff8800', 'rgb(1,2,3)' or 'random' into RGBA."""
    if isinstance(value, (tuple, list)):
        rgb = tuple(int(v) for v in value)
    else:
        s = str(value).strip()
        if s.lower() in ("random", "rand", "?"):
            s = random_color()
        try:
            rgb = ImageColor.getrgb(s)
        except ValueError:
            try:
                rgb = ImageColor.getrgb("#" + s)
            except ValueError:
                raise WallplayError(
                    f"Unknown colour '{value}'. Use a name like 'hotpink', hex like '#ff8800', or 'random'."
                ) from None
    if len(rgb) == 3:
        rgb = tuple(rgb) + (255,)
    if alpha is not None:
        rgb = tuple(rgb[:3]) + (int(alpha),)
    return tuple(rgb)


def parse_alpha(value) -> int:
    """Accept 0-1 floats or 0-255 ints, or percentages like 50%."""
    s = str(value).strip()
    if s.endswith("%"):
        return max(0, min(255, int(float(s[:-1]) * 2.55)))
    f = float(s)
    if f <= 1:
        return max(0, int(f * 255))
    return max(0, min(255, int(f)))
