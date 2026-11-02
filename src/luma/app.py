import argparse
import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from luma.system import autostart
from luma import saving
from luma.capture.desktop import DesktopCapturer, enable_per_monitor_dpi
from luma.system.hotkeys import HotkeyListener
from luma import APP_NAME, __version__
from luma.editor.overlay import CaptureSession
from luma.preferences import preferences
from luma.ui.settings_dialog import SettingsDialog
from luma.ui.theme import MENU_STYLE
from luma.ui.toast import Toast

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"
LOG_PATH = Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "app.log"
ERROR_ALREADY_EXISTS = 183
TRIM_DELAY_MS = 1500
COLOR_SWATCH_SIZE = (150, 96)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
psapi = ctypes.WinDLL("psapi", use_last_error=True)
psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
log = logging.getLogger("luma")


def trim_memory():
    """Hand idle pages back to Windows so the tray app stays tiny between captures."""
    if not psapi.EmptyWorkingSet(kernel32.GetCurrentProcess()):
        raise OSError(f"EmptyWorkingSet failed: {ctypes.get_last_error()}")


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
        self.hotkeys = HotkeyListener()
        self.session = None
        self.toast = None
        self.configure_autostart()
        self.tray = QSystemTrayIcon(self.icon)
        self.menu = self.build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.hotkeys.pressed.connect(self.capture)
        self.hotkeys.unavailable.connect(self.warn_shortcut_unavailable)
        self.app.aboutToQuit.connect(self.capturer.close)
        self.refresh_tooltip()

    def configure_autostart(self):
        """Packaged builds register themselves on first run; the settings dialog decides after that."""
        if not getattr(sys, "frozen", False):
            return
        store = QSettings(APP_NAME, APP_NAME)
        if not store.value("autostart_configured", False, bool):
            autostart.enable(APP_NAME)
            store.setValue("autostart_configured", True)
        elif autostart.is_enabled(APP_NAME):
            autostart.enable(APP_NAME)

    def build_menu(self):
        menu = QMenu()
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction(f"{APP_NAME} {__version__}").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Capture", self.capture)
        menu.addAction("Open screenshots folder", saving.open_save_folder)
        menu.addAction("Settings...", self.open_settings)
        menu.addSeparator()
        menu.addAction("Quit", self.app.quit)
        return menu

    def refresh_tooltip(self):
        self.tray.setToolTip(f"{APP_NAME} - {preferences.capture_shortcut} to capture")

    def run(self, open_now):
        self.capturer.snapshot()
        self.tray.show()
        self.hotkeys.start()
        self.trim_soon()
        if open_now:
            self.capture()
        return self.app.exec()

    def trim_soon(self):
        QTimer.singleShot(TRIM_DELAY_MS, trim_memory)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.capture()

    def warn_shortcut_unavailable(self, shortcut):
        self.tray.showMessage(
            APP_NAME,
            f"The shortcut {shortcut} is already used by another app. Pick a different one in Settings.",
            QSystemTrayIcon.MessageIcon.Warning,
        )

    def open_settings(self):
        self.hotkeys.suspend()
        SettingsDialog().exec()
        self.hotkeys.reload()
        self.refresh_tooltip()
        if self.session is not None:
            self.session.refocus()

    def capture(self):
        if self.session is not None:
            return
        started = time.perf_counter()
        shots = self.capturer.snapshot()
        self.session = CaptureSession(shots)
        self.session.finished.connect(self.on_finished)
        self.session.color_picked.connect(self.on_color_picked)
        self.session.settings_requested.connect(self.open_settings)
        self.session.cancelled.connect(self.on_cancelled)
        self.session.show()
        log.info("overlay open in %.0f ms", (time.perf_counter() - started) * 1000)

    def on_finished(self, image, action):
        self.end_session()
        if action == "copy":
            QGuiApplication.clipboard().setImage(image)
            title, detail = "Copied to clipboard", f"{image.width()} x {image.height()}"
            if preferences.save_on_copy:
                title, detail = "Copied and saved", saving.save_to_default_folder(image).name
        else:
            path = saving.save(image)
            if path is None:
                return
            title, detail = "Saved", path.name
        self.confirm(image, title, detail)

    def on_color_picked(self, color):
        self.end_session()
        code = color.name().upper()
        QGuiApplication.clipboard().setText(code)
        swatch = QImage(COLOR_SWATCH_SIZE[0], COLOR_SWATCH_SIZE[1], QImage.Format.Format_RGB32)
        swatch.fill(color)
        self.confirm(swatch, "Color copied", code)

    def on_cancelled(self):
        self.end_session()

    def end_session(self):
        self.session = None
        self.trim_soon()

    def confirm(self, image, title, detail):
        if not preferences.show_confirmation:
            return
        self.toast = Toast(image, title, detail)
        self.toast.show_briefly()


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
