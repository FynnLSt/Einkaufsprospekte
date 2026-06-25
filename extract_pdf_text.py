#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Fehler: PyMuPDF ist nicht installiert.")
    print("Installiere es mit: pip install PyMuPDF")
    sys.exit(1)


PDF_DIR = Path("latest")
TEXT_DIR = Path("latest_text")
TEXT_ARCHIVE_DIR = Path("Archiv_text")


def timestamp_string() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def archive_old_text_files() -> None:
    TEXT_DIR.mkdir(exist_ok=True)
    TEXT_ARCHIVE_DIR.mkdir(exist_ok=True)

    archive_stamp = timestamp_string()

    for path in TEXT_DIR.iterdir():
        if not path.is_file():
            continue

        target_name = f"{path.stem}_archiviert_{archive_stamp}{path.suffix}"
        target_path = TEXT_ARCHIVE_DIR / target_name

        counter = 1
        while target_path.exists():
            target_path = TEXT_ARCHIVE_DIR / f"{path.stem}_archiviert_{archive_stamp}_{counter}{path.suffix}"
            counter += 1

        shutil.move(str(path), str(target_path))
        print(f"Text archiviert: {target_path}")


def extract_text_from_pdf(pdf_path: Path) -> str:
    output_parts: list[str] = []

    with fitz.open(pdf_path) as doc:
        for page_number, page in enumerate(doc, start=1):
            try:
                text = page.get_text("text")
                text = clean_text(text)
            except Exception as exc:
                print(f"Fehler auf Seite {page_number} in {pdf_path.name}: {exc}")
                text = ""

            output_parts.append(
                f"\n\n===== SEITE {page_number} =====\n\n{text}"
            )

    return "\n".join(output_parts).strip()


def main() -> int:
    if not PDF_DIR.exists():
        print(f"Fehler: Ordner nicht gefunden: {PDF_DIR}")
        return 1

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"Keine PDFs gefunden in: {PDF_DIR}")
        return 1

    TEXT_DIR.mkdir(exist_ok=True)
    TEXT_ARCHIVE_DIR.mkdir(exist_ok=True)

    archive_old_text_files()

    print("Starte Textextraktion...")

    warnings: list[str] = []

    for pdf_path in pdf_files:
        print(f"Verarbeite: {pdf_path.name}")

        try:
            full_text = extract_text_from_pdf(pdf_path)
        except Exception as exc:
            print(f"Fehler beim Verarbeiten von {pdf_path.name}: {exc}")
            continue

        txt_path = TEXT_DIR / f"{pdf_path.stem}.txt"
        txt_path.write_text(full_text, encoding="utf-8")

        print(f"Gespeichert: {txt_path}")

        if len(full_text) < 500:
            warnings.append(
                f"{pdf_path.name}: sehr wenig Text extrahiert. "
                "Möglicherweise ist das ein Bild-PDF oder braucht OCR."
            )

    if warnings:
        print()
        print("Warnungen:")
        for warning in warnings:
            print(f"- {warning}")

    print()
    print("Textextraktion abgeschlossen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())