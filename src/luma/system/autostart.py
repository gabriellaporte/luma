import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    interpreter = Path(sys.executable).with_name("pythonw.exe")
    return f'"{interpreter}" "{Path(sys.argv[0]).resolve()}"'


def is_enabled(app_name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, app_name)
    except FileNotFoundError:
        return False
    return True


def enable(app_name):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, launch_command())


def disable(app_name):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, app_name)
        except FileNotFoundError:
            pass
