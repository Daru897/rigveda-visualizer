#!/usr/bin/env python3
"""
Refined parser for Detlef Eichler transliteration HTML.
Handles sub-verse markers like 1.1.1a / 1.1.1b / 1.1.1c and groups them into a single entry
for base verse 1.1.1 (concatenating subparts in suffix order).
Outputs JSON Lines file with fields:
{
  "mandala": int,
  "sukta": int,
  "verse": int,
  "deity": "",
  "sanskrit": "",
  "transliteration": "full concatenated text",
  "translation": ""
}
"""

import re
import json
import os
from bs4 import BeautifulSoup
from collections import defaultdict, OrderedDict

INPUT_HTML = "../Data/Raw/samhita_translit_full.html"   # adjust if different
OUTPUT_JSON = "../Data/rigveda_translit.jsonl"          # JSON Lines (one JSON per line)

# Match verse markers like "1.1.1", "1.1.1a", optionally surrounded by pipes or || markers.
# Capture mandala, sukta, verse, optional letter suffix.
VERSE_ID_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)([a-z]?)')

def clean_segment_text(s):
    # Basic cleaning: replace NBSP, collapse whitespace, remove leftover pipe markers
    s = s.replace('\u00A0', ' ')
    s = s.replace('||', ' ').replace('|', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def parse_html_grouping(input_path):
    with open(input_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    text = soup.get_text("\n")
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Combine lines into blocks separated by blank lines (retain original ordering)
    blocks = []
    buffer = []
    for ln in lines:
        if ln.strip() == "":
            if buffer:
                blocks.append(" ".join(buffer))
                buffer = []
        else:
            buffer.append(ln)
    if buffer:
        blocks.append(" ".join(buffer))

    # We'll accumulate segments per base verse key (mandala,sukta,verse)
    grouped = defaultdict(list)  # key -> list of (suffix, segment_text, orig_order_index)

    for b_idx, block in enumerate(blocks):
        # find all verse-id matches and their spans in this block
        matches = list(VERSE_ID_RE.finditer(block))
        if not matches:
            # no markers: skip or optionally log
            continue

        # If there's only one marker and no following markers, the segment is rest of block
        for i, m in enumerate(matches):
            mandala = int(m.group(1))
            sukta = int(m.group(2))
            verse_num = int(m.group(3))
            suffix = m.group(4) or ""   # "" if no suffix, else 'a','b',...
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(block)
            segment = block[start:end]
            segment = clean_segment_text(segment)
            # Use base key as tuple
            key = (mandala, sukta, verse_num)
            # We'll keep orig ordering by block index and the suffix lexicographic order when concatenating
            grouped[key].append((suffix, segment, b_idx))

    # Build final entries: for each key, sort by (block index, suffix) and concatenate segments
    entries = []
    for key, segs in grouped.items():
        # sort primarily by block index (so original block order), secondarily by suffix ('' < 'a' < 'b'...)
        segs_sorted = sorted(segs, key=lambda x: (x[2], (x[0] if x[0] != "" else " ")))
        concatenated = " | ".join([s[1] for s in segs_sorted if s[1]])
        mandala, sukta, verse_num = key
        entry = {
            "mandala": mandala,
            "sukta": sukta,
            "verse": verse_num,
            "deity": "",
            "sanskrit": "",
            "transliteration": concatenated,
            "translation": ""
        }
        entries.append(entry)

    # Sort entries by mandala,sukta,verse
    entries.sort(key=lambda e: (e["mandala"], e["sukta"], e["verse"]))
    return entries

def save_jsonl(entries, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Saved {len(entries)} entries to {out_path}")

if __name__ == "__main__":
    entries = parse_html_grouping(INPUT_HTML)
    print("Parsed entries:", len(entries))
    for e in entries[:5]:
        print(f'{e["mandala"]}.{e["sukta"]}.{e["verse"]} -> {e["transliteration"][:120]}')
    save_jsonl(entries, OUTPUT_JSON)
