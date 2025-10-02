# Scripts/aggregate_griffith.py
"""
Aggregate files under Data/Raw/Griffith/mandala_* into Data/rigveda.csv

It attempts to read CSV/TSV/JSON/text files and normalizes columns:
Mandala,Sukta,Verse,Deity,Transliteration,Translation,Confidence
"""
from pathlib import Path
import pandas as pd
import re

ROOT = Path(".")
RAW = ROOT / "Data" / "Raw" / "Griffith"
OUT = ROOT / "Data" / "rigveda.csv"
EXPECTED_COLS = ["Mandala", "Sukta", "Verse", "Deity", "Transliteration", "Translation", "Confidence"]

def try_read_file(p: Path):
    # returns DataFrame or None
    try:
        if p.suffix.lower() == ".csv":
            return pd.read_csv(p)
        if p.suffix.lower() == ".tsv":
            return pd.read_csv(p, sep="\t")
        if p.suffix.lower() == ".json":
            return pd.read_json(p, lines=False)
        # try delimiters
        for sep in [",", "\t", "|", ";"]:
            try:
                df = pd.read_csv(p, sep=sep, engine="python")
                # heuristics: must have at least 2 columns
                if df.shape[1] >= 2:
                    return df
            except Exception:
                continue
        # fallback: create single-column DataFrame
        text = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        return pd.DataFrame({"Text": text})
    except Exception as e:
        print(f"Failed to read {p}: {e}")
        return None

def extract_mandala_number(folder_name: str):
    m = re.search(r"(\d{1,3})", folder_name)
    return int(m.group(1)) if m else None

def normalize_df(df: pd.DataFrame, mandala_hint=None):
    # ensure expected columns
    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    if mandala_hint is not None:
        df["Mandala"] = df.get("Mandala", mandala_hint).fillna(mandala_hint)
    # coerce numeric
    for c in ["Mandala", "Sukta", "Verse"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    if "Confidence" in df.columns:
        df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0.0)
    else:
        df["Confidence"] = 0.0
    # keep only expected columns (and preserve extra columns if needed)
    return df[EXPECTED_COLS]

def main():
    if not RAW.exists():
        print(f"No raw data folder found at {RAW}. Exiting.")
        return
    collected = []
    # iterate mandala directories
    for mandala_dir in sorted(RAW.iterdir()):
        if not mandala_dir.is_dir():
            continue
        mandala_no = extract_mandala_number(mandala_dir.name)
        print(f"Processing {mandala_dir} -> mandala {mandala_no}")
        for f in sorted(mandala_dir.glob("*")):
            if not f.is_file():
                continue
            df = try_read_file(f)
            if df is None:
                print(f"Skipping {f}")
                continue
            # normalize and append
            try:
                normalized = normalize_df(df, mandala_hint=mandala_no)
                collected.append(normalized)
            except Exception as e:
                print(f"Normalize failed for {f}: {e}")
    if not collected:
        print("No files aggregated. Exiting.")
        return
    full = pd.concat(collected, ignore_index=True, sort=False)
    # final normalization
    # replace None/NA with empty strings for text columns
    full["Deity"] = full["Deity"].fillna("Unknown")
    full["Transliteration"] = full["Transliteration"].fillna("")
    full["Translation"] = full["Translation"].fillna("")
    # write out
    OUT.parent.mkdir(parents=True, exist_ok=True)
    full.to_csv(OUT, index=False)
    print(f"Wrote aggregated CSV to {OUT} with {len(full)} rows.")

if __name__ == "__main__":
    main()
