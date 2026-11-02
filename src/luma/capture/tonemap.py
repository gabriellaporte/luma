import numpy as np

FLOAT16_VALUE_COUNT = 65536


def srgb_encode(linear):
    encoded = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)
    return (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def float16_to_srgb_lut(sdr_white):
    """Every float16 bit pattern mapped to an 8-bit sRGB value, SDR white landing on 255."""
    patterns = np.arange(FLOAT16_VALUE_COUNT, dtype=np.uint16).view(np.float16)
    linear = np.nan_to_num(patterns.astype(np.float32), nan=0.0, posinf=65504.0, neginf=0.0) / sdr_white
    return srgb_encode(np.maximum(linear, 0.0))


def tone_map_scrgb(pixels, sdr_white):
    """Exact for everything up to SDR white; brighter HDR pixels keep hue instead of clipping."""
    rgb = pixels[..., :3]
    mapped = float16_to_srgb_lut(sdr_white)[rgb.view(np.uint16)]
    peak = rgb.max(axis=-1)
    highlights = peak > sdr_white
    if highlights.any():
        bright = np.maximum(np.nan_to_num(rgb[highlights].astype(np.float32), nan=0.0), 0.0)
        bright /= np.maximum(bright.max(axis=1, keepdims=True), 1e-6)
        mapped[highlights] = srgb_encode(bright)
    return mapped
