#!/usr/bin/env python3
"""
scripts/clean_griffith_csv.py

Robust cleaner for the griffith_map.csv produced by griffith_plain_to_csv.py.

Inputs:
  - CSV with columns: mandala,sukta,verse_index,translation_text  (UTF-8)

Outputs:
  - <out_prefix>_clean.csv        : cleaned mapping ready for merge_translations.py
  - <out_prefix>_review.csv       : ambiguous / candidate rows for manual review
  - <out_prefix>_stats.json       : statistics and diagnostics

Usage:
  python3 scripts/clean_griffith_csv.py \
     --input data/translations/griffith_map.csv \
     --out-prefix data/translations/griffith_map \
     --min-length 20 \
     --verbose

Defaults:
  out_prefix -> input path without extension (adds _clean.csv etc)
"""

import argparse
import csv
import json
import os
import re
import html
from collections import defaultdict
from pathlib import Path

# ---- heuristics / regexes ----
BOILERPLATE_PATTERNS = [
    r'^\s*Index\b', r'^\s*Next:', r'^\s*Previous:', r'^\s*Contents\b',
    r'^\s*Sacred Texts\b', r'^\s*Hinduism\b', r'^\s*All Rights Reserved\b',
    r'^\s*Table of Contents\b', r'^\s*Copyright', r'^\s*By R\. T\. H\. Griffith',
    r'^\s*Translated by', r'^\s*Download Options\b', r'^\s*Full Text\b',
    r'^\s*Read Online\b', r'^\s*Visit\b', r'^\s*For more', r'={3,}', r'-{3,}'
]
BOILERPLATE_RE = re.compile("|".join(f"(?:{p})" for p in BOILERPLATE_PATTERNS), re.I)

HTML_TAG_RE = re.compile(r'<[^>]+>')
MULTI_WHITESPACE_RE = re.compile(r'\s+')

NAV_TOKEN_RE = re.compile(r'\b(Next|Previous|Index|Back|Forward|Home)\b', re.I)
UPPERCASE_WORD_RE = re.compile(r'^[\sA-Z0-9\W]{5,}$')  # lines that are mostly uppercase punctuation/numbers

# score weights
LENGTH_WEIGHT = 1.0
LOWERCASE_RATIO_WEIGHT = 2.0
UPPERCASE_PENALTY = -5.0
NAV_PENALTY = -10.0
JUNK_PENALTY = -20.0

def load_csv(path):
    import pandas as pd
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    # coerce columns to expected names if possible
    cols = {c.lower(): c for c in df.columns}
    mapping = {}
    for expected in ('mandala','sukta','verse_index','translation_text'):
        if expected not in cols:
            # try fuzzy matches
            for c in df.columns:
                if c.lower().startswith(expected[0:3]):
                    mapping[expected] = c
                    break
        else:
            mapping[expected] = cols[expected]
    # If translation_text still missing, find the last text-like column
    if 'translation_text' not in mapping:
        # choose the longest-named column or last column
        mapping['translation_text'] = df.columns[-1]
    # normalize and cast numeric fields
    df2 = df.rename(columns=mapping)
    # Ensure numeric columns exist
    for k in ('mandala','sukta','verse_index'):
        if k not in df2.columns:
            df2[k] = ''
    return df2[['mandala','sukta','verse_index','translation_text']].copy()

def clean_text(s):
    if s is None:
        return ""
    # unescape html entities
    s = html.unescape(str(s))
    # remove HTML tags
    s = HTML_TAG_RE.sub(' ', s)
    # replace weird separators
    s = re.sub(r'[\u2012\u2013\u2014\u2015]', '-', s)  # dash variants
    # collapse whitespace
    s = MULTI_WHITESPACE_RE.sub(' ', s).strip()
    # tidy common leading bullets or numbering fragments
    s = re.sub(r'^\s*[-•\*]+\s*', '', s)
    # remove common nav tokens at ends/starts
    s = re.sub(r'^(Next:|Previous:).*$','', s, flags=re.I).strip()
    return s

def is_junk(s):
    if not s or len(s) < 3:
        return True
    if BOILERPLATE_RE.search(s):
        return True
    # lines that are mostly uppercase/non-letter characters are junk
    # if over 60% chars are non-lowercase letters, treat as junk
    letters = re.findall(r'[A-Za-z]', s)
    if len(letters) < 2 and len(s) < 40:
        # too short and no letters
        return True
    # nav tokens large presence
    if NAV_TOKEN_RE.search(s) and len(s) < 80:
        return True
    # common "Index" style duplicates
    if re.search(r'\b(Index|Contents|Prev|Next|Sanskrit|Sanskrit Index)\b', s, re.I):
        return True
    return False

def score_text(s):
    """
    Higher score = more likely to be a valid verse translation.
    Heuristic:
     - longer text -> better (length)
     - higher lowercase ratio -> better
     - presence of obvious nav/boilerplate -> heavy penalty
     - mostly uppercase -> penalty
    """
    if not s:
        return -9999
    length = len(s)
    letters = re.findall(r'[A-Za-z]', s)
    lower = re.findall(r'[a-z]', s)
    lower_ratio = len(lower) / (len(letters) or 1)
    score = LENGTH_WEIGHT * length + LOWERCASE_RATIO_WEIGHT * (lower_ratio * 100)
    if UPPERCASE_WORD_RE.search(s):
        score += UPPERCASE_PENALTY
    if NAV_TOKEN_RE.search(s):
        score += NAV_PENALTY
    if BOILERPLATE_RE.search(s):
        score += JUNK_PENALTY
    # tiny boost for punctuation variety (real sentences have commas/periods)
    punct_count = sum(s.count(x) for x in [',', '.', ';', ':', '—', '-'])
    score += 0.5 * punct_count
    return score

def canonical_int(v):
    try:
        return int(float(v))
    except Exception:
        return 0

def dedupe_and_select(rows):
    """
    rows: list of dicts with mandala,sukta,verse_index,translation_text
    Returns:
      selected (dict) : the single best row
      others (list)   : other rows (for review or drop)
    """
    # compute score per row
    scored = []
    for r in rows:
        txt = r['translation_text']
        s = score_text(txt)
        scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    others = [r for _, r in scored[1:]]
    # also consider if best score is suspicious (too low) mark for review
    best_score = scored[0][0]
    return best, others, best_score

def clean_dataframe(df, min_length=20, verbose=False, review_thresh=10):
    # Apply cleaning rules
    cleaned_rows = []
    review_rows = []
    stats = {
        'total_rows': 0,
        'dropped_junk': 0,
        'kept': 0,
        'dedup_groups': 0,
        'ambiguous_groups': 0
    }

    # normalize and clean text column
    df['translation_text'] = df['translation_text'].astype(str).fillna('').apply(clean_text)
    # cast numeric fields
    df['mandala_i'] = df['mandala'].apply(canonical_int)
    df['sukta_i'] = df['sukta'].apply(canonical_int)
    df['verse_i'] = df['verse_index'].apply(canonical_int)

    stats['total_rows'] = len(df)

    # drop rows where mandala or sukta are 0 (likely header/intro) OR where text is junk
    cand = []
    for _, row in df.iterrows():
        m = row['mandala_i']; s = row['sukta_i']; v = row['verse_i']
        txt = row['translation_text'].strip()
        if m <= 0 or s <= 0:
            stats['dropped_junk'] += 1
            if verbose:
                print(f"Drop header/intro row: mandala={m},sukta={s},len={len(txt)}")
            continue
        if is_junk(txt):
            stats['dropped_junk'] += 1
            if verbose:
                print(f"Drop junk row: mandala={m},sukta={s},verse={v},text_snip={txt[:60]!r}")
            continue
        if len(txt) < min_length:
            stats['dropped_junk'] += 1
            if verbose:
                print(f"Drop short row (<{min_length}): mandala={m},sukta={s},verse={v},len={len(txt)}")
            continue
        cand.append({
            'mandala': m, 'sukta': s, 'verse_index': v,
            'translation_text': txt
        })

    # group by (mandala,sukta,verse_index)
    groups = defaultdict(list)
    for r in cand:
        key = (r['mandala'], r['sukta'], r['verse_index'])
        groups[key].append(r)

    stats['dedup_groups'] = len(groups)

    for key, rows in groups.items():
        if len(rows) == 1:
            # single candidate: keep
            cleaned_rows.append(rows[0])
            stats['kept'] += 1
        else:
            # dedupe & select best
            best, others, best_score = dedupe_and_select(rows)
            cleaned_rows.append(best)
            stats['kept'] += 1
            # if best score is low or other rows have close scores, mark for review
            # compute score gap
            others_scores = [score_text(o['translation_text']) for o in others]
            gap = (best_score - max(others_scores)) if others_scores else best_score
            if best_score < review_thresh or gap < 5:
                stats['ambiguous_groups'] += 1
                # include all rows for review
                for r in rows:
                    review_rows.append({
                        'mandala': r['mandala'],
                        'sukta': r['sukta'],
                        'verse_index': r['verse_index'],
                        'translation_text': r['translation_text'],
                        'score': score_text(r['translation_text'])
                    })

    return cleaned_rows, review_rows, stats

def write_clean_outputs(cleaned_rows, review_rows, out_prefix):
    clean_path = f"{out_prefix}_clean.csv"
    review_path = f"{out_prefix}_review.csv"
    stats_path = f"{out_prefix}_stats.json"

    # write clean CSV
    with open(clean_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['mandala','sukta','verse_index','translation_text'])
        for r in sorted(cleaned_rows, key=lambda x: (x['mandala'], x['sukta'], x['verse_index'])):
            writer.writerow([r['mandala'], r['sukta'], r['verse_index'], r['translation_text']])

    # write review CSV (if any)
    with open(review_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['mandala','sukta','verse_index','score','translation_text'])
        for r in sorted(review_rows, key=lambda x: (x['mandala'], x['sukta'], x['verse_index'], -x['score'])):
            writer.writerow([r['mandala'], r['sukta'], r['verse_index'], r['score'], r['translation_text']])

    return clean_path, review_path, stats_path

def main():
    parser = argparse.ArgumentParser(description="Robustly clean griffith_map.csv")
    parser.add_argument("--input","-i", required=True, help="Input CSV path (mandala,sukta,verse_index,translation_text)")
    parser.add_argument("--out-prefix","-o", required=False, help="Output prefix (default: input file without ext)")
    parser.add_argument("--min-length", type=int, default=20, help="Minimum characters to consider a verse (default 20)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print("Input file not found:", inp)
        return

    out_prefix = args.out_prefix or str(inp.with_suffix(''))

    df = load_csv(str(inp))
    cleaned_rows, review_rows, stats = clean_dataframe(df, min_length=args.min_length, verbose=args.verbose)

    # write outputs
    clean_path, review_path, stats_path = write_clean_outputs(cleaned_rows, review_rows, out_prefix)

    # write stats file
    stats.update({'total_input_rows': len(df)})
    with open(stats_path, 'w', encoding='utf-8') as sf:
        json.dump(stats, sf, ensure_ascii=False, indent=2)

    print("Cleaned mapping written to:", clean_path)
    print("Review candidates written to:", review_path)
    print("Stats written to:", stats_path)
    print("Summary:", json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
