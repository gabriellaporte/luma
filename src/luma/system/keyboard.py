import ctypes
from ctypes import wintypes

KEYEVENTF_KEYUP = 0x0002
KEY_DOWN_MASK = 0x8000
VK_MENU = 0x12
VK_CONTROL = 0x11
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def force_foreground(window):
    """Put the window on top and give it keyboard focus even when a game owns the foreground.

    Windows only lets the foreground app take focus, so a synthetic Alt press and a brief input
    attachment to the foreground thread lift that lock.
    """
    handle = int(window.winId())
    foreground_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    own_thread = kernel32.GetCurrentThreadId()
    attached = bool(foreground_thread) and foreground_thread != own_thread
    if attached:
        user32.AttachThreadInput(own_thread, foreground_thread, True)
    try:
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetWindowPos(handle, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetForegroundWindow(handle)
        user32.BringWindowToTop(handle)
    finally:
        if attached:
            user32.AttachThreadInput(own_thread, foreground_thread, False)


def is_foreground(window):
    return user32.GetForegroundWindow() == int(window.winId())


def is_ctrl_down():
    return bool(user32.GetAsyncKeyState(VK_CONTROL) & KEY_DOWN_MASK)
