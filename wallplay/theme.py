"""Windows colour settings: dark/light mode, transparency, accent colour."""
from __future__ import annotations

import colorsys
import struct
import winreg

from PIL import Image

from . import winapi
from .common import WallplayError, parse_color

PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
DWM = r"Software\Microsoft\Windows\DWM"
ACCENT = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"


def _get(path, name, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def _set(path, name, value, kind=winreg.REG_DWORD):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, kind, value)


def current_mode() -> str:
    return "light" if _get(PERSONALIZE, "AppsUseLightTheme", 1) else "dark"


def set_mode(mode: str) -> str:
    mode = mode.lower()
    if mode == "toggle":
        mode = "dark" if current_mode() == "light" else "light"
    if mode not in ("dark", "light"):
        raise WallplayError("theme must be dark, light or toggle")
    v = 1 if mode == "light" else 0
    _set(PERSONALIZE, "AppsUseLightTheme", v)
    _set(PERSONALIZE, "SystemUsesLightTheme", v)
    winapi.broadcast_setting_change("ImmersiveColorSet")
    return mode


def set_transparency(on: bool) -> None:
    _set(PERSONALIZE, "EnableTransparency", 1 if on else 0)
    winapi.broadcast_setting_change("ImmersiveColorSet")


def set_accent_bars(on: bool) -> None:
    """Show the accent colour on Start/taskbar and window title bars."""
    _set(PERSONALIZE, "ColorPrevalence", 1 if on else 0)
    _set(DWM, "ColorPrevalence", 1 if on else 0)
    winapi.broadcast_setting_change("ImmersiveColorSet")


def _shade(rgb, f):
    if f >= 0:
        return tuple(int(c + (255 - c) * f) for c in rgb)
    return tuple(int(c * (1 + f)) for c in rgb)


def _abgr(rgb):
    r, g, b = rgb
    return 0xFF000000 | (b << 16) | (g << 8) | r


def set_accent(color) -> tuple:
    rgb = parse_color(color)[:3]
    shades = [_shade(rgb, f) for f in (0.6, 0.4, 0.2, 0.0, -0.25, -0.45, -0.65)] + [(0x88, 0x88, 0x88)]
    palette = b"".join(struct.pack("BBBB", *s, 0) for s in shades)
    _set(ACCENT, "AccentPalette", palette, winreg.REG_BINARY)
    _set(ACCENT, "AccentColorMenu", _abgr(shades[3]))
    _set(ACCENT, "StartColorMenu", _abgr(shades[4]))
    _set(DWM, "AccentColor", _abgr(rgb))
    r, g, b = rgb
    _set(DWM, "ColorizationColor", 0xC4000000 | (r << 16) | (g << 8) | b)
    _set(DWM, "ColorizationAfterglow", 0xC4000000 | (r << 16) | (g << 8) | b)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "AutoColorization", 0, winreg.REG_DWORD, 0)
    except OSError:
        pass
    winapi.broadcast_setting_change("ImmersiveColorSet")
    return rgb


def accent_auto() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "AutoColorization", 0, winreg.REG_DWORD, 1)
    winapi.broadcast_setting_change("ImmersiveColorSet")


def vibrant_color(img: Image.Image) -> tuple:
    """Pick the most 'accent-worthy' colour from an image."""
    small = img.convert("RGB").resize((96, 96))
    pal = small.quantize(colors=8).convert("RGB").getcolors(96 * 96) or []
    best, score = (0, 120, 215), -1
    for count, c in pal:
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
        sc = s * 2 + (1 - abs(v - 0.7)) + count / (96 * 96)
        if v > 0.25 and sc > score:
            best, score = c, sc
    return best
