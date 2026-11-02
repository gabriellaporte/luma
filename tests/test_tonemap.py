import numpy as np

from luma.capture.tonemap import float16_to_srgb_lut, tone_map_scrgb

SDR_WHITE = 3.0


def srgb_to_linear(value):
    value = value / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def test_sdr_white_maps_to_pure_white_and_black_stays_black():
    lut = float16_to_srgb_lut(SDR_WHITE)
    assert lut[np.float16(SDR_WHITE).view(np.uint16)] == 255
    assert lut[np.float16(0).view(np.uint16)] == 0


def test_ordinary_sdr_colors_round_trip_exactly():
    lut = float16_to_srgb_lut(SDR_WHITE)
    for original in (1, 17, 68, 128, 200, 254):
        scrgb = np.float16(srgb_to_linear(original) * SDR_WHITE)
        assert abs(int(lut[scrgb.view(np.uint16)]) - original) <= 1


def test_nan_and_negative_values_do_not_break_the_table():
    lut = float16_to_srgb_lut(SDR_WHITE)
    assert lut[np.float16(np.nan).view(np.uint16)] == 0
    assert lut[np.float16(-1.0).view(np.uint16)] == 0


def test_highlights_keep_their_hue_instead_of_clipping_to_white():
    pixel = np.array([[[SDR_WHITE * 2, SDR_WHITE, 0.0, 1.0]]], dtype=np.float16)
    red, green, blue = tone_map_scrgb(pixel, SDR_WHITE)[0, 0]
    assert red == 255 and 0 < green < 255 and blue == 0
