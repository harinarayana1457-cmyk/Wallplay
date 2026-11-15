"""Thin ctypes layer over the Win32 APIs wallplay needs."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
from pathlib import Path

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("wallplay only works on Windows.")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HWND = wt.HWND
LRESULT = ctypes.c_ssize_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _proto(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


FindWindowW = _proto(user32, "FindWindowW", HWND, wt.LPCWSTR, wt.LPCWSTR)
FindWindowExW = _proto(user32, "FindWindowExW", HWND, HWND, HWND, wt.LPCWSTR, wt.LPCWSTR)
SendMessageW = _proto(user32, "SendMessageW", LRESULT, HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
SendMessageTimeoutW = _proto(user32, "SendMessageTimeoutW", LRESULT, HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                             wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t))
EnumWindows = _proto(user32, "EnumWindows", wt.BOOL, WNDENUMPROC, wt.LPARAM)
EnumChildWindows = _proto(user32, "EnumChildWindows", wt.BOOL, HWND, WNDENUMPROC, wt.LPARAM)
GetWindowThreadProcessId = _proto(user32, "GetWindowThreadProcessId", wt.DWORD, HWND, ctypes.POINTER(wt.DWORD))
SetParent = _proto(user32, "SetParent", HWND, HWND, HWND)
GetParent = _proto(user32, "GetParent", HWND, HWND)
GetAncestor = _proto(user32, "GetAncestor", HWND, HWND, wt.UINT)
SetWindowPos = _proto(user32, "SetWindowPos", wt.BOOL, HWND, HWND, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, wt.UINT)
GetWindowLongPtrW = _proto(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, HWND, ctypes.c_int)
SetWindowLongPtrW = _proto(user32, "SetWindowLongPtrW", ctypes.c_ssize_t, HWND, ctypes.c_int, ctypes.c_ssize_t)
ShowWindow = _proto(user32, "ShowWindow", wt.BOOL, HWND, ctypes.c_int)
IsWindowVisible = _proto(user32, "IsWindowVisible", wt.BOOL, HWND)
IsWindow = _proto(user32, "IsWindow", wt.BOOL, HWND)
InvalidateRect = _proto(user32, "InvalidateRect", wt.BOOL, HWND, ctypes.c_void_p, wt.BOOL)
UpdateWindow = _proto(user32, "UpdateWindow", wt.BOOL, HWND)
GetClientRect = _proto(user32, "GetClientRect", wt.BOOL, HWND, ctypes.POINTER(wt.RECT))
GetWindowRect = _proto(user32, "GetWindowRect", wt.BOOL, HWND, ctypes.POINTER(wt.RECT))
ScreenToClient = _proto(user32, "ScreenToClient", wt.BOOL, HWND, ctypes.POINTER(wt.POINT))
GetCursorPos = _proto(user32, "GetCursorPos", wt.BOOL, ctypes.POINTER(wt.POINT))
WindowFromPoint = _proto(user32, "WindowFromPoint", HWND, wt.POINT)
GetAsyncKeyState = _proto(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
GetSystemMetrics = _proto(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
SystemParametersInfoW = _proto(user32, "SystemParametersInfoW", wt.BOOL, wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT)
SetLayeredWindowAttributes = _proto(user32, "SetLayeredWindowAttributes", wt.BOOL, HWND, wt.DWORD, wt.BYTE, wt.DWORD)
GetClassNameW = _proto(user32, "GetClassNameW", ctypes.c_int, HWND, wt.LPWSTR, ctypes.c_int)

OpenProcess = _proto(kernel32, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
CloseHandle = _proto(kernel32, "CloseHandle", wt.BOOL, wt.HANDLE)
VirtualAllocEx = _proto(kernel32, "VirtualAllocEx", ctypes.c_void_p, wt.HANDLE, ctypes.c_void_p,
                        ctypes.c_size_t, wt.DWORD, wt.DWORD)
VirtualFreeEx = _proto(kernel32, "VirtualFreeEx", wt.BOOL, wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD)
ReadProcessMemory = _proto(kernel32, "ReadProcessMemory", wt.BOOL, wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
WriteProcessMemory = _proto(kernel32, "WriteProcessMemory", wt.BOOL, wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
QueryFullProcessImageNameW = _proto(kernel32, "QueryFullProcessImageNameW", wt.BOOL, wt.HANDLE, wt.DWORD,
                                    wt.LPWSTR, ctypes.POINTER(wt.DWORD))
GetTickCount64 = _proto(kernel32, "GetTickCount64", ctypes.c_ulonglong)

# constants
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CHILD, WS_VISIBLE, WS_POPUP = 0x40000000, 0x10000000, 0x80000000
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x00080000, 0x00000020
WS_EX_APPWINDOW, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00040000, 0x00000080, 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x40, 0x20
LWA_COLORKEY, LWA_ALPHA = 0x1, 0x2
SPI_GETDESKWALLPAPER, SPI_SETDESKWALLPAPER, SPI_GETWORKAREA = 0x0073, 0x0014, 0x0030
SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 0x1, 0x2


def set_dpi_aware() -> None:
    """Make coordinates physical pixels so icon/screen maths line up."""
    try:
        ctypes.WinDLL("user32").SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
        return
    except Exception:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


set_dpi_aware()


# ---------------------------------------------------------------- screen / cursor
def screen_size() -> tuple[int, int]:
    return GetSystemMetrics(0), GetSystemMetrics(1)


def work_area() -> tuple[int, int, int, int]:
    r = wt.RECT()
    if SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
        return r.left, r.top, r.right, r.bottom
    w, h = screen_size()
    return 0, 0, w, h


def cursor_pos() -> tuple[int, int]:
    p = wt.POINT()
    GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def to_client(hwnd, x: int, y: int) -> tuple[int, int]:
    p = wt.POINT(x, y)
    ScreenToClient(hwnd, ctypes.byref(p))
    return p.x, p.y


def class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def key_down(vk: int) -> bool:
    return bool(GetAsyncKeyState(vk) & 0x8000)


# ---------------------------------------------------------------- desktop windows
def _enum_toplevel():
    found = []

    @WNDENUMPROC
    def cb(hwnd, _lp):
        found.append(hwnd)
        return True

    EnumWindows(cb, 0)
    return found


def find_desktop_listview():
    """Return (defview, listview) hwnds of the desktop icon view."""
    progman = FindWindowW("Progman", None)
    defview = FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else None
    if not defview:
        for hwnd in _enum_toplevel():
            dv = FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if dv:
                defview = dv
                break
    if not defview and progman:
        found = []

        @WNDENUMPROC
        def _cb(h, _lp):
            if class_name(h) == "SHELLDLL_DefView":
                found.append(h)
                return False
            return True

        EnumChildWindows(progman, _cb, 0)
        defview = found[0] if found else None
    listview = FindWindowExW(defview, None, "SysListView32", None) if defview else None
    return defview, listview


def desktop_hwnds() -> set:
    """All windows that count as 'the desktop' for click detection."""
    progman = FindWindowW("Progman", None)
    defview, lv = find_desktop_listview()
    hs = {h for h in (progman, defview, lv) if h}
    for hwnd in _enum_toplevel():
        if class_name(hwnd) == "WorkerW":
            hs.add(hwnd)
    if progman:
        w = FindWindowExW(progman, None, "WorkerW", None)
        if w:
            hs.add(w)
    return hs


def _make_child(hwnd) -> None:
    style = GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU)
    style |= WS_CHILD | WS_VISIBLE
    SetWindowLongPtrW(hwnd, GWL_STYLE, style)
    ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
    ex &= ~WS_EX_APPWINDOW
    ex |= WS_EX_LAYERED
    SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)


def make_clickthrough_overlay(hwnd, width: int, height: int, color_key: int = 0x00010101) -> None:
    """Make a borderless window 100% click-through, transparent on color_key, and hidden from Alt+Tab."""
    ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex &= ~WS_EX_APPWINDOW
    ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    SetLayeredWindowAttributes(hwnd, color_key, 255, LWA_COLORKEY)
    HWND_TOPMOST = HWND(-1)
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED)


def attach_behind_icons(hwnd, width: int, height: int) -> tuple[str, int]:
    """Re-parent a top-level window so it renders between the wallpaper and the icons.

    Returns (mode, parent_hwnd). Handles both the classic WorkerW layout and the
    Windows 11 24H2+ "raised desktop" layout where DefView lives inside Progman.
    """
    progman = FindWindowW("Progman", None)
    if not progman:
        raise RuntimeError("Progman window not found (is Explorer running?)")
    res = ctypes.c_size_t()
    # Ask Explorer to spawn the WorkerW that sits behind the icons.
    SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(res))
    SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(res))

    defview = FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    if defview:  # Windows 11 24H2+
        workerw = FindWindowExW(progman, None, "WorkerW", None)
        _make_child(hwnd)
        SetParent(hwnd, progman)
        x, y = to_client(progman, 0, 0)
        SetWindowPos(hwnd, defview, x, y, width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED)
        if workerw:
            SetWindowPos(workerw, hwnd, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        return "raised", progman

    workerw = None
    for top in _enum_toplevel():
        if FindWindowExW(top, None, "SHELLDLL_DefView", None):
            workerw = FindWindowExW(None, top, "WorkerW", None)
            break
    if not workerw:
        raise RuntimeError("Couldn't find the WorkerW window behind the desktop icons.")
    _make_child(hwnd)
    SetParent(hwnd, workerw)
    x, y = to_client(workerw, 0, 0)
    SetWindowPos(hwnd, None, x, y, width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED)
    return "workerw", workerw


# ---------------------------------------------------------------- wallpaper + settings
def get_wallpaper_path() -> str:
    buf = ctypes.create_unicode_buffer(1024)
    SystemParametersInfoW(SPI_GETDESKWALLPAPER, 1024, buf, 0)
    return buf.value


def transcoded_wallpaper() -> Path | None:
    p = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
    return p if p.exists() else None


def set_wallpaper(path: str, persist: bool = True) -> None:
    flags = (SPIF_UPDATEINIFILE | SPIF_SENDCHANGE) if persist else 0
    if not SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, ctypes.c_wchar_p(str(path)), flags):
        raise OSError(f"Windows refused to set the wallpaper (error {ctypes.get_last_error()})")


def broadcast_setting_change(area: str = "ImmersiveColorSet") -> None:
    buf = ctypes.create_unicode_buffer(area)
    res = ctypes.c_size_t()
    SendMessageTimeoutW(HWND(0xFFFF), 0x001A, 0, ctypes.addressof(buf), 0x0002, 300, ctypes.byref(res))


def process_image(pid: int) -> str:
    h = OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        CloseHandle(h)


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", wt.BYTE), ("BatteryFlag", wt.BYTE), ("BatteryLifePercent", wt.BYTE),
                ("SystemStatusFlag", wt.BYTE), ("BatteryLifeTime", wt.DWORD), ("BatteryFullLifeTime", wt.DWORD)]


def battery() -> tuple[int, bool] | None:
    s = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(s)) or s.BatteryLifePercent == 255 or s.BatteryFlag == 128:
        return None
    return s.BatteryLifePercent, s.ACLineStatus == 1


def uptime_seconds() -> int:
    return GetTickCount64() // 1000
