#!/usr/bin/env python3
"""
scripts/clean_griffith_csv.py

Clean Griffith CSV: Split concatenated verses, correct misprints/archaic, dedup, output CSV/JSONL.
Handles Pandas errors with quoting/on_bad_lines.

Usage:
  python scripts/clean_griffith_csv.py \
    --input data/translations/griffith_map.csv \
    --output data/translations/griffith_map_clean.csv \
    --jsonl data/translations/griffith_map_clean.jsonl \
    --modernize  # Light archaic fixes
"""

import argparse
import csv
import json
import pandas as pd
import re
from pathlib import Path

def split_and_correct(df, modernize=True):
    # Corrections dict
    corrections = {
        'lavishest': 'lavishes', 'obtaineth': 'obtains', 'thou encompassest': 'you encompass',
        'goeth': 'goes', 'Aṅgiras': 'Angiras', 'Varuṇa': 'Varuna', 'might power': 'mighty power',
        'hitherward': 'hereward'
    }
    if modernize:
        corrections.update({'thee': 'you', 'thou': 'you', 'wilt': 'will', 'hast': 'have'})

    expanded_rows = []
    for _, row in df.iterrows():
        text = str(row['translation_text'])
        # Split on verse numbers: match 'num text' until next num
        pattern = r'(\d+)\s+(.*?)(?=\s+\d+\s+|$)(?s)'
        matches = list(re.finditer(pattern, text, re.DOTALL))
        for match in matches:
            num = int(match.group(1))
            verse_text = match.group(2).strip()
            if len(verse_text) > 10:  # Min length filter
                # Apply corrections
                corrected = verse_text
                for wrong, right in corrections.items():
                    corrected = corrected.replace(wrong, right)
                expanded_rows.append({
                    'mandala': int(row['mandala']),
                    'sukta': int(row['sukta']),
                    'verse_index': num,
                    'translation_text': corrected
                })

    new_df = pd.DataFrame(expanded_rows)
    # Dedup
    new_df = new_df.drop_duplicates(subset=['mandala', 'sukta', 'verse_index'])
    # Sort
    new_df = new_df.sort_values(['mandala', 'sukta', 'verse_index']).reset_index(drop=True)
    return new_df

def main():
    p = argparse.ArgumentParser(description="Clean Griffith CSV: Split verses, fix misprints.")
    p.add_argument("--input", "-i", required=True, help="Input CSV")
    p.add_argument("--output", "-o", default="data/translations/griffith_map_clean.csv", help="Output CSV")
    p.add_argument("--jsonl", help="Optional JSONL output")
    p.add_argument("--modernize", action="store_true", help="Apply light modernization")
    p.add_argument("--min-length", type=int, default=10, help="Min verse length")
    args = p.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return 1

    # Robust read_csv (uses args.input - FIXED)
    df = pd.read_csv(input_path, quoting=csv.QUOTE_ALL, on_bad_lines='warn', encoding='utf-8')

    clean_df = split_and_correct(df, modernize=args.modernize)

    # Output CSV
    clean_df.to_csv(args.output, index=False)
    print(f"Wrote {len(clean_df)} cleaned rows to {args.output}")

    # Optional JSONL
    if args.jsonl:
        clean_df.to_json(args.jsonl, orient='records', lines=True)
        print(f"Wrote JSONL to {args.jsonl}")

    # Stats
    total = len(clean_df)
    coverage = (clean_df['translation_text'].str.len() > args.min_length).mean() * 100
    print(f"Stats: {total} rows, {coverage:.1f}% coverage (> {args.min_length} chars)")

    # Summary JSON
    summary = {'total_rows': total, 'coverage_pct': coverage, 'modernized': args.modernize}
    sum_path = Path(args.output).with_suffix('.json')
    with open(sum_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {sum_path}")

    # Sample
    print("\nSample (first 5):")
    print(clean_df.head().to_string(index=False))

if __name__ == "__main__":
    main()