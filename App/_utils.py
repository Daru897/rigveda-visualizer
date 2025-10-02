# App/_utils.py
from pathlib import Path
import pandas as pd
import re
import sys
import pandas as pd
pd.set_option('future.no_silent_downcasting', True)

import subprocess
from pathlib import Path

OUT = ROOT / "Data" / "rigveda.csv"
if not OUT.exists():
    # run aggregator synchronously - optionally silent
    subprocess.run(["python", str(ROOT / "Scripts" / "aggregate_griffith.py"), "--quiet"], check=True)
# now read OUT
df = pd.read_csv(OUT)


# Determine project root relative to App/ (assumes App/ is directly under project root)
APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DATA_CSV = ROOT / "Data" / "rigveda.csv"
RAW_GRIFFITH = ROOT / "Data" / "Raw" / "Griffith"

EXPECTED_COLS = ["Mandala", "Sukta", "Verse", "Deity", "Transliteration", "Translation", "Confidence"]

def try_read_file(p: Path):
    """Attempt to read a file into a DataFrame using heuristics."""
    try:
        if p.suffix.lower() == ".csv":
            return pd.read_csv(p)
        if p.suffix.lower() == ".tsv":
            return pd.read_csv(p, sep="\t")
        if p.suffix.lower() == ".json":
            return pd.read_json(p, lines=False)
        # try common delimiters
        for sep in [",", "\t", "|", ";"]:
            try:
                df = pd.read_csv(p, sep=sep, engine="python")
                if df.shape[1] >= 2:
                    return df
            except Exception:
                continue
        # fallback: each line as a row in 'Text' column
        text = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        return pd.DataFrame({"Text": text})
    except Exception as e:
        print(f"[utils.try_read_file] Failed to read {p}: {e}")
        return None

def extract_mandala_number(folder_name: str):
    m = re.search(r"(\d{1,3})", folder_name)
    return int(m.group(1)) if m else None

def normalize_df(df: pd.DataFrame):
    """Ensure expected columns exist, coerce types, and return a safe dataframe."""
    # Copy to avoid mutating original
    df = df.copy()
    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = pd.NA

    # Coerce numeric fields
    for c in ["Mandala", "Sukta", "Verse"]:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        except Exception:
            pass

    # Confidence numeric 0.0-1.0
    try:
        df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0.0)
    except Exception:
        df["Confidence"] = 0.0

    # Text fields safe
    df["Deity"] = df["Deity"].fillna("Unknown").astype(str)
    df["Transliteration"] = df["Transliteration"].fillna("").astype(str)
    df["Translation"] = df["Translation"].fillna("").astype(str)

    # Ensure expected column order
    available = [c for c in EXPECTED_COLS if c in df.columns]
    return df[available]

def aggregate_raw_griffith_in_memory():
    """
    If Data/rigveda.csv not present, attempt to read files under Data/Raw/Griffith/mandala_*
    and concatenate them into a single DataFrame (in-memory). This is a fallback; for
    production you should run Scripts/aggregate_griffith.py to produce Data/rigveda.csv.
    """
    if not RAW_GRIFFITH.exists():
        return None

    all_rows = []
    for mandala_dir in sorted(RAW_GRIFFITH.iterdir()):
        if not mandala_dir.is_dir():
            continue
        mandala_no = extract_mandala_number(mandala_dir.name)
        for f in sorted(mandala_dir.glob("*")):
            if not f.is_file():
                continue
            df = try_read_file(f)
            if df is None:
                continue
            # attach mandala hint if missing
            if mandala_no is not None and "Mandala" not in df.columns:
                df["Mandala"] = mandala_no
            all_rows.append(df)
    if not all_rows:
        return None
    try:
        combined = pd.concat(all_rows, ignore_index=True, sort=False)
        return combined
    except Exception as e:
        print(f"[utils.aggregate_raw_griffith_in_memory] concat failed: {e}")
        return None

def load_dataset():
    """
    Public loader:
      - Try Data/rigveda.csv
      - Else try to aggregate raw griffith folders in-memory
      - Else return None
    """
    if DATA_CSV.exists():
        try:
            df = pd.read_csv(DATA_CSV)
            return normalize_df(df)
        except Exception as e:
            print(f"[utils.load_dataset] failed to read {DATA_CSV}: {e}")

    # Try in-memory aggregation
    df_agg = aggregate_raw_griffith_in_memory()
    if df_agg is not None:
        return normalize_df(df_agg)

    return None
