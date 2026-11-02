import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from luma.preferences import preferences  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_preferences(tmp_path, monkeypatch, qapp):
    """Preferences backed by a throwaway ini file instead of the real registry key."""
    store = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(preferences, "store", store)
    return preferences
