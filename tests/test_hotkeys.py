import pytest

from luma.system.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, to_windows_hotkey


@pytest.mark.parametrize(
    "shortcut, expected",
    [
        ("Print", (0, 0x2C)),
        ("Ctrl+Alt+A", (MOD_CONTROL | MOD_ALT, 0x41)),
        ("Ctrl+Shift+S", (MOD_CONTROL | MOD_SHIFT, 0x53)),
        ("F9", (0, 0x78)),
        ("Ctrl+Space", (MOD_CONTROL, 0x20)),
    ],
)
def test_shortcuts_become_windows_hotkeys(shortcut, expected, qapp):
    assert to_windows_hotkey(shortcut) == expected


@pytest.mark.parametrize("shortcut", ["", "Ctrl", "Ctrl+Left", "A, B"])
def test_unsupported_shortcuts_are_rejected(shortcut, qapp):
    with pytest.raises(ValueError):
        to_windows_hotkey(shortcut)
