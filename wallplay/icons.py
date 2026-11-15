"""Move, arrange and animate the real desktop icons (Explorer's SysListView32)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import random
import time
from dataclasses import dataclass

from . import winapi as w
from .common import STATE_DIR, WallplayError, ensure_dir, read_json, write_json

LVM_GETITEMCOUNT = 0x1004
LVM_SETITEMPOSITION = 0x100F
LVM_GETITEMPOSITION = 0x1010
LVM_GETITEMSPACING = 0x1033
LVM_SETEXTENDEDLISTVIEWSTYLE = 0x1036
LVM_GETITEMTEXTW = 0x1073
LVS_EX_SNAPTOGRID = 0x00080000
LVS_AUTOARRANGE = 0x0100
LVIF_TEXT = 0x1

LAYOUT_DIR = STATE_DIR / "layouts"
SHAPES = ["circle", "heart", "spiral", "wave", "star", "grid", "line", "diagonal", "square", "triangle",
          "infinity", "smile", "scatter"]
ANIMATIONS = ["dance", "orbit", "gravity", "follow", "flee", "magnet", "rain"]


class LVITEMW(ctypes.Structure):
    _fields_ = [("mask", wt.UINT), ("iItem", ctypes.c_int), ("iSubItem", ctypes.c_int), ("state", wt.UINT),
                ("stateMask", wt.UINT), ("pszText", ctypes.c_void_p), ("cchTextMax", ctypes.c_int),
                ("iImage", ctypes.c_int), ("lParam", wt.LPARAM), ("iIndent", ctypes.c_int),
                ("iGroupId", ctypes.c_int), ("cColumns", wt.UINT), ("puColumns", ctypes.c_void_p),
                ("piColFmt", ctypes.c_void_p), ("iGroup", ctypes.c_int)]


@dataclass
class Icon:
    index: int
    name: str
    x: int
    y: int


class Desktop:
    def __init__(self):
        self.defview, self.lv = w.find_desktop_listview()
        if not self.lv:
            raise WallplayError("Couldn't find the desktop icon view. Is Explorer running and are icons enabled?")

    # ---------------------------------------------------------------- basics
    def count(self) -> int:
        return w.SendMessageW(self.lv, LVM_GETITEMCOUNT, 0, 0)

    def icons(self) -> list[Icon]:
        n = self.count()
        pid = wt.DWORD()
        w.GetWindowThreadProcessId(self.lv, ctypes.byref(pid))
        h = w.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid.value)
        if not h:
            raise WallplayError("Not allowed to talk to Explorer (try running the terminal as your normal user).")
        remote = w.VirtualAllocEx(h, None, 4096, 0x3000, 0x04)
        try:
            out = []
            text_addr = remote + 1024
            for i in range(n):
                w.SendMessageW(self.lv, LVM_GETITEMPOSITION, i, remote)
                pt = wt.POINT()
                w.ReadProcessMemory(h, remote, ctypes.byref(pt), ctypes.sizeof(pt), None)
                item = LVITEMW(mask=LVIF_TEXT, iItem=i, iSubItem=0, pszText=text_addr, cchTextMax=512)
                w.WriteProcessMemory(h, remote + 128, ctypes.byref(item), ctypes.sizeof(item), None)
                w.SendMessageW(self.lv, LVM_GETITEMTEXTW, i, remote + 128)
                buf = ctypes.create_unicode_buffer(512)
                w.ReadProcessMemory(h, text_addr, buf, ctypes.sizeof(buf), None)
                out.append(Icon(i, buf.value, pt.x, pt.y))
            return out
        finally:
            w.VirtualFreeEx(h, remote, 0, 0x8000)
            w.CloseHandle(h)

    def set_pos(self, index: int, x: float, y: float) -> None:
        xi, yi = max(0, min(32767, int(x))), max(0, min(32767, int(y)))
        w.SendMessageW(self.lv, LVM_SETITEMPOSITION, index, (yi << 16) | xi)

    def free_layout(self) -> None:
        """Turn off auto-arrange and snap-to-grid so icons can sit anywhere."""
        style = w.GetWindowLongPtrW(self.lv, w.GWL_STYLE)
        if style & LVS_AUTOARRANGE:
            w.SetWindowLongPtrW(self.lv, w.GWL_STYLE, style & ~LVS_AUTOARRANGE)
        w.SendMessageW(self.lv, LVM_SETEXTENDEDLISTVIEWSTYLE, LVS_EX_SNAPTOGRID, 0)

    def spacing(self) -> tuple[int, int]:
        r = w.SendMessageW(self.lv, LVM_GETITEMSPACING, 0, 0)
        cx, cy = r & 0xFFFF, (r >> 16) & 0xFFFF
        return (cx or 75), (cy or 100)

    def area(self) -> tuple[int, int, int, int]:
        """Primary monitor work area in listview coordinates."""
        l, t, r, b = w.work_area()
        x0, y0 = w.to_client(self.lv, l, t)
        return x0, y0, x0 + (r - l), y0 + (b - t)

    def cursor(self) -> tuple[int, int]:
        return w.to_client(self.lv, *w.cursor_pos())

    def visible(self) -> bool:
        return bool(w.IsWindowVisible(self.lv))

    def show(self, on: bool) -> None:
        w.ShowWindow(self.lv, 5 if on else 0)

    def refresh(self) -> None:
        w.InvalidateRect(self.lv, None, True)
        w.UpdateWindow(self.lv)

    # ---------------------------------------------------------------- centre <-> item coords
    def center_of(self, ic: Icon):
        sx, sy = self.spacing()
        return ic.x + sx / 2, ic.y + sy / 2.6

    def put_center(self, index, cx, cy):
        sx, sy = self.spacing()
        self.set_pos(index, cx - sx / 2, cy - sy / 2.6)

    # ---------------------------------------------------------------- layouts
    def save_layout(self, name: str) -> int:
        ensure_dir()
        LAYOUT_DIR.mkdir(exist_ok=True)
        data = [{"name": i.name, "x": i.x, "y": i.y} for i in self.icons()]
        write_json(LAYOUT_DIR / f"{name}.json", data)
        return len(data)

    def load_layout(self, name: str, animate: bool = True) -> int:
        data = read_json(LAYOUT_DIR / f"{name}.json", None)
        if data is None:
            raise WallplayError(f"No saved layout '{name}'. See `icons layouts`.")
        pool: dict[str, list] = {}
        for e in data:
            pool.setdefault(e["name"], []).append((e["x"], e["y"]))
        icons = self.icons()
        targets = {}
        for ic in icons:
            if pool.get(ic.name):
                targets[ic.index] = pool[ic.name].pop(0)
        self.free_layout()
        self.tween(icons, targets, centers=False, secs=0.6 if animate else 0)
        return len(targets)

    def ensure_backups(self) -> None:
        if not (LAYOUT_DIR / "original.json").exists():
            self.save_layout("original")
        self.save_layout("_undo")

    # ---------------------------------------------------------------- motion
    def tween(self, icons, targets: dict, centers=True, secs=0.7):
        """Smoothly move icons to targets {index: (x, y)}."""
        sx, sy = self.spacing()
        start = {ic.index: (ic.x, ic.y) for ic in icons}
        goal = {}
        for idx, (x, y) in targets.items():
            goal[idx] = (x - sx / 2, y - sy / 2.6) if centers else (x, y)
        frames = max(1, int(secs * 60))
        for f in range(1, frames + 1):
            t = f / frames
            e = 1 - (1 - t) ** 3  # ease-out cubic
            for idx, (gx, gy) in goal.items():
                x0, y0 = start.get(idx, (gx, gy))
                self.set_pos(idx, x0 + (gx - x0) * e, y0 + (gy - y0) * e)
            if frames > 1:
                time.sleep(1 / 60)
        self.refresh()

    def arrange(self, shape: str, secs=0.8) -> int:
        icons = self.icons()
        if not icons:
            raise WallplayError("Your desktop has no icons to play with.")
        self.ensure_backups()
        self.free_layout()
        pts = shape_points(shape, len(icons), self.area(), self.spacing())
        self.tween(icons, {ic.index: p for ic, p in zip(icons, pts)}, secs=secs)
        return len(icons)

    def shuffle(self) -> None:
        icons = self.icons()
        self.ensure_backups()
        self.free_layout()
        spots = [self.center_of(i) for i in icons]
        random.shuffle(spots)
        self.tween(icons, {ic.index: p for ic, p in zip(icons, spots)})

    def move(self, query: str, at: str) -> str:
        from .wallpaper import resolve_pos
        icons = self.icons()
        ic = find_icon(icons, query)
        self.ensure_backups()
        self.free_layout()
        l, t, r, b = self.area()
        x, y, _, _ = resolve_pos(at, r - l, b - t)
        self.tween(icons, {ic.index: (l + x, t + y)})
        return ic.name

    def animate(self, kind: str, seconds: float | None = None) -> None:
        icons = self.icons()
        if not icons:
            raise WallplayError("Your desktop has no icons to play with.")
        self.ensure_backups()
        self.free_layout()
        anim = Animation(self, icons, kind)
        try:
            _loop(anim.step, seconds)
        finally:
            # glide everyone back home
            cur = [Icon(ic.index, ic.name, int(p[0] - anim.sx / 2), int(p[1] - anim.sy / 2.6))
                   for ic, p in zip(icons, anim.pos)]
            self.tween(cur, {ic.index: h for ic, h in zip(icons, anim.home)}, secs=0.6)


def find_icon(icons, query):
    q = str(query).lower()
    if q.isdigit() and 0 <= int(q) - 1 < len(icons):
        return icons[int(q) - 1]
    exact = [i for i in icons if i.name.lower() == q]
    part = [i for i in icons if q in i.name.lower()]
    if exact or part:
        return (exact or part)[0]
    raise WallplayError(f"No desktop icon matching '{query}'. Try `icons list`.")


def _loop(step, seconds=None, fps=50):
    t0 = time.perf_counter()
    frame = 1 / fps
    try:
        while seconds is None or time.perf_counter() - t0 < seconds:
            ts = time.perf_counter()
            step(ts - t0)
            rest = frame - (time.perf_counter() - ts)
            if rest > 0:
                time.sleep(rest)
    except KeyboardInterrupt:
        pass


class Animation:
    def __init__(self, desk: Desktop, icons, kind):
        if kind not in ANIMATIONS:
            raise WallplayError(f"Unknown animation '{kind}'. Try: {', '.join(ANIMATIONS)}")
        self.d, self.icons, self.kind = desk, icons, kind
        self.sx, self.sy = desk.spacing()
        self.home = [desk.center_of(i) for i in icons]
        self.pos = [list(p) for p in self.home]
        self.vel = [[0.0, 0.0] for _ in icons]
        self.area = desk.area()
        self.last = [None] * len(icons)
        if kind == "gravity":
            self.vel = [[random.uniform(-6, 6), random.uniform(-14, -4)] for _ in icons]
        if kind == "rain":
            l, t, r, b = self.area
            self.pos = [[p[0], t - random.uniform(50, (b - t))] for p in self.home]

    def _put(self, i):
        x, y = self.pos[i]
        key = (int(x), int(y))
        if key != self.last[i]:
            self.last[i] = key
            self.d.put_center(self.icons[i].index, x, y)

    def _lerp_to(self, i, tx, ty, k=0.15):
        p = self.pos[i]
        p[0] += (tx - p[0]) * k
        p[1] += (ty - p[1]) * k

    def step(self, t):
        n = len(self.icons)
        l, top, r, b = self.area
        cx, cy = (l + r) / 2, (top + b) / 2
        mx, my = self.d.cursor()
        k = self.kind
        for i in range(n):
            p, v = self.pos[i], self.vel[i]
            hx, hy = self.home[i]
            if k == "dance":
                self._lerp_to(i, hx + math.sin(t * 3 + i * 0.7) * 18, hy + math.sin(t * 6 + i * 0.5) * 32, 0.3)
            elif k == "orbit":
                R = min(r - l, b - top) * 0.36 * (0.85 + 0.15 * math.sin(t * 1.7))
                a = t * 0.9 + 2 * math.pi * i / n
                self._lerp_to(i, cx + R * math.cos(a), cy + R * math.sin(a), 0.12)
            elif k == "magnet":
                R = 40 + 9 * n
                a = t * 1.5 + 2 * math.pi * i / n
                self._lerp_to(i, mx + R * math.cos(a), my + R * math.sin(a), 0.1)
            elif k == "follow":
                if i == 0:
                    self._lerp_to(i, mx + 50, my + 50, 0.22)
                else:
                    px, py = self.pos[i - 1]
                    dx, dy = p[0] - px, p[1] - py
                    dist = math.hypot(dx, dy) or 1
                    gap = self.sx * 0.85
                    self._lerp_to(i, px + dx / dist * gap, py + dy / dist * gap, 0.35)
            elif k == "flee":
                dx, dy = p[0] - mx, p[1] - my
                dist = math.hypot(dx, dy) or 1
                R = 200
                if dist < R:
                    push = (R - dist) / R * 9
                    v[0] += dx / dist * push
                    v[1] += dy / dist * push
                v[0] += (hx - p[0]) * 0.03
                v[1] += (hy - p[1]) * 0.03
                v[0] *= 0.82
                v[1] *= 0.82
                p[0] += v[0]
                p[1] += v[1]
            elif k in ("gravity", "rain"):
                floor = b - self.sy * 0.75
                v[1] += 0.9 if k == "gravity" else 0.5
                dx, dy = p[0] - mx, p[1] - my
                dist = math.hypot(dx, dy) or 1
                if dist < 110:  # mouse kicks icons
                    v[0] += dx / dist * 6
                    v[1] += dy / dist * 6 - 4
                p[0] += v[0]
                p[1] += v[1]
                if p[1] > floor:
                    p[1] = floor
                    v[1] *= -0.55
                    v[0] *= 0.85
                    if k == "rain" and abs(v[1]) < 2:
                        p[1] = top - random.uniform(50, 400)
                        p[0] = random.uniform(l + 40, r - 40)
                        v[0], v[1] = 0.0, random.uniform(0, 3)
                if p[0] < l + self.sx / 2 or p[0] > r - self.sx / 2:
                    v[0] *= -0.8
                    p[0] = max(l + self.sx / 2, min(r - self.sx / 2, p[0]))
            self._put(i)


# ==================================================================== shapes
def _along(poly, n, closed=True):
    pts = list(poly) + ([poly[0]] if closed else [])
    segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(segs) or 1
    step = total / (n if closed else max(1, n - 1))
    out, seg, acc = [], 0, 0.0
    for kk in range(n):
        d = kk * step
        while seg < len(segs) - 1 and acc + segs[seg] < d:
            acc += segs[seg]
            seg += 1
        f = (d - acc) / (segs[seg] or 1)
        (x0, y0), (x1, y1) = pts[seg], pts[seg + 1]
        out.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    return out


def shape_points(kind, n, rect, spacing=(75, 100)):
    l, t, r, b = rect
    W, H = r - l, b - t
    cx, cy = l + W / 2, t + H / 2
    R = min(W, H) * 0.38
    sx, sy = spacing
    rng = range(n)
    den = max(1, n - 1)
    if kind == "circle":
        return [(cx + R * math.cos(2 * math.pi * i / n - math.pi / 2),
                 cy + R * math.sin(2 * math.pi * i / n - math.pi / 2)) for i in rng]
    if kind == "spiral":
        out = []
        for i in rng:
            f = i / den
            a = f * 4.2 * math.pi
            rr = R * (0.08 + 0.92 * f)
            out.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        return out
    if kind == "wave":
        return [(l + W * 0.08 + W * 0.84 * i / den, cy + math.sin(i / den * 3 * math.pi) * H * 0.28) for i in rng]
    if kind == "line":
        return [(l + W * 0.06 + W * 0.88 * i / den, cy) for i in rng]
    if kind == "diagonal":
        return [(l + W * 0.1 + W * 0.8 * i / den, t + H * 0.1 + H * 0.8 * i / den) for i in rng]
    if kind == "grid":
        cols = max(1, math.ceil(math.sqrt(n * W / max(1, H))))
        rows = math.ceil(n / cols)
        gx = min(sx * 1.6, W * 0.9 / cols)
        gy = min(sy * 1.3, H * 0.9 / max(1, rows))
        x0 = cx - gx * (cols - 1) / 2
        y0 = cy - gy * (rows - 1) / 2
        return [(x0 + gx * (i % cols), y0 + gy * (i // cols)) for i in rng]
    if kind == "scatter":
        return [(random.uniform(l + sx, r - sx), random.uniform(t + sy, b - sy)) for _ in rng]
    if kind == "heart":
        poly = []
        for i in range(200):
            a = 2 * math.pi * i / 200
            x = 16 * math.sin(a) ** 3
            y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
            poly.append((cx + x * R / 16, cy + y * R / 16 + R * 0.1))
        return _along(poly, n)
    if kind == "star":
        poly = [(cx + (R if j % 2 == 0 else R * 0.42) * math.cos(-math.pi / 2 + j * math.pi / 5),
                 cy + (R if j % 2 == 0 else R * 0.42) * math.sin(-math.pi / 2 + j * math.pi / 5)) for j in range(10)]
        return _along(poly, n)
    if kind == "square":
        return _along([(cx - R, cy - R), (cx + R, cy - R), (cx + R, cy + R), (cx - R, cy + R)], n)
    if kind == "triangle":
        return _along([(cx + R * math.cos(a), cy + R * math.sin(a) + R * 0.15)
                       for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)], n)
    if kind == "infinity":
        poly = []
        for i in range(200):
            a = 2 * math.pi * i / 200
            d = 1 + math.sin(a) ** 2
            poly.append((cx + R * 1.5 * math.cos(a) / d, cy + R * 1.5 * math.sin(a) * math.cos(a) / d))
        return _along(poly, n)
    if kind == "smile":
        if n < 6:
            return shape_points("circle", n, rect, spacing)
        eyes = [(cx - R * 0.35, cy - R * 0.3), (cx + R * 0.35, cy - R * 0.3)]
        rest = n - 2
        mouth_n = max(3, rest // 3)
        face_n = rest - mouth_n
        mouth = [(cx + R * 0.55 * math.cos(a), cy + R * 0.1 + R * 0.45 * math.sin(a))
                 for a in [math.pi * (0.15 + 0.7 * j / max(1, mouth_n - 1)) for j in range(mouth_n)]]
        face = [(cx + R * 1.05 * math.cos(2 * math.pi * j / max(1, face_n)),
                 cy + R * 1.05 * math.sin(2 * math.pi * j / max(1, face_n))) for j in range(face_n)]
        return eyes + mouth + face
    raise WallplayError(f"Unknown shape '{kind}'. Try: {', '.join(SHAPES)}")
