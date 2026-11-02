import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PySide6.QtGui import QImage, QTransform
from windows_capture import DxgiDuplicationSession

from luma.capture.displays import MonitorShot, hdr_sdr_white_scrgb, list_monitors
from luma.capture.tonemap import tone_map_scrgb

log = logging.getLogger("luma")
CAPTURE_TIMEOUT_MS = 100
REFRESH_TIMEOUT_MS = 16
CAPTURE_MAX_ATTEMPTS = 30
ROTATION_DEGREES_BY_ORIENTATION = {0: 0, 1: 90, 2: 180, 3: -90}


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
            self.workers[index].submit(self.grab, index, sdr_white) for index in range(1, len(monitors) + 1)
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
            frame = session.acquire_frame(CAPTURE_TIMEOUT_MS if is_first_capture else REFRESH_TIMEOUT_MS)
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
