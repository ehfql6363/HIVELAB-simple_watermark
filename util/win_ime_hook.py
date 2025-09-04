# win_ime_hook.py
# Windows IME composition hook for Tkinter widgets (Entry, etc.)
from __future__ import annotations
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
imm32  = ctypes.windll.imm32

# Win32 types
LRESULT = wintypes.LPARAM
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# Constants
GCS_COMPSTR    = 0x0008   # composition (preedit) string
GCS_RESULTSTR  = 0x0800   # committed string
WM_IME_STARTCOMPOSITION = 0x010D
WM_IME_COMPOSITION      = 0x010F
WM_IME_ENDCOMPOSITION   = 0x010E
WM_DESTROY              = 0x0002

GWLP_WNDPROC = -4

# storages
_prev_procs: dict[int, int] = {}
_callbacks:  dict[int, callable] = {}

def _get_preedit(hwnd: int) -> str:
    himc = imm32.ImmGetContext(hwnd)
    if not himc:
        return ""
    try:
        # get comp length (in bytes)
        size = imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)
        if size <= 0:
            return ""
        # size is bytes; allocate wchar buffer of len = size/2
        wchar_count = size // 2
        buf = (wintypes.WCHAR * (wchar_count + 1))()
        imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, ctypes.byref(buf), size)
        return ctypes.wstring_at(ctypes.byref(buf))
    finally:
        imm32.ImmReleaseContext(hwnd, himc)

@WNDPROC
def _wndproc(hwnd, msg, wparam, lparam):
    cb = _callbacks.get(int(hwnd))
    try:
        if msg == WM_IME_STARTCOMPOSITION:
            if cb:
                cb(preedit="", composing=True)
        elif msg == WM_IME_COMPOSITION:
            if cb:
                pre = _get_preedit(int(hwnd))
                cb(preedit=pre, composing=True)
        elif msg == WM_IME_ENDCOMPOSITION:
            if cb:
                cb(preedit="", composing=False)
        elif msg == WM_DESTROY:
            # auto-uninstall on destroy
            uninstall_ime_hook(hwnd)
    except Exception:
        pass

    # call original proc
    orig = _prev_procs.get(int(hwnd))
    if orig:
        return ctypes.windll.user32.CallWindowProcW(orig, hwnd, msg, wparam, lparam)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

def install_ime_hook(hwnd: int, on_update: callable):
    """
    hwnd: widget.winfo_id()
    on_update(preedit: str, composing: bool): callback
    """
    if not hwnd or hwnd in _prev_procs:
        _callbacks[int(hwnd)] = on_update
        return

    prev = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(_wndproc, ctypes.c_void_p).value)
    _prev_procs[int(hwnd)] = prev
    _callbacks[int(hwnd)] = on_update

def uninstall_ime_hook(hwnd: int):
    hwnd = int(hwnd)
    try:
        prev = _prev_procs.pop(hwnd, None)
        _callbacks.pop(hwnd, None)
        if prev:
            user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, prev)
    except Exception:
        pass
