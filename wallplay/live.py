"""Live, interactive desktop overlay layer.

Run as a background process:  python -m wallplay.live <effect> [arg]
Renders on a transparent click-through overlay so it works on all Windows 10/11
builds (including 24H2/26H2) without blocking clicks on icons or apps.
"""
from __future__ import annotations

import math
import random
import sys
import tkinter as tk
import traceback

from PIL import Image, ImageDraw, ImageOps, ImageTk

from . import winapi as w
from .common import STATE_DIR, ensure_dir, random_color

STOP_FILE = STATE_DIR / "live.stop"
READY_FILE = STATE_DIR / "live.ready"
LOG_FILE = STATE_DIR / "live.log"
TRANSPARENT_HEX = "#010101"
TRANSPARENT_RGB = (1, 1, 1)
EFFECTS = ["snow", "fireflies", "bubbles", "matrix", "starfield", "fireworks", "pet", "rain"]
BURST_COLORS = ["#ff5e7e", "#ffd166", "#06d6a0", "#4cc9f0", "#c77dff", "#ffffff", "#ff9e00"]


# ===================================================================== effects
class Effect:
    def __init__(self, cv: tk.Canvas, W, H, arg=None):
        self.cv, self.W, self.H, self.arg = cv, W, H, arg
        self.parts = []  # [item, x, y, vx, vy, life, r]
        self.t = 0.0
        self.setup()

    def setup(self):
        pass

    def update(self, mx, my, click):
        pass

    def burst(self, x, y, n=48, colors=None, speed=7.0):
        colors = colors or BURST_COLORS
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(speed * 0.3, speed)
            r = random.uniform(2.2, 4.5)
            item = self.cv.create_oval(x - r, y - r, x + r, y + r, fill=random.choice(colors), outline="")
            self.parts.append([item, x, y, math.cos(a) * s, math.sin(a) * s, random.randint(35, 70), r])

    def step(self, mx, my, click):
        self.t += 1 / 30
        if click:
            self.burst(*click)
        self.update(mx, my, click)
        alive = []
        for p in self.parts:
            item, x, y, vx, vy, life, r = p
            vy += 0.18
            vx *= 0.985
            x, y, life = x + vx, y + vy, life - 1
            r *= 0.985
            if life <= 0:
                self.cv.delete(item)
                continue
            self.cv.coords(item, x - r, y - r, x + r, y + r)
            alive.append([item, x, y, vx, vy, life, r])
        self.parts = alive


class Snow(Effect):
    def setup(self):
        self.flakes = []
        for _ in range(220):
            r = random.uniform(2.0, 5.2)
            x, y = random.uniform(0, self.W), random.uniform(0, self.H)
            col = random.choice(["#ffffff", "#f0f7ff", "#dbeafe"])
            item = self.cv.create_oval(0, 0, 0, 0, fill=col, outline="#93c5fd")
            self.flakes.append([item, x, y, 0.0, r * 0.45 + 0.5, r, random.uniform(0, 6.3)])

    def update(self, mx, my, click):
        R = 150
        for f in self.flakes:
            item, x, y, vx, vy, r, ph = f
            dx, dy = x - mx, y - my
            d2 = dx * dx + dy * dy
            if d2 < R * R:
                d = math.sqrt(d2) + 0.01
                force = (R - d) / R * 2.4
                vx += dx / d * force
                vy += dy / d * force
            vx = vx * 0.93 + math.sin(self.t * 1.3 + ph) * 0.05
            vy = vy * 0.93 + (r * 0.45 + 0.5) * 0.07
            x, y = x + vx, y + vy
            if y > self.H + 5:
                y, x = -5, random.uniform(0, self.W)
            x %= self.W
            f[1:5] = [x, y, vx, vy]
            self.cv.coords(item, x - r, y - r, x + r, y + r)


class Rain(Effect):
    def setup(self):
        self.drops = []
        for _ in range(240):
            x, y = random.uniform(0, self.W), random.uniform(0, self.H)
            ln = random.uniform(12, 26)
            item = self.cv.create_line(0, 0, 0, 0, fill="#7dd3fc", width=2)
            self.drops.append([item, x, y, ln, random.uniform(14, 22)])

    def update(self, mx, my, click):
        for d in self.drops:
            item, x, y, ln, sp = d
            y += sp
            x += 2
            # umbrella: the cursor shields the rain under it
            if abs(x - mx) < 75 and my - 12 < y < my + 8:
                self.burst(x, my - 8, n=2, colors=["#bae6fd", "#ffffff"], speed=3)
                y = -random.uniform(0, 200)
                x = random.uniform(0, self.W)
            if y > self.H:
                y, x = -ln, random.uniform(0, self.W)
            d[1], d[2] = x, y
            self.cv.coords(item, x, y, x - 2 * ln / sp, y - ln)


class Fireflies(Effect):
    def setup(self):
        self.flies = []
        for _ in range(75):
            x, y = random.uniform(0, self.W), random.uniform(0, self.H)
            r = random.uniform(2.8, 4.8)
            glow = self.cv.create_oval(0, 0, 0, 0, fill="#b45309", outline="")
            core = self.cv.create_oval(0, 0, 0, 0, fill="#fef08a", outline="")
            self.flies.append([glow, core, x, y, random.uniform(0, 6.3), r, random.uniform(0, 6.3)])

    def update(self, mx, my, click):
        for f in self.flies:
            glow, core, x, y, ang, r, ph = f
            ang += random.uniform(-0.28, 0.28)
            dx, dy = mx - x, my - y
            d = math.hypot(dx, dy)
            sp = 1.4
            if 25 < d < 380:  # drawn towards the cursor
                target = math.atan2(dy, dx)
                ang += math.atan2(math.sin(target - ang), math.cos(target - ang)) * 0.09
                sp = 2.6
            x = (x + math.cos(ang) * sp) % self.W
            y = (y + math.sin(ang) * sp) % self.H
            bright = (math.sin(self.t * 3.2 + ph) + 1) / 2
            gr = r * (2.2 + 1.8 * bright)
            f[2:5] = [x, y, ang]
            self.cv.coords(glow, x - gr, y - gr, x + gr, y + gr)
            self.cv.coords(core, x - r, y - r, x + r, y + r)
            self.cv.itemconfigure(
                glow, fill="#f59e0b" if bright > 0.5 else "#92400e",
            )
            self.cv.itemconfigure(
                core, fill="#fef9c3" if bright > 0.35 else "#fde047",
            )


class Bubbles(Effect):
    def setup(self):
        self.bubbles = [self._new(random.uniform(0, self.H)) for _ in range(45)]

    def _new(self, y=None):
        r = random.uniform(14, 44)
        x = random.uniform(0, self.W)
        y = self.H + r + random.uniform(0, 300) if y is None else y
        col = random.choice(["#7dd3fc", "#a5f3fc", "#f9a8d4", "#c4b5fd", "#bae6fd"])
        ring = self.cv.create_oval(0, 0, 0, 0, outline=col, width=2)
        shine = self.cv.create_arc(0, 0, 0, 0, start=100, extent=60, style="arc", outline="#ffffff", width=2)
        return [ring, shine, x, y, r, random.uniform(0.8, 2.1), random.uniform(0, 6.3)]

    def update(self, mx, my, click):
        for i, b in enumerate(self.bubbles):
            ring, shine, x, y, r, sp, ph = b
            y -= sp
            x += math.sin(self.t * 2 + ph) * 0.7
            if math.hypot(x - mx, y - my) < r + 10 or y < -r:  # pop!
                if y >= -r:
                    self.burst(x, y, n=16, colors=["#7dd3fc", "#ffffff", "#f9a8d4"], speed=4.5)
                self.cv.delete(ring)
                self.cv.delete(shine)
                self.bubbles[i] = self._new()
                continue
            b[2], b[3] = x, y
            self.cv.coords(ring, x - r, y - r, x + r, y + r)
            k = r * 0.7
            self.cv.coords(shine, x - k, y - k, x + k, y + k)


class Matrix(Effect):
    CHARS = "アイウエオカキクケコサシスセソタチツテトナニヌネノ0123456789$#@%&*+="

    def setup(self):
        self.font = ("Consolas", 14, "bold")
        self.lh = 18
        self.cols = []
        for x in range(12, self.W, 24):
            n = random.randint(8, 22)
            trail = self.cv.create_text(x, 0, text="", fill="#00e65b", font=self.font, anchor="s")
            head = self.cv.create_text(x, 0, text="", fill="#e6ffe9", font=self.font, anchor="s")
            self.cols.append([trail, head, x, random.uniform(-self.H, 0), random.uniform(3.5, 9.5), n,
                              [random.choice(self.CHARS) for _ in range(n)]])

    def update(self, mx, my, click):
        for c in self.cols:
            trail, head, x, y, sp, n, chars = c
            near = abs(x - mx) < 80
            y += sp * (2.3 if near else 1)
            if random.random() < 0.3:
                chars[random.randrange(n)] = random.choice(self.CHARS)
            if y - n * self.lh > self.H:
                y = random.uniform(-300, 0)
            c[3] = y
            self.cv.itemconfigure(trail, text="\n".join(chars[:-1]), fill="#86efac" if near else "#00e65b")
            self.cv.coords(trail, x, y - self.lh)
            self.cv.itemconfigure(head, text=chars[-1])
            self.cv.coords(head, x, y)


class Starfield(Effect):
    def setup(self):
        self.cx, self.cy = self.W / 2, self.H / 2
        self.stars = [self._new(random.uniform(0.1, 1)) for _ in range(240)]
        self.boost = 0

    def _new(self, z=1.0):
        item = self.cv.create_line(0, 0, 0, 0, fill="#ffffff", width=2)
        return [item, random.uniform(-1, 1) * self.W, random.uniform(-1, 1) * self.H, z, None]

    def update(self, mx, my, click):
        if click:
            self.boost = 45
        self.boost = max(0, self.boost - 1)
        self.cx += (mx - self.cx) * 0.05
        self.cy += (my - self.cy) * 0.05
        speed = 0.009 + (0.032 if self.boost else 0)
        for s in self.stars:
            item, x, y, z, prev = s
            z -= speed
            if z <= 0.02:
                s[1:5] = [random.uniform(-1, 1) * self.W, random.uniform(-1, 1) * self.H, 1.0, None]
                continue
            px, py = self.cx + x / z * 0.5, self.cy + y / z * 0.5
            if prev is None:
                prev = (px, py)
            shade = int(min(255, 110 + (1 - z) * 145))
            self.cv.itemconfigure(item, fill="#%02x%02x%02x" % (shade, shade, 255), width=2 if z > 0.45 else 3)
            self.cv.coords(item, prev[0], prev[1], px, py)
            s[3], s[4] = z, (px, py)


class Fireworks(Effect):
    def setup(self):
        self.rockets = []
        self.next = 0

    def update(self, mx, my, click):
        self.next -= 1
        if self.next <= 0:
            self.next = random.randint(18, 48)
            x = random.uniform(self.W * 0.1, self.W * 0.9)
            item = self.cv.create_oval(0, 0, 0, 0, fill="#ffe8a3", outline="")
            self.rockets.append([item, x, self.H, random.uniform(-1.5, 1.5), random.uniform(-17, -12)])
        alive = []
        for r in self.rockets:
            item, x, y, vx, vy = r
            vy += 0.25
            x, y = x + vx, y + vy
            if vy >= -1:
                self.cv.delete(item)
                c = random_color()
                self.burst(x, y, n=70, colors=[c, "#ffffff", random_color()], speed=8.5)
                continue
            self.cv.coords(item, x - 3, y - 3, x + 3, y + 3)
            alive.append([item, x, y, vx, vy])
        self.rockets = alive


class Pet(Effect):
    NAMES = {"cat": "🐈", "dog": "🐕", "fox": "🦊", "unicorn": "🦄", "penguin": "🐧", "duck": "🦆",
             "dino": "🦖", "ghost": "👻", "snail": "🐌", "turtle": "🐢", "bee": "🐝", "robot": "🤖"}

    def setup(self):
        emoji = self.NAMES.get(str(self.arg or "cat").lower(), self.arg or "🐈")
        raw = self._render_emoji(emoji, 96)
        self.img_l = ImageTk.PhotoImage(raw)
        self.img_r = ImageTk.PhotoImage(ImageOps.mirror(raw))
        self.zz = ImageTk.PhotoImage(self._render_emoji("💤", 40))
        self.heart = ImageTk.PhotoImage(self._render_emoji("💖", 32))
        self.x, self.y = self.W / 2, self.H * 0.65
        self.vy = 0.0
        self.face_left = True
        self.item = self.cv.create_image(self.x, self.y, image=self.img_l)
        self.zz_item = None
        self.hearts = []
        self.last_mouse, self.still = None, 0

    def _render_emoji(self, ch, size) -> Image.Image:
        from .wallpaper import EMOJI_FONT, load_font
        font = load_font(EMOJI_FONT, size)
        side = int(size * 1.45)
        rgba = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        ImageDraw.Draw(rgba).text((side / 2, side / 2), ch, font=font, embedded_color=True, anchor="mm")
        # Flatten onto TRANSPARENT_RGB for crisp chroma-key rendering without dark fringes
        out = Image.new("RGB", (side, side), TRANSPARENT_RGB)
        src = rgba.load()
        dst = out.load()
        for yy in range(side):
            for xx in range(side):
                r, g, b, a = src[xx, yy]
                if a >= 90:
                    if (r, g, b) == TRANSPARENT_RGB:
                        r, g, b = 4, 4, 4
                    dst[xx, yy] = (r, g, b)
        return out

    def update(self, mx, my, click):
        moved = self.last_mouse != (mx, my)
        self.last_mouse = (mx, my)
        self.still = 0 if moved else self.still + 1
        dx, dy = mx - self.x, my - self.y
        d = math.hypot(dx, dy)
        if click and math.hypot(click[0] - self.x, click[1] - self.y) < 85:
            self.vy = -15  # boop -> jump + hearts
            for _ in range(6):
                self._heart()
        if d > 70 and self.still < 120:
            sp = min(7.5, d * 0.055)
            self.x += dx / d * sp
            self.y += dy / d * sp
            if abs(dx) > 4:
                self.face_left = dx < 0
        elif d <= 70 and random.random() < 0.05:
            self._heart()
        self.vy += 0.9
        self.y += self.vy if self.vy < 0 else 0
        if self.vy > 0:
            self.vy = 0
        self.cv.itemconfigure(self.item, image=self.img_l if self.face_left else self.img_r)
        bob = math.sin(self.t * 12) * 3.5 if d > 70 and self.still < 120 else 0
        self.cv.coords(self.item, self.x, self.y + bob)
        if self.still > 150 and self.zz_item is None:
            self.zz_item = self.cv.create_image(self.x + 50, self.y - 55, image=self.zz)
        elif self.still <= 150 and self.zz_item is not None:
            self.cv.delete(self.zz_item)
            self.zz_item = None
        alive = []
        for h in self.hearts:
            item, hx, hy, life = h
            hy -= 1.6
            hx += math.sin(life / 6) * 0.8
            life -= 1
            if life <= 0:
                self.cv.delete(item)
                continue
            self.cv.coords(item, hx, hy)
            alive.append([item, hx, hy, life])
        self.hearts = alive

    def _heart(self):
        hx, hy = self.x + random.uniform(-30, 30), self.y - 50
        self.hearts.append([self.cv.create_image(hx, hy, image=self.heart), hx, hy, 60])


CLASSES = {"snow": Snow, "fireflies": Fireflies, "bubbles": Bubbles, "matrix": Matrix,
           "starfield": Starfield, "fireworks": Fireworks, "pet": Pet, "rain": Rain}


# ===================================================================== runner
def run(effect: str, arg=None):
    ensure_dir()
    STOP_FILE.unlink(missing_ok=True)
    READY_FILE.unlink(missing_ok=True)
    try:
        cls = CLASSES[effect]
        W, H = w.screen_size()
        root = tk.Tk()
        root.title("wallplay-live")
        root.overrideredirect(True)
        root.geometry(f"{W}x{H}+0+0")
        root.configure(bg=TRANSPARENT_HEX)
        root.wm_attributes("-transparentcolor", TRANSPARENT_HEX)
        root.wm_attributes("-topmost", True)

        cv = tk.Canvas(root, width=W, height=H, highlightthickness=0, bd=0, bg=TRANSPARENT_HEX)
        cv.pack(fill="both", expand=True)
        root.update_idletasks()
        root.update()

        hwnd = w.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
        w.make_clickthrough_overlay(hwnd, W, H)

        eff = cls(cv, W, H, arg)
        READY_FILE.write_text("ready", encoding="utf-8")
        state = {"down": False, "tick": 0}

        def tick():
            state["tick"] += 1
            if state["tick"] % 10 == 0 and STOP_FILE.exists():
                shutdown()
                return
            if state["tick"] % 90 == 0:
                # Keep click-through overlay on top without activating
                w.SetWindowPos(hwnd, w.HWND(-1), 0, 0, W, H, w.SWP_NOACTIVATE | w.SWP_NOMOVE | w.SWP_NOSIZE)
            sx, sy = w.cursor_pos()
            down = w.key_down(0x01)
            click = (sx, sy) if (down and not state["down"]) else None
            state["down"] = down
            try:
                eff.step(sx, sy, click)
            except tk.TclError:
                return
            root.after(30, tick)

        def shutdown():
            READY_FILE.unlink(missing_ok=True)
            STOP_FILE.unlink(missing_ok=True)
            try:
                root.destroy()
            except Exception:
                pass

        root.after(30, tick)
        root.mainloop()
    except KeyboardInterrupt:
        pass
    except Exception:
        LOG_FILE.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CLASSES:
        print(f"usage: python -m wallplay.live <{'|'.join(EFFECTS)}> [arg]")
        sys.exit(2)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
