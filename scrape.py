"""Scrape Corsica Ferries prices using Playwright and append to CSV."""

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

URL = (
    "https://www.corsica-ferries.de/resa/leistungen/"
    "?c=rBvbmBryhLlChChUllnhBchQnsJeClJlJlJlJnossendmScdfvc3ynnrynTmBryrBvbhLlLlLh3lnjnjnjndmSnnjn"
)

CSV_PATH = Path(__file__).parent / "data" / "prices.csv"
DEBUG_DIR = Path(__file__).parent / "debug"

# Cloudflare challenge page titles (both languages)
CF_CHALLENGE_TITLES = {"just a moment", "nur einen moment"}


def _is_challenge_page(title: str) -> bool:
    """Return True if the page title indicates a Cloudflare challenge."""
    t = title.lower().rstrip("….\u2026 ")
    return any(t.startswith(cf) for cf in CF_CHALLENGE_TITLES)


def fetch_page() -> str:
    """Fetch the booking page HTML using a stealth headless browser."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()
        # Apply playwright-stealth patches (webdriver, plugins, webgl, etc.)
        stealth_sync(page)

        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            print("Navigating to page...")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # Wait for Cloudflare challenge to auto-resolve
            # Poll for up to 90 seconds checking if we've left the challenge page
            for i in range(18):
                page.wait_for_timeout(5000)
                title = page.title()
                print(f"  [{(i+1)*5}s] Page title: {title}")

                if not _is_challenge_page(title):
                    print("Cloudflare challenge passed!")
                    break
            else:
                page.screenshot(path=str(DEBUG_DIR / "page_cf_stuck.png"), full_page=True)
                (DEBUG_DIR / "page.html").write_text(page.content(), encoding="utf-8")
                browser.close()
                raise RuntimeError("Cloudflare challenge did not resolve within 90s")

            # Now on the real page — wait for content to render
            page.wait_for_timeout(3000)

            # Handle cookie consent
            try:
                accept_btn = page.locator("text=ICH AKZEPTIERE").first
                accept_btn.click(timeout=5000)
                print("Cookie consent dismissed.")
                page.wait_for_timeout(2000)
            except Exception:
                print("No cookie consent dialog (or already dismissed).")

            # Save debug artifacts
            page.screenshot(path=str(DEBUG_DIR / "page_final.png"), full_page=True)
            html = page.content()
            (DEBUG_DIR / "page.html").write_text(html, encoding="utf-8")

            if "Tarif" not in html:
                print("WARNING: 'Tarif' not found in page HTML", file=sys.stderr)
                browser.close()
                raise RuntimeError("Price data not found on page")

        except Exception:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(DEBUG_DIR / "page_error.png"), full_page=True)
                (DEBUG_DIR / "page.html").write_text(page.content(), encoding="utf-8")
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
