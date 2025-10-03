#!/usr/bin/env python3
"""
scripts/merge_translations.py  (robust)

Merge Griffith (or other) translations into an existing canonical JSONL dataset.

Features:
 - Accepts Griffith mapping in CSV or JSONL format (automatic detection).
 - Exact match by (mandala, sukta, verse_index) when possible.
 - Fallback "sequence alignment" per (mandala, sukta) to map translations by order
   if exact verse_index keys are missing or inconsistent across sources.
 - Optionally overwrite existing translations with --overwrite.
 - Creates backups (if requested), detailed summary JSON and a mismatch CSV for manual review.

Usage:
  python3 scripts/merge_translations.py \
    --dataset data/processed/rigveda_mandalas_1-10.jsonl \
    --griffith data/translations/griffith_map_clean.csv \
    --out data/processed/rigveda_with_translations.jsonl \
    [--overwrite] [--backup] [--fuzzy] [--report data/processed/griffith_merge_report.csv]

Notes:
 - The script is conservative by default (won't overwrite translations without --overwrite).
 - Use --fuzzy to attempt sequence-based mapping when verse_index mismatches are present.
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import sys
from typing import Dict, Tuple, List, Any
from collections import defaultdict, Counter
from copy import deepcopy

# ---------- Helper loaders ----------

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    records = []
    with open(path, 'r', encoding='utf-8') as fh:
        for i, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                records.append(obj)
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSONL at {path} line {i}: {e}")
    return records

def write_jsonl(records: List[Dict[str, Any]], out_path: str):
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

def load_translations(path: str) -> Dict[Tuple[int,int,int], str]:
    """
    Load translations mapping from CSV or JSONL into a dict keyed by (mandala,sukta,verse_index).
    If verse_index is missing or zero in source, it will still load rows keyed with verse_index==0.
    """
    path_l = path.lower()
    mapping = {}
    entries_by_ms = defaultdict(list)  # for sequence fallback
    if path_l.endswith('.csv'):
        with open(path, 'r', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            # normalize header names
            for i, row in enumerate(reader, start=1):
                try:
                    m = int(row.get('mandala') or row.get('mandal') or row.get('m') or 0)
                except:
                    m = 0
                try:
                    s = int(row.get('sukta') or row.get('hymn') or row.get('s') or 0)
                except:
                    s = 0
                try:
                    v = int(row.get('verse_index') or row.get('verse') or row.get('verse_no') or 0)
                except:
                    v = 0
                # pick possible translation columns
                t = row.get('translation_text') or row.get('translation') or row.get('text') or ""
                t = t.strip()
                mapping[(m,s,v)] = t
                entries_by_ms[(m,s)].append(((m,s,v), t))
    else:
        # try jsonl or json
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                # check if first non-empty line is JSON object or array
                peek = None
                for line in fh:
                    if line.strip():
                        peek = line.strip()
                        break
                fh.seek(0)
                if peek and peek.startswith('['):
                    # JSON array
                    obj = json.load(fh)
                    items = obj
                else:
                    # assume JSONL
                    items = []
                    fh.seek(0)
                    for line in fh:
                        if not line.strip():
                            continue
                        items.append(json.loads(line))
        except Exception as e:
            raise RuntimeError(f"Could not read translations file {path}: {e}")

        for item in items:
            try:
                m = int(item.get('mandala') or item.get('m') or 0)
            except:
                m = 0
            try:
                s = int(item.get('sukta') or item.get('hymn') or 0)
            except:
                s = 0
            try:
                v = int(item.get('verse_index') or item.get('verse') or 0)
            except:
                v = 0
            t = item.get('translation_text') or item.get('translation') or item.get('text') or ""
            t = str(t).strip()
            mapping[(m,s,v)] = t
            entries_by_ms[(m,s)].append(((m,s,v), t))

    return mapping, entries_by_ms

# ---------- Core merge logic ----------

def index_dataset(dataset: List[Dict[str, Any]]):
    """Create index: exact mapping (m,s,v) -> list of indices in dataset list."""
    index = defaultdict(list)
    ms_index = defaultdict(list)  # (m,s) -> list of dataset indices in natural order
    for idx, rec in enumerate(dataset):
        try:
            m = int(rec.get('mandala') or 0)
        except:
            m = 0
        try:
            s = int(rec.get('sukta') or 0)
        except:
            s = 0
        try:
            v = int(rec.get('verse_index') or 0)
        except:
            v = 0
        index[(m,s,v)].append(idx)
        ms_index[(m,s)].append((idx, v))
    # sort ms_index by verse_index so order is stable
    for k in list(ms_index.keys()):
        ms_index[k].sort(key=lambda x: (x[1] if isinstance(x[1], (int,float)) else 0))
    return index, ms_index

def backup_file(path: str):
    if not os.path.exists(path):
        return None
    bak = path + ".bak"
    i = 1
    while os.path.exists(bak):
        bak = f"{path}.bak{i}"
        i += 1
    import shutil
    shutil.copyfile(path, bak)
    return bak

def merge(dataset_path: str, griffith_path: str, out_path: str,
          overwrite: bool=False, backup: bool=False, fuzzy: bool=False, report_path: str=None):
    # Load dataset
    dataset = load_jsonl(dataset_path)
    orig_dataset = deepcopy(dataset)

    # Optionally backup original dataset file
    backup_path = None
    if backup:
        backup_path = backup_file(dataset_path)

    # Build index
    index_exact, ms_index = index_dataset(dataset)

    # Load translations
    griffith_map, griffith_by_ms = load_translations(griffith_path)

    # Prepare summary counters
    stats = {
        'total_dataset_records': len(dataset),
        'total_translation_entries': len(griffith_map),
        'exact_matches_applied': 0,
        'sequence_matches_applied': 0,
        'skipped_existing_translations': 0,
        'overwritten_translations': 0,
        'unmatched_translation_keys': 0,
        'unmapped_translation_examples': []
    }

    # Track which dataset indices were updated
    updated_indices = set()

    # 1) Exact matching by (m,s,v)
    for key, text in griffith_map.items():
        m,s,v = key
        if v is None:
            v = 0
        if key in index_exact:
            idxs = index_exact[key]
            for idx in idxs:
                rec = dataset[idx]
                existing = rec.get('translation')
                if existing and existing != "" and not overwrite:
                    stats['skipped_existing_translations'] += 1
                    # tag notes to indicate presence if not present
                    notes = rec.get('notes') or ""
                    if 'griffith_present' not in notes:
                        notes = (notes + ";" if notes else "") + "griffith_present"
                        rec['notes'] = notes
                else:
                    rec['translation'] = text
                    notes = rec.get('notes') or ""
                    action = "griffith_overwritten" if existing and overwrite else "griffith_merged"
                    rec['notes'] = (notes + ";" if notes else "") + action
                    updated_indices.add(idx)
                    if existing and overwrite:
                        stats['overwritten_translations'] += 1
                    else:
                        stats['exact_matches_applied'] += 1
        else:
            # will try sequence fallback later
            stats['unmatched_translation_keys'] += 1
            if len(stats['unmapped_translation_examples']) < 20:
                stats['unmapped_translation_examples'].append({'key':key, 'text_snip': text[:200]})

    # 2) Sequence alignment fallback (per mandala,sukta)
    if fuzzy:
        # For each (m,s) present in griffith_by_ms, try to align by order with dataset entries for same (m,s)
        for ms, entries in griffith_by_ms.items():
            m,s = ms
            # get dataset indices list for same (m,s)
            if ms not in ms_index:
                continue
            ds_list = ms_index[ms]  # list of (idx, verse_index) sorted by verse_index
            ds_indices = [t[0] for t in ds_list]
            # build list of griffith entries ordered by verse_index from their keys if present, else insertion order
            # griffith entries in entries: list of ((m,s,v), text)
            # sort by v where v>0 else keep input order
            def _sort_key(item):
                (km,ks,kv), txt = item
                return (kv if isinstance(kv,(int,float)) and kv>0 else 1e9)
            entries_sorted = sorted(entries, key=_sort_key)
            # if counts match or griffith has fewer, align by index
            if len(entries_sorted) == 0 or len(ds_indices) == 0:
                continue
            # We'll match up to min length
            n_match = min(len(entries_sorted), len(ds_indices))
            for i in range(n_match):
                (gkey, gtext) = entries_sorted[i]
                target_idx = ds_indices[i]
                rec = dataset[target_idx]
                existing = rec.get('translation')
                # only update if empty or overwrite
                if existing and existing != "" and not overwrite:
                    stats['skipped_existing_translations'] += 1
                    if len(stats['unmapped_translation_examples']) < 20:
                        stats['unmapped_translation_examples'].append({'sequence_skipped': (ms, i), 'existing_snip': existing[:120]})
                    continue
                rec['translation'] = gtext
                notes = rec.get('notes') or ""
                rec['notes'] = (notes + ";" if notes else "") + "griffith_seq_merged"
                updated_indices.add(target_idx)
                stats['sequence_matches_applied'] += 1
                # If this gkey had previously been counted as unmatched, decrement
                if gkey in griffith_map:
                    # we matched this key; reduce unmatched counter if previously counted
                    # (we don't remove from griffith_map dict, just adjust stats)
                    pass

    # 3) Final reporting: count leftover unmatched translation keys
    unmatched = []
    for key, text in griffith_map.items():
        m,s,v = key
        if key in index_exact:
            # matched earlier
            continue
        # if fuzzy used we might have matched via sequence; detect if any dataset entries for ms have that text
        matched_via_seq = False
        if fuzzy:
            ds_ms = ms_index.get((m,s), [])
            # look for any dataset rec at idx that has translation exactly equal to this text
            for idx,vv in ds_ms:
                if dataset[idx].get('translation') and dataset[idx]['translation'].strip() == text.strip():
                    matched_via_seq = True
                    break
        if not matched_via_seq:
            unmatched.append({'key': key, 'text_snip': text[:200]})
    stats['final_unmatched_translation_keys'] = len(unmatched)
    stats['final_unmatched_examples'] = unmatched[:20]

    # 4) Write out merged dataset
    write_jsonl(dataset, out_path)

    # 5) Write summary JSON
    summary = {
        "dataset_input": dataset_path,
        "translations_input": griffith_path,
        "output": out_path,
        "backup_created": backup_path if backup else None,
        "stats": stats,
        "updated_record_count": len(updated_indices)
    }
    summary_path = os.path.splitext(out_path)[0] + "_merge_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as sf:
        json.dump(summary, sf, ensure_ascii=False, indent=2)

    # 6) Write report CSV if requested (deltas + unmatched)
    if report_path:
        # Report rows: dataset rec id, mandala,sukta,verse_index,existing_translation,merged_translation,notes
        with open(report_path, 'w', encoding='utf-8', newline='') as rf:
            writer = csv.writer(rf)
            writer.writerow(['dataset_index','id','mandala','sukta','verse_index','existing_translation','new_translation','notes'])
            for idx, rec in enumerate(dataset):
                did = rec.get('id')
                m = rec.get('mandala'); s = rec.get('sukta'); v = rec.get('verse_index')
                existing = None
                # compare to original dataset to show change
                orig_rec = orig_dataset[idx] if idx < len(orig_dataset) else {}
                existing = orig_rec.get('translation') if orig_rec else None
                newt = rec.get('translation')
                if (existing and existing != "") or (newt and newt != ""):
                    writer.writerow([idx, did, m, s, v, existing or "", newt or "", rec.get('notes') or ""])
        # Also write unmatched translations to a separate file for manual inspection
        unmatched_path = os.path.splitext(report_path)[0] + "_unmatched.csv"
        with open(unmatched_path, 'w', encoding='utf-8', newline='') as uf:
            writer = csv.writer(uf)
            writer.writerow(['mandala','sukta','verse_index','translation_snip'])
            for u in unmatched:
                (m,s,v) = u['key']
                writer.writerow([m,s,v,u['text_snip']])
    return summary_path

# ---------- CLI ----------

def main():
    p = argparse.ArgumentParser(description="Robust merge of Griffith translations into canonical Rigveda JSONL")
    p.add_argument("--dataset", required=True, help="Path to dataset JSONL (canonical) to merge into")
    p.add_argument("--griffith", required=True, help="Path to Griffith translations (CSV or JSONL)")
    p.add_argument("--out", required=True, help="Output JSONL path for merged dataset")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing non-null translations in dataset")
    p.add_argument("--backup", action="store_true", help="Backup the original dataset JSONL (dataset.jsonl.bak)")
    p.add_argument("--fuzzy", action="store_true", help="Enable sequence-based fallback mapping per (mandala,sukta)")
    p.add_argument("--report", default=None, help="Optional CSV path to write a detailed merge report")
    args = p.parse_args()

    summary_path = merge(
        dataset_path=args.dataset,
        griffith_path=args.griffith,
        out_path=args.out,
        overwrite=args.overwrite,
        backup=args.backup,
        fuzzy=args.fuzzy,
        report_path=args.report
    )
    print("Merge complete. Summary JSON written to:", os.path.splitext(args.out)[0] + "_merge_summary.json")
    if args.report:
        print("Detailed report written to:", args.report)
        print("Unmatched translation keys written to:", os.path.splitext(args.report)[0] + "_unmatched.csv")

if __name__ == "__main__":
    main()
