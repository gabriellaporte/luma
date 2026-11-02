import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from luma.preferences import preferences

IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WebP": "webp"}
LOSSY_FORMATS = ("JPEG", "WebP")
FALLBACK_STEM = "Luma"
INVALID_FILE_NAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
FILE_DIALOG_FILTER = "PNG (*.png);;JPEG (*.jpg);;WebP (*.webp)"


def file_stem(template, moment):
    stem = INVALID_FILE_NAME_CHARACTERS.sub("-", moment.strftime(template)).strip().rstrip(".")
    return stem or FALLBACK_STEM


def default_path(moment=None):
    folder = Path(preferences.save_folder)
    extension = IMAGE_FORMATS[preferences.image_format]
    stem = file_stem(preferences.file_name_template, moment or datetime.now())
    path = folder / f"{stem}.{extension}"
    copy_number = 2
    while path.exists():
        path = folder / f"{stem} ({copy_number}).{extension}"
        copy_number += 1
    return path


def write(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    quality = preferences.image_quality if path.suffix.lower() in (".jpg", ".jpeg", ".webp") else -1
    if not image.save(str(path), None, quality):
        raise OSError(f"Could not save {path}")
    return path


def save_to_default_folder(image):
    return write(image, default_path())


def save_with_dialog(image):
    """Returns the saved path, or None when the user cancels the dialog."""
    chosen, _filter = QFileDialog.getSaveFileName(
        None, "Save screenshot", str(default_path()), FILE_DIALOG_FILTER
    )
    return write(image, Path(chosen)) if chosen else None


def save(image):
    return save_with_dialog(image) if preferences.ask_where_to_save else save_to_default_folder(image)


def open_save_folder():
    folder = Path(preferences.save_folder)
    folder.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
