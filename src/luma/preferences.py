from pathlib import Path

from PySide6.QtCore import QSettings

from luma import APP_NAME


class Setting:
    """A typed, persistent option; the default's type decides how the stored value is read."""

    def __init__(self, default):
        self.default = default

    def __set_name__(self, owner, name):
        self.key = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.store.value(self.key, self.default, type(self.default))

    def __set__(self, instance, value):
        instance.store.setValue(self.key, value)


class Preferences:
    capture_shortcut = Setting("Print")
    secondary_shortcut = Setting("Ctrl+Alt+A")
    show_confirmation = Setting(True)
    show_hint = Setting(True)

    save_folder = Setting(str(Path.home() / "Pictures" / APP_NAME))
    file_name_template = Setting("Luma %Y-%m-%d %H.%M.%S")
    image_format = Setting("PNG")
    image_quality = Setting(90)
    ask_where_to_save = Setting(False)
    save_on_copy = Setting(False)

    pen_color = Setting("#ff3b30")
    pen_size = Setting(6)
    default_tool = Setting("")
    dim_percent = Setting(50)

    def __init__(self):
        self.store = QSettings(APP_NAME, APP_NAME)

    def reset(self):
        for name, value in vars(type(self)).items():
            if isinstance(value, Setting):
                self.store.remove(name)


preferences = Preferences()
