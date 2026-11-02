import argparse
import ctypes
import logging
import os
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import autostart
from display import DesktopCapturer, enable_per_monitor_dpi
from overlay import CaptureSession
from toast import Toast
from identity import APP_NAME, __version__

BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_PATH = BUNDLE_DIR / "assets" / "icon.ico"
LOG_PATH = Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "app.log"
SAVE_DIR = Path.home() / "Pictures" / APP_NAME
ERROR_ALREADY_EXISTS = 183
TRIM_DELAY_MS = 1500
SWATCH_SIZE = (150, 96)

VK_SNAPSHOT = 0x2C
VK_A = 0x41
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEYS = {
    1: ("Print Screen", 0, VK_SNAPSHOT),
    2: ("Ctrl+Alt+A", MOD_CONTROL | MOD_ALT, VK_A),
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
psapi = ctypes.WinDLL("psapi", use_last_error=True)
psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
log = logging.getLogger("luma")


class HotkeyListener(QObject):
    pressed = Signal()

    def start(self):
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        registered = 0
        for hotkey_id, (name, modifiers, key) in HOTKEYS.items():
            if user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, key):
                registered += 1
                log.info("hotkey registered: %s", name)
            else:
                log.error("hotkey unavailable (in use by another app?): %s", name)
        if not registered:
            return
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                self.pressed.emit()


def trim_memory():
    """Hand idle pages back to Windows so the tray app stays tiny between captures."""
    if not psapi.EmptyWorkingSet(kernel32.GetCurrentProcess()):
        raise OSError(f"EmptyWorkingSet failed: {ctypes.get_last_error()}")


def save_image(image):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    path = SAVE_DIR / f"luma-{datetime.now():%Y%m%d-%H%M%S}.png"
    if not image.save(str(path)):
        raise OSError(f"Could not save {path}")
    return path


def compose_desktop(shots):
    left = min(s.monitor.rect.left() for s in shots)
    top = min(s.monitor.rect.top() for s in shots)
    right = max(s.monitor.rect.right() + 1 for s in shots)
    bottom = max(s.monitor.rect.bottom() + 1 for s in shots)
    desktop = QImage(right - left, bottom - top, QImage.Format.Format_RGB32)
    desktop.fill(0)
    painter = QPainter(desktop)
    for shot in shots:
        painter.drawImage(shot.monitor.rect.left() - left, shot.monitor.rect.top() - top, shot.image)
    painter.end()
    return desktop


class App:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName(APP_NAME)
        self.app.setApplicationVersion(__version__)
        self.icon = QIcon(str(ICON_PATH))
        self.app.setWindowIcon(self.icon)
        self.capturer = DesktopCapturer()
        self.session = None
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.configure_autostart()
        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip(f"{APP_NAME} - Print Screen to capture")
        self.menu = self.build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.app.aboutToQuit.connect(self.capturer.close)

    def configure_autostart(self):
        """Packaged builds register themselves on first run; later the tray menu decides."""
        if not getattr(sys, "frozen", False):
            return
        if not self.settings.value("autostart_configured", False, bool):
            autostart.enable(APP_NAME)
            self.settings.setValue("autostart_configured", True)
        elif autostart.is_enabled(APP_NAME):
            autostart.enable(APP_NAME)

    def build_menu(self):
        menu = QMenu()
        title = menu.addAction(f"{APP_NAME} {__version__}")
        title.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Capture\tPrint Screen", self.capture)
        menu.addAction("Open screenshots folder", self.open_folder)
        menu.addSeparator()
        startup = menu.addAction("Start with Windows")
        startup.setCheckable(True)
        startup.setChecked(autostart.is_enabled(APP_NAME))
        startup.toggled.connect(self.set_autostart)
        menu.addSeparator()
        menu.addAction("Quit", self.app.quit)
        return menu

    def set_autostart(self, enabled):
        if enabled:
            autostart.enable(APP_NAME)
        else:
            autostart.disable(APP_NAME)

    def run(self, open_now):
        self.capturer.snapshot()
        self.tray.show()
        self.trim_soon()
        if open_now:
            self.capture()
        else:
            self.hotkeys = HotkeyListener()
            self.hotkeys.pressed.connect(self.capture)
            self.hotkeys.start()
        return self.app.exec()

    def trim_soon(self):
        QTimer.singleShot(TRIM_DELAY_MS, trim_memory)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.capture()

    def open_folder(self):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(SAVE_DIR)))

    def capture(self):
        if self.session is not None:
            return
        started = time.perf_counter()
        shots = self.capturer.snapshot()
        self.session = CaptureSession(shots)
        self.session.finished.connect(self.on_finished)
        self.session.color_picked.connect(self.on_color_picked)
        self.session.cancelled.connect(self.on_cancelled)
        self.session.show()
        log.info("overlay open in %.0f ms", (time.perf_counter() - started) * 1000)

    def on_finished(self, image, action):
        self.session = None
        self.trim_soon()
        if action == "copy":
            QGuiApplication.clipboard().setImage(image)
            message = "Copied to clipboard"
        else:
            message = f"Saved {save_image(image).name}"
        self.toast = Toast(image, message)
        self.toast.show_briefly()

    def on_color_picked(self, color):
        self.session = None
        self.trim_soon()
        code = color.name().upper()
        QGuiApplication.clipboard().setText(code)
        swatch = QImage(SWATCH_SIZE[0], SWATCH_SIZE[1], QImage.Format.Format_RGB32)
        swatch.fill(color)
        self.toast = Toast(swatch, f"Copied {code}")
        self.toast.show_briefly()

    def on_cancelled(self):
        self.session = None
        self.trim_soon()


def acquire_single_instance():
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}SingleInstance")
    return handle, ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="open the capture overlay immediately")
    parser.add_argument("--dump", type=Path, help="save the tone-mapped desktop to a PNG and exit")
    args = parser.parse_args()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sys.excepthook = lambda kind, error, trace: log.error("uncaught", exc_info=(kind, error, trace))
    enable_per_monitor_dpi()

    if args.dump:
        capturer = DesktopCapturer()
        capturer.snapshot()
        compose_desktop(capturer.snapshot()).save(str(args.dump))
        capturer.close()
        return 0

    mutex, already_running = acquire_single_instance()
    if already_running:
        return 0
    try:
        return App().run(open_now=args.now)
    finally:
        kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    sys.exit(main())
