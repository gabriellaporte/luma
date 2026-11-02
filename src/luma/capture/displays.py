import ctypes
from ctypes import wintypes
from typing import NamedTuple

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

SDR_WHITE_LEVEL_DIVISOR = 1000.0
ENUM_CURRENT_SETTINGS = -1
QDC_ONLY_ACTIVE_PATHS = 2
DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
DEVICE_INFO_GET_SDR_WHITE_LEVEL = 11
PATH_INFO_SIZE = 72
MODE_INFO_SIZE = 64
PATH_TARGET_ADAPTER_OFFSET = 20
PATH_TARGET_ID_OFFSET = 28
DISPLAY_MODE_SIZE = 220
DISPLAY_MODE_REMAINDER_SIZE = 128
PORTRAIT_ORIENTATIONS = (1, 3)
user32 = ctypes.WinDLL("user32", use_last_error=True)


class Luid(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class DeviceInfoHeader(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapter", Luid),
        ("id", wintypes.UINT),
    ]


class AdvancedColorInfo(ctypes.Structure):
    _fields_ = [
        ("header", DeviceInfoHeader),
        ("flags", wintypes.UINT),
        ("color_encoding", wintypes.UINT),
        ("bits_per_channel", wintypes.UINT),
    ]

    @property
    def is_enabled(self):
        return bool(self.flags & 0b10)


class SdrWhiteLevel(ctypes.Structure):
    _fields_ = [("header", DeviceInfoHeader), ("level", wintypes.ULONG)]


class WinRect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("monitor", WinRect),
        ("work", WinRect),
        ("flags", wintypes.DWORD),
        ("device", wintypes.WCHAR * 32),
    ]


class DisplayMode(ctypes.Structure):
    _fields_ = [
        ("device_name", wintypes.WCHAR * 32),
        ("spec_version", wintypes.WORD),
        ("driver_version", wintypes.WORD),
        ("size", wintypes.WORD),
        ("driver_extra", wintypes.WORD),
        ("fields", wintypes.DWORD),
        ("position_x", wintypes.LONG),
        ("position_y", wintypes.LONG),
        ("orientation", wintypes.DWORD),
        ("fixed_output", wintypes.DWORD),
        ("remainder", ctypes.c_ubyte * DISPLAY_MODE_REMAINDER_SIZE),
    ]


class Monitor(NamedTuple):
    rect: QRect
    orientation: int

    @property
    def native_size(self):
        width, height = self.rect.width(), self.rect.height()
        return (height, width) if self.orientation in PORTRAIT_ORIENTATIONS else (width, height)


class MonitorShot(NamedTuple):
    monitor: Monitor
    image: QImage


def enable_per_monitor_dpi():
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def list_monitors():
    monitors = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HANDLE,
        wintypes.HDC,
        ctypes.POINTER(WinRect),
        wintypes.LPARAM,
    )

    def collect(handle, _dc, rect, _data):
        r = rect.contents
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        user32.GetMonitorInfoW(handle, ctypes.byref(info))
        mode = DisplayMode(size=DISPLAY_MODE_SIZE)
        user32.EnumDisplaySettingsW(info.device, ENUM_CURRENT_SETTINGS, ctypes.byref(mode))
        monitors.append(Monitor(QRect(r.left, r.top, r.right - r.left, r.bottom - r.top), mode.orientation))
        return True

    user32.EnumDisplayMonitors(None, None, callback_type(collect), 0)
    return monitors


def hdr_sdr_white_scrgb():
    """SDR white level, in scRGB units, of the first monitor with HDR enabled (None if no HDR)."""
    path_count = wintypes.UINT()
    mode_count = wintypes.UINT()
    result = user32.GetDisplayConfigBufferSizes(
        QDC_ONLY_ACTIVE_PATHS, ctypes.byref(path_count), ctypes.byref(mode_count)
    )
    if result:
        raise OSError(f"GetDisplayConfigBufferSizes failed: {result}")
    paths = (ctypes.c_ubyte * (PATH_INFO_SIZE * path_count.value))()
    modes = (ctypes.c_ubyte * (MODE_INFO_SIZE * mode_count.value))()
    result = user32.QueryDisplayConfig(
        QDC_ONLY_ACTIVE_PATHS,
        ctypes.byref(path_count),
        paths,
        ctypes.byref(mode_count),
        modes,
        None,
    )
    if result:
        raise OSError(f"QueryDisplayConfig failed: {result}")

    for index in range(path_count.value):
        base = index * PATH_INFO_SIZE
        adapter = Luid.from_buffer(paths, base + PATH_TARGET_ADAPTER_OFFSET)
        target_id = wintypes.UINT.from_buffer(paths, base + PATH_TARGET_ID_OFFSET).value

        color = AdvancedColorInfo()
        color.header = DeviceInfoHeader(
            DEVICE_INFO_GET_ADVANCED_COLOR_INFO, ctypes.sizeof(color), adapter, target_id
        )
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(color)) or not color.is_enabled:
            continue

        white = SdrWhiteLevel()
        white.header = DeviceInfoHeader(
            DEVICE_INFO_GET_SDR_WHITE_LEVEL, ctypes.sizeof(white), adapter, target_id
        )
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(white)):
            raise OSError("DisplayConfigGetDeviceInfo(SDR white level) failed")
        return white.level / SDR_WHITE_LEVEL_DIVISOR
    return None
