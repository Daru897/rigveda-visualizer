#!/usr/bin/env python3
"""
Parse the downloaded Detlef Eichler transliteration HTML (Padapatha / no accents)
and produce a JSON lines file with entries:
{
  "mandala": int,
  "sukta": int,
  "verse": int,
  "deity": "",            # empty for now
  "sanskrit": "",         # empty for now (you can add Devanagari later)
  "transliteration": "....",
  "translation": ""       # keep empty until you map Griffith lines
}
"""

import re
import json
import os
from bs4 import BeautifulSoup

INPUT_HTML = "../data/raw/samhita_translit_full.html"   # adjust if different
OUTPUT_JSON = "../data/rigveda_translit.jsonl"          # JSON Lines (one JSON per line)

# regex to find verse identifiers, e.g. "1.1.1", "1.1.1a", or "||1.1.1||"
VERSE_ID_RE = re.compile(r'(?:(?:\|\|)?\s*(\d+)\.(\d+)\.(\d+)([a-z]?)\s*(?:\|\|)?)')

def clean_text(s):
    # remove excessive whitespace and padapatha separators, keep punctuation
    s = s.replace('\u00A0', ' ')  # non-breaking space
    # remove leading/trailing vertical bars and duplicate pipes
    s = s.replace('||', ' ').replace('|', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def parse_html(input_path):
    with open(input_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # get body text preserving line breaks
    # many pages include everything as plain text inside <body>
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]

    entries = []
    buffer = []
    for ln in lines:
        if not ln:
            # blank line = end of current block
            if buffer:
                block = " ".join(buffer)
                # try to find the first verse id in the block
                m = VERSE_ID_RE.search(block)
                if m:
                    mandala = int(m.group(1))
                    sukta = int(m.group(2))
                    verse_num = int(m.group(3))
                    # Extract transliteration by removing all verse-number markers
                    translit = VERSE_ID_RE.sub('', block)
                    translit = clean_text(translit)
                    entry = {
                        "mandala": mandala,
                        "sukta": sukta,
                        "verse": verse_num,
                        "deity": "",
                        "sanskrit": "",
                        "transliteration": translit,
                        "translation": ""
                    }
                    entries.append(entry)
                else:
                    # no verse id found — optionally skip or log
                    pass
                buffer = []
            continue

        # Many files list numeric headings like "1.1.1a agnimīle..." OR show padapatha lines.
        # Collect the lines until a blank line - that'll be a block for one verse (usually).
        buffer.append(ln)

    # catch any trailing buffer
    if buffer:
        block = " ".join(buffer)
        m = VERSE_ID_RE.search(block)
        if m:
            mandala = int(m.group(1))
            sukta = int(m.group(2))
            verse_num = int(m.group(3))
            translit = VERSE_ID_RE.sub('', block)
            translit = clean_text(translit)
            entries.append({
                "mandala": mandala,
                "sukta": sukta,
                "verse": verse_num,
                "deity": "",
                "sanskrit": "",
                "transliteration": translit,
                "translation": ""
            })

    return entries

def save_jsonl(entries, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Saved {len(entries)} entries to {out_path}")

if __name__ == "__main__":
    entries = parse_html(INPUT_HTML)
    print("Parsed entries:", len(entries))
    # show first 3 for quick sanity check
    for i, e in enumerate(entries[:3]):
        print(i+1, e["mandala"], e["sukta"], e["verse"], "-", e["transliteration"][:120])
    save_jsonl(entries, OUTPUT_JSON)
