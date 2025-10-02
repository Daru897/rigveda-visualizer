#!/usr/bin/env python3
"""
Parse Griffith hymn-level HTML files saved under:
  data/raw/griffith/mandala_{MM}/hymn_{NNN}.html

Build a mapping: (mandala, sukta, verse) -> concatenated English translation text,
then merge into transliteration JSONL (data/rigveda_translit.jsonl) producing:
  data/rigveda_merged.jsonl

This parser is conservative: it looks for numeric verse markers like "1.1.1" (with optional
letter suffixes), groups subparts (a/b/c), and concatenates them in order. It also attempts
a couple of fallback heuristics for pages where verse IDs are absent but the page appears to
contain a single hymn — in that case it tries to infer mandala/hymn from the filename and
assign translation text to verses by splitting on line breaks (best-effort).
"""

import re
import json
import os
from pathlib import Path
from bs4 import BeautifulSoup
from collections import defaultdict

# === CONFIG: adjust if necessary ===
GRIFFITH_FOLDER = Path("Data/Raw/Griffith")
TRANSLIT_JSONL = Path("Data/rigveda_translit.jsonl")
OUTPUT_JSONL = Path("Data/rigveda_merged.jsonl")

# Match verse markers like "1.1.1" or "1.1.1a"
VERSE_ID_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)([a-z]?)', flags=re.IGNORECASE)

# Heuristics: if a hymn page has no verse ids, we'll try to split by line/numbering.
FALLBACK_SPLIT_RE = re.compile(r'(?:\d+\.\d+\.\d+)', flags=re.IGNORECASE)

def ensure_out_dirs():
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

def list_hymn_files(base_folder: Path):
    """Yield paths of hymn files like .../mandala_01/hymn_001.html"""
    for mandala_dir in sorted(base_folder.glob("mandala_*")):
        for hymn_file in sorted(mandala_dir.glob("hymn_*.html")):
            yield mandala_dir, hymn_file

def read_html(path: Path):
    return path.read_text(encoding="utf-8", errors="ignore")

def text_blocks_from_html(html: str):
    """Return list of cleaned 'blocks' from page text (split on double newlines)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    # Normalize whitespace and split into blocks separated by blank lines
    lines = [ln.rstrip() for ln in text.splitlines()]
    blocks = []
    buf = []
    for ln in lines:
        if ln.strip() == "":
            if buf:
                blocks.append(" ".join(buf).strip())
                buf = []
        else:
            buf.append(ln.strip())
    if buf:
        blocks.append(" ".join(buf).strip())
    return blocks

def extract_from_blocks(blocks, filename_key=None):
    """
    Extract mapping from blocks. Returns dict: key=(mandala,sukta,verse) -> list of (suffix, segment, order)
    If blocks contain explicit verse ids, we use them. Otherwise returns {} (so caller may use fallback).
    """
    mapping = defaultdict(list)
    for b_idx, block in enumerate(blocks):
        matches = list(VERSE_ID_RE.finditer(block))
        if not matches:
            continue
        for i, m in enumerate(matches):
            mandala = int(m.group(1))
            sukta = int(m.group(2))
            verse_num = int(m.group(3))
            suffix = m.group(4) or ""
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(block)
            segment = block[start:end]
            segment = segment.replace('\u00A0', ' ').replace('||', ' ').replace('|', ' ')
            segment = re.sub(r'\s+', ' ', segment).strip()
            key = (mandala, sukta, verse_num)
            mapping[key].append((suffix, segment, b_idx))
    return mapping

def fallback_extract_single_page(blocks, mandala_num, hymn_num):
    """
    If a hymn page lacked explicit verse ids, try a fallback:
    - join all blocks, split on sentence/line endings and assign sequential verse numbers starting at 1
    Note: this is approximate and should be used only as last resort.
    """
    joined = " || ".join(blocks)
    # Try to split on '|' or double space or punctuation
    parts = [p.strip() for p in re.split(r'\s*\|\s*|\s{2,}|\.(?=\s+[A-Z])', joined) if p.strip()]
    mapping = {}
    for idx, part in enumerate(parts, start=1):
        key = (mandala_num, hymn_num, idx)
        mapping.setdefault(key, []).append(("", part, 0))
    return mapping

def build_translations_map():
    """
    Walk hymn HTML files, extract verse segments and return translations_map:
      (mandala,sukta,verse) -> concatenated translation string
    """
    map_accum = defaultdict(list)
    found_files = 0
    for mandala_dir, hymn_file in list_hymn_files(GRIFFITH_FOLDER):
        found_files += 1
        html = read_html(hymn_file)
        blocks = text_blocks_from_html(html)
        extracted = extract_from_blocks(blocks, filename_key=hymn_file)
        if extracted:
            # extend into accumulator
            for key, segs in extracted.items():
                map_accum[key].extend(segs)
        else:
            # fallback: try to infer mandala,hymn from path name: mandala_01/hymn_001.html
            m_m = re.search(r"mandala_(\d+)", str(mandala_dir.name))
            m_h = re.search(r"hymn_(\d+)", hymn_file.name)
            if m_m and m_h:
                mandala_num = int(m_m.group(1))
                hymn_num = int(m_h.group(1))
                fb = fallback_extract_single_page(blocks, mandala_num, hymn_num)
                for key, segs in fb.items():
                    map_accum[key].extend(segs)
            else:
                # skip if we can't parse filenames
                continue

    # Now process accumulated segments: sort and concatenate per key
    translations_map = {}
    for key, segs in map_accum.items():
        # sort by block index and suffix ('' < 'a' < 'b')
        segs_sorted = sorted(segs, key=lambda x: (x[2], (x[0] if x[0] != "" else " ")))
        concatenated = " ".join([s[1] for s in segs_sorted if s[1]])
        translations_map[key] = concatenated

    print(f"Processed {found_files} hymn files; extracted translations for {len(translations_map)} verse keys.")
    return translations_map

def load_translit_entries(path: Path):
    entries = []
    if not path.exists():
        raise FileNotFoundError(f"Transliteration JSONL not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entries.append(json.loads(line))
    return entries

def merge_and_save(translit_entries, translations_map, out_path: Path):
    missing = 0
    for e in translit_entries:
        key = (e["mandala"], e["sukta"], e["verse"])
        if key in translations_map:
            e["translation"] = translations_map[key]
        else:
            e["translation"] = ""
            missing += 1
    print(f"Merging done. Missing translations for {missing} transliteration entries.")
    # Save JSONL
    ensure_out_dirs()
    with out_path.open("w", encoding="utf-8") as f:
        for e in translit_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Saved merged file to {out_path} (total entries: {len(translit_entries)})")

if __name__ == "__main__":
    print("Building Griffith translations map from folder:", GRIFFITH_FOLDER)
    translations_map = build_translations_map()

    print("Loading transliteration entries from:", TRANSLIT_JSONL)
    translit_entries = load_translit_entries(TRANSLIT_JSONL)

    print("Merging translations...")
    merge_and_save(translit_entries, translations_map, OUTPUT_JSONL)
    print("All done.")
