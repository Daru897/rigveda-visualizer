#!/usr/bin/env python3
"""
scripts/parse_rigveda.py

Optimized: Enhanced header parsing (danda split), stanza split (danda+num capture),
expanded regex/maps, pada extraction, dedup, stats. Outputs schema + 'padas'.

Usage:
  python scripts/parse_rigveda.py \
    --input-dir data/raw \
    --input-glob 'rigveda_mandala_*.json' \
    --output data/processed/rigveda_mandalas_1-10.jsonl \
    --page-helper data/raw/2015.237767.The-Hymns_page_numbers.json \
    --max-suktas 100  # Optional: Limit for MVP
"""

import argparse
import json
import os
import glob
import re
import unicodedata
from collections import defaultdict, Counter
from datetime import datetime

# ------- Constants & Maps -------
DEITY_MAP = {
    "९": "अग्निः", "१०": "इन्द्रः", "४": "सोम पवमानः", "१२": "विश्वेदेवाः",
    "११": "विष्णुः", "१": "वायुः", "२": "वरुणः", "३": "मित्रः", "५": "अश्विनौ"
    # Expand from sources as needed
}

METRE_RE = re.compile(r'(गायत्री|त्रिष्टुप्|अनुष्टुप्|जगती|विराट्|पङ्क्ति|बृहती|अतिजगती|धृतिः|त्रिष्टुभ्|अनुष्टुभ्|gāyatrī|triṣṭubh|anuṣṭubh|jagatī|br̥hatī)', re.I)
RISHI_RE_LAT = re.compile(r'\b(मधुच्छन्दा|वैश्वामित्र|गृत्समद|वामदेव|गौतम|कश्यप|आङ्गिरस|भरद्वाज|वसिष्ठ|Atri|Vishvamitra|Vasistha|Bharadvaja|Kashyapa|Angiras|Gritsamada|Kanva|Dirghatamas)\b', re.I)
LATIN_DEITY_RE = re.compile(r'\b(Agni|Indra|Varuna|Soma|Rudra|Vayu|Surya|Mitra|Brahma|Aditi|Usas|Prajapati|Dawn|Dyaus|Ashvins|Maruts|Vishvadevas)\b', re.I)

VERSE_NUMBERED_MARKER = re.compile(r'^\s*\(?\d+\)?\s*[\.\-]?', flags=re.M)
SUKTA_END_RE = re.compile(r'॥इति .*? मण्डलं समाप्तम्॥', re.I | re.DOTALL)

def normalize_text(s):
    if s is None:
        return ""
    if isinstance(s, (list, tuple)):
        s = "\n".join(map(str, s))
    s = str(s)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = SUKTA_END_RE.sub('', s)  # Remove end markers
    lines = [ln.rstrip() for ln in s.split("\n")]
    return "\n".join(lines).strip()

def extract_header_fields(text):
    """Parse header: Split first non-empty line by । for [num rishi] । deity । metre."""
    if not text:
        return None, None, None, [], ""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return None, None, None, [], text
    header_line = lines[0].strip()
    parts = re.split(r'।', header_line)
    deity = None
    rishi = None
    metre = None
    header_lines = [header_line] + lines[1:3]  # Up to 3 lines
    body_start = 1 if len(lines) > 1 else 0
    body = "\n".join(lines[body_start:]).strip()

    # Deity: parts[1], map if code
    if len(parts) > 1:
        deity_part = parts[1].strip()
        deity = DEITY_MAP.get(deity_part, deity_part)
    if not deity:
        m = LATIN_DEITY_RE.search(header_line)
        if m:
            deity = m.group(1).title()

    # Rishi: parts[0] after num
    if len(parts) > 0:
        rishi_part = parts[0].strip().split(maxsplit=1)
        if len(rishi_part) > 1:
            rishi = rishi_part[1]
    if not rishi:
        m = RISHI_RE_LAT.search(header_line)
        if m:
            rishi = m.group(1)

    # Metre: parts[2] or regex
    if len(parts) > 2:
        metre_part = parts[2].strip()
        if metre_part:
            metre = metre_part
    if not metre:
        m = METRE_RE.search(header_line)
        if m:
            metre = m.group(1)

    # Multi-metre: Take first (e.g., "त्रिष्टुप्, १ अतिजगती" → "त्रिष्टुप्")
    if metre and ',' in metre:
        metre = metre.split(',')[0].strip()

    # Find body start in original
    body = text.splitlines()[len(header_lines):]
    body = "\n".join(body).strip()

    return deity, rishi, metre, header_lines, body

def split_into_stanzas(body, metre=None):
    """Split: Primary on ॥num॥; fallback blank/numbered. Add padas per stanza."""
    if not body:
        return []
    # Primary: Split on ॥\d+॥, capture num
    stanzas = re.split(r'॥(\d+)॥', body)
    verses = []
    i = 0
    while i < len(stanzas):
        if i + 1 < len(stanzas) and stanzas[i+1].isdigit():
            num = int(stanzas[i+1])
            content = normalize_text(stanzas[i])
            padas = re.split(r'।', content)[:4]  # Up to 4 padas; trim empty
            padas = [p.strip() for p in padas if p.strip()]
            # Approx syllable split if no dandas (for Gayatri: ~8 syl/pada)
            if not padas and metre == 'गायत्री':
                words = content.split()
                padas = [' '.join(words[j:j+3]) for j in range(0, len(words), 3)][:3]  # Rough 8-syl
            verses.append({'num': num, 'sanskrit': content, 'padas': padas})
            i += 2
        else:
            i += 1
    # Fallback if no dandas
    if not verses:
        fallback = re.split(r'\n\s*\n', body)
        for vi, stanza in enumerate(fallback[:10], 1):  # Limit
            content = normalize_text(stanza)
            padas = re.split(r'।', content)[:4]
            padas = [p.strip() for p in padas if p.strip()]
            verses.append({'num': vi, 'sanskrit': content, 'padas': padas})
    return verses

def parse_files(input_dir, pattern, output_file, page_helper_path=None, max_suktas=None):
    files = glob.glob(os.path.join(input_dir, pattern))
    files.sort()  # Mandala order
    records = []
    stats = defaultdict(int)
    id_counter = Counter()
    seen_ids = set()
    page_helper = {}
    if page_helper_path:
        with open(page_helper_path, 'r', encoding='utf-8') as f:
            page_helper = json.load(f)

    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            for entry in data:
                mandala = entry.get('mandala', 0)
                sukta = entry.get('sukta', 0)
                if max_suktas and sukta > max_suktas:
                    continue
                text = normalize_text(entry.get('text', ''))
                deity, rishi, metre, _, body = extract_header_fields(text)
                verses = split_into_stanzas(body, metre)
                for v in verses:
                    rec_id = f"RV-{mandala:02d}-{sukta:03d}-{v['num']:02d}"
                    if rec_id in seen_ids:
                        continue  # Dedup
                    seen_ids.add(rec_id)
                    rec = {
                        "id": rec_id,
                        "mandala": int(mandala),
                        "sukta": int(sukta),
                        "verse_index": int(v['num']),
                        "verse_id": f"{mandala}.{sukta}.{v['num']}",
                        "deity": deity,
                        "rishi": rishi,
                        "sanskrit": v['sanskrit'],
                        "transliteration": None,
                        "translation": None,
                        "metre": metre,
                        "padas": v['padas'],  # New: For viz
                        "source_file": os.path.basename(file),
                        "page_number": page_helper.get(f"{mandala}-{sukta}-{v['num']}", None),
                        "notes": None
                    }
                    # Notes
                    notes = []
                    if not deity: notes.append("deity_missing")
                    if not rishi: notes.append("rishi_missing")
                    if not metre: notes.append("metre_missing")
                    if notes: rec["notes"] = ";".join(notes)
                    records.append(rec)
                    stats[mandala] += 1
                    id_counter[rec_id] += 1
        except Exception as e:
            print(f"Error parsing {file}: {e}", file=sys.stderr)

    # Dedup post-process: Keep longest sanskrit per ID
    deduped = {}
    for rec in records:
        vid = rec['verse_id']
        if vid not in deduped or len(rec['sanskrit']) > len(deduped[vid]['sanskrit']):
            deduped[vid] = rec
    records = list(deduped.values())

    # Output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as out_fh:
        for rec in records:
            out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Enhanced summary
    total = len(rec)
    coverage = {k: {'verses': v, 'deity_%': sum(1 for r in records if r['mandala']==k and r['deity']) / v * 100 if v else 0} for k,v in stats.items()}
    summary = {
        "generated_at": datetime.now().isoformat(),
        "input_pattern": pattern,
        "total_records": total,
        "by_mandala": dict(coverage),
        "duplicates": [k for k,v in id_counter.items() if v>1]
    }
    summary_path = os.path.splitext(output_file)[0] + "_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as sf:
        json.dump(summary, sf, ensure_ascii=False, indent=2)
    return summary

def main():
    import sys
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", default="data/raw")
    p.add_argument("--input-glob", default="rigveda_mandala_*.json")
    p.add_argument("--output", default="data/processed/rigveda_mandalas_1-10.jsonl")
    p.add_argument("--page-helper", default=None)
    p.add_argument("--max-suktas", type=int, default=None, help="Limit suktas per mandala")
    args = p.parse_args()

    summary = parse_files(args.input_dir, args.input_glob, args.output, args.page_helper, args.max_suktas)
    summary_path = os.path.splitext(args.output)[0] + "_summary.json"
    print(f"Wrote {summary['total_records']} records to {args.output}")
    print("By mandala (verses, deity %):", {k: f"{v['verses']} ({v['deity_%']:.1f}%)" for k,v in summary['by_mandala'].items()})
    if summary["duplicates"]:
        print(f"Warning: {len(summary['duplicates'])} duplicate IDs (sample): {summary['duplicates'][:5]}")
    print(f"Summary: {summary_path}")

if __name__ == "__main__":
    main()