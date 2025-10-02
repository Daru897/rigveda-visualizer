#!/usr/bin/env python3
"""
Parse Griffith translation HTML and align translations to transliteration entries.

Steps:
1. Read Griffith HTML (local file or fetch from a URL).
2. Extract verse segments using verse-id regex like "1.1.1" (handles optional suffixes like a/b/c).
3. Build a mapping: (mandala, sukta, verse) -> concatenated translation text.
4. Read transliteration JSONL produced earlier and inject the 'translation' field by key.
5. Write merged JSONL.

Adjust INPUT paths at the top to match your repo layout.
"""

import re
import json
import os
from bs4 import BeautifulSoup
from collections import defaultdict
import requests

# === CONFIG ===
# Path to the previously-generated transliteration JSONL (output of parse_translit_html_refined.py)
TRANSLIT_JSONL = "../Data/rigveda_translit.jsonl"

# Local Griffith HTML (if you've downloaded), else set GRIFFITH_HTML = None and GRIFFITH_URL will be used.
GRIFFITH_HTML = "../Data/Raw/griffith_full.html"   # adjust if local file name differs; set to None to fetch URL
GRIFFITH_URL = "https://www.sacred-texts.com/hin/rigveda/rv01001.htm"  # Example: Book 1 Hymn 1 page (site uses one-hymn-per-page)
# Note: sacred-texts often spreads hymns over many pages. If you have a combined HTML, use that path.

# Output merged JSONL
OUTPUT_JSONL = "../Data/rigveda_merged.jsonl"

# Verse ID regex: matches 1.1.1 or 1.1.1a etc. (captures optional suffix letter)
VERSE_ID_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)([a-z]?)')

# Heuristic patterns sometimes used in Griffith pages:
# - Numbers like "1.1.1." at start of line
# - Scenes where the hymn title lines appear; we ignore those and only capture lines following verse ids.

def load_html(local_path=None, url=None):
    if local_path and os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            return f.read()
    elif url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    else:
        raise ValueError("Provide either local_path or url for Griffith HTML")

def extract_translations_from_html(html_text):
    """
    Returns dict: (mandala,sukta,verse) -> concatenated translation text
    """
    soup = BeautifulSoup(html_text, "html.parser")
    # Get body text with line breaks
    text = soup.get_text("\n")
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Combine into blocks separated by blank lines (common structure)
    blocks = []
    buffer = []
    for ln in lines:
        if ln.strip() == "":
            if buffer:
                blocks.append(" ".join(buffer))
                buffer = []
        else:
            buffer.append(ln.strip())
    if buffer:
        blocks.append(" ".join(buffer))

    # Find all verse-id occurrences inside blocks and build mapping
    mapping = defaultdict(list)  # key -> list of (suffix, segment_text, block_idx)

    for b_idx, block in enumerate(blocks):
        # find all verse-id matches and spans
        matches = list(VERSE_ID_RE.finditer(block))
        if not matches:
            # Some Griffith pages label verses like "I." etc. Or the page might be a single hymn without numeric verse markers.
            # Try a fallback: sometimes lines start with "1." or "1." alone -> not robust. Skip block if no numeric markers.
            continue

        for i, m in enumerate(matches):
            mandala = int(m.group(1))
            sukta = int(m.group(2))
            verse_num = int(m.group(3))
            suffix = m.group(4) or ""
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(block)
            segment = block[start:end]
            # clean segment
            seg = segment.replace('\u00A0', ' ')
            seg = seg.replace('||', ' ').replace('|', ' ')
            seg = re.sub(r'\s+', ' ', seg).strip()
            key = (mandala, sukta, verse_num)
            mapping[key].append((suffix, seg, b_idx))

    # Concatenate segments per key in sensible order
    translations = {}
    for key, segs in mapping.items():
        segs_sorted = sorted(segs, key=lambda x: (x[2], (x[0] if x[0] != "" else " ")))
        text_concat = " ".join([s[1] for s in segs_sorted if s[1]])
        translations[key] = text_concat

    return translations

def load_translit_entries(translit_jsonl_path):
    entries = []
    with open(translit_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            entries.append(obj)
    return entries

def merge_translations(translit_entries, translations_map):
    merged = []
    missing = 0
    for e in translit_entries:
        key = (e["mandala"], e["sukta"], e["verse"])
        # try exact match
        if key in translations_map:
            e["translation"] = translations_map[key]
        else:
            # try forgiving fallback: sometimes Griffith numbering differs on sukta/verse split.
            # We'll assign empty string but record missing count.
            e["translation"] = ""
            missing += 1
        merged.append(e)
    return merged, missing

def save_jsonl(entries, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Saved {len(entries)} merged entries to {out_path}")

if __name__ == "__main__":
    print("Loading Griffith HTML...")
    html = None
    try:
        html = load_html(local_path=GRIFFITH_HTML, url=None if GRIFFITH_HTML else GRIFFITH_URL)
    except Exception as ex:
        print("Failed to load local HTML; attempting to fetch from URL...", ex)
        html = load_html(local_path=None, url=GRIFFITH_URL)

    print("Extracting translations...")
    translations_map = extract_translations_from_html(html)
    print("Translations extracted for keys:", len(translations_map))

    print("Loading transliteration entries...")
    translit_entries = load_translit_entries(TRANSLIT_JSONL)
    print("Transliteration entries:", len(translit_entries))

    print("Merging translations into transliteration entries...")
    merged_entries, missing = merge_translations(translit_entries, translations_map)
    print(f"Merged. Missing translations for {missing} transliteration entries (they will have empty 'translation').")

    save_jsonl(merged_entries, OUTPUT_JSONL)
    print("Done.")
