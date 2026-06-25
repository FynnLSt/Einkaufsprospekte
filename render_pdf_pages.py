#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import shutil
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Fehler: PyMuPDF ist nicht installiert.")
    print("Installiere es mit: pip install PyMuPDF")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Fehler: Pillow ist nicht installiert.")
    print("Installiere es mit: pip install Pillow")
    sys.exit(1)


# ------------------------------------------------------------
# Einstellungen
# ------------------------------------------------------------

PDF_DIR = Path("latest")
IMAGE_DIR = Path("latest_images")

# 120 ist ein guter Kompromiss:
# hoch genug zum Lesen, aber nicht komplett riesig.
IMAGE_DPI = 120

# Falls Bilder zu groß werden, z. B. auf 100 oder 90 senken.
PNG_COMPRESS_LEVEL = 9

# Empfehlung: False lassen, damit das Repo nicht riesig wird.
# Alte Bilder werden dann gelöscht und durch neue ersetzt.
ARCHIVE_OLD_IMAGES = False
ARCHIVE_IMAGE_DIR = Path("Archiv_images")


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def clear_or_archive_latest_images() -> None:
    """
    Entfernt oder archiviert alte Bilder aus latest_images.
    """
    if not IMAGE_DIR.exists():
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        return

    if ARCHIVE_OLD_IMAGES:
        from datetime import datetime

        ARCHIVE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        target_dir = ARCHIVE_IMAGE_DIR / f"latest_images_archiviert_{stamp}"
        shutil.move(str(IMAGE_DIR), str(target_dir))

        print(f"Alte Bilder archiviert nach: {target_dir}")

        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    else:
        shutil.rmtree(IMAGE_DIR)
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        print("Alte Bilder aus latest_images gelöscht.")


def render_page_to_png(page: fitz.Page, output_path: Path, dpi: int) -> None:
    """
    Rendert eine PDF-Seite als PNG.
    """
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    pix = page.get_pixmap(matrix=matrix, alpha=False)

    image = Image.frombytes(
        "RGB",
        (pix.width, pix.height),
        pix.samples
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    image.save(
        output_path,
        format="PNG",
        optimize=True,
        compress_level=PNG_COMPRESS_LEVEL
    )


def render_pdf(pdf_path: Path) -> None:
    """
    Rendert eine komplette PDF in einen eigenen Unterordner.
    """
    output_folder = IMAGE_DIR / pdf_path.stem
    output_folder.mkdir(parents=True, exist_ok=True)

    print(f"Verarbeite PDF: {pdf_path.name}")

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        print(f"Fehler beim Öffnen von {pdf_path.name}: {exc}")
        return

    try:
        total_pages = len(doc)

        for page_index, page in enumerate(doc, start=1):
            output_path = output_folder / f"page_{page_index:03d}.png"

            print(f"  Seite {page_index}/{total_pages} → {output_path}")

            try:
                render_page_to_png(page, output_path, IMAGE_DPI)
            except Exception as exc:
                print(f"  Fehler beim Rendern von Seite {page_index}: {exc}")

    finally:
        doc.close()


# ------------------------------------------------------------
# Hauptprogramm
# ------------------------------------------------------------

def main() -> int:
    if not PDF_DIR.exists():
        print(f"Fehler: Ordner nicht gefunden: {PDF_DIR}")
        return 1

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"Keine PDFs gefunden in: {PDF_DIR}")
        return 1

    clear_or_archive_latest_images()

    print("Starte PDF-zu-PNG-Rendering...")
    print(f"DPI: {IMAGE_DPI}")
    print()

    for pdf_path in pdf_files:
        render_pdf(pdf_path)

    print()
    print("Fertig. PNG-Seiten wurden erzeugt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())