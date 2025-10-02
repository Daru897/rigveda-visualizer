#!/usr/bin/env python3
"""
Assign 'deity' field to rigveda entries by searching transliteration and translation text.

Input:  data/rigveda_merged.jsonl    (produced earlier)
Output: data/rigveda_with_deity.jsonl
        data/deity_review.csv        (low-confidence or missing assignments for manual review)
"""

import json
import os
import re
from pathlib import Path
from collections import OrderedDict
from difflib import get_close_matches
import csv
import unicodedata

# ---------- CONFIG ----------
INPUT_JSONL = Path("Data/rigveda_merged.jsonl")
OUTPUT_JSONL = Path("data/rigveda_with_deity.jsonl")
REVIEW_CSV = Path("data/deity_review.csv")

# Minimum confidence threshold to avoid review (0..1)
CONF_THRESHOLD = 0.6

# A curated list of canonical deity names with common variants (extend as needed)
DEITY_LOOKUP = OrderedDict([
    # canonical: [variants...]
    ("Agni", ["agni", "agnim", "agnī", "agnīḥ", "agniḥ", "agnimīle"]),
    ("Indra", ["indra", "indrā", "indras"]),
    ("Soma", ["soma", "sōma", "somaḥ"]),
    ("Varuna", ["varuna", "varuṇa", "varuṇā"]),
    ("Mitra", ["mitra", "mitrá", "mitrā"]),
    ("Rudra", ["rudra", "rudrá"]),
    ("Aśvins", ["ashvins", "aśvins", "aśvin"]),
    ("Vishvakarman", ["vishvakarman", "viśvakarman"]),
    ("Vayu", ["vayu", "vāyu"]),
    ("Prajapati", ["prajapati", "prajāpati"]),
    ("Maruts", ["marut", "maruts", "maruta", "marutah"]),
    ("Brahmanaspati", ["brahmanaspati", "brahmanaspatiḥ"]),
    ("Sukra", ["sukra"]),  # rare
    ("Dyaus", ["dyaus", "dyauś"]),
    ("Ushas", ["ushas", "uṣas"]),
    ("Aditi", ["aditi"]),
    ("Prithvi", ["prthivi", "prthivī", "prthivī́", "prithvi", "prthvī"]),
    ("Vritra", ["vritra"]),
    ("Tvashtri", ["tvashtri", "tvaṣṭṛ", "tvastri"]),
    ("Yama", ["yama", "yamaḥ"]),
    ("Apas", ["apas", "apasas", "apaś"]),
    # add more as you find missing names
])

# Priority order for picking when multiple deities found in a verse.
# Earlier entries in DEITY_LOOKUP already reflect some priority; we will use the order there.
# ---------- END CONFIG ----------

# Utility: normalize transliteration/diacritics -> plain ascii lowercase
def normalize_text(s: str) -> str:
    if s is None:
        return ""
    # Unicode NFKD + remove non-spacing marks (diacritics)
    s_norm = unicodedata.normalize("NFKD", s)
    s_norm = "".join(ch for ch in s_norm if not unicodedata.combining(ch))
    # Replace punctuation and pipes etc. with spaces
    s_norm = re.sub(r"[|,;:()\[\]{}\"’'—–•]", " ", s_norm)
    s_norm = re.sub(r"\s+", " ", s_norm).strip().lower()
    return s_norm

# Build inverted index of variant -> canonical
VARIANT_TO_CANON = {}
for canon, variants in DEITY_LOOKUP.items():
    for v in variants:
        VARIANT_TO_CANON[v.lower()] = canon

# Also build a short-list of simple tokens to check for quickly
SINGLE_TOKEN_VARIANTS = set(VARIANT_TO_CANON.keys())

# Helper: find candidate deity names present in a text (returns set of canonicals)
def find_deities_in_text(text: str):
    found = {}
    txt = normalize_text(text)
    if not txt:
        return found  # empty mapping

    # 1) Exact substring search for multiword and variants
    for variant, canon in VARIANT_TO_CANON.items():
        # use word boundary for variant to reduce false positives
        # but variants may be substrings (e.g., 'agni' in 'agnim'), so check both
        if re.search(rf"\b{re.escape(variant)}\b", txt) or variant in txt:
            found[canon] = found.get(canon, 0) + 2  # higher weight for transliteration exact match

    # 2) Token-level matching against single tokens
    tokens = re.findall(r"[a-z0-9]+", txt)
    for tok in tokens:
        if tok in SINGLE_TOKEN_VARIANTS:
            canon = VARIANT_TO_CANON[tok]
            found[canon] = found.get(canon, 0) + 1

    return found  # mapping canonical -> score (relative)

# Confidence scoring: combine translit score and translation score with weights
TRANSLIT_WEIGHT = 0.7
TRANSLATION_WEIGHT = 0.3

def score_deity_for_entry(translit_text, translation_text):
    # find matches in both fields
    t_matches = find_deities_in_text(translit_text)
    tr_matches = find_deities_in_text(translation_text)

    # Merge: sum weighted scores
    merged = {}
    for canon, sc in t_matches.items():
        merged[canon] = merged.get(canon, 0) + sc * TRANSLIT_WEIGHT
    for canon, sc in tr_matches.items():
        merged[canon] = merged.get(canon, 0) + sc * TRANSLATION_WEIGHT

    # Normalize to 0..1 by dividing by max possible observed (simple heuristic)
    if not merged:
        return None, 0.0, {}
    # Choose best candidate
    best = max(merged.items(), key=lambda x: x[1])
    # compute confidence: best_score / sum_of_scores (how dominant it is)
    total = sum(merged.values())
    confidence = float(best[1]) / float(total) if total > 0 else 0.0
    # also normalize by an upper bound (empirical): cap at 1
    confidence = min(confidence, 1.0)
    return best[0], confidence, merged

def main():
    if not INPUT_JSONL.exists():
        raise FileNotFoundError(f"Input JSONL not found: {INPUT_JSONL}")

    out_entries = []
    review_rows = []

    with INPUT_JSONL.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            translit = obj.get("transliteration", "") or ""
            translation = obj.get("translation", "") or ""

            canon, conf, merged_scores = score_deity_for_entry(translit, translation)

            # If confidence below threshold, we will mark for review
            if canon and conf >= CONF_THRESHOLD:
                obj["deity"] = canon
                obj["deity_confidence"] = round(conf, 3)
            elif canon:
                obj["deity"] = canon
                obj["deity_confidence"] = round(conf, 3)
                # For low confidence still assign but add to review list
                review_rows.append({
                    "mandala": obj.get("mandala"),
                    "sukta": obj.get("sukta"),
                    "verse": obj.get("verse"),
                    "assigned_deity": canon,
                    "confidence": round(conf,3),
                    "top_scores": json.dumps(merged_scores, ensure_ascii=False),
                    "transliteration": translit[:200],
                    "translation": translation[:300]
                })
            else:
                obj["deity"] = ""
                obj["deity_confidence"] = 0.0
                review_rows.append({
                    "mandala": obj.get("mandala"),
                    "sukta": obj.get("sukta"),
                    "verse": obj.get("verse"),
                    "assigned_deity": "",
                    "confidence": 0.0,
                    "top_scores": "",
                    "transliteration": translit[:200],
                    "translation": translation[:300]
                })

            out_entries.append(obj)

    # Save merged JSONL
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSONL.open("w", encoding="utf-8") as fout:
        for e in out_entries:
            fout.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Saved {len(out_entries)} entries with deity field to {OUTPUT_JSONL}")

    # Save review CSV
    if review_rows:
        REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
        with REVIEW_CSV.open("w", newline='', encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=[
                "mandala", "sukta", "verse", "assigned_deity", "confidence", "top_scores", "transliteration", "translation"
            ])
            writer.writeheader()
            for r in review_rows:
                writer.writerow(r)
        print(f"Wrote {len(review_rows)} rows to review CSV: {REVIEW_CSV}")
    else:
        print("No review rows; all entries had high confidence.")

if __name__ == "__main__":
    main()
