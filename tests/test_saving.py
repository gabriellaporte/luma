from datetime import datetime

import pytest
from PySide6.QtGui import QColor, QImage

from luma import saving

MOMENT = datetime(2026, 11, 1, 23, 45, 7)


@pytest.fixture
def image():
    picture = QImage(40, 30, QImage.Format.Format_RGB32)
    picture.fill(QColor("#3b82f6"))
    return picture


def test_file_stem_expands_date_codes_and_strips_forbidden_characters():
    assert saving.file_stem("Shot %Y-%m-%d %H.%M.%S", MOMENT) == "Shot 2026-11-01 23.45.07"
    assert saving.file_stem('a<b>:"c"/d?', MOMENT) == "a-b---c--d-"


def test_empty_template_falls_back_to_a_default_name():
    assert saving.file_stem("", MOMENT) == saving.FALLBACK_STEM


def test_existing_files_are_never_overwritten(isolated_preferences, tmp_path, image):
    isolated_preferences.save_folder = str(tmp_path)
    isolated_preferences.file_name_template = "shot"
    first = saving.write(image, saving.default_path(MOMENT))
    second = saving.write(image, saving.default_path(MOMENT))
    assert first.name == "shot.png"
    assert second.name == "shot (2).png"


@pytest.mark.parametrize("image_format, extension", [("PNG", ".png"), ("JPEG", ".jpg"), ("WebP", ".webp")])
def test_every_format_is_written_to_disk(isolated_preferences, tmp_path, image, image_format, extension):
    isolated_preferences.save_folder = str(tmp_path / "nested" / "folder")
    isolated_preferences.image_format = image_format
    path = saving.save_to_default_folder(image)
    assert path.suffix == extension and path.stat().st_size > 0
    assert QImage(str(path)).size() == image.size()
