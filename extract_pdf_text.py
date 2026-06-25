#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from datetime import datetime
import json
import re
import shutil
import sys
from typing import Any

import fitz  # PyMuPDF
from PIL import Image
import pytesseract


PDF_DIR = Path("latest")

TEXT_DIR = Path("latest_text")
LAYOUT_DIR = Path("latest_layout")

TEXT_ARCHIVE_DIR = Path("Archiv_text")
LAYOUT_ARCHIVE_DIR = Path("Archiv_layout")

OCR_DPI = 200
MIN_TEXT_LENGTH_FOR_NO_OCR = 500


def timestamp_string() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def archive_folder_content(source_dir: Path, archive_dir: Path) -> None:
    source_dir.mkdir(exist_ok=True)
    archive_dir.mkdir(exist_ok=True)

    stamp = timestamp_string()

    for path in source_dir.iterdir():
        if not path.is_file():
            continue

        target_path = archive_dir / f"{path.stem}_archiviert_{stamp}{path.suffix}"

        counter = 1
        while target_path.exists():
            target_path = archive_dir / f"{path.stem}_archiviert_{stamp}_{counter}{path.suffix}"
            counter += 1

        shutil.move(str(path), str(target_path))
        print(f"Archiviert: {target_path}")


def page_to_image(page: fitz.Page, dpi: int = OCR_DPI) -> Image.Image:
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    image = Image.frombytes(
        "RGB",
        [pix.width, pix.height],
        pix.samples
    )

    return image


def extract_pdf_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    """
    Extrahiert Textblöcke mit Koordinaten direkt aus dem PDF.
    """
    blocks = []

    page_dict = page.get_text("dict")

    for block_index, block in enumerate(page_dict.get("blocks", []), start=1):
        if block.get("type") != 0:
            continue

        bbox = block.get("bbox", [0, 0, 0, 0])

        lines_text = []

        for line in block.get("lines", []):
            spans_text = []

            for span in line.get("spans", []):
                text = span.get("text", "")
                if text.strip():
                    spans_text.append(text)

            line_text = clean_text(" ".join(spans_text))
            if line_text:
                lines_text.append(line_text)

        block_text = clean_text("\n".join(lines_text))

        if not block_text:
            continue

        blocks.append({
            "source": "pdf_text",
            "block_index": block_index,
            "bbox": {
                "x0": round(float(bbox[0]), 2),
                "y0": round(float(bbox[1]), 2),
                "x1": round(float(bbox[2]), 2),
                "y1": round(float(bbox[3]), 2),
            },
            "text": block_text
        })

    return blocks


def extract_ocr_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    """
    OCR-Fallback für Seiten ohne brauchbaren eingebetteten Text.
    Gibt Wörter/Zeilen mit Koordinaten zurück.
    """
    image = page_to_image(page)

    data = pytesseract.image_to_data(
        image,
        lang="deu",
        output_type=pytesseract.Output.DICT,
        config="--psm 6"
    )

    words = []

    for i in range(len(data["text"])):
        text = data["text"][i].strip()

        if not text:
            continue

        try:
            conf = float(data["conf"][i])
        except ValueError:
            conf = -1

        if conf < 30:
            continue

        words.append({
            "text": text,
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i]),
            "conf": conf,
            "line_num": int(data["line_num"][i]),
            "block_num": int(data["block_num"][i]),
            "par_num": int(data["par_num"][i]),
        })

    # Wörter zu Zeilen gruppieren
    grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = {}

    for word in words:
        key = (
            word["block_num"],
            word["par_num"],
            word["line_num"]
        )
        grouped.setdefault(key, []).append(word)

    ocr_blocks = []

    for index, (_, line_words) in enumerate(grouped.items(), start=1):
        line_words.sort(key=lambda w: w["left"])

        text = clean_text(" ".join(w["text"] for w in line_words))

        if not text:
            continue

        x0 = min(w["left"] for w in line_words)
        y0 = min(w["top"] for w in line_words)
        x1 = max(w["left"] + w["width"] for w in line_words)
        y1 = max(w["top"] + w["height"] for w in line_words)

        avg_conf = sum(w["conf"] for w in line_words) / len(line_words)

        ocr_blocks.append({
            "source": "ocr",
            "block_index": index,
            "bbox": {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
            },
            "confidence": round(avg_conf, 2),
            "text": text
        })

    return ocr_blocks


def make_human_readable_text(file_name: str, pages: list[dict[str, Any]]) -> str:
    """
    Erzeugt eine .txt-Datei, die für Menschen und ChatGPT lesbar ist.
    Enthält pro Seite sowohl PDF-Textblöcke als auch OCR-Blöcke mit Koordinaten.
    """
    parts = [
        f"DATEI: {file_name}",
        "",
        "Hinweis:",
        "Diese Datei enthält Prospekttext mit Positionsdaten.",
        "Es werden zwei Quellen gespeichert:",
        "1. PDF-TEXT-BLÖCKE = Text, der direkt im PDF eingebettet ist.",
        "2. OCR-BLÖCKE = Text, der aus dem Seitenbild erkannt wurde.",
        "",
        "x0/y0 = linke obere Ecke, x1/y1 = rechte untere Ecke.",
        "Dadurch kann man Preise besser Produkten in der Nähe zuordnen.",
        ""
    ]

    for page in pages:
        pdf_blocks = page.get("pdf_text_blocks", [])
        ocr_blocks = page.get("ocr_blocks", [])

        parts.append("")
        parts.append(f"===== SEITE {page['page_number']} =====")
        parts.append(f"Extraktionsmethode: {page.get('method', 'unbekannt')}")
        parts.append(f"PDF-Text-Länge: {page.get('pdf_text_length', 0)} Zeichen")
        parts.append(f"OCR-Text-Länge: {page.get('ocr_text_length', 0)} Zeichen")
        parts.append("")

        # ------------------------------------------------------------
        # PDF-Textblöcke
        # ------------------------------------------------------------

        parts.append("----- PDF-TEXT-BLÖCKE -----")

        if not pdf_blocks:
            parts.append("[Kein PDF-Text erkannt]")
            parts.append("")
        else:
            sorted_pdf_blocks = sorted(
                pdf_blocks,
                key=lambda b: (b["bbox"]["y0"], b["bbox"]["x0"])
            )

            for block in sorted_pdf_blocks:
                bbox = block["bbox"]

                parts.append(
                    f"[PDF_TEXT | BLOCK {block['block_index']} | "
                    f"x0={bbox['x0']} y0={bbox['y0']} "
                    f"x1={bbox['x1']} y1={bbox['y1']}]"
                )
                parts.append(block["text"])
                parts.append("")

        # ------------------------------------------------------------
        # OCR-Blöcke
        # ------------------------------------------------------------

        parts.append("")
        parts.append("----- OCR-BLÖCKE -----")

        if not ocr_blocks:
            parts.append("[Kein OCR-Text erkannt]")
            parts.append("")
        else:
            sorted_ocr_blocks = sorted(
                ocr_blocks,
                key=lambda b: (b["bbox"]["y0"], b["bbox"]["x0"])
            )

            for block in sorted_ocr_blocks:
                bbox = block["bbox"]
                confidence = block.get("confidence", "n/a")

                parts.append(
                    f"[OCR | BLOCK {block['block_index']} | "
                    f"x0={bbox['x0']} y0={bbox['y0']} "
                    f"x1={bbox['x1']} y1={bbox['y1']} | "
                    f"conf={confidence}]"
                )
                parts.append(block["text"])
                parts.append("")

    return "\n".join(parts).strip() + "\n"


def process_pdf(pdf_path: Path) -> tuple[str, dict[str, Any]]:
    """
    Verarbeitet eine PDF komplett.

    Für jede Seite wird immer beides gemacht:
    1. PDF-Text mit Koordinaten extrahieren
    2. OCR-Text mit Koordinaten extrahieren

    Dadurch können später beide Datenquellen gemeinsam ausgewertet werden.
    """
    pages_output = []

    with fitz.open(pdf_path) as doc:
        total_pages = len(doc)

        for page_number, page in enumerate(doc, start=1):
            print(f"  Seite {page_number}/{total_pages}")

            # ------------------------------------------------------------
            # 1. Eingebetteten PDF-Text extrahieren
            # ------------------------------------------------------------
            try:
                pdf_blocks = extract_pdf_blocks(page)
            except Exception as exc:
                print(f"  Fehler bei PDF-Text auf Seite {page_number}: {exc}")
                pdf_blocks = []

            embedded_text = clean_text(
                "\n".join(block["text"] for block in pdf_blocks)
            )

            # ------------------------------------------------------------
            # 2. OCR immer zusätzlich ausführen
            # ------------------------------------------------------------
            try:
                ocr_blocks = extract_ocr_blocks(page)
            except Exception as exc:
                print(f"  Fehler bei OCR auf Seite {page_number}: {exc}")
                ocr_blocks = []

            ocr_text = clean_text(
                "\n".join(block["text"] for block in ocr_blocks)
            )

            # ------------------------------------------------------------
            # 3. Beide Ergebnisse für diese Seite speichern
            # ------------------------------------------------------------
            pages_output.append({
                "page_number": page_number,
                "method": "pdf_text_and_ocr",
                "pdf_text_blocks": pdf_blocks,
                "ocr_blocks": ocr_blocks,
                "pdf_text_length": len(embedded_text),
                "ocr_text_length": len(ocr_text)
            })

    layout_json = {
        "file": pdf_path.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pages": pages_output
    }

    readable_text = make_human_readable_text(pdf_path.name, pages_output)

    return readable_text, layout_json


def main() -> int:
    if not PDF_DIR.exists():
        print(f"Fehler: Ordner nicht gefunden: {PDF_DIR}")
        return 1

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"Keine PDFs gefunden in: {PDF_DIR}")
        return 1

    TEXT_DIR.mkdir(exist_ok=True)
    LAYOUT_DIR.mkdir(exist_ok=True)
    TEXT_ARCHIVE_DIR.mkdir(exist_ok=True)
    LAYOUT_ARCHIVE_DIR.mkdir(exist_ok=True)

    archive_folder_content(TEXT_DIR, TEXT_ARCHIVE_DIR)
    archive_folder_content(LAYOUT_DIR, LAYOUT_ARCHIVE_DIR)

    print("Starte Layout- und OCR-Extraktion...")

    for pdf_path in pdf_files:
        print(f"Verarbeite: {pdf_path.name}")

        try:
            readable_text, layout_json = process_pdf(pdf_path)
        except Exception as exc:
            print(f"Fehler beim Verarbeiten von {pdf_path.name}: {exc}")
            continue

        txt_path = TEXT_DIR / f"{pdf_path.stem}.txt"
        json_path = LAYOUT_DIR / f"{pdf_path.stem}.json"

        txt_path.write_text(readable_text, encoding="utf-8")
        json_path.write_text(
            json.dumps(layout_json, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(f"Gespeichert: {txt_path}")
        print(f"Gespeichert: {json_path}")

    print()
    print("Fertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())