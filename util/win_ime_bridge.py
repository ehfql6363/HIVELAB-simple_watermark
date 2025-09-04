# win_ime_bridge.py
from __future__ import annotations
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
imm32  = ctypes.windll.imm32

LRESULT = wintypes.LRESULT
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# IME constants
WM_IME_STARTCOMPOSITION = 0x010D
WM_IME_COMPOSITION      = 0x010F
WM_IME_ENDCOMPOSITION   = 0x010E
WM_DESTROY              = 0x0002
GCS_COMPSTR             = 0x0008
GCS_RESULTSTR           = 0x0800

GWLP_WNDPROC = -4

_prev_proc_root: dict[int, int] = {}
_entry_callbacks: dict[int, callable] = {}   # hwnd(entry) -> cb(preedit:str, composing:bool)
_root_hwnd: int | None = None

def _get_focus_hwnd() -> int:
    h = user32.GetFocus()
    return int(h) if h else 0

def _get_preedit(hwnd: int) -> str:
    himc = imm32.ImmGetContext(hwnd)
    if not himc:
        return ""
    try:
        size = imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)
        if size <= 0:
            return ""
        count = size // 2  # WCHAR count
        buf = (wintypes.WCHAR * (count + 1))()
        imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, ctypes.byref(buf), size)
        return ctypes.wstring_at(ctypes.byref(buf))
    finally:
        imm32.ImmReleaseContext(hwnd, himc)

@WNDPROC
def _root_wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg in (WM_IME_STARTCOMPOSITION, WM_IME_COMPOSITION, WM_IME_ENDCOMPOSITION):
            focus = _get_focus_hwnd()
            cb = _entry_callbacks.get(focus)
            if cb:
                if msg == WM_IME_ENDCOMPOSITION:
                    cb(preedit="", composing=False)
                else:
                    pre = _get_preedit(focus)
                    cb(preedit=pre, composing=True)
        elif msg == WM_DESTROY:
            uninstall_root_hook(hwnd)
    except Exception:
        pass

    prev = _prev_proc_root.get(int(hwnd))
    if prev:
        return ctypes.windll.user32.CallWindowProcW(prev, hwnd, msg, wparam, lparam)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

def install_root_hook(root_hwnd: int):
    """Hook the toplevel window once."""
    global _root_hwnd
    root_hwnd = int(root_hwnd)
    if root_hwnd in _prev_proc_root:
        _root_hwnd = root_hwnd
        return
    prev = user32.SetWindowLongPtrW(root_hwnd, GWLP_WNDPROC, ctypes.cast(_root_wndproc, ctypes.c_void_p).value)
    _prev_proc_root[root_hwnd] = prev
    _root_hwnd = root_hwnd

def uninstall_root_hook(root_hwnd: int):
    root_hwnd = int(root_hwnd)
    try:
        prev = _prev_proc_root.pop(root_hwnd, None)
        if prev:
            user32.SetWindowLongPtrW(root_hwnd, GWLP_WNDPROC, prev)
    except Exception:
        pass

def register_entry(hwnd: int, on_update: callable):
    """Register a Tk Entry's HWND to receive preedit callbacks while focused."""
    _entry_callbacks[int(hwnd)] = on_update

def unregister_entry(hwnd: int):
    _entry_callbacks.pop(int(hwnd), None)
