#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from datetime import date, datetime
import argparse
import calendar
import re
import shutil
import sys


# ------------------------------------------------------------
# Einstellungen
# ------------------------------------------------------------

LATEST_IMAGES_DIR = Path("latest_images")
ARCHIVE_IMAGES_DIR = Path("Archiv_images")

ARCHIVE_DIRS = [
    Path("Archiv"),
    Path("Archiv_text"),
    Path("Archiv_layout"),
    Path("Archiv_images"),
]

RETENTION_MONTHS = 6

DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ------------------------------------------------------------
# Datums-Hilfsfunktionen
# ------------------------------------------------------------

def today_local() -> date:
    """
    Nutzt das aktuelle Systemdatum.
    In GitHub Actions wird die Zeitzone über TZ=Europe/Berlin gesetzt,
    wenn du das im Workflow so ausführst.
    """
    return date.today()


def subtract_months(source_date: date, months: int) -> date:
    """
    Zieht eine Anzahl Monate von einem Datum ab.
    Beispiel:
    2026-06-25 minus 6 Monate = 2025-12-25
    """
    month = source_date.month - months
    year = source_date.year

    while month <= 0:
        month += 12
        year -= 1

    last_day = calendar.monthrange(year, month)[1]
    day = min(source_date.day, last_day)

    return date(year, month, day)


def extract_first_date_from_name(name: str) -> date | None:
    """
    Sucht das erste Datum im Format YYYY-MM-DD in einem Datei- oder Ordnernamen.

    Beispiel:
    aldi_sued_2026-06-25_archiviert_2026-07-01.txt
    → 2026-06-25

    Das ist bewusst das erste Datum, weil das normalerweise das Prospektdatum ist.
    """
    match = DATE_PATTERN.search(name)

    if not match:
        return None

    raw_date = match.group(1)

    try:
        return datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return None


def unique_target_path(target_path: Path) -> Path:
    """
    Verhindert Überschreiben, falls ein Archivziel schon existiert.
    """
    if not target_path.exists():
        return target_path

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = target_path.with_name(f"{target_path.stem}_archiviert_{stamp}{target_path.suffix}")

    if not base.exists():
        return base

    counter = 1
    while True:
        candidate = target_path.with_name(
            f"{target_path.stem}_archiviert_{stamp}_{counter}{target_path.suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


# ------------------------------------------------------------
# Images archivieren
# ------------------------------------------------------------

def archive_latest_images(dry_run: bool = False) -> None:
    """
    Verschiebt die aktuellen PNG-Ordner aus latest_images/ nach Archiv_images/.

    Beispiel:
    latest_images/lidl_2026-06-25/
    → Archiv_images/lidl_2026-06-25/
    """
    if not LATEST_IMAGES_DIR.exists():
        print(f"Kein Ordner vorhanden: {LATEST_IMAGES_DIR}")
        return

    ARCHIVE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    entries = sorted(LATEST_IMAGES_DIR.iterdir())

    if not entries:
        print(f"Keine Images zum Archivieren in: {LATEST_IMAGES_DIR}")
        return

    print("Archiviere latest_images/...")

    for entry in entries:
        target = ARCHIVE_IMAGES_DIR / entry.name
        target = unique_target_path(target)

        if dry_run:
            print(f"[DRY RUN] Würde verschieben: {entry} → {target}")
            continue

        shutil.move(str(entry), str(target))
        print(f"Archiviert: {entry} → {target}")

    # latest_images bleibt als leerer Ordner bestehen
    LATEST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# Archiv bereinigen
# ------------------------------------------------------------

def remove_path(path: Path, dry_run: bool = False) -> None:
    """
    Löscht Datei oder Ordner.
    """
    if dry_run:
        print(f"[DRY RUN] Würde löschen: {path}")
        return

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()

    print(f"Gelöscht: {path}")


def cleanup_archive_dir(archive_dir: Path, cutoff_date: date, dry_run: bool = False) -> None:
    """
    Löscht Einträge aus einem Archivordner, wenn ihr erstes Datum im Namen
    älter als cutoff_date ist.

    Es werden nur Top-Level-Einträge geprüft.
    Bei Archiv_images/ werden also ganze Prospektordner gelöscht,
    nicht einzelne page_001.png-Dateien.
    """
    if not archive_dir.exists():
        print(f"Archivordner nicht vorhanden, wird erstellt: {archive_dir}")

        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)

        return

    print(f"Prüfe Archivordner: {archive_dir}")

    for entry in sorted(archive_dir.iterdir()):
        entry_date = extract_first_date_from_name(entry.name)

        if entry_date is None:
            print(f"Übersprungen, kein Datum im Namen gefunden: {entry}")
            continue

        if entry_date < cutoff_date:
            remove_path(entry, dry_run=dry_run)
        else:
            print(f"Behalten: {entry} ({entry_date})")


def cleanup_all_archives(dry_run: bool = False) -> None:
    """
    Bereinigt alle Archivordner anhand der 6-Monats-Regel.
    """
    current_date = today_local()
    cutoff_date = subtract_months(current_date, RETENTION_MONTHS)

    print("Archiv-Bereinigung")
    print(f"Aktuelles Datum: {current_date}")
    print(f"Behalte Dateien ab: {cutoff_date}")
    print(f"Lösche Dateien mit Datum vor: {cutoff_date}")
    print()

    for archive_dir in ARCHIVE_DIRS:
        cleanup_archive_dir(
            archive_dir=archive_dir,
            cutoff_date=cutoff_date,
            dry_run=dry_run
        )
        print()


# ------------------------------------------------------------
# Hauptprogramm
# ------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archiviert latest_images und löscht Archivdaten älter als 6 Monate."
    )

    parser.add_argument(
        "--archive-images",
        action="store_true",
        help="Archiviert nur latest_images nach Archiv_images."
    )

    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Bereinigt nur die Archivordner."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeigt nur an, was passieren würde, ohne Dateien zu ändern."
    )

    args = parser.parse_args()

    if args.archive_images and args.cleanup_only:
        print("Fehler: --archive-images und --cleanup-only können nicht gleichzeitig verwendet werden.")
        return 1

    if args.archive_images:
        archive_latest_images(dry_run=args.dry_run)
        return 0

    if args.cleanup_only:
        cleanup_all_archives(dry_run=args.dry_run)
        return 0

    # Standardmodus, falls man das Skript manuell ohne Parameter startet:
    # erst Images archivieren, dann Archive bereinigen.
    archive_latest_images(dry_run=args.dry_run)
    print()
    cleanup_all_archives(dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())