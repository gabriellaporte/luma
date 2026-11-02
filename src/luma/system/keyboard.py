import ctypes
from ctypes import wintypes

KEYEVENTF_KEYUP = 0x0002
KEY_DOWN_MASK = 0x8000
VK_MENU = 0x12
VK_CONTROL = 0x11

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def force_foreground(window):
    """Windows only lets the foreground app take focus; a synthetic Alt press lifts that lock."""
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(int(window.winId()))


def is_ctrl_down():
    return bool(user32.GetAsyncKeyState(VK_CONTROL) & KEY_DOWN_MASK)
