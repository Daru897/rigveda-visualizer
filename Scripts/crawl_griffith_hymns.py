#!/usr/bin/env python3
"""
Hymn-level crawler for Griffith's Rig Veda on sacred-texts.com

What it does:
- For mandala in 1..10:
    - For hymn_num starting at 1, attempts to download page at:
      https://www.sacred-texts.com/hin/rigveda/rv{MM}{NNN:03d}.htm
      where MM is mandala with 2 digits, NNN is hymn number with 3 digits.
    - Stops when it sees `max_consecutive_misses` consecutive missing pages.
- Saves files to data/raw/griffith/mandala_{M}/hymn_{NNN}.html
- Writes a manifest file data/raw/griffith/manifest.json

Notes:
- You can tweak MAX_HYMN_TRY to limit search (e.g., to 200).
- Uses polite delay between requests and basic retry on transient HTTP errors.
"""

import os
import time
import json
import requests
from pathlib import Path

BASE_URL_TEMPLATE = "https://www.sacred-texts.com/hin/rigveda/rv{mandala:02d}{hymn:03d}.htm"

# Config
MANDALA_START = 1
MANDALA_END = 10
MAX_HYMN_TRY = 400            # upper bound to attempt per mandala (failsafe)
MAX_CONSECUTIVE_MISSES = 5    # stop for this mandala after this many consecutive 404s
REQUEST_DELAY = 0.8           # seconds between requests (polite)
RETRY_ON_ERROR = 2            # retries for transient status codes (e.g., 500), with backoff
TIMEOUT = 20                  # request timeout
OUTPUT_BASE = Path("Data/Raw/griffith")

HEADERS = {
    "User-Agent": "RigVedaCrawler/1.0 (+https://github.com/your-username/rigveda-visualizer) Python/requests"
}

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def save_html(path: Path, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def is_page_valid(content: str) -> bool:
    """
    Basic heuristic to detect whether a downloaded page is actually a hymn page.
    We check that it contains 'The Rig Veda' or 'Ralph T.H. Griffith' or 'Rig-Veda Book' etc.
    This avoids saving generic 404 pages that sometimes return 200.
    """
    text = content.lower()
    checks = ["the rig veda", "ralph t.h. griffith", "rig-veda", "rig veda", "hymn"]
    return any(ch in text for ch in checks)

def fetch_url(url: str):
    tries = 0
    while True:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            return r
        except requests.RequestException as ex:
            tries += 1
            if tries > RETRY_ON_ERROR:
                print(f"[ERROR] Failed to fetch {url} after {tries} tries: {ex}")
                return None
            backoff = 1.0 * tries
            print(f"[WARN] transient error fetching {url}: {ex}. retrying in {backoff}s...")
            time.sleep(backoff)

def crawl():
    ensure_dir(OUTPUT_BASE)
    manifest = []

    for mandala in range(MANDALA_START, MANDALA_END + 1):
        mandala_dir = OUTPUT_BASE / f"mandala_{mandala:02d}"
        ensure_dir(mandala_dir)
        print(f"\n=== Mandala {mandala} -> saving to {mandala_dir} ===")

        consecutive_misses = 0
        hymns_found = 0

        for hymn in range(1, MAX_HYMN_TRY + 1):
            url = BASE_URL_TEMPLATE.format(mandala=mandala, hymn=hymn)
            print(f"Fetching {url} ...", end=" ")
            r = fetch_url(url)
            if r is None:
                print("failed (no response).")
                # treat as miss but continue
                consecutive_misses += 1
            else:
                status = r.status_code
                if status == 200:
                    content = r.text
                    # some servers return a generic 200 page for missing pages; ensure content looks valid
                    if not is_page_valid(content):
                        print("received 200 but content doesn't look like a hymn page -> mark miss")
                        consecutive_misses += 1
                    else:
                        # Save
                        fname = mandala_dir / f"hymn_{hymn:03d}.html"
                        save_html(fname, content)
                        manifest.append({
                            "mandala": mandala,
                            "hymn": hymn,
                            "url": url,
                            "path": str(fname.as_posix())
                        })
                        hymns_found += 1
                        consecutive_misses = 0
                        print(f"saved ({hymns_found} found so far).")
                elif status in (403, 404):
                    print(f"{status} -> missing")
                    consecutive_misses += 1
                else:
                    print(f"{status} -> unexpected status, treating as miss")
                    consecutive_misses += 1

            # Polite throttle
            time.sleep(REQUEST_DELAY)

            # Break condition: after N consecutive misses assume the hymn list ended
            if consecutive_misses >= MAX_CONSECUTIVE_MISSES:
                print(f"Stopped Mandala {mandala}: {consecutive_misses} consecutive misses (assumed end).")
                break

        print(f"Mandala {mandala} completed: {hymns_found} hymn pages saved.")
    # Save manifest
    manifest_path = OUTPUT_BASE / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)
    print(f"\nCrawl finished. Manifest saved to {manifest_path}. Total pages saved: {len(manifest)}")

if __name__ == "__main__":
    crawl()
