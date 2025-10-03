# test.py  — robust loader + diagnostics
import os, sys
from pathlib import Path
import pandas as pd
import json

ROOT = Path(".").resolve()
CSV = ROOT / "Data" / "rigveda.csv"
JSONL_CANDIDATES = [
    ROOT / "Data" / "rigveda.jsonl",
    ROOT / "Data" / "rigveda_merged.jsonl",
    ROOT / "Data" / "rigveda_translit.jsonl",
    ROOT / "Data" / "rigveda_with_deity.jsonl"
]

def try_read_csv(path):
    print(f"Trying pd.read_csv({path}) with default engine...")
    try:
        df = pd.read_csv(path)
        print("Success: read_csv default engine.")
        return df
    except Exception as e:
        print("read_csv default engine FAILED:", repr(e))
    # try python engine (more tolerant)
    try:
        print("Trying engine='python' fallback...")
        df = pd.read_csv(path, engine="python", low_memory=False)
        print("Success: read_csv engine='python'.")
        return df
    except Exception as e:
        print("engine='python' FAILED:", repr(e))
    # try reading as JSON lines
    try:
        print("Trying pd.read_json(lines=True) as fallback...")
        df = pd.read_json(path, lines=True)
        print("Success: read_json lines=True.")
        return df
    except Exception as e:
        print("read_json lines=True FAILED:", repr(e))
    return None

def try_read_jsonl(path):
    print(f"Trying to read as JSONL: {path}")
    try:
        df = pd.read_json(path, lines=True)
        print("Success: JSONL loaded with pd.read_json(..., lines=True).")
        return df
    except Exception as e:
        print("pd.read_json lines=True FAILED:", repr(e))
    # try manual: read line count and sample
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            first = fh.readline()
            print("First line preview:", first[:400])
    except Exception as e:
        print("Could not open file for preview:", repr(e))
    return None

def main():
    # 1) check CSV exists
    if CSV.exists():
        print("Found Data/rigveda.csv (size bytes):", CSV.stat().st_size)
        # quick sniff: show first 5 lines
        try:
            with open(CSV, "r", encoding="utf-8", errors="ignore") as fh:
                preview = [next(fh) for _ in range(5)]
            print("First 5 lines (preview):")
            print("".join(preview))
        except StopIteration:
            print("File has fewer than 5 lines.")
        except Exception as e:
            print("Could not preview file:", repr(e))

        df = try_read_csv(CSV)
        if df is None:
            print("All CSV read attempts failed. Consider checking for malformed lines, embedded nulls, or large memory usage.")
            print("You can try: pd.read_csv('Data/rigveda.csv', engine='python', sep=';', error_bad_lines=False)  # older pandas")
            sys.exit(1)

        print("Dataframe shape:", df.shape)
        print("Columns:", df.columns.tolist())
        # show sample rows if small
        print(df.head(3).to_dict(orient='records'))
        return

    # 2) try known JSONL candidates
    for p in JSONL_CANDIDATES:
        if p.exists():
            print(f"Found candidate JSONL: {p}")
            df = try_read_jsonl(p)
            if df is not None:
                print("Dataframe shape:", df.shape)
                print("Columns:", df.columns.tolist())
                print(df.head(3).to_dict(orient='records'))
                return

    # 3) no prebuilt file found, attempt to detect raw folders
    alt = ROOT / "Data" / "Raw"
    if alt.exists():
        print("No CSV/JSONL found; Data/Raw exists. Listing top folders:")
        for p in sorted(alt.iterdir())[:20]:
            print(" -", p)
        print("If you want to (re)build Data/rigveda.csv run: python Scripts/aggregate_griffith.py")
    else:
        print("No Data/rigveda.csv, no JSONL candidates, and Data/Raw not found. Ensure you're in the repo root and the data exists.")

if __name__ == '__main__':
    main()
