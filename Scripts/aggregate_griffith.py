# Scripts/aggregate_griffith.py
"""
Aggregator wrapper (improved)
- Dynamically loads parse_griffith_from_folder.py
- Calls build_translations_map(), load_translit_entries(path?) safely (detects signature)
- merge_and_save(...)
- Accepts parser failure and fallbacks
- Handles merged JSONL *or* CSV fallback paths gracefully
"""
from pathlib import Path
import importlib.util
import json
import re
import sys
import pandas as pd
import argparse
import inspect

parser = argparse.ArgumentParser()
parser.add_argument("--quiet", action="store_true")
parser.add_argument("--only-mandala", type=int, default=None)
args = parser.parse_args()
VERBOSE = not args.quiet

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CANDIDATE_DIRS = [
    PROJECT_ROOT / "Data" / "Raw" / "data" / "raw" / "griffith",
    PROJECT_ROOT / "Data" / "Raw" / "griffith",
    PROJECT_ROOT / "Data" / "Raw" / "Griffith",
    PROJECT_ROOT / "Data" / "data" / "raw" / "griffith",
    PROJECT_ROOT / "data" / "raw" / "griffith",
]

OUT_CSV = PROJECT_ROOT / "Data" / "rigveda.csv"
OUT_JSONL = PROJECT_ROOT / "Data" / "rigveda.jsonl"
MERGED_JSONL = PROJECT_ROOT / "Data" / "rigveda_merged.jsonl"

PARSER_FILE_CANDIDATES = [
    PROJECT_ROOT / "Data" / "Raw" / "data" / "raw" / "parse_griffith_from_folder.py",
    PROJECT_ROOT / "Data" / "Raw" / "parse_griffith_from_folder.py",
    PROJECT_ROOT / "Scripts" / "parse_griffith_from_folder.py",
    PROJECT_ROOT / "parse_griffith_from_folder.py",
]

def find_griffith_root():
    for p in CANDIDATE_DIRS:
        if p.exists() and p.is_dir():
            return p
    return None

def find_parser_file():
    for p in PARSER_FILE_CANDIDATES:
        if p.exists() and p.is_file():
            return p
    return None

def load_parser_module(path: Path):
    spec = importlib.util.spec_from_file_location("parse_griffith_from_folder_mod", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def call_parser_workflow(parser_mod, griffith_root):
    """
    Patch parser module paths, call functions:
      - build_translations_map()
      - load_translit_entries(path?)  <-- call with argument if function signature requires it
      - merge_and_save(translit_entries, translations_map, output_path)
    Returns path to merged JSONL (parser_mod.OUTPUT_JSONL) on success.
    """
    if VERBOSE:
        print("Patching parser module paths to use griffith root:", griffith_root)
    # patch module constants
    parser_mod.GRIFFITH_FOLDER = griffith_root
    # if translit JSONL exists at project level, set it on module
    candidate_translit = PROJECT_ROOT / "Data" / "rigveda_translit.jsonl"
    if candidate_translit.exists():
        parser_mod.TRANSLIT_JSONL = candidate_translit
    parser_mod.OUTPUT_JSONL = MERGED_JSONL

    # 1) build translations_map
    if VERBOSE:
        print("Calling build_translations_map() ...")
    translations_map = parser_mod.build_translations_map()

    # 2) load translit entries (call with or without path depending on signature)
    if VERBOSE:
        print("Inspecting load_translit_entries signature ...")
    load_fn = parser_mod.load_translit_entries
    sig = inspect.signature(load_fn)
    # prefer to pass parser_mod.TRANSLIT_JSONL if function takes a parameter
    try:
        if len(sig.parameters) == 0:
            if VERBOSE:
                print("Calling load_translit_entries() without args")
            translit_entries = load_fn()
        else:
            if VERBOSE:
                print("Calling load_translit_entries(path) with", getattr(parser_mod, "TRANSLIT_JSONL", None))
            translit_entries = load_fn(getattr(parser_mod, "TRANSLIT_JSONL", None))
    except Exception as e:
        # bubble up with context
        raise RuntimeError(f"load_translit_entries() call failed: {e}")

    # 3) merge and save
    if VERBOSE:
        print("Calling merge_and_save(translit_entries, translations_map, OUTPUT_JSONL) ...")
    # If merge_and_save expects different params, we try to detect via signature
    merge_fn = parser_mod.merge_and_save
    merge_sig = inspect.signature(merge_fn)
    try:
        # Try the common signature first
        if len(merge_sig.parameters) >= 3:
            merge_fn(translit_entries, translations_map, parser_mod.OUTPUT_JSONL)
        else:
            # fallback: try calling with just entries + map and let module handle writing
            merge_fn(translit_entries, translations_map)
    except Exception as e:
        raise RuntimeError(f"merge_and_save() call failed: {e}")

    return parser_mod.OUTPUT_JSONL

def merged_jsonl_to_outputs(merged_path: Path):
    """
    Accept either a JSONL (preferred) or a CSV (fallback) and produce OUT_CSV + OUT_JSONL.
    """
    if not merged_path.exists():
        raise FileNotFoundError(f"Merged file not found: {merged_path}")

    # If merged_path is CSV, read it directly
    if merged_path.suffix.lower() in (".csv",):
        if VERBOSE:
            print("Merged path is CSV; reading directly:", merged_path)
        df = pd.read_csv(merged_path, engine="python", low_memory=False)
    else:
        # attempt to read as JSONL
        if VERBOSE:
            print("Merged path presumed JSONL; reading as JSON lines:", merged_path)
        df = pd.read_json(merged_path, lines=True)

    # Normalize expected columns
    expected = ["Mandala","Sukta","Verse","Deity","Transliteration","Translation","Confidence"]
    for c in expected:
        if c not in df.columns:
            df[c] = pd.NA

    for c in ["Mandala","Sukta","Verse"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0.0)
    df["Deity"] = df["Deity"].fillna("Unknown")
    df["Transliteration"] = df["Transliteration"].fillna("").astype(str)
    df["Translation"] = df["Translation"].fillna("").astype(str)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    # write normalized jsonl as well
    with open(OUT_JSONL, "w", encoding="utf-8") as fh:
        for rec in df.to_dict(orient="records"):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if VERBOSE:
        print(f"Wrote final CSV to {OUT_CSV} and JSONL to {OUT_JSONL} (rows: {len(df)})")
    return OUT_CSV

def read_html_as_text(path: Path):
    """Lightweight HTML->text fallback using bs4 if available."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None
    txt = path.read_text(encoding="utf-8", errors="ignore")
    if BeautifulSoup:
        soup = BeautifulSoup(txt, "html.parser")
        main = soup.body or soup
        return main.get_text(separator="\n").strip()
    # crude fallback
    return re.sub(r"<[^>]+>", "", txt).strip()

def fallback_plaintext_aggregate(griffith_root):
    """
    Create a CSV + JSONL by dumping the plain text of hymn HTML files.
    Returns the path to the CSV (OUT_CSV).
    """
    rows = []
    mandala_dirs = sorted([d for d in griffith_root.iterdir() if d.is_dir() and re.search(r"mandala", d.name, re.I)])
    if not mandala_dirs:
        mandala_dirs = [griffith_root]

    for mandala_dir in mandala_dirs:
        try:
            mandala_no = int(re.search(r"(\d{1,3})", mandala_dir.name).group(1)) if re.search(r"(\d{1,3})", mandala_dir.name) else None
        except Exception:
            mandala_no = None
        for f in sorted(mandala_dir.glob("*.html")):
            if not f.is_file():
                continue
            text = read_html_as_text(f)
            m = re.search(r"hymn[_\-]?0*([0-9]{1,4})", f.name, re.I)
            sukta_guess = int(m.group(1)) if m else None
            rows.append({
                "Mandala": mandala_no,
                "Sukta": sukta_guess,
                "Verse": None,
                "Deity": None,
                "Transliteration": text,
                "Translation": None,
                "Confidence": 1.0,
                "source_file": str(f.relative_to(PROJECT_ROOT)),
            })

    if not rows:
        raise RuntimeError("Fallback found no hymn files.")

    df = pd.DataFrame(rows)
    for c in ["Mandala","Sukta","Verse"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0.0)
    df["Deity"] = df["Deity"].fillna("Unknown")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    with open(OUT_JSONL, "w", encoding="utf-8") as fh:
        for rec in df.to_dict(orient="records"):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if VERBOSE:
        print("Fallback plaintext aggregation wrote", OUT_CSV, "with rows:", len(df))
    return OUT_CSV

def main():
    griffith_root = find_griffith_root()
    if not griffith_root:
        print("❌ Griffith hymns folder not found. Checked these candidates:")
        for c in CANDIDATE_DIRS:
            print(" -", c)
        sys.exit(1)
    if VERBOSE:
        print("Using griffith root:", griffith_root)

    parser_file = find_parser_file()
    parser_mod = None
    if parser_file:
        if VERBOSE:
            print("Found parser file at:", parser_file)
        try:
            parser_mod = load_parser_module(parser_file)
        except Exception as e:
            if VERBOSE:
                print("Failed to load parser module:", e)
            parser_mod = None

    merged_source = None

    if parser_mod:
        try:
            merged_source = call_parser_workflow(parser_mod, griffith_root)
        except Exception as e:
            if VERBOSE:
                print("Parser workflow failed:", e)
            parser_mod = None

    if not merged_source:
        if VERBOSE:
            print("Falling back to plaintext aggregation...")
        merged_source = fallback_plaintext_aggregate(griffith_root)

    # merged_source may be CSV or JSONL; handle either
    try:
        out_csv = merged_jsonl_to_outputs(Path(merged_source))
        if VERBOSE:
            print("Aggregation completed. Final CSV:", out_csv)
    except Exception as e:
        print("Failed converting merged data to outputs:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
