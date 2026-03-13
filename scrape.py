"""Scrape Corsica Ferries prices and append to CSV."""

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = (
    "https://www.corsica-ferries.de/resa/leistungen/"
    "?c=rBvbmBryhLlChChUllnhBchQnsJeClJlJlJlJnossendmScdfvc3ynnrynTmBryrBvbhLlLlLh3lnjnjnjndmSnnjn"
)

CSV_PATH = Path(__file__).parent / "data" / "prices.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def fetch_page() -> str:
    """Fetch the booking page HTML."""
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_prices(html: str) -> dict:
    """Extract tariff prices and total from the HTML."""
    prices = {}

    # Standard / Flex tariffs — pattern: "Standard Tarif376,00 €" or "Flexibler Tarif425,00 €"
    # The page has two occurrences of each: first for Hinreise, second for Rückreise.
    standard_matches = re.findall(r"Standard\s+Tarif\s*([\d.,]+)\s*€", html)
    flex_matches = re.findall(r"Flexibler\s+Tarif\s*([\d.,]+)\s*€", html)

    if len(standard_matches) >= 2:
        prices["outbound_standard"] = standard_matches[0].replace(".", "").replace(",", ".")
        prices["return_standard"] = standard_matches[1].replace(".", "").replace(",", ".")
    if len(flex_matches) >= 2:
        prices["outbound_flex"] = flex_matches[0].replace(".", "").replace(",", ".")
        prices["return_flex"] = flex_matches[1].replace(".", "").replace(",", ".")

    # Total reservation price — pattern: "Ihre Reservierung899,00 €"
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
        print(f"  {key}: {val} €")

    return 0


if __name__ == "__main__":
    sys.exit(main())
