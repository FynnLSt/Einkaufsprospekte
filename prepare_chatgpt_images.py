#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from PIL import Image

SOURCE_DIR = Path("latest_images")
OUTPUT_DIR = Path("latest_images_chatgpt")

MAX_WIDTH = 1800
JPEG_QUALITY = 88

def convert_image(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGB")

    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        new_size = (MAX_WIDTH, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(
        dst,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )

def main() -> int:
    if not SOURCE_DIR.exists():
        print(f"Ordner nicht gefunden: {SOURCE_DIR}")
        return 1

    if OUTPUT_DIR.exists():
        import shutil
        shutil.rmtree(OUTPUT_DIR)

    count = 0
    for src in sorted(SOURCE_DIR.glob("*/page_*.png")):
        relative = src.relative_to(SOURCE_DIR)
        dst = OUTPUT_DIR / relative.with_suffix(".jpg")
        convert_image(src, dst)
        print(f"{src} -> {dst}")
        count += 1

    print(f"Fertig. {count} Bilder erzeugt in {OUTPUT_DIR}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
