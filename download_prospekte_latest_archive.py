#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from playwright.sync_api import sync_playwright


LATEST_DIR = Path("latest")
LIDL_REGION_ID = 31
LIDL_OVERVIEW_URL = "https://www.lidl.de/c/online-prospekte/s10005610"
LIDL_API_URL = "https://endpoints.leaflets.schwarz/v4/flyer"

ALDI_HOME_URL = "https://www.aldi-sued.de/"

EDEKA_IFRAME_URL = "https://blaetterkatalog.edeka.de/NORDBAYERN/EDEKA_CENTER_STENGEL_MFRANKEN_WEST/index.html"
EDEKA_PDF_URL = "https://blaetterkatalog.edeka.de/NORDBAYERN/EDEKA_CENTER_STENGEL_MFRANKEN_WEST/blaetterkatalog/pdf/complete.pdf"

NETTO_STORE_ID = "8361"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def today_string() -> str:
    return date.today().isoformat()


def clear_latest_pdfs() -> None:
    """
    Löscht bestehende PDFs aus latest, ohne sie zu archivieren.
    Dadurch enthält latest während des Laufs nur die neu heruntergeladenen Prospekte.
    Die Roh-PDFs werden später im Workflow nicht mehr ins Repository aufgenommen.
    """
    LATEST_DIR.mkdir(exist_ok=True)

    pdf_files = sorted(LATEST_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"Keine alten PDFs zum Löschen in: {LATEST_DIR}")
        return

    for path in pdf_files:
        path.unlink()
        print(f"Alte PDF gelöscht: {path}")


def output_file(store_name: str) -> Path:
    return LATEST_DIR / f"{store_name}_{today_string()}.pdf"


def request_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.text


def decode_url(value: str, base_url: str = "") -> str:
    value = html.unescape(value)
    try:
        value = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        value = value.replace("\\/", "/").replace("\\u002F", "/").replace("\\u0026", "&")
    return urljoin(base_url, value)


def download_pdf(url: str, output_path: Path, referer: str | None = None) -> None:
    headers = {**HEADERS, "Accept": "application/pdf,*/*"}
    if referer:
        headers["Referer"] = referer

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, headers=headers, stream=True, timeout=180) as response:
        response.raise_for_status()

        with output_path.open("wb") as file:
            first_chunk = True
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                if first_chunk and not chunk[:50].lstrip().startswith(b"%PDF"):
                    raise RuntimeError(f"Keine PDF-Antwort: {url}")

                first_chunk = False
                file.write(chunk)

    print(f"Gespeichert: {output_path.resolve()}")


def accept_cookies(page) -> None:
    for pattern in [r"alle akzeptieren", r"akzeptieren", r"zustimmen", r"einverstanden"]:
        try:
            button = page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE))
            if button.count() > 0:
                button.first.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass


def extract_publitas_pdf_url_from_html(page_html: str, base_url: str) -> str:
    patterns = [
        r'"downloadPdfUrl"\s*:\s*"([^"]+)"',
        r'id=["\']downloadAsPdf["\'][^>]+href=["\']([^"\']+\.pdf[^"\']*)["\']',
        r'href=["\']([^"\']+\.pdf[^"\']*)["\'][^>]+id=["\']downloadAsPdf["\']',
        r'data-href=["\']download_pdf["\'][^>]+href=["\']([^"\']+\.pdf[^"\']*)["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, page_html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return decode_url(match.group(1), base_url)

    raise RuntimeError("Keine PDF-URL im Publitas-HTML gefunden.")


def extract_publitas_pdf_url(viewer_url: str) -> str:
    return extract_publitas_pdf_url_from_html(request_text(viewer_url), viewer_url)


def find_lidl_pdf_url() -> tuple[str, str]:
    page_html = request_text(LIDL_OVERVIEW_URL)

    match = re.search(
        r"/l/prospekte/(aktionsprospekt-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}-\d{4}-[A-Za-z0-9]+)",
        page_html,
    )
    if not match:
        raise RuntimeError("Lidl: Kein aktueller Aktionsprospekt gefunden.")

    flyer_identifier = match.group(1)
    viewer_url = f"https://www.lidl.de/l/prospekte/{flyer_identifier}"

    response = requests.get(
        LIDL_API_URL,
        params={
            "flyer_identifier": flyer_identifier,
            "region_id": LIDL_REGION_ID,
            "region_code": LIDL_REGION_ID,
        },
        headers={
            **HEADERS,
            "Accept": "application/json,text/plain,*/*",
            "Origin": "https://www.lidl.de",
            "Referer": "https://www.lidl.de/",
        },
        timeout=45,
    )
    response.raise_for_status()

    flyer = response.json().get("flyer", {})
    pdf_url = flyer.get("hiResPdfUrl") or flyer.get("pdfUrl")
    if not pdf_url:
        raise RuntimeError("Lidl: Keine PDF-URL in der API-Antwort gefunden.")

    return pdf_url, viewer_url


def find_aldi_viewer_url(page) -> str:
    page.goto(ALDI_HOME_URL, wait_until="domcontentloaded", timeout=60000)
    accept_cookies(page)
    page.wait_for_selector('a[href*="prospekt.aldi-sued.de"]', state="attached", timeout=30000)

    links = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href*="prospekt.aldi-sued.de"]'))
          .map(a => ({
            href: a.href,
            text: (a.innerText || '').trim(),
            aria: a.getAttribute('aria-label') || '',
            outer: a.outerHTML || ''
          }))
        """
    )

    for link in links:
        text = f"{link['text']} {link['aria']} {link['outer']}".lower()
        if "prospekt der aktuellen woche" in text:
            return re.sub(r"/page/\d+$", "", link["href"].rstrip("/"))

    for link in links:
        if re.search(r"/kw\d{2}-\d{2}-op-mp(?:/|$)", link["href"]):
            return re.sub(r"/page/\d+$", "", link["href"].rstrip("/"))

    raise RuntimeError("ALDI: Aktueller Prospekt-Link nicht gefunden.")


def netto_viewer_candidates() -> list[str]:
    """
    Netto blockiert die Übersichtsseite automatisiert.
    Der Filialprospekt nutzt aktuell den Wochen-Slug hz{KW}_kisa.
    """
    _, week, _ = date.today().isocalendar()

    candidates = []
    for kw in [week, week + 1, week - 1]:
        if 1 <= kw <= 53:
            candidates.append(
                f"https://wochenprospekt.netto-online.de/hz{kw:02d}_kisa/page/1?storeid={NETTO_STORE_ID}"
            )

    return candidates


def find_netto_pdf_url() -> tuple[str, str]:
    last_error = None

    for viewer_url in netto_viewer_candidates():
        try:
            page_html = request_text(viewer_url)
            pdf_url = extract_publitas_pdf_url_from_html(page_html, viewer_url)
            return pdf_url, viewer_url
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Netto: Kein gültiger Wochenprospekt gefunden. Letzter Fehler: {last_error}")


def main() -> int:
    LATEST_DIR.mkdir(exist_ok=True)

    clear_latest_pdfs()

    errors: list[str] = []

    try:
        print("Lidl ...")
        pdf_url, referer = find_lidl_pdf_url()
        download_pdf(pdf_url, output_file("lidl"), referer)
    except Exception as exc:
        errors.append(f"Lidl fehlgeschlagen: {exc}")

    try:
        print("EDEKA ...")
        download_pdf(EDEKA_PDF_URL, output_file("edeka_fuerth"), EDEKA_IFRAME_URL)
    except Exception as exc:
        errors.append(f"EDEKA fehlgeschlagen: {exc}")

    try:
        print("Netto ...")
        pdf_url, referer = find_netto_pdf_url()
        download_pdf(pdf_url, output_file("netto_fuerth"), referer)
    except Exception as exc:
        errors.append(f"Netto fehlgeschlagen: {exc}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="de-DE",
            viewport={"width": 1365, "height": 900},
            user_agent=HEADERS["User-Agent"],
        )
        page = context.new_page()

        try:
            print("ALDI ...")
            viewer_url = find_aldi_viewer_url(page)
            pdf_url = extract_publitas_pdf_url(viewer_url + "/page/1")
            download_pdf(pdf_url, output_file("aldi_sued"), viewer_url)
        except Exception as exc:
            errors.append(f"ALDI fehlgeschlagen: {exc}")

        browser.close()

    if errors:
        print("\nFehler:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nFertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
