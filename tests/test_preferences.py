def test_defaults_and_typed_round_trip(isolated_preferences):
    preferences = isolated_preferences
    assert preferences.image_format == "PNG" and preferences.show_hint is True

    preferences.image_quality = 70
    preferences.show_hint = False
    preferences.default_tool = "arrow"
    assert preferences.image_quality == 70
    assert preferences.show_hint is False
    assert preferences.default_tool == "arrow"


def test_reset_restores_every_default(isolated_preferences):
    preferences = isolated_preferences
    preferences.file_name_template = "custom"
    preferences.dim_percent = 10
    preferences.reset()
    assert preferences.file_name_template == "Luma %Y-%m-%d %H.%M.%S"
    assert preferences.dim_percent == 50
