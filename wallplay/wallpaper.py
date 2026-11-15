"""Wallpaper engine: non-destructive editing (base image + filters + layers)."""
from __future__ import annotations

import calendar
import contextlib
import copy
import datetime as dt
import getpass
import math
import os
import platform
import random
import shutil
import socket
import textwrap
import winreg
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from . import winapi
from .common import STATE_DIR, WallplayError, ensure_dir, parse_alpha, parse_color, random_color, read_json, write_json

FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FONT_FILES = {
    "regular": "segoeui.ttf", "bold": "segoeuib.ttf", "light": "segoeuil.ttf", "semibold": "seguisb.ttf",
    "black": "seguibl.ttf", "italic": "segoeuii.ttf", "mono": "consola.ttf", "script": "segoesc.ttf",
    "print": "segoepr.ttf", "serif": "georgia.ttf", "impact": "impact.ttf", "comic": "comic.ttf",
}
EMOJI_FONT = "seguiemj.ttf"

STICKERS = {
    "cat": "🐱", "dog": "🐶", "panda": "🐼", "fox": "🦊", "unicorn": "🦄", "butterfly": "🦋", "penguin": "🐧",
    "heart": "❤", "star": "⭐", "sparkles": "✨", "fire": "🔥", "rocket": "🚀", "moon": "🌙", "sun": "🌞",
    "rainbow": "🌈", "flower": "🌸", "sunflower": "🌻", "tree": "🌳", "cactus": "🌵", "mushroom": "🍄",
    "leaf": "🍁", "wave": "🌊", "snowman": "⛄", "ghost": "👻", "alien": "👽", "robot": "🤖", "skull": "💀",
    "crown": "👑", "pizza": "🍕", "coffee": "☕", "cake": "🎂", "music": "🎵", "party": "🎉", "gem": "💎",
    "smile": "😄", "cool": "😎", "love": "😍", "wink": "😉", "think": "🤔", "planet": "🪐", "earth": "🌍",
    "lightning": "⚡", "cloud": "☁", "umbrella": "☂", "game": "🎮", "book": "📚", "bulb": "💡", "clover": "🍀",
}

QUOTES = [
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("Done is better than perfect.", "Sheryl Sandberg"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("Creativity is intelligence having fun.", "Albert Einstein"),
    ("Dream big. Start small. Act now.", "Robin Sharma"),
    ("You miss 100% of the shots you don't take.", "Wayne Gretzky"),
    ("Be so good they can't ignore you.", "Steve Martin"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Small steps every day.", "Unknown"),
]

LAYER_KINDS = ["text", "emoji", "shape", "clock", "date", "calendar", "quote", "note", "greeting",
               "sysinfo", "countdown", "image"]
SHAPES = ["circle", "ring", "square", "triangle", "star", "heart", "diamond", "moon"]
TIME_WIDGETS = {"clock", "date", "calendar", "greeting", "sysinfo", "countdown"}

# default size as a fraction of screen height
DEFAULT_SIZE = {"text": 0.09, "emoji": 0.15, "shape": 0.22, "clock": 0.13, "date": 0.045, "calendar": 0.026,
                "quote": 0.035, "note": 0.028, "greeting": 0.06, "sysinfo": 0.024, "countdown": 0.09, "image": 1.0}
DEFAULT_COLOR = {"note": "#fff176", "shape": "hotpink", "calendar": "#ff4f8b"}


def load_font(name: str | None, size: int):
    fname = FONT_FILES.get((name or "regular").lower(), name or "segoeui.ttf")
    for cand in (fname, FONTS_DIR / fname, FONTS_DIR / (str(fname) + ".ttf")):
        try:
            return ImageFont.truetype(str(cand), max(1, int(size)))
        except OSError:
            continue
    return ImageFont.load_default(max(1, int(size)))


# ================================================================== positions
POS_KEYWORDS = {
    "center": (0.5, 0.5), "middle": (0.5, 0.5), "c": (0.5, 0.5),
    "top": (0.5, 0.0), "bottom": (0.5, 1.0), "left": (0.0, 0.5), "right": (1.0, 0.5),
    "top-left": (0.0, 0.0), "topleft": (0.0, 0.0), "tl": (0.0, 0.0),
    "top-right": (1.0, 0.0), "topright": (1.0, 0.0), "tr": (1.0, 0.0),
    "bottom-left": (0.0, 1.0), "bottomleft": (0.0, 1.0), "bl": (0.0, 1.0),
    "bottom-right": (1.0, 1.0), "bottomright": (1.0, 1.0), "br": (1.0, 1.0),
}


def resolve_pos(at, W: int, H: int, bottom_inset: int = 0):
    """Return (x, y, anchor_x, anchor_y). Accepts keywords, 'x,y' pixels or '30%,70%'."""
    s = str(at or "center").strip().lower().replace(" ", "")
    margin = int(min(W, H) * 0.05)
    if s in POS_KEYWORDS:
        fx, fy = POS_KEYWORDS[s]
        x = margin + fx * (W - 2 * margin)
        y = margin + fy * (H - 2 * margin - bottom_inset)
        return x, y, fx, fy
    parts = s.replace(";", ",").split(",")
    if len(parts) != 2:
        raise WallplayError(f"Bad position '{at}'. Use center/top-left/... or 'x,y' or '30%,60%'.")

    def conv(p, total):
        try:
            return float(p[:-1]) / 100 * total if p.endswith("%") else float(p)
        except ValueError:
            raise WallplayError(f"Bad position '{at}'.") from None

    return conv(parts[0], W), conv(parts[1], H), 0.5, 0.5


def safe_composite(canvas: Image.Image, tile: Image.Image, left: int, top: int) -> None:
    W, H = canvas.size
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(W, left + tile.width), min(H, top + tile.height)
    if x1 <= x0 or y1 <= y0:
        return
    piece = tile.crop((x0 - left, y0 - top, x1 - left, y1 - top))
    canvas.alpha_composite(piece, (x0, y0))


def place(canvas, tile, at, bottom_inset=0):
    x, y, ax, ay = resolve_pos(at, canvas.width, canvas.height, bottom_inset)
    safe_composite(canvas, tile, int(x - tile.width * ax), int(y - tile.height * ay))


# ================================================================== filters
FILTERS: dict[str, dict] = {}


def flt(name, usage, doc):
    def deco(fn):
        FILTERS[name] = {"fn": fn, "usage": usage, "doc": doc}
        return fn
    return deco


def _rgb(c):
    return parse_color(c)[:3]


@flt("gray", "gray", "black & white")
def f_gray(img):
    return ImageOps.grayscale(img).convert("RGB")


@flt("invert", "invert", "negative colours")
def f_invert(img):
    return ImageOps.invert(img.convert("RGB"))


@flt("sepia", "sepia", "old-photo look")
def f_sepia(img):
    return ImageOps.colorize(ImageOps.grayscale(img), "#1e1408", "#fff3d6", mid="#a77b4f")


@flt("tint", "tint <color> [strength 0-1]", "wash everything in a colour")
def f_tint(img, color="hotpink", strength=0.35):
    col = ImageOps.colorize(ImageOps.grayscale(img), "black", "white", mid=_rgb(color))
    return Image.blend(img, col, max(0.0, min(1.0, float(strength))))


@flt("hue", "hue <degrees>", "rotate every colour around the colour wheel")
def f_hue(img, degrees=90):
    h, s, v = img.convert("HSV").split()
    shift = int(round(float(degrees) / 360 * 256)) % 256
    h = h.point(lambda p: (p + shift) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


@flt("duotone", "duotone <dark> <light>", "two-colour poster look")
def f_duotone(img, dark="#1a0b3d", light="#ff8ad8"):
    return ImageOps.colorize(ImageOps.grayscale(img), _rgb(dark), _rgb(light))


@flt("bright", "bright <factor>", "brightness (1 = unchanged)")
def f_bright(img, factor=1.3):
    return ImageEnhance.Brightness(img).enhance(float(factor))


@flt("contrast", "contrast <factor>", "contrast (1 = unchanged)")
def f_contrast(img, factor=1.3):
    return ImageEnhance.Contrast(img).enhance(float(factor))


@flt("saturate", "saturate <factor>", "colour intensity (0 = gray, 2 = vivid)")
def f_saturate(img, factor=1.8):
    return ImageEnhance.Color(img).enhance(float(factor))


@flt("blur", "blur [radius]", "soft focus")
def f_blur(img, radius=8):
    return img.filter(ImageFilter.GaussianBlur(float(radius)))


@flt("pixelate", "pixelate [block]", "retro pixels")
def f_pixelate(img, block=16):
    b = max(2, int(block))
    small = img.resize((max(1, img.width // b), max(1, img.height // b)), Image.BILINEAR)
    return small.resize(img.size, Image.NEAREST)


@flt("posterize", "posterize [bits 1-8]", "flat comic colours")
def f_posterize(img, bits=3):
    return ImageOps.posterize(img.convert("RGB"), max(1, min(8, int(bits))))


@flt("vignette", "vignette [strength 0-1]", "dark cinematic corners")
def f_vignette(img, strength=0.7):
    s = float(strength)
    grad = Image.radial_gradient("L").resize(img.size, Image.BILINEAR)
    mask = grad.point(lambda p: int(min(255, (p / 255) ** 2.2 * 255 * s * 1.4)))
    return Image.composite(Image.new("RGB", img.size, 0), img, mask)


@flt("neon", "neon", "glowing edges on dark")
def f_neon(img):
    edges = ImageEnhance.Brightness(img.filter(ImageFilter.FIND_EDGES)).enhance(3.0)
    glow = edges.filter(ImageFilter.GaussianBlur(5))
    dark = ImageEnhance.Brightness(img).enhance(0.22)
    return ImageChops.add(ImageChops.add(dark, glow), edges)


@flt("glitch", "glitch [amount]", "RGB split + broken scanlines")
def f_glitch(img, amount=12):
    a = int(amount)
    r, g, b = img.convert("RGB").split()
    out = Image.merge("RGB", (ImageChops.offset(r, a, 0), g, ImageChops.offset(b, -a, 0)))
    rnd = random.Random(a)  # deterministic so re-renders don't jump around
    w, h = out.size
    for _ in range(10):
        y = rnd.randrange(h)
        bh = rnd.randrange(4, max(5, h // 18))
        band = out.crop((0, y, w, min(h, y + bh)))
        out.paste(ImageChops.offset(band, rnd.randint(-a * 5, a * 5), 0), (0, y))
    return out


@flt("dream", "dream", "soft dreamy glow")
def f_dream(img):
    glow = img.filter(ImageFilter.GaussianBlur(18))
    return Image.blend(img, ImageChops.screen(img, glow), 0.6)


@flt("cartoon", "cartoon", "flat colours + ink outlines")
def f_cartoon(img):
    flat = ImageOps.posterize(img.filter(ImageFilter.SMOOTH_MORE).convert("RGB"), 3)
    edges = ImageOps.grayscale(img).filter(ImageFilter.FIND_EDGES).point(lambda p: 0 if p > 40 else 255)
    return ImageChops.multiply(flat, edges.convert("RGB"))


@flt("sketch", "sketch", "pencil drawing")
def f_sketch(img):
    return ImageOps.grayscale(img).filter(ImageFilter.CONTOUR).convert("RGB")


@flt("mirror", "mirror", "flip left-right")
def f_mirror(img):
    return ImageOps.mirror(img)


@flt("flip", "flip", "flip upside-down")
def f_flip(img):
    return ImageOps.flip(img)


# ================================================================== bases
def make_gradient(size, colors, angle=135.0):
    W, H = size
    d = int(math.hypot(W, H)) + 2
    mask = Image.linear_gradient("L").resize((d, d)).rotate(-float(angle) + 90, resample=Image.BICUBIC)
    mask = mask.crop(((d - W) // 2, (d - H) // 2, (d - W) // 2 + W, (d - H) // 2 + H))
    cols = [_rgb(c) for c in colors]
    if len(cols) == 1:
        return Image.new("RGB", size, cols[0])
    if len(cols) == 2:
        return ImageOps.colorize(mask, cols[0], cols[1])
    return ImageOps.colorize(mask, cols[0], cols[-1], mid=cols[1])


def make_aurora(size, seed=None):
    rnd = random.Random(seed)
    W, H = size
    sw, sh = max(1, W // 4), max(1, H // 4)  # draw small, blur, upscale = fast + smooth
    bg = tuple(int(c * 0.25) for c in _rgb(_rand_color(rnd)))
    img = Image.new("RGB", (sw, sh), bg)
    d = ImageDraw.Draw(img)
    for _ in range(rnd.randint(5, 8)):
        r = rnd.randint(min(sw, sh) // 4, min(sw, sh) // 1)
        x, y = rnd.randint(-r // 2, sw), rnd.randint(-r // 2, sh)
        d.ellipse((x - r, y - r, x + r, y + r), fill=_rgb(_rand_color(rnd)))
    img = img.filter(ImageFilter.GaussianBlur(min(sw, sh) // 5))
    return img.resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))


def _rand_color(rnd):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(rnd.random(), rnd.uniform(0.5, 0.9), rnd.uniform(0.7, 1.0))
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


# ================================================================== layers
def _text_tile(text, font, fill, *, align="center", shadow=0, stroke=0, stroke_fill=None, embedded=False,
               spacing=None):
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = getattr(font, "size", 20)
    kw = dict(font=font, spacing=int(size * 0.15) if spacing is None else spacing, align=align)
    if stroke:
        kw["stroke_width"] = stroke
    box = probe.multiline_textbbox((0, 0), text, **kw)
    pad = max(4, int(size * 0.12)) + shadow * 3 + stroke
    w, h = box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2
    img = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    org = (pad - box[0], pad - box[1])
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).multiline_text((org[0] + shadow, org[1] + shadow), text, fill=(0, 0, 0, 150), **kw)
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(1, shadow))))
    if stroke and stroke_fill is not None:
        kw["stroke_fill"] = stroke_fill
    ImageDraw.Draw(img).multiline_text(org, text, fill=fill, embedded_color=embedded, **kw)
    return img


def _stack(tiles, gap=0, align="center"):
    w = max(t.width for t in tiles)
    h = sum(t.height for t in tiles) + gap * (len(tiles) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for t in tiles:
        x = {"left": 0, "right": w - t.width}.get(align, (w - t.width) // 2)
        out.alpha_composite(t, (x, y))
        y += t.height + gap
    return out


def _card(tile, pad, radius, fill=(0, 0, 0, 90)):
    out = Image.new("RGBA", (tile.width + pad * 2, tile.height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, out.width - 1, out.height - 1), radius, fill=fill)
    out.alpha_composite(tile, (pad, pad))
    return out


def _shape_tile(kind, size, color, outline=False):
    s = max(4, int(size))
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    width = max(2, s // 12)
    fill = None if outline else color
    line = color if outline else None
    c, r = s / 2, s / 2 - width
    if kind == "circle":
        d.ellipse((width, width, s - width, s - width), fill=fill, outline=line, width=width)
    elif kind == "ring":
        d.ellipse((width, width, s - width, s - width), outline=color, width=max(3, s // 8))
    elif kind == "square":
        d.rounded_rectangle((width, width, s - width, s - width), s // 7, fill=fill, outline=line, width=width)
    elif kind == "triangle":
        pts = [(c + r * math.cos(a), c + r * math.sin(a) + r * 0.15)
               for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)]
        d.polygon(pts, fill=fill, outline=line, width=width)
    elif kind == "diamond":
        d.polygon([(c, width), (s - width, c), (c, s - width), (width, c)], fill=fill, outline=line, width=width)
    elif kind == "star":
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((c + rr * math.cos(a), c + rr * math.sin(a) + r * 0.06))
        d.polygon(pts, fill=fill, outline=line, width=width)
    elif kind == "heart":
        pts = []
        for i in range(120):
            t = 2 * math.pi * i / 120
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((c + x * r / 17, c + y * r / 17 + r * 0.05))
        d.polygon(pts, fill=fill, outline=line, width=width)
    elif kind == "moon":
        d.ellipse((width, width, s - width, s - width), fill=color)
        off = s * 0.28
        d.ellipse((width + off, width - off * 0.4, s - width + off, s - width - off * 0.4), fill=(0, 0, 0, 0))
    else:
        raise WallplayError(f"Unknown shape '{kind}'. Try: {', '.join(SHAPES)}")
    return img


def _day_part(hour):
    return "morning" if 5 <= hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 22 else "night"


def render_layer(L: dict, W: int, H: int) -> Image.Image | None:
    kind = L["kind"]
    size = int(float(L.get("size") or DEFAULT_SIZE.get(kind, 0.08) * H))
    color = parse_color(L.get("color") or DEFAULT_COLOR.get(kind, "white"))
    shadow = int(L.get("shadow", max(2, size // 22)))
    font_name = L.get("font")
    now = dt.datetime.now()

    if kind == "text":
        tile = _text_tile(str(L.get("text", "")).replace("\\n", "\n"), load_font(font_name or "bold", size), color,
                          shadow=shadow, align=L.get("align", "center"))
    elif kind == "emoji":
        tile = _text_tile(L.get("text", "⭐"), load_font(EMOJI_FONT, size), (255, 255, 255, 255),
                          shadow=shadow, embedded=True)
    elif kind == "shape":
        tile = _shape_tile(L.get("shape", "circle"), size, color, outline=str(L.get("outline", "0")) in ("1", "true", "yes"))
    elif kind == "clock":
        fmt = "%I:%M" if str(L.get("format", "24")) == "12" else "%H:%M"
        big = _text_tile(now.strftime(fmt).lstrip("0") if fmt.startswith("%I") else now.strftime(fmt),
                         load_font(font_name or "light", size), color, shadow=shadow)
        small = _text_tile(now.strftime("%A, %d %B"), load_font("semibold", size * 0.24), color,
                           shadow=max(1, shadow // 2))
        tile = _stack([big, small], gap=-int(size * 0.12))
    elif kind == "date":
        tile = _text_tile(now.strftime(L.get("format", "%A, %d %B %Y")), load_font(font_name or "semibold", size),
                          color, shadow=shadow)
    elif kind == "greeting":
        name = L.get("name") or getpass.getuser().split(".")[0].capitalize()
        tile = _text_tile(f"Good {_day_part(now.hour)}, {name}", load_font(font_name or "light", size), color,
                          shadow=shadow)
    elif kind == "quote":
        body = textwrap.fill(f"“{L.get('text', '')}”", 38)
        q = _text_tile(body, load_font(font_name or "italic", size), color, shadow=shadow)
        a = _text_tile(f"— {L.get('author', '')}", load_font("semibold", size * 0.7), color, shadow=shadow)
        tile = _stack([q, a], align="right") if L.get("author") else q
    elif kind == "note":
        text = "\n".join(textwrap.fill(p, 22) for p in str(L.get("text", "")).replace("\\n", "\n").split("\n"))
        inner = _text_tile(text, load_font(font_name or "print", size), (40, 40, 40, 255), align="left")
        pad = int(size * 0.8)
        paper = Image.new("RGBA", (inner.width + pad * 2, inner.height + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(paper).rounded_rectangle((0, 0, paper.width - 1, paper.height - 1), int(size * 0.3),
                                                fill=color)
        ImageDraw.Draw(paper).rectangle((paper.width * 0.35, 0, paper.width * 0.65, size * 0.45),
                                        fill=(255, 255, 255, 110))  # tape
        paper.alpha_composite(inner, (pad, pad))
        sh = Image.new("RGBA", (paper.width + 40, paper.height + 40), (0, 0, 0, 0))
        sh.paste((0, 0, 0, 90), (26, 28, 26 + paper.width, 28 + paper.height))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        sh.alpha_composite(paper, (20, 20))
        tile = sh
    elif kind == "calendar":
        tile = _calendar_tile(now.date(), size, color)
    elif kind == "sysinfo":
        up = winapi.uptime_seconds()
        lines = [f"{getpass.getuser()} @ {socket.gethostname()}",
                 f"{platform.system()} {platform.release()} · build {platform.version().split('.')[-1]}",
                 f"up {up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m"]
        bat = winapi.battery()
        if bat:
            lines.append(f"battery {bat[0]}%{' ⚡' if bat[1] else ''}")
        tile = _card(_text_tile("\n".join(lines), load_font(font_name or "mono", size), color, align="left"),
                     int(size * 0.6), int(size * 0.6))
    elif kind == "countdown":
        try:
            target = dt.date.fromisoformat(str(L.get("date")))
        except ValueError:
            raise WallplayError("countdown needs a date like 2026-12-31") from None
        days = (target - now.date()).days
        big = _text_tile(str(abs(days)), load_font(font_name or "black", size), color, shadow=shadow)
        label = L.get("text") or target.strftime("%d %b %Y")
        word = "days until" if days >= 0 else "days since"
        small = _text_tile(f"{word} {label}", load_font("semibold", size * 0.3), color, shadow=max(1, shadow // 2))
        tile = _stack([big, small], gap=-int(size * 0.1))
    elif kind == "image":
        p = Path(str(L.get("path", "")))
        if not p.exists():
            return None
        tile = Image.open(p).convert("RGBA")
        scale = float(L.get("scale", 1.0))
        if scale != 1.0:
            tile = tile.resize((max(1, int(tile.width * scale)), max(1, int(tile.height * scale))), Image.LANCZOS)
    else:
        raise WallplayError(f"Unknown layer kind '{kind}'")

    if "alpha" in L and kind != "note":
        a = parse_alpha(L["alpha"])
        tile.putalpha(tile.getchannel("A").point(lambda p: p * a // 255))
    angle = float(L.get("angle", 0) or 0)
    if angle:
        tile = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
    return tile


def _calendar_tile(today, size, accent):
    cell = int(size * 1.9)
    f = load_font("semibold", size)
    fh = load_font("bold", int(size * 1.25))
    weeks = calendar.Calendar(0).monthdayscalendar(today.year, today.month)
    pad = int(size * 0.9)
    head = int(size * 2.2)
    w = cell * 7 + pad * 2
    h = head + cell * (len(weeks) + 1) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), int(size * 0.9), fill=(0, 0, 0, 110))
    d.text((w / 2, pad + head / 2.5), today.strftime("%B %Y"), font=fh, fill="white", anchor="mm")
    for i, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
        d.text((pad + cell * i + cell / 2, pad + head + cell / 2), name, font=f,
               fill=(255, 255, 255, 150) if i < 5 else accent[:3] + (200,), anchor="mm")
    for r, week in enumerate(weeks, start=1):
        for i, day in enumerate(week):
            if not day:
                continue
            cx, cy = pad + cell * i + cell / 2, pad + head + cell * r + cell / 2
            if day == today.day:
                rr = cell * 0.42
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=accent)
            d.text((cx, cy), str(day), font=f, fill="white", anchor="mm")
    return img


# ================================================================== the engine
def _reg_get(name, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def _reg_set(name, value):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(value))


class Wall:
    def __init__(self):
        ensure_dir()
        self.file = STATE_DIR / "wall.json"
        self.s = read_json(self.file, {})
        if "original" not in self.s:
            self._capture_original()

    # ---------------------------------------------------------- state
    def save(self):
        write_json(self.file, self.s)
        self._cleanup_bases()

    def _cleanup_bases(self):
        used = {self.s.get("base")} | {h.get("base") for h in self.s.get("history", [])}
        for p in STATE_DIR.glob("base_*.png"):
            if p.name not in used:
                with contextlib.suppress(OSError):
                    p.unlink()

    def _capture_original(self):
        cur = winapi.get_wallpaper_path()
        src = Path(cur) if cur and Path(cur).exists() else winapi.transcoded_wallpaper()
        copy_path = None
        if src and src.exists():
            try:
                img = Image.open(src)
                img.load()
                copy_path = STATE_DIR / "original.png"
                img.convert("RGB").save(copy_path)
            except OSError:
                copy_path = None
        self.s = {
            "original": {"path": cur, "copy": str(copy_path) if copy_path else None,
                         "style": _reg_get("WallpaperStyle", "10"), "tile": _reg_get("TileWallpaper", "0")},
            "base": None, "filters": [], "layers": [], "history": [], "auto": True, "counter": 0,
        }
        self.s["base"] = self._new_base(Image.open(copy_path) if copy_path else make_aurora(winapi.screen_size(), 7))
        self.save()

    def _new_base(self, img: Image.Image) -> str:
        self.s["counter"] = self.s.get("counter", 0) + 1
        name = f"base_{self.s['counter']}.png"
        img.convert("RGB").save(STATE_DIR / name, compress_level=1)
        return name

    @property
    def auto(self) -> bool:
        return bool(self.s.get("auto", True))

    @contextlib.contextmanager
    def change(self, apply=True):
        """Snapshot for undo, let the caller mutate, then save (+apply)."""
        snap = {k: copy.deepcopy(self.s[k]) for k in ("base", "filters", "layers")}
        yield
        hist = self.s.setdefault("history", [])
        hist.append(snap)
        del hist[:-30]
        self.save()
        if apply and self.auto:
            self.apply()

    def undo(self) -> bool:
        hist = self.s.get("history", [])
        if not hist:
            return False
        self.s.update(hist.pop())
        self.save()
        if self.auto:
            self.apply()
        return True

    # ---------------------------------------------------------- base
    def set_base_image(self, img):
        with self.change():
            self.s["base"] = self._new_base(img)

    def solid(self, color):
        self.set_base_image(Image.new("RGB", winapi.screen_size(), _rgb(color)))

    def gradient(self, colors, angle=135):
        self.set_base_image(make_gradient(winapi.screen_size(), colors, angle))

    def aurora(self, seed=None):
        self.set_base_image(make_aurora(winapi.screen_size(), seed))

    def image(self, path):
        p = Path(path).expanduser()
        if not p.exists():
            raise WallplayError(f"No such file: {p}")
        try:
            img = Image.open(p)
            img.load()
        except OSError:
            raise WallplayError(f"Not an image I can read: {p}") from None
        self.set_base_image(img)

    def original_base(self):
        cp = self.s["original"].get("copy")
        if not cp or not Path(cp).exists():
            raise WallplayError("I don't have a copy of your original wallpaper.")
        self.set_base_image(Image.open(cp))

    def reset(self):
        with self.change():
            cp = self.s["original"].get("copy")
            if cp and Path(cp).exists():
                self.s["base"] = self._new_base(Image.open(cp))
            self.s["filters"] = []
            self.s["layers"] = []

    def restore(self):
        """Put the user's original wallpaper back exactly as it was."""
        o = self.s["original"]
        target = o.get("path")
        if not target or not Path(target).exists():
            target = o.get("copy")
        if not target or not Path(target).exists():
            raise WallplayError("Original wallpaper file is missing.")
        _reg_set("WallpaperStyle", o.get("style", "10"))
        _reg_set("TileWallpaper", o.get("tile", "0"))
        winapi.set_wallpaper(target)
        with self.change(apply=False):
            if o.get("copy") and Path(o["copy"]).exists():
                self.s["base"] = self._new_base(Image.open(o["copy"]))
            self.s["filters"], self.s["layers"] = [], []
        return target

    # ---------------------------------------------------------- filters
    def add_filter(self, name, args):
        if name not in FILTERS:
            raise WallplayError(f"Unknown filter '{name}'")
        # validate by running on a tiny image first (catches bad args before touching the desktop)
        try:
            FILTERS[name]["fn"](Image.new("RGB", (64, 64), (120, 80, 200)), *args)
        except WallplayError:
            raise
        except (TypeError, ValueError) as e:
            raise WallplayError(f"Bad arguments for {name}: {e}. Usage: {FILTERS[name]['usage']}") from None
        with self.change():
            self.s["filters"].append({"name": name, "args": list(args)})

    def remove_filter(self, which):
        with self.change():
            if str(which) == "all":
                self.s["filters"] = []
            else:
                i = self._index(which, self.s["filters"])
                self.s["filters"].pop(i)

    # ---------------------------------------------------------- layers
    def _index(self, which, seq):
        if str(which).lower() in ("last", "-1"):
            i = len(seq) - 1
        else:
            try:
                i = int(which) - 1
            except ValueError:
                raise WallplayError(f"'{which}' isn't a number. Use `layers` / `filters` to see numbers.") from None
        if not 0 <= i < len(seq):
            raise WallplayError(f"There is no #{which} (have {len(seq)}).")
        return i

    def add_layer(self, layer: dict) -> int:
        render_layer(layer, *winapi.screen_size())  # validate early
        with self.change():
            self.s["layers"].append(layer)
        return len(self.s["layers"])

    def edit_layer(self, which, **opts):
        i = self._index(which, self.s["layers"])
        new = dict(self.s["layers"][i], **opts)
        render_layer(new, *winapi.screen_size())
        with self.change():
            self.s["layers"][i] = new

    def remove_layer(self, which):
        with self.change():
            if str(which) == "all":
                self.s["layers"] = []
            else:
                self.s["layers"].pop(self._index(which, self.s["layers"]))

    def front(self, which):
        with self.change():
            i = self._index(which, self.s["layers"])
            self.s["layers"].append(self.s["layers"].pop(i))

    def has_time_widgets(self):
        return any(L["kind"] in TIME_WIDGETS for L in self.s["layers"])

    # ---------------------------------------------------------- output
    def render(self, size=None) -> Image.Image:
        W, H = size or winapi.screen_size()
        bp = STATE_DIR / str(self.s.get("base"))
        base = Image.open(bp).convert("RGB") if bp.is_file() else make_aurora((W, H), 1)
        img = ImageOps.fit(base, (W, H), Image.LANCZOS)
        for f in self.s["filters"]:
            img = FILTERS[f["name"]]["fn"](img, *f["args"]).convert("RGB")
        canvas = img.convert("RGBA")
        inset = max(0, winapi.screen_size()[1] - winapi.work_area()[3]) if size is None else 0
        for L in self.s["layers"]:
            tile = render_layer(L, W, H)
            if tile is not None:
                place(canvas, tile, L.get("at", "center"), inset)
        return canvas.convert("RGB")

    def apply(self) -> Path:
        img = self.render()
        self.s["counter"] = self.s.get("counter", 0) + 1
        for old in STATE_DIR.glob("wall_*.png"):
            with contextlib.suppress(OSError):
                old.unlink()
        out = STATE_DIR / f"wall_{self.s['counter']}.png"  # new name each time forces Windows to refresh
        img.save(out, compress_level=1)
        _reg_set("WallpaperStyle", "10")
        _reg_set("TileWallpaper", "0")
        winapi.set_wallpaper(str(out))
        self.s["applied"] = out.name
        write_json(self.file, self.s)
        return out

    def preview(self) -> Path:
        out = STATE_DIR / "preview.png"
        self.render().save(out)
        return out


def surprise_filters():
    looks = [
        [("hue", [random.choice([60, 120, 180, 240, 300])])],
        [("duotone", [random_color(), random_color()])],
        [("tint", [random_color(), 0.45]), ("vignette", [0.7])],
        [("neon", [])],
        [("glitch", [random.randint(8, 25)])],
        [("dream", []), ("saturate", [1.6])],
        [("posterize", [3]), ("saturate", [1.8])],
        [("cartoon", [])],
        [("pixelate", [random.choice([10, 16, 24])]), ("saturate", [1.5])],
        [("sepia", []), ("vignette", [0.8])],
    ]
    return random.choice(looks)
