import ctypes
import logging
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from functools import lru_cache
from typing import NamedTuple

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QTransform
from windows_capture import DxgiDuplicationSession

log = logging.getLogger("luma")

SDR_WHITE_LEVEL_DIVISOR = 1000.0
CAPTURE_TIMEOUT_MS = 100
CAPTURE_MAX_ATTEMPTS = 30
FLOAT16_VALUE_COUNT = 65536

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
ROTATION_DEGREES_BY_ORIENTATION = {0: 0, 1: 90, 2: 180, 3: -90}
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
        monitors.append(
            Monitor(QRect(r.left, r.top, r.right - r.left, r.bottom - r.top), mode.orientation)
        )
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


def srgb_encode(linear):
    encoded = np.where(
        linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055
    )
    return (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


@lru_cache(maxsize=4)
def float16_to_srgb_lut(sdr_white):
    """Every float16 bit pattern mapped to an 8-bit sRGB value, SDR white landing on 255."""
    patterns = np.arange(FLOAT16_VALUE_COUNT, dtype=np.uint16).view(np.float16)
    linear = np.nan_to_num(patterns.astype(np.float32), nan=0.0, posinf=65504.0, neginf=0.0) / sdr_white
    return srgb_encode(np.maximum(linear, 0.0))


def tone_map_scrgb(pixels, sdr_white):
    """Exact for everything up to SDR white; brighter HDR pixels keep hue instead of clipping."""
    rgb = pixels[..., :3]
    mapped = float16_to_srgb_lut(sdr_white)[rgb.view(np.uint16)]
    peak = rgb.max(axis=-1)
    highlights = peak > sdr_white
    if highlights.any():
        bright = np.nan_to_num(rgb[highlights].astype(np.float32), nan=0.0)
        bright /= np.maximum(bright.max(axis=1, keepdims=True), 1e-6)
        mapped[highlights] = srgb_encode(bright)
    return mapped


def native_image(frame, sdr_white):
    pixels = frame.to_numpy()
    if frame.color_format == "rgba16f":
        if sdr_white is None:
            raise RuntimeError("HDR frame received but no monitor reports HDR enabled")
        rgb = np.ascontiguousarray(tone_map_scrgb(pixels, sdr_white))
        height, width, _channels = rgb.shape
        image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888)
        return image.convertToFormat(QImage.Format.Format_RGB32)
    height, width, _channels = pixels.shape
    return QImage(pixels.data, width, height, width * 4, QImage.Format.Format_RGB32).copy()


def upright(image, orientation):
    degrees = ROTATION_DEGREES_BY_ORIENTATION[orientation]
    if degrees == 0:
        return image
    return image.transformed(QTransform().rotate(degrees))


class DesktopCapturer:
    """Keeps one DXGI duplication session per monitor alive so a capture is just a frame grab.

    Sessions live on dedicated threads: the native objects must stay on the thread that made them.
    """

    def __init__(self):
        self.monitors = []
        self.workers = {}
        self.sessions = {}
        self.latest = {}

    def close(self):
        for index, worker in self.workers.items():
            worker.submit(self.release, index).result()
            worker.shutdown()
        self.workers = {}

    def release(self, index):
        self.latest.pop(index, None)
        del self.sessions[index]

    def snapshot(self):
        monitors = list_monitors()
        if monitors != self.monitors:
            self.reset(monitors)
        sdr_white = hdr_sdr_white_scrgb()
        futures = [
            self.workers[index].submit(self.grab, index, sdr_white)
            for index in range(1, len(monitors) + 1)
        ]
        return self.place([future.result() for future in futures])

    def reset(self, monitors):
        self.close()
        self.monitors = monitors
        self.latest = {}
        self.workers = {index: ThreadPoolExecutor(1) for index in range(1, len(monitors) + 1)}
        self.sessions = {
            index: worker.submit(DxgiDuplicationSession, monitor_index=index).result()
            for index, worker in self.workers.items()
        }

    def grab(self, index, sdr_white):
        try:
            frame = self.next_frame(index)
        except Exception:
            log.exception("display duplication lost on monitor %s; recreating", index)
            self.sessions[index].recreate()
            self.latest.pop(index, None)
            frame = self.next_frame(index)
        if frame is not None:
            self.latest[index] = native_image(frame, sdr_white)
        return self.latest[index]

    def next_frame(self, index):
        """A new frame, or None when nothing on screen changed since the last one."""
        session = self.sessions[index]
        is_first_capture = index not in self.latest
        attempts = CAPTURE_MAX_ATTEMPTS if is_first_capture else 1
        for _attempt in range(attempts):
            frame = session.acquire_frame(CAPTURE_TIMEOUT_MS)
            if frame is not None and frame.to_numpy().any():
                return frame
        if is_first_capture:
            raise RuntimeError("Display capture returned no pixels")
        return None

    def place(self, images):
        unplaced = list(self.monitors)
        shots = []
        for image in images:
            size = (image.width(), image.height())
            monitor = next((m for m in unplaced if m.native_size == size), None)
            if monitor is None:
                raise RuntimeError(f"No monitor matches captured frame {size}")
            unplaced.remove(monitor)
            shots.append(MonitorShot(monitor, upright(image, monitor.orientation)))
        return shots
