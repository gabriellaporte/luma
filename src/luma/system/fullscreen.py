import ctypes

QUNS_RUNNING_D3D_FULL_SCREEN = 3

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)


def exclusive_fullscreen_active():
    """True while a Direct3D app owns the display exclusively; nothing can be drawn over it."""
    state = ctypes.c_int()
    result = shell32.SHQueryUserNotificationState(ctypes.byref(state))
    if result:
        raise OSError(f"SHQueryUserNotificationState failed: {result:#x}")
    return state.value == QUNS_RUNNING_D3D_FULL_SCREEN


def release_cursor_clip():
    """Games lock the cursor inside their window; free it so the capture overlay can be used."""
    if not user32.ClipCursor(None):
        raise OSError(f"ClipCursor failed: {ctypes.get_last_error()}")
