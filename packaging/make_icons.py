"""Builds assets/icon.ico and assets/icon.png from assets/logo.png (any size, squared automatically)."""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "src" / "luma" / "assets"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_SIZE = 256


def squared(image):
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def main():
    logo = squared(Image.open(ASSETS / "logo.png").convert("RGBA"))
    logo.save(ASSETS / "icon.ico", sizes=[(size, size) for size in ICO_SIZES])
    logo.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS).save(ASSETS / "icon.png")


if __name__ == "__main__":
    main()
