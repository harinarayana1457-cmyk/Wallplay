"""Interactive shell & CLI for wallplay."""
from __future__ import annotations

import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import icons as icmod
from . import live as livemod
from . import theme as thmod
from . import wallpaper as wpmod
from . import winapi
from .common import STATE_DIR, WallplayError, ensure_dir, read_json, write_json

console = Console()
LIVE_STATE = STATE_DIR / "live.json"
PRESET_DIR = STATE_DIR / "presets"


def ok(msg: str) -> None:
    console.print(f"[bold green]✔[/] {msg}")


def info(msg: str) -> None:
    console.print(f"[cyan]•[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/] {msg}")


def split_opts(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split ['hello', 'at=top-right', 'color=hotpink'] -> (['hello'], {'at': 'top-right', ...})."""
    pos, opts = [], {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--") and "=" not in tok and i + 1 < len(tokens):
            opts[tok[2:].replace("-", "_")] = tokens[i + 1]
            i += 2
            continue
        if "=" in tok and not tok.startswith("="):
            k, v = tok.split("=", 1)
            k = k.lstrip("-").replace("-", "_")
            if k.isidentifier():
                opts[k] = v
                i += 1
                continue
        pos.append(tok)
        i += 1
    return pos, opts


def strip_inline_comment(line: str) -> str:
    """Strip `# ...` comments outside quotes while preserving `#ff8800` hex colors."""
    quote = None
    for i, ch in enumerate(line):
        if ch in ('"', "'") and (i == 0 or line[i - 1] != "\\"):
            quote = None if quote == ch else (ch if quote is None else quote)
        elif ch == "#" and quote is None and (i == 0 or line[i - 1].isspace()):
            rest_token = line[i + 1 :].split(None, 1)[0] if line[i + 1 :].strip() else ""
            is_hex = len(rest_token) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in rest_token)
            if not is_hex:
                return line[:i].rstrip()
    return line


def split_commands(line: str) -> list[str]:
    """Split on `;` outside quotes after stripping inline `# ...` comments."""
    cleaned = strip_inline_comment(line)
    parts, cur, quote = [], [], None
    for i, ch in enumerate(cleaned):
        if ch in ('"', "'") and (i == 0 or cleaned[i - 1] != "\\"):
            quote = None if quote == ch else (ch if quote is None else quote)
            cur.append(ch)
        elif ch == ";" and quote is None:
            s = "".join(cur).strip()
            if s:
                parts.append(s)
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


# ==================================================================== live daemon
def live_info() -> dict | None:
    d = read_json(LIVE_STATE, None)
    if not d:
        return None
    pid = int(d.get("pid", 0))
    img = winapi.process_image(pid).lower() if pid else ""
    if "python" not in img:
        LIVE_STATE.unlink(missing_ok=True)
        return None
    return d


def stop_live(quiet: bool = False) -> bool:
    d = live_info()
    ensure_dir()
    livemod.STOP_FILE.write_text("stop", encoding="utf-8")
    if not d:
        livemod.READY_FILE.unlink(missing_ok=True)
        if not quiet:
            info("No live wallpaper is running.")
        return False
    pid = int(d["pid"])
    for _ in range(25):
        if "python" not in winapi.process_image(pid).lower():
            break
        time.sleep(0.08)
    else:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    LIVE_STATE.unlink(missing_ok=True)
    livemod.STOP_FILE.unlink(missing_ok=True)
    livemod.READY_FILE.unlink(missing_ok=True)
    if not quiet:
        ok("Stopped live wallpaper.")
    return True


def start_live(effect: str, arg: str | None = None) -> None:
    effect = effect.lower()
    if effect not in livemod.EFFECTS:
        raise WallplayError(f"Unknown live effect '{effect}'. Try: {', '.join(livemod.EFFECTS)}")
    stop_live(quiet=True)
    ensure_dir()
    livemod.STOP_FILE.unlink(missing_ok=True)
    livemod.READY_FILE.unlink(missing_ok=True)
    livemod.LOG_FILE.unlink(missing_ok=True)
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    cmd = [exe, "-m", "wallplay.live", effect] + ([arg] if arg else [])
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if not pyw.exists() else 0
    proc = subprocess.Popen(cmd, creationflags=flags)
    for _ in range(30):
        if livemod.READY_FILE.exists():
            break
        if proc.poll() is not None:
            err = livemod.LOG_FILE.read_text(encoding="utf-8").strip() if livemod.LOG_FILE.exists() else "process exited early"
            raise WallplayError(f"Live effect failed to start:\n{err}")
        time.sleep(0.05)
    write_json(LIVE_STATE, {"pid": proc.pid, "effect": effect, "arg": arg})
    label = f"{effect} ({arg})" if arg else effect
    ok(f"Live interactive effect [bold]{label}[/] is now running (PID {proc.pid}).")
    info("Move your mouse or click anywhere to interact! Run `live stop` when you want to turn it off.")


# ==================================================================== command runner
class App:
    def __init__(self):
        self.wall = wpmod.Wall()

    def desk(self) -> icmod.Desktop:
        return icmod.Desktop()

    def run_tokens(self, tokens: list[str]) -> bool:
        if not tokens:
            return True
        self.wall.reload()
        cmd = tokens[0].lower()
        rest = tokens[1:]

        if cmd in ("quit", "exit", "q"):
            return False
        if cmd in ("help", "?", "h"):
            self.cmd_help(rest)
        elif cmd == "status":
            self.cmd_status()
        elif cmd in ("solid", "color", "colour"):
            if not rest:
                raise WallplayError("Usage: solid <color>   e.g. solid hotpink  or  solid #1e293b  or  solid random")
            self.wall.solid(rest[0])
            ok(f"Solid wallpaper set to [bold]{rest[0]}[/].")
        elif cmd in ("gradient", "grad"):
            pos, opts = split_opts(rest)
            if len(pos) < 2:
                raise WallplayError("Usage: gradient <color1> <color2> [color3] [angle=135]")
            self.wall.gradient(pos, float(opts.get("angle", 135)))
            ok(f"Gradient wallpaper: {' → '.join(pos)}")
        elif cmd == "aurora":
            seed = int(rest[0]) if rest and rest[0].lstrip("-").isdigit() else None
            self.wall.aurora(seed)
            ok("Generated fresh aurora wallpaper.")
        elif cmd in ("image", "open", "bg"):
            if not rest:
                raise WallplayError("Usage: image <path-to-picture>")
            self.wall.image(" ".join(rest))
            ok(f"Wallpaper base set from {rest[0]}.")
        elif cmd == "original":
            keep = bool(rest and rest[0].lower() in ("base", "keep"))
            self.wall.original_base(keep_overlays=keep)
            if keep:
                ok("Base reset to your original wallpaper (keeping filters/layers).")
            else:
                ok("Reset to your clean original wallpaper (cleared filters & stickers/layers).")
        elif cmd in wpmod.FILTERS:
            self.wall.add_filter(cmd, rest)
            ok(f"Added filter [bold]{cmd}[/] {' '.join(rest)}".strip())
        elif cmd == "filter":
            if not rest:
                self.cmd_filters()
            else:
                self.wall.add_filter(rest[0].lower(), rest[1:])
                ok(f"Added filter [bold]{rest[0]}[/].")
        elif cmd == "filters":
            self.cmd_filters()
        elif cmd == "unfilter":
            which = rest[0] if rest else "last"
            self.wall.remove_filter(which)
            ok(f"Removed filter ({which}).")
        elif cmd == "surprise":
            with self.wall.change():
                self.wall.s["filters"] = [{"name": n, "args": a} for n, a in wpmod.surprise_filters()]
            names = ", ".join(f["name"] for f in self.wall.s["filters"])
            ok(f"Surprise look applied: [bold]{names}[/]")
        elif cmd == "add":
            self.cmd_add(rest)
        elif cmd == "stickers":
            self.cmd_stickers()
        elif cmd == "layers":
            self.cmd_layers()
        elif cmd == "edit":
            if not rest:
                raise WallplayError("Usage: edit <#id|last> key=value ...   e.g. edit 1 at=top-left color=gold")
            pos, opts = split_opts(rest[1:])
            if pos and "text" not in opts:
                opts["text"] = " ".join(pos)
            self.wall.edit_layer(rest[0], **opts)
            ok(f"Updated layer {rest[0]}.")
        elif cmd in ("remove", "rm", "del"):
            which = rest[0] if rest else "last"
            self.wall.remove_layer(which)
            ok(f"Removed layer ({which}).")
        elif cmd == "front":
            self.wall.front(rest[0] if rest else "last")
            ok("Moved layer to front.")
        elif cmd == "clear":
            what = (rest[0] if rest else "all").lower()
            if what in ("layers", "layer"):
                self.wall.remove_layer("all")
                ok("Cleared all layers.")
            elif what in ("filters", "filter"):
                self.wall.remove_filter("all")
                ok("Cleared all filters.")
            else:
                with self.wall.change():
                    self.wall.s["filters"] = []
                    self.wall.s["layers"] = []
                ok("Cleared all filters and layers.")
        elif cmd == "undo":
            sub = rest[0].lower() if rest else "all"
            if sub in ("step", "1", "last", "one"):
                if self.wall.undo_step():
                    ok("Undid last single step.")
                else:
                    warn("Nothing left in history to step back.")
            else:
                stop_live(quiet=True)
                self.wall.restore()
                if (icmod.LAYOUT_DIR / "original.json").exists():
                    with _suppress_missing():
                        self.desk().load_layout("original")
                ok("Undid all changes — stickers, widgets, filters, wallpaper & icons restored to original. (Use `undo step` to undo just 1 step.)")
        elif cmd == "reset":
            self.wall.reset()
            ok("Reset to your clean original wallpaper.")
        elif cmd == "restore":
            stop_live(quiet=True)
            target = self.wall.restore()
            with _suppress_missing():
                self.desk().load_layout("original")
            ok(f"Restored original wallpaper ({target}) and icon layout.")
        elif cmd == "apply":
            p = self.wall.apply()
            ok(f"Applied wallpaper ({p.name}).")
        elif cmd == "preview":
            p = self.wall.preview()
            os.startfile(str(p))
            ok(f"Opened preview ({p}).")
        elif cmd == "export":
            if not rest:
                raise WallplayError("Usage: export <path.png>")
            out = Path(" ".join(rest)).expanduser()
            self.wall.render().save(out)
            ok(f"Saved rendered wallpaper to {out}.")
        elif cmd == "watch":
            self.cmd_watch(int(rest[0]) if rest else 30)
        elif cmd in ("icons", "icon"):
            self.cmd_icons(rest)
        elif cmd == "live":
            self.cmd_live(rest)
        elif cmd == "theme":
            self.cmd_theme(rest)
        elif cmd == "accent":
            self.cmd_accent(rest)
        elif cmd == "preset":
            self.cmd_preset(rest)
        else:
            raise WallplayError(f"Unknown command '{cmd}'. Type `help` to see everything you can do.")
        return True

    # ---------------------------------------------------------------- add
    def cmd_add(self, tokens: list[str]) -> None:
        if not tokens:
            raise WallplayError(
                "Usage: add <text|sticker|shape|clock|date|calendar|quote|note|greeting|sysinfo|countdown|image> ..."
            )
        kind = tokens[0].lower()
        pos, opts = split_opts(tokens[1:])
        aliases = {"sticker": "emoji", "cal": "calendar", "greet": "greeting", "sys": "sysinfo", "img": "image",
                   "pic": "image", "time": "clock"}
        kind = aliases.get(kind, kind)
        if kind not in wpmod.LAYER_KINDS:
            # Convenience: `add cat at=top-left` or `add "Hello!" color=gold`
            first = tokens[0]
            pos2, opts2 = split_opts(tokens)
            if first.lower() in wpmod.STICKERS:
                kind, pos, opts = "emoji", [wpmod.STICKERS[first.lower()]], opts2
            else:
                kind, pos, opts = "text", pos2, opts2

        layer: dict = {"kind": kind, **opts}
        if kind == "text":
            if not pos and "text" not in layer:
                raise WallplayError('Usage: add text "Hello world" [at=center] [color=white] [size=90] [font=bold]')
            layer.setdefault("text", " ".join(pos))
        elif kind == "emoji":
            if not pos and "text" not in layer:
                raise WallplayError("Usage: add sticker <name-or-emoji> [at=...] [size=160]   (see `stickers`)")
            raw = pos[0] if pos else layer["text"]
            layer["text"] = wpmod.STICKERS.get(raw.lower(), raw)
            layer.setdefault("name", raw.lower())
        elif kind == "shape":
            sh = (pos[0].lower() if pos else layer.get("shape", "circle"))
            layer["shape"] = sh
        elif kind == "quote":
            if pos:
                layer["text"] = " ".join(pos)
            elif "text" not in layer:
                q, a = random.choice(wpmod.QUOTES)
                layer["text"], layer["author"] = q, a
        elif kind == "note":
            if not pos and "text" not in layer:
                raise WallplayError('Usage: add note "Buy milk" [at=top-right] [color=#fff176]')
            layer.setdefault("text", " ".join(pos))
            layer.setdefault("at", "top-right")
        elif kind == "greeting":
            if pos:
                layer["name"] = " ".join(pos)
        elif kind == "countdown":
            if not pos and "date" not in layer:
                raise WallplayError('Usage: add countdown YYYY-MM-DD ["Label"] [at=...]')
            if pos:
                layer["date"] = pos[0]
            if len(pos) > 1:
                layer.setdefault("text", " ".join(pos[1:]))
        elif kind == "image":
            if not pos and "path" not in layer:
                raise WallplayError("Usage: add image <path> [at=...] [scale=0.5] [angle=10]")
            layer.setdefault("path", str(Path(" ".join(pos)).expanduser().resolve()))

        idx = self.wall.add_layer(layer)
        ok(f"Added {kind} as layer [bold]#{idx}[/].")

    def cmd_stickers(self) -> None:
        cells = [f"[bold]{k}[/] {v}" for k, v in sorted(wpmod.STICKERS.items())]
        rows = [",  ".join(cells[i : i + 6]) for i in range(0, len(cells), 6)]
        console.print(Panel("\n".join(rows), title="Built-in stickers (or paste any emoji!)", border_style="magenta"))

    def cmd_filters(self) -> None:
        t = Table(title="Active Filters", show_header=True, header_style="bold cyan")
        t.add_column("#", style="dim", width=4)
        t.add_column("Filter")
        t.add_column("Args")
        for i, f in enumerate(self.wall.s["filters"], 1):
            t.add_row(str(i), f["name"], " ".join(str(a) for a in f["args"]))
        if not self.wall.s["filters"]:
            info("No active filters. Available: " + ", ".join(sorted(wpmod.FILTERS)))
        else:
            console.print(t)

    def cmd_layers(self) -> None:
        layers = self.wall.s["layers"]
        if not layers:
            info("No layers on the wallpaper yet. Try `add clock at=center` or `add sticker cat at=bottom-right`.")
            return
        t = Table(title="Wallpaper Layers (bottom → top)", header_style="bold magenta")
        t.add_column("#", style="dim", width=4)
        t.add_column("Kind", style="bold")
        t.add_column("At")
        t.add_column("Details")
        for i, L in enumerate(layers, 1):
            at = str(L.get("at", "center"))
            extra = {k: v for k, v in L.items() if k not in ("kind", "at")}
            t.add_row(str(i), L["kind"], at, ", ".join(f"{k}={v}" for k, v in extra.items()))
        console.print(t)

    def cmd_watch(self, interval: int = 30) -> None:
        info(f"Refreshing widgets every {interval}s. Press Ctrl+C to stop.")
        try:
            while True:
                self.wall.apply()
                time.sleep(max(5, interval))
        except KeyboardInterrupt:
            ok("Stopped watching.")

    # ---------------------------------------------------------------- icons
    def cmd_icons(self, tokens: list[str]) -> None:
        d = self.desk()
        if not tokens or tokens[0] == "list":
            t = Table(title=f"Desktop Icons ({d.count()})", header_style="bold green")
            t.add_column("#", width=4, style="dim")
            t.add_column("Name")
            t.add_column("Position (x, y)", justify="right")
            for ic in d.icons():
                t.add_row(str(ic.index + 1), ic.name, f"{ic.x}, {ic.y}")
            console.print(t)
            return

        sub = tokens[0].lower()
        rest = tokens[1:]
        if sub in icmod.SHAPES:
            n = d.arrange(sub)
            ok(f"Arranged {n} icons into a [bold]{sub}[/].")
        elif sub == "arrange":
            shape = rest[0].lower() if rest else "circle"
            n = d.arrange(shape)
            ok(f"Arranged {n} icons into a [bold]{shape}[/].")
        elif sub == "shuffle":
            d.shuffle()
            ok("Shuffled icon positions.")
        elif sub == "move":
            if len(rest) < 2:
                raise WallplayError('Usage: icons move <name-or-#> <position>   e.g. icons move "Recycle Bin" bottom-right')
            name = d.move(rest[0], rest[1])
            ok(f"Moved [bold]{name}[/] to {rest[1]}.")
        elif sub in icmod.ANIMATIONS or sub == "animate":
            kind = rest[0].lower() if sub == "animate" and rest else sub
            tail = rest[1:] if sub == "animate" else rest
            pos, opts = split_opts(tail)
            secs = float(opts["seconds"]) if "seconds" in opts else (float(pos[0]) if pos else None)
            msg = f"for {secs:g}s" if secs else "(press Ctrl+C to stop and glide icons back)"
            info(f"Animating icons: [bold]{kind}[/] {msg}…")
            d.animate(kind, seconds=secs)
            ok("Icons returned to their spots.")
        elif sub == "hide":
            d.show(False)
            ok("Desktop icons hidden (`icons show` brings them back).")
        elif sub == "show":
            d.show(True)
            ok("Desktop icons visible.")
        elif sub == "save":
            name = rest[0] if rest else "saved"
            n = d.save_layout(name)
            ok(f"Saved {n} icon positions as layout [bold]{name}[/].")
        elif sub in ("load", "restore"):
            name = rest[0] if rest else "original"
            n = d.load_layout(name)
            ok(f"Restored {n} icons from layout [bold]{name}[/].")
        elif sub == "undo":
            n = d.load_layout("_undo")
            ok(f"Undid icon move ({n} icons).")
        elif sub == "layouts":
            icmod.LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
            names = sorted(p.stem for p in icmod.LAYOUT_DIR.glob("*.json") if not p.stem.startswith("_"))
            info("Saved icon layouts: " + (", ".join(names) if names else "(none yet)"))
        else:
            raise WallplayError(
                f"Unknown icons command '{sub}'. Shapes: {', '.join(icmod.SHAPES)}. "
                f"Animations: {', '.join(icmod.ANIMATIONS)}."
            )

    # ---------------------------------------------------------------- live
    def cmd_live(self, tokens: list[str]) -> None:
        if not tokens or tokens[0] in ("status", "list"):
            cur = live_info()
            if cur:
                ok(f"Live wallpaper running: [bold]{cur['effect']}[/] (PID {cur['pid']})")
            else:
                info("No live wallpaper running. Available: " + ", ".join(livemod.EFFECTS))
            return
        sub = tokens[0].lower()
        if sub in ("stop", "off", "kill"):
            stop_live()
        else:
            start_live(sub, tokens[1] if len(tokens) > 1 else None)

    # ---------------------------------------------------------------- theme & accent
    def cmd_theme(self, tokens: list[str]) -> None:
        if not tokens:
            info(f"Current Windows theme is [bold]{thmod.current_mode()}[/]. Usage: theme <dark|light|toggle|glass on|off>")
            return
        sub = tokens[0].lower()
        if sub in ("dark", "light", "toggle"):
            now = thmod.set_mode(sub)
            ok(f"Switched Windows + apps to [bold]{now}[/] mode.")
        elif sub in ("glass", "transparency"):
            on = (tokens[1].lower() if len(tokens) > 1 else "on") in ("on", "1", "true", "yes")
            thmod.set_transparency(on)
            ok(f"Taskbar/window transparency {'enabled' if on else 'disabled'}.")
        elif sub in ("bars", "titlebars"):
            on = (tokens[1].lower() if len(tokens) > 1 else "on") in ("on", "1", "true", "yes")
            thmod.set_accent_bars(on)
            ok(f"Accent colour on taskbar & title bars {'enabled' if on else 'disabled'}.")
        else:
            raise WallplayError("Usage: theme <dark|light|toggle|glass on|off|bars on|off>")

    def cmd_accent(self, tokens: list[str]) -> None:
        if not tokens:
            raise WallplayError("Usage: accent <color|match|auto|random>")
        arg = tokens[0].lower()
        if arg == "auto":
            thmod.accent_auto()
            ok("Windows will pick the accent colour automatically.")
        elif arg in ("match", "wall", "wallpaper"):
            rgb = thmod.vibrant_color(self.wall.render((320, 180)))
            thmod.set_accent(rgb)
            hx = "#%02x%02x%02x" % rgb
            ok(f"Matched Windows accent colour to your wallpaper ([bold]{hx}[/]).")
        else:
            rgb = thmod.set_accent(arg)
            hx = "#%02x%02x%02x" % rgb
            ok(f"Set Windows accent colour to [bold]{hx}[/].")

    # ---------------------------------------------------------------- presets
    def cmd_preset(self, tokens: list[str]) -> None:
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        if not tokens or tokens[0] == "list":
            names = sorted(p.stem for p in PRESET_DIR.glob("*.json"))
            info("Presets: " + (", ".join(names) if names else "(none saved yet — `preset save <name>`)"))
            return
        sub = tokens[0].lower()
        if sub == "save" and len(tokens) > 1:
            name = tokens[1]
            pdir = PRESET_DIR / name
            pdir.mkdir(parents=True, exist_ok=True)
            base_file = STATE_DIR / str(self.wall.s.get("base"))
            if base_file.is_file():
                shutil.copy2(base_file, pdir / "base.png")
            write_json(PRESET_DIR / f"{name}.json", {
                "filters": self.wall.s["filters"], "layers": self.wall.s["layers"],
                "has_base": base_file.is_file(),
            })
            with _suppress_missing():
                self.desk().save_layout(f"preset_{name}")
            ok(f"Saved preset [bold]{name}[/] (wallpaper + icon layout).")
        elif sub == "load" and len(tokens) > 1:
            name = tokens[1]
            data = read_json(PRESET_DIR / f"{name}.json", None)
            if not data:
                raise WallplayError(f"No preset named '{name}'.")
            with self.wall.change():
                bpath = PRESET_DIR / name / "base.png"
                if data.get("has_base") and bpath.is_file():
                    from PIL import Image
                    self.wall.s["base"] = self.wall._new_base(Image.open(bpath))
                self.wall.s["filters"] = data.get("filters", [])
                self.wall.s["layers"] = data.get("layers", [])
            with _suppress_missing():
                self.desk().load_layout(f"preset_{name}")
            ok(f"Loaded preset [bold]{name}[/].")
        else:
            raise WallplayError("Usage: preset <list | save <name> | load <name>>")

    # ---------------------------------------------------------------- status & help
    def cmd_status(self) -> None:
        W, H = winapi.screen_size()
        lv = live_info()
        ic_count = "?"
        with _suppress_missing():
            ic_count = str(self.desk().count())
        lines = [
            f"[bold]Screen:[/] {W}×{H}   [bold]Theme:[/] {thmod.current_mode()}   [bold]Desktop icons:[/] {ic_count}",
            f"[bold]Filters ({len(self.wall.s['filters'])}):[/] "
            + (", ".join(f["name"] for f in self.wall.s["filters"]) or "none"),
            f"[bold]Layers ({len(self.wall.s['layers'])}):[/] "
            + (", ".join(L["kind"] for L in self.wall.s["layers"]) or "none"),
            f"[bold]Live layer:[/] " + (f"{lv['effect']} (PID {lv['pid']})" if lv else "off"),
        ]
        console.print(Panel("\n".join(lines), title="wallplay status", border_style="cyan"))

    def cmd_help(self, rest: list[str]) -> None:
        text = r"""[bold cyan]Wallpaper Base & Colours[/]
  [bold]solid[/] <color|random>                   Fill with a colour (`solid hotpink`, `solid #0f172a`)
  [bold]gradient[/] <c1> <c2> \[c3] \[angle=135]   Smooth multi-stop colour gradient
  [bold]aurora[/] \[seed]                         Procedural dreamy aurora wallpaper
  [bold]image[/] <path>                          Use any picture as the base
  [bold]original[/]                              Go back to your original photo as the base

[bold cyan]Colour & Art Filters[/]  [dim](stack as many as you want!)[/]
  [bold]tint[/] <color> \[0-1]   [bold]hue[/] <deg>        [bold]duotone[/] <dark> <light>   [bold]saturate[/] <f>
  [bold]bright[/] <f>           [bold]contrast[/] <f>     [bold]gray[/]    [bold]sepia[/]    [bold]invert[/]  [bold]blur[/] \[r]
  [bold]pixelate[/] \[size]      [bold]posterize[/] \[1-8]  [bold]vignette[/] \[0-1]   [bold]neon[/]    [bold]glitch[/] \[amt]
  [bold]dream[/]                [bold]cartoon[/]          [bold]sketch[/]           [bold]mirror[/]  [bold]flip[/]
  [bold]surprise[/]             Random filter combo      [bold]unfilter[/] \[#|last|all]

[bold cyan]Add Things To Your Wallpaper[/]  [dim](positions: center, top-left, bottom-right, 50%,20%, 400,300 …)[/]
  [bold]add text[/] "Hello" \[at=...] \[color=...] \[size=90] \[font=bold|mono|script|impact] \[angle=-8]
  [bold]add sticker[/] <cat|rocket|fire|✨|...> \[at=...] \[size=160] \[angle=15]      ([bold]stickers[/] lists all)
  [bold]add shape[/] <circle|ring|star|heart|triangle|square|diamond|moon> \[color=...] \[outline=1]
  [bold]add note[/] "Remember this!" \[at=top-right] \[color=#fff176] \[angle=-4]     Sticky note with tape
  [bold]add clock[/] \[at=center] \[format=24|12]   [bold]add calendar[/] \[at=bottom-left] \[color=#ff4f8b]
  [bold]add quote[/] \["text"] \[author=...]        [bold]add greeting[/] \[Name]   [bold]add sysinfo[/]
  [bold]add countdown[/] YYYY-MM-DD \["Trip!"]     [bold]add image[/] <file.png> \[at=...] \[scale=0.5]
  [bold]layers[/] · [bold]edit[/] <#> key=val · [bold]remove[/] \[#|last|all] · [bold]front[/] <#> · [bold]watch[/] \[secs]

[bold cyan]Play With Your Desktop Icons[/]
  [bold]icons list[/] · [bold]icons move[/] <name|#> <pos> · [bold]icons shuffle[/] · [bold]icons hide[/] / [bold]show[/]
  [bold]icons[/] <circle|heart|spiral|wave|star|grid|line|diagonal|square|triangle|infinity|smile|scatter>
  [bold]icons[/] <dance|orbit|gravity|follow|flee|magnet|rain> \[seconds]    [dim](mouse-interactive!)[/]
  [bold]icons save[/] <name> · [bold]icons load[/] <name> · [bold]icons restore[/] · [bold]icons undo[/]

[bold cyan]Live Interactive Wallpaper[/]  [dim](renders *behind* your icons, reacts to mouse + clicks)[/]
  [bold]live[/] <snow|fireflies|bubbles|matrix|starfield|fireworks|rain>
  [bold]live pet[/] \[cat|dog|fox|duck|dino|unicorn|penguin|ghost|robot]     Desktop pet that chases your mouse
  [bold]live stop[/] · [bold]live status[/]

[bold cyan]Windows Colours & Safety[/]
  [bold]theme[/] <dark|light|toggle|glass on|off|bars on|off>   [bold]accent[/] <color|match|auto|random>
  [bold]undo[/] (undoes all changes: stickers, filters, base & icons) · [bold]undo step[/] (undo 1 step)
  [bold]clear[/] \[layers|filters|all] · [bold]reset[/] · [bold]restore[/]
  [bold]preset save[/] <name> · [bold]preset load[/] <name> · [bold]preview[/] · [bold]export[/] <file.png>"""
        console.print(Panel(text, title="wallplay commands", border_style="bright_blue"))


class _suppress_missing:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is not None and issubclass(exc_type, WallplayError)


# ==================================================================== REPL + entrypoint
BANNER = r"""[bold magenta]
 __      ____ _ ___| |_ __ | | __ _ _   _
 \ \ /\ / / _` | | | '_ \| |/ _` | | | |
  \ V  V / (_| | | | |_) | | (_| | |_| |
   \_/\_/ \__,_|_|_| .__/|_|\__,_|\__, |
                   |_|            |___/ [/]  [dim]play with your desktop from the terminal[/]"""


def repl(app: App) -> None:
    console.print(BANNER)
    app.cmd_status()
    console.print(
        "[dim]Try:[/] [bold]aurora[/], [bold]add clock at=center[/], [bold]add sticker cat at=bottom-right[/], "
        "[bold]icons heart[/], [bold]icons flee 8[/], [bold]live fireflies[/], [bold]help[/], [bold]restore[/]\n"
    )
    while True:
        try:
            line = console.input("[bold magenta]wallplay[/][bold cyan] ❯ [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not line:
            continue
        for part in split_commands(line):
            try:
                tokens = shlex.split(part)
            except ValueError as e:
                warn(str(e))
                continue
            try:
                if not app.run_tokens(tokens):
                    return
            except WallplayError as e:
                warn(str(e))
            except Exception as e:
                console.print(f"[bold red]Error:[/] {e}")


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    args = []
    for tok in raw:
        if tok.startswith("#") and not (len(tok) in (4, 7, 9) and all(c in "0123456789abcdefABCDEF" for c in tok[1:])):
            break
        args.append(tok)
    app = App()
    if not args:
        repl(app)
        return
    try:
        app.run_tokens(args)
    except WallplayError as e:
        warn(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        console.print()


if __name__ == "__main__":
    main()
