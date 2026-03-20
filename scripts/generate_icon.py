from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    output_path = Path("assets") / "app.ico"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    size = 256
    image = Image.new("RGBA", (size, size), "#10324d")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 238, 238), radius=44, fill="#f4f1ea")
    draw.rounded_rectangle((42, 56, 214, 120), radius=20, fill="#1d6f8d")
    draw.rounded_rectangle((42, 136, 214, 200), radius=20, fill="#d66c44")
    draw.polygon([(124, 78), (174, 78), (146, 32), (196, 32), (130, 8), (88, 62)], fill="#f4f1ea")
    draw.polygon([(132, 176), (82, 176), (110, 222), (60, 222), (126, 246), (168, 192)], fill="#f4f1ea")
    image.save(output_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])


if __name__ == "__main__":
    main()
