"""Builds the Windows executable (dist/Luma) and optionally installs it for the current user.

    python packaging/build.py            build only
    python packaging/build.py --install  build, copy to %LOCALAPPDATA%\\Programs, add a Start Menu shortcut, launch
"""

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

import PyInstaller.__main__
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

from luma import APP_NAME, __version__

PACKAGING_DIR = Path(__file__).resolve().parent
ROOT = PACKAGING_DIR.parent
ASSETS_DIR = ROOT / "src" / "luma" / "assets"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist" / APP_NAME
INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME
START_MENU = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
REMOVE_ATTEMPTS = 8
REMOVE_RETRY_SECONDS = 1
EXCLUDED_MODULES = ["tkinter", "PIL", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf"]


def write_version_info():
    numbers = tuple(int(part) for part in __version__.split(".")) + (0,)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("FileDescription", f"{APP_NAME} screenshot tool"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", APP_NAME),
                            StringStruct("OriginalFilename", f"{APP_NAME}.exe"),
                            StringStruct("ProductName", APP_NAME),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    BUILD_DIR.mkdir(exist_ok=True)
    path = BUILD_DIR / "version_info.txt"
    path.write_text(str(info), encoding="utf-8")
    return path


def build():
    PyInstaller.__main__.run(
        [
            str(PACKAGING_DIR / "launcher.py"),
            "--noconfirm",
            "--windowed",
            "--name", APP_NAME,
            "--icon", str(ASSETS_DIR / "icon.ico"),
            "--add-data", f"{ASSETS_DIR};luma/assets",
            "--version-file", str(write_version_info()),
            "--collect-all", "windows_capture",
            "--paths", str(PACKAGING_DIR / "cv2_stub"),
            "--paths", str(ROOT / "src"),
            "--distpath", str(ROOT / "dist"),
            "--workpath", str(BUILD_DIR),
            "--specpath", str(BUILD_DIR),
            *[arg for module in EXCLUDED_MODULES for arg in ("--exclude-module", module)],
        ]
    )


def drop_unused_opencv():
    opencv_dir = DIST_DIR / "_internal" / "cv2"
    if opencv_dir.exists():
        shutil.rmtree(opencv_dir)


def stop_running_instances():
    subprocess.run(["taskkill", "/F", "/IM", f"{APP_NAME}.exe"], capture_output=True)


def remove_install_dir():
    """Windows keeps files locked for a moment after a process dies, so retry briefly."""
    for attempt in range(REMOVE_ATTEMPTS):
        try:
            shutil.rmtree(INSTALL_DIR)
            return
        except PermissionError:
            if attempt == REMOVE_ATTEMPTS - 1:
                raise
            time.sleep(REMOVE_RETRY_SECONDS)


def install():
    stop_running_instances()
    if INSTALL_DIR.exists():
        remove_install_dir()
    shutil.copytree(DIST_DIR, INSTALL_DIR)
    executable = INSTALL_DIR / f"{APP_NAME}.exe"
    shortcut = START_MENU / f"{APP_NAME}.lnk"
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{shortcut}');"
        "$s.TargetPath = '{target}'; $s.WorkingDirectory = '{folder}'; $s.Save()"
    ).format(shortcut=shortcut, target=executable, folder=INSTALL_DIR)
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    subprocess.Popen([str(executable)], cwd=INSTALL_DIR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    build()
    drop_unused_opencv()
    if args.install:
        install()


if __name__ == "__main__":
    main()
