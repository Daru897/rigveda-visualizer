#!/usr/bin/env python3
"""
griffith_plain_to_csv_v2.py

A more robust converter from a plain-text Griffith translation -> verse mapping CSV/JSONL.

Produces:
  - CSV: mandala,sukta,verse_index,translation_text
  - JSONL: same objects, one per line

Key features:
 - Aggressive pre-clean of navigation/boilerplate
 - Stateful detection of Book/Mandala and Hymn/Sukta headings
 - Flexible verse-number detection (arabic, parenthesized, roman)
 - Paragraph fallback when explicit numbers are absent
 - Dry-run mode to inspect parsed output

Usage:
  python scripts/griffith_plain_to_csv_v2.py --input data/raw/griffith_plain.txt --out-dir data/translations --dry-run --verbose

Then run without --dry-run to write files:
  python scripts/griffith_plain_to_csv_v2.py --input data/raw/griffith_plain.txt --out-dir data/translations --min-length 12
"""
from pathlib import Path
import re
import argparse
import unicodedata
import html
import json
import csv
import sys

# ---- Regexes ----
MANDALA_RE = re.compile(r'^\s*(?:RIG[-\s]?VEDA\s+BOOK|BOOK|MANDALA|BOOK OF)\b.*?([IVXLCDM]+|\d+)', re.I)
HYMN_RE = re.compile(r'^\s*(?:HYMN|HYMN\s+NO|HYMN\s+NUMBER)\b.*?([IVXLCDM]+|\d+)', re.I)
HYMN_ALT_RE = re.compile(r'^\s*(?:HYMN)\s+([IVXLCDM]+|\d+)\b(?:\s*[\.\-:])?\s*(.*)$', re.I)
VERSE_RE = re.compile(r'^\s*\(?\s*(\d+|[IVXLCDM]+)\s*\)?\s*(?:[.\-—:)]\s*)?(.*)$')
ROMAN_ONLY = re.compile(r'^[IVXLCDM]+$', re.I)

BOILERPLATE_PHRASES = [
    r'Sacred Texts', r'Next:', r'Previous:', r'Table of Contents', r'Index',
    r'Sanskrit', r'All Rights Reserved', r'Full Text', r'Download Options',
    r'Read Online', r'Translated by', r'By R\. T\. H\. Griffith', r'—\s*HYMN'
]
BOILERPLATE_RE = re.compile("|".join(f"(?:{p})" for p in BOILERPLATE_PHRASES), re.I)

HTML_TAG_RE = re.compile(r'<[^>]+>')
WHITESPACE_RE = re.compile(r'\s+')

def normalize_line(s):
    if s is None:
        return ""
    s = str(s)
    s = html.unescape(s)
    s = HTML_TAG_RE.sub(' ', s)
    s = unicodedata.normalize("NFC", s)
    s = s.replace('\r\n', '\n').replace('\r','\n')
    s = WHITESPACE_RE.sub(' ', s).strip()
    return s

def looks_like_junk(line):
    if not line:
        return True
    if BOILERPLATE_RE.search(line):
        return True
    # lines with too few letters are junk
    letters = re.findall(r'[A-Za-z]', line)
    if len(letters) < 3 and len(line) < 40:
        return True
    # navigation-like short caps
    if len(line) < 60 and re.search(r'\b(Next|Previous|Index|Contents|Back)\b', line, re.I):
        return True
    return False

def roman_to_int(r):
    r = r.upper()
    vals = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
    total = 0; prev = 0
    for ch in reversed(r):
        v = vals.get(ch,0)
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total

def detect_mandala_token(line):
    m = MANDALA_RE.search(line)
    if not m:
        return None
    tok = m.group(1)
    tok = tok.strip()
    if ROMAN_ONLY.match(tok):
        return roman_to_int(tok)
    try:
        return int(tok)
    except:
        return None

def detect_hymn_token(line):
    # try HYMN I. Agni style
    m = HYMN_ALT_RE.match(line)
    if m:
        tok = m.group(1)
        try:
            if ROMAN_ONLY.match(tok):
                return roman_to_int(tok)
            return int(tok)
        except:
            return None
    m2 = HYMN_RE.search(line)
    if m2:
        tok = m2.group(1)
        if ROMAN_ONLY.match(tok):
            return roman_to_int(tok)
        try:
            return int(tok)
        except:
            return None
    return None

def split_paragraphs(lines):
    # split raw text lines into paragraphs separated by blank-ish lines
    paras = []
    buf = []
    for ln in lines:
        s = ln.strip()
        if s == "":
            if buf:
                paras.append(" ".join(buf).strip())
                buf = []
            continue
        buf.append(s)
    if buf:
        paras.append(" ".join(buf).strip())
    return paras

def parse_file(lines, min_length=10, allow_roman=True, verbose=False):
    """
    Stateful parsing:
     - iterate paragraphs
     - update mandala/hymn when headings detected
     - extract numbered verses (or assign sequential verse_index per hymn)
    Returns list of dicts: {'mandala':int,'sukta':int,'verse_index':int,'translation_text':str}
    """
    entries = []
    current_mandala = 0
    current_sukta = 0
    verse_counter = 0

    paras = split_paragraphs(lines)
    if verbose:
        print(f"[parser] paragraphs: {len(paras)}", file=sys.stderr)

    for i, p in enumerate(paras):
        ln = normalize_line(p)
        if not ln or looks_like_junk(ln):
            if verbose:
                print(f"[skip] paragraph {i} junk/boilerplate: {ln[:80]!r}", file=sys.stderr)
            continue

        # Update mandala if paragraph looks like a Book/Mandala heading
        mand_tok = detect_mandala_token(ln)
        if mand_tok:
            current_mandala = mand_tok
            current_sukta = 0
            verse_counter = 0
            if verbose:
                print(f"[mandala] detected mandala {current_mandala} at para {i}", file=sys.stderr)
            # possible rest of line contains heading; skip to next para
            continue

        # Update hymn/sukta if detected
        hymn_tok = detect_hymn_token(ln)
        if hymn_tok:
            current_sukta = hymn_tok
            verse_counter = 0
            if verbose:
                print(f"[hymn] detected hymn/sukta {current_sukta} at para {i}", file=sys.stderr)
            # There may be a title (deity name) after the hymn token; don't treat as verse
            continue

        # Check for explicit verse numbering within paragraph (one or many numbered lines)
        # We'll split paragraph into lines and test each for number markers
        para_lines = [l.strip() for l in re.split(r'\n+', p) if l.strip()]
        explicit_found = False
        for pl in para_lines:
            m = VERSE_RE.match(pl)
            if m:
                num_tok = m.group(1)
                rest = m.group(2).strip()
                # parse number (arabic or roman)
                try:
                    if ROMAN_ONLY.match(num_tok) and allow_roman:
                        num_val = roman_to_int(num_tok)
                    else:
                        num_val = int(num_tok)
                except:
                    num_val = None
                # If we have a number, take rest as verse text (if rest long enough)
                if num_val is not None and rest and len(rest) >= min_length:
                    explicit_found = True
                    verse_counter = num_val
                    entries.append({'mandala': current_mandala, 'sukta': current_sukta, 'verse_index': verse_counter, 'translation_text': rest})
                else:
                    # If number present but rest short/empty, we may need to collect following lines.
                    # For simplicity treat the full paragraph as stanza and assign num_val if present.
                    if num_val is not None:
                        explicit_found = True
                        verse_counter = num_val
                        text = pl
                        if len(text) >= min_length:
                            entries.append({'mandala': current_mandala, 'sukta': current_sukta, 'verse_index': verse_counter, 'translation_text': text})
                # continue checking other lines in paragraph
        if explicit_found:
            continue

        # If paragraph contains no explicit numbers, treat it as a stanza:
        verse_counter += 1
        if len(ln) >= min_length:
            entries.append({'mandala': current_mandala, 'sukta': current_sukta, 'verse_index': verse_counter, 'translation_text': ln})
        else:
            if verbose:
                print(f"[short] paragraph {i} shorter than min_length -> skipped: {ln[:80]!r}", file=sys.stderr)
    return entries

def write_outputs(entries, out_dir:Path, prefix="griffith_map_v2"):
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{prefix}.csv"
    jsonl_path = out_dir / f"{prefix}.jsonl"
    # write CSV
    with csv_path.open("w", encoding="utf-8", newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['mandala','sukta','verse_index','translation_text'])
        for e in entries:
            writer.writerow([e['mandala'], e['sukta'], e['verse_index'], e['translation_text']])
    # write JSONL
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return csv_path, jsonl_path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input","-i", required=True, help="Input plain-text Griffith file")
    p.add_argument("--out-dir","-o", default="data/translations", help="Output directory")
    p.add_argument("--min-length", type=int, default=10, help="Minimum characters to consider a stanza")
    p.add_argument("--dry-run", action="store_true", help="Don't write files; print a sample and stats")
    p.add_argument("--allow-roman", action="store_true", help="Parse roman numeral verse numbers")
    p.add_argument("--verbose", action="store_true", help="Verbose logs to stderr")
    args = p.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print("Input file not found:", inp, file=sys.stderr); sys.exit(2)
    lines = []
    with inp.open("r", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            lines.append(ln.rstrip("\n"))

    entries = parse_file(lines, min_length=args.min_length, allow_roman=args.allow_roman, verbose=args.verbose)

    # Post-process: coerce zeros -> 0, fill defaults, and remove entries with no mandala/sukta (optional)
    # Keep entries even when mandala/sukta == 0 (you may inspect them), but we will report counts.
    total = len(entries)
    by_ms_count = {}
    for e in entries:
        key = (int(e['mandala'] or 0), int(e['sukta'] or 0))
        by_ms_count[key] = by_ms_count.get(key,0) + 1

    if args.dry_run:
        print(f"Parsed entries: {total}", file=sys.stderr)
        sample = entries[:40]
        for e in sample:
            print(f"{e['mandala']},{e['sukta']},{e['verse_index']}: {e['translation_text'][:160]}")
        # print basic distribution for inspection
        print("\nCounts per (mandala,sukta) sample (top 20):", file=sys.stderr)
        items = sorted(by_ms_count.items(), key=lambda x: (-x[1], x[0]))[:20]
        for k,v in items:
            print(f"{k}: {v}", file=sys.stderr)
        print("\nDry-run complete. If output looks good, re-run without --dry-run to write CSV/JSONL.", file=sys.stderr)
        return

    out_dir = Path(args.out_dir)
    csv_path, jsonl_path = write_outputs(entries, out_dir)
    print("Wrote:", csv_path, jsonl_path, file=sys.stderr)
    print(f"Total entries written: {total}", file=sys.stderr)

if __name__ == "__main__":
    main()
