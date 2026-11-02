import ctypes
import logging
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence

from preferences import preferences

log = logging.getLogger("luma")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_USER = 0x0400
WM_RELOAD = WM_USER + 1
WM_SUSPEND = WM_USER + 2
PM_NOREMOVE = 0
VK_F1 = 0x70
QT_F1_TO_F24 = range(Qt.Key_F1.value, Qt.Key_F24.value + 1)
SPECIAL_KEYS = {
    Qt.Key_Print: 0x2C,
    Qt.Key_Pause: 0x13,
    Qt.Key_ScrollLock: 0x91,
    Qt.Key_Insert: 0x2D,
    Qt.Key_Delete: 0x2E,
    Qt.Key_Home: 0x24,
    Qt.Key_End: 0x23,
    Qt.Key_PageUp: 0x21,
    Qt.Key_PageDown: 0x22,
    Qt.Key_Space: 0x20,
}
MODIFIER_FLAGS = [
    (Qt.ControlModifier, MOD_CONTROL),
    (Qt.AltModifier, MOD_ALT),
    (Qt.ShiftModifier, MOD_SHIFT),
    (Qt.MetaModifier, MOD_WIN),
]


def to_windows_hotkey(text):
    """(modifiers, virtual key) for a shortcut such as "Ctrl+Alt+A"; ValueError if unsupported."""
    sequence = QKeySequence.fromString(text)
    if sequence.count() != 1:
        raise ValueError(f"Not a single shortcut: {text!r}")
    combination = sequence[0]
    key = combination.key()
    modifiers = sum(flag for qt_flag, flag in MODIFIER_FLAGS if combination.keyboardModifiers() & qt_flag)
    if key in SPECIAL_KEYS:
        return modifiers, SPECIAL_KEYS[key]
    if key.value in QT_F1_TO_F24:
        return modifiers, VK_F1 + key.value - Qt.Key_F1.value
    if Qt.Key_A.value <= key.value <= Qt.Key_Z.value or Qt.Key_0.value <= key.value <= Qt.Key_9.value:
        return modifiers, key.value
    raise ValueError(f"Unsupported key: {text!r}")


class HotkeyListener(QObject):
    """Owns a thread with a message loop, because Windows ties hotkeys to the thread that set them."""

    pressed = Signal()
    unavailable = Signal(str)

    def __init__(self):
        super().__init__()
        self.thread_id = None
        self.ready = threading.Event()
        self.registered_ids = []

    def start(self):
        threading.Thread(target=self.listen, daemon=True).start()
        self.ready.wait()

    def reload(self):
        self.post(WM_RELOAD)

    def suspend(self):
        self.post(WM_SUSPEND)

    def post(self, message):
        user32.PostThreadMessageW(self.thread_id, message, 0, 0)

    def listen(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, WM_USER, WM_USER, PM_NOREMOVE)
        self.ready.set()
        self.register()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                self.pressed.emit()
            elif message.message == WM_RELOAD:
                self.unregister()
                self.register()
            elif message.message == WM_SUSPEND:
                self.unregister()

    def register(self):
        for hotkey_id, text in enumerate([preferences.capture_shortcut, preferences.secondary_shortcut], 1):
            if not text:
                continue
            modifiers, key = to_windows_hotkey(text)
            if user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, key):
                self.registered_ids.append(hotkey_id)
                log.info("hotkey registered: %s", text)
            else:
                log.error("hotkey unavailable (in use by another app?): %s", text)
                self.unavailable.emit(text)

    def unregister(self):
        for hotkey_id in self.registered_ids:
            user32.UnregisterHotKey(None, hotkey_id)
        self.registered_ids = []
