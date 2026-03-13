"""Scrape Corsica Ferries prices using Playwright and append to CSV."""

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = (
    "https://www.corsica-ferries.de/resa/leistungen/"
    "?c=rBvbmBryhLlChChUllnhBchQnsJeClJlJlJlJnossendmScdfvc3ynnrynTmBryrBvbhLlLlLh3lnjnjnjndmSnnjn"
)

CSV_PATH = Path(__file__).parent / "data" / "prices.csv"
DEBUG_DIR = Path(__file__).parent / "debug"


def fetch_page() -> str:
    """Fetch the booking page HTML using a headless browser."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # Give JS time to render
            page.wait_for_timeout(5000)

            # Dismiss cookie consent if present
            try:
                accept_btn = page.locator("text=ICH AKZEPTIERE").first
                accept_btn.click(timeout=5000)
                print("Cookie consent dismissed.")
                page.wait_for_timeout(3000)
            except Exception:
                print("No cookie consent dialog found (or already dismissed).")

            # Wait for tariff section
            page.wait_for_selector("text=Standard Tarif", timeout=30000)

            html = page.content()
        except Exception:
            # Save debug artifacts on any failure
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(DEBUG_DIR / "page.png"), full_page=True)
                (DEBUG_DIR / "page.html").write_text(page.content(), encoding="utf-8")
                print("DEBUG: saved screenshot and HTML to debug/", file=sys.stderr)
            except Exception:
                print("DEBUG: could not save debug artifacts", file=sys.stderr)
            browser.close()
            raise

        browser.close()
    return html


def parse_prices(html: str) -> dict:
    """Extract tariff prices and total from the HTML."""
    prices = {}

    # Standard / Flex tariffs — two occurrences each: Hinreise then Rückreise
    standard_matches = re.findall(r"Standard\s+Tarif\s*([\d.,]+)\s*€", html)
    flex_matches = re.findall(r"Flexibler\s+Tarif\s*([\d.,]+)\s*€", html)

    if len(standard_matches) >= 2:
        prices["outbound_standard"] = standard_matches[0].replace(".", "").replace(",", ".")
        prices["return_standard"] = standard_matches[1].replace(".", "").replace(",", ".")
    if len(flex_matches) >= 2:
        prices["outbound_flex"] = flex_matches[0].replace(".", "").replace(",", ".")
        prices["return_flex"] = flex_matches[1].replace(".", "").replace(",", ".")

    # Total reservation price
    total_match = re.search(r"Ihre\s+Reservierung\s*([\d.,]+)\s*€", html)
    if total_match:
        prices["total"] = total_match.group(1).replace(".", "").replace(",", ".")

    return prices


def append_to_csv(prices: dict) -> None:
    """Append a row with timestamp and prices to the CSV file."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp",
        "outbound_standard",
        "outbound_flex",
        "return_standard",
        "return_flex",
        "total",
    ]

    write_header = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0

    with CSV_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        row = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        row.update(prices)
        writer.writerow(row)


def main() -> int:
    html = fetch_page()
    prices = parse_prices(html)

    if not prices:
        print("ERROR: Could not parse any prices from the page.", file=sys.stderr)
        return 1

    append_to_csv(prices)

    print(f"Recorded at {datetime.now(timezone.utc).isoformat(timespec='seconds')}:")
    for key, val in prices.items():
        print(f"  {key}: {val} EUR")

    return 0


if __name__ == "__main__":
    sys.exit(main())
