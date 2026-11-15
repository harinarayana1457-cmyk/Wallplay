"""Live, interactive wallpaper layer rendered *behind* the desktop icons.

Run as a background process:  python -m wallplay.live <effect> [arg]
Everything reacts to your mouse cursor; clicking empty desktop makes fireworks.
"""
from __future__ import annotations

import math
import random
import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageTk

from . import winapi as w
from .common import STATE_DIR, ensure_dir, random_color

STOP_FILE = STATE_DIR / "live.stop"
EFFECTS = ["snow", "fireflies", "bubbles", "matrix", "starfield", "fireworks", "pet", "rain"]
BURST_COLORS = ["#ff5e7e", "#ffd166", "#06d6a0", "#4cc9f0", "#c77dff", "#ffffff", "#ff9e00"]


def current_wallpaper_image(size, darken=1.0):
    p = w.get_wallpaper_path()
    src = Path(p) if p and Path(p).exists() else w.transcoded_wallpaper()
    try:
        img = Image.open(src).convert("RGB") if src else Image.new("RGB", size, "#101020")
    except OSError:
        img = Image.new("RGB", size, "#101020")
    img = ImageOps.fit(img, size, Image.LANCZOS)
    if darken != 1.0:
        img = ImageEnhance.Brightness(img).enhance(darken)
    return img


# ===================================================================== effects
class Effect:
    darken = 1.0

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
            r = random.uniform(2, 4)
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
        for _ in range(240):
            r = random.uniform(1.2, 4.2)
            x, y = random.uniform(0, self.W), random.uniform(0, self.H)
            item = self.cv.create_oval(0, 0, 0, 0, fill="white", outline="")
            self.flakes.append([item, x, y, 0.0, r * 0.45 + 0.4, r, random.uniform(0, 6.3)])

    def update(self, mx, my, click):
        R = 140
        for f in self.flakes:
            item, x, y, vx, vy, r, ph = f
            dx, dy = x - mx, y - my
            d2 = dx * dx + dy * dy
            if d2 < R * R:
                d = math.sqrt(d2) + 0.01
                force = (R - d) / R * 2.2
                vx += dx / d * force
                vy += dy / d * force
            vx = vx * 0.93 + math.sin(self.t * 1.3 + ph) * 0.04
            vy = vy * 0.93 + (r * 0.45 + 0.4) * 0.07
            x, y = x + vx, y + vy
            if y > self.H + 5:
                y, x = -5, random.uniform(0, self.W)
            x %= self.W
            f[1:5] = [x, y, vx, vy]
            self.cv.coords(item, x - r, y - r, x + r, y + r)


class Rain(Effect):
    darken = 0.7

    def setup(self):
        self.drops = []
        for _ in range(260):
            x, y = random.uniform(0, self.W), random.uniform(0, self.H)
            ln = random.uniform(10, 24)
            item = self.cv.create_line(0, 0, 0, 0, fill="#9fc6ff", width=1)
            self.drops.append([item, x, y, ln, random.uniform(14, 22)])

    def update(self, mx, my, click):
        for d in self.drops:
            item, x, y, ln, sp = d
            y += sp
            x += 2
            # umbrella: the cursor shields the rain under it
            if abs(x - mx) < 70 and my - 10 < y < my + 6:
                self.burst(x, my - 8, n=2, colors=["#cfe3ff"], speed=3)
                y = -random.uniform(0, 200)
                x = random.uniform(0, self.W)
            if y > self.H:
                y, x = -ln, random.uniform(0, self.W)
            d[1], d[2] = x, y
            self.cv.coords(item, x, y, x - 2 * ln / sp, y - ln)


class Fireflies(Effect):
    darken = 0.55

    def setup(self):
        self.flies = []
        for _ in range(70):
            x, y = random.uniform(0, self.W), random.uniform(0, self.H)
            r = random.uniform(2, 3.5)
            glow = self.cv.create_oval(0, 0, 0, 0, fill="#5c5a1e", outline="")
            core = self.cv.create_oval(0, 0, 0, 0, fill="#fffb96", outline="")
            self.flies.append([glow, core, x, y, random.uniform(0, 6.3), r, random.uniform(0, 6.3)])

    def update(self, mx, my, click):
        for f in self.flies:
            glow, core, x, y, ang, r, ph = f
            ang += random.uniform(-0.3, 0.3)
            dx, dy = mx - x, my - y
            d = math.hypot(dx, dy)
            sp = 1.2
            if 30 < d < 320:  # drawn towards the cursor
                target = math.atan2(dy, dx)
                ang += math.atan2(math.sin(target - ang), math.cos(target - ang)) * 0.08
                sp = 2.2
            x = (x + math.cos(ang) * sp) % self.W
            y = (y + math.sin(ang) * sp) % self.H
            bright = (math.sin(self.t * 3 + ph) + 1) / 2
            gr = r * (2.5 + 2 * bright)
            f[2:5] = [x, y, ang]
            self.cv.coords(glow, x - gr, y - gr, x + gr, y + gr)
            self.cv.coords(core, x - r, y - r, x + r, y + r)
            self.cv.itemconfigure(core, fill="#fffb96" if bright > 0.35 else "#a8a34a")


class Bubbles(Effect):
    def setup(self):
        self.bubbles = [self._new(random.uniform(0, self.H)) for _ in range(40)]

    def _new(self, y=None):
        r = random.uniform(12, 42)
        x = random.uniform(0, self.W)
        y = self.H + r + random.uniform(0, 300) if y is None else y
        ring = self.cv.create_oval(0, 0, 0, 0, outline="#d6f1ff", width=2)
        shine = self.cv.create_arc(0, 0, 0, 0, start=100, extent=60, style="arc", outline="white", width=2)
        return [ring, shine, x, y, r, random.uniform(0.6, 1.8), random.uniform(0, 6.3)]

    def update(self, mx, my, click):
        for i, b in enumerate(self.bubbles):
            ring, shine, x, y, r, sp, ph = b
            y -= sp
            x += math.sin(self.t * 2 + ph) * 0.6
            if math.hypot(x - mx, y - my) < r + 6 or y < -r:  # pop!
                if y >= -r:
                    self.burst(x, y, n=14, colors=["#d6f1ff", "#ffffff", "#a0e7ff"], speed=4)
                self.cv.delete(ring)
                self.cv.delete(shine)
                self.bubbles[i] = self._new()
                continue
            b[2], b[3] = x, y
            self.cv.coords(ring, x - r, y - r, x + r, y + r)
            k = r * 0.7
            self.cv.coords(shine, x - k, y - k, x + k, y + k)


class Matrix(Effect):
    darken = 0.3
    CHARS = "アイウエオカキクケコサシスセソタチツテトナニヌネノ0123456789$#@%&*+="

    def setup(self):
        self.font = ("Consolas", 14, "bold")
        self.lh = 18
        self.cols = []
        for x in range(10, self.W, 22):
            n = random.randint(8, 24)
            trail = self.cv.create_text(x, 0, text="", fill="#00d75a", font=self.font, anchor="s")
            head = self.cv.create_text(x, 0, text="", fill="#e6ffe9", font=self.font, anchor="s")
            self.cols.append([trail, head, x, random.uniform(-self.H, 0), random.uniform(3, 9), n,
                              [random.choice(self.CHARS) for _ in range(n)]])

    def update(self, mx, my, click):
        for c in self.cols:
            trail, head, x, y, sp, n, chars = c
            near = abs(x - mx) < 70
            y += sp * (2.2 if near else 1)
            if random.random() < 0.3:
                chars[random.randrange(n)] = random.choice(self.CHARS)
            if y - n * self.lh > self.H:
                y = random.uniform(-300, 0)
            c[3] = y
            self.cv.itemconfigure(trail, text="\n".join(chars[:-1]), fill="#b4ffc8" if near else "#00d75a")
            self.cv.coords(trail, x, y - self.lh)
            self.cv.itemconfigure(head, text=chars[-1])
            self.cv.coords(head, x, y)


class Starfield(Effect):
    darken = 0.25

    def setup(self):
        self.cx, self.cy = self.W / 2, self.H / 2
        self.stars = [self._new(random.uniform(0.1, 1)) for _ in range(260)]
        self.boost = 0

    def _new(self, z=1.0):
        item = self.cv.create_line(0, 0, 0, 0, fill="white")
        return [item, random.uniform(-1, 1) * self.W, random.uniform(-1, 1) * self.H, z, None]

    def update(self, mx, my, click):
        if click:
            self.boost = 45
        self.boost = max(0, self.boost - 1)
        self.cx += (mx - self.cx) * 0.04
        self.cy += (my - self.cy) * 0.04
        speed = 0.008 + (0.03 if self.boost else 0)
        for s in self.stars:
            item, x, y, z, prev = s
            z -= speed
            if z <= 0.02:
                s[1:5] = [random.uniform(-1, 1) * self.W, random.uniform(-1, 1) * self.H, 1.0, None]
                continue
            px, py = self.cx + x / z * 0.5, self.cy + y / z * 0.5
            if prev is None:
                prev = (px, py)
            shade = int(min(255, 80 + (1 - z) * 200))
            self.cv.itemconfigure(item, fill="#%02x%02x%02x" % (shade, shade, 255), width=1 if z > 0.5 else 2)
            self.cv.coords(item, prev[0], prev[1], px, py)
            s[3], s[4] = z, (px, py)


class Fireworks(Effect):
    darken = 0.6

    def setup(self):
        self.rockets = []
        self.next = 0

    def update(self, mx, my, click):
        self.next -= 1
        if self.next <= 0:
            self.next = random.randint(20, 55)
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
                self.burst(x, y, n=70, colors=[c, "#ffffff", random_color()], speed=8)
                continue
            self.cv.coords(item, x - 2.5, y - 2.5, x + 2.5, y + 2.5)
            alive.append([item, x, y, vx, vy])
        self.rockets = alive


class Pet(Effect):
    NAMES = {"cat": "🐈", "dog": "🐕", "fox": "🦊", "unicorn": "🦄", "penguin": "🐧", "duck": "🦆",
             "dino": "🦖", "ghost": "👻", "snail": "🐌", "turtle": "🐢", "bee": "🐝", "robot": "🤖"}

    def setup(self):
        emoji = self.NAMES.get(str(self.arg or "cat").lower(), self.arg or "🐈")
        self.img_l = self._emoji(emoji, 96)
        self.img_r = ImageTk.PhotoImage(ImageOps.mirror(ImageTk.getimage(self.img_l)))
        self.zz = self._emoji("💤", 40)
        self.heart = self._emoji("💖", 32)
        self.x, self.y = self.W / 2, self.H * 0.7
        self.vy = 0.0
        self.face_left = True
        self.item = self.cv.create_image(self.x, self.y, image=self.img_l)
        self.zz_item = None
        self.hearts = []
        self.last_mouse, self.still = None, 0

    def _emoji(self, ch, size):
        from .wallpaper import EMOJI_FONT, load_font
        font = load_font(EMOJI_FONT, size)
        img = Image.new("RGBA", (int(size * 1.4), int(size * 1.4)), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((img.width / 2, img.height / 2), ch, font=font, embedded_color=True, anchor="mm")
        return ImageTk.PhotoImage(img)

    def update(self, mx, my, click):
        moved = self.last_mouse != (mx, my)
        self.last_mouse = (mx, my)
        self.still = 0 if moved else self.still + 1
        dx, dy = mx - self.x, my - self.y
        d = math.hypot(dx, dy)
        if click and math.hypot(click[0] - self.x, click[1] - self.y) < 60:
            self.vy = -14  # boop -> jump + hearts
            for _ in range(6):
                self._heart()
        if d > 70 and self.still < 120:
            sp = min(7, d * 0.05)
            self.x += dx / d * sp
            self.y += dy / d * sp
            if abs(dx) > 4:
                self.face_left = dx < 0
        elif d <= 70 and random.random() < 0.04:
            self._heart()
        self.vy += 0.9
        self.y += self.vy if self.vy < 0 else 0
        if self.vy > 0:
            self.vy = 0
        self.cv.itemconfigure(self.item, image=self.img_l if self.face_left else self.img_r)
        bob = math.sin(self.t * 12) * 3 if d > 70 and self.still < 120 else 0
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
    if STOP_FILE.exists():
        STOP_FILE.unlink()
    cls = CLASSES[effect]
    W, H = w.screen_size()
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-alpha", 0.0)  # invisible until it's tucked behind the icons
    root.geometry(f"{W}x{H}+0+0")
    root.configure(bg="black")
    cv = tk.Canvas(root, width=W, height=H, highlightthickness=0, bd=0, bg="black")
    cv.pack(fill="both", expand=True)
    bg = ImageTk.PhotoImage(current_wallpaper_image((W, H), cls.darken), master=root)
    cv.create_image(0, 0, image=bg, anchor="nw")
    root.update()

    hwnd = w.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
    mode, parent = w.attach_behind_icons(hwnd, W, H)
    w.SetLayeredWindowAttributes(hwnd, 0, 255, w.LWA_ALPHA)
    desk = w.desktop_hwnds() | {hwnd, root.winfo_id()}
    eff = cls(cv, W, H, arg)
    state = {"down": False, "tick": 0}

    def tick():
        state["tick"] += 1
        if state["tick"] % 15 == 0 and (STOP_FILE.exists() or not w.IsWindow(parent)):
            shutdown()
            return
        sx, sy = w.cursor_pos()
        rx, ry = sx, sy
        try:
            import ctypes.wintypes as wt
            import ctypes
            r = wt.RECT()
            w.GetWindowRect(hwnd, ctypes.byref(r))
            rx, ry = sx - r.left, sy - r.top
        except Exception:
            pass
        down = w.key_down(0x01)
        click = None
        if down and not state["down"]:
            import ctypes.wintypes as wt
            under = w.WindowFromPoint(wt.POINT(sx, sy))
            if under in desk or (under and w.GetAncestor(under, 2) in desk):
                click = (rx, ry)
        state["down"] = down
        try:
            eff.step(rx, ry, click)
        except tk.TclError:
            return
        root.after(33, tick)

    def shutdown():
        try:
            root.destroy()
        finally:
            if mode == "workerw":  # repaint the static wallpaper
                p = w.get_wallpaper_path()
                if p:
                    w.set_wallpaper(p, persist=False)

    root.after(50, tick)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CLASSES:
        print(f"usage: python -m wallplay.live <{'|'.join(EFFECTS)}> [arg]")
        sys.exit(2)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
