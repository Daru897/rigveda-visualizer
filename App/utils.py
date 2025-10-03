# App/utils.py
from pathlib import Path
import pandas as pd

pd.set_option("future.no_silent_downcasting", True)

# Paths
APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DATA_DIR = ROOT / "Data"
RIGVEDA_CSV = DATA_DIR / "rigveda.csv"
RAW_GRIFFITH = DATA_DIR / "Raw" / "Griffith"

EXPECTED_COLS = [
    "Mandala", "Sukta", "Verse",
    "Deity", "Transliteration", "Translation", "Confidence"
]

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    for c in ["Mandala", "Sukta", "Verse"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0.0)
    df["Deity"] = df["Deity"].fillna("Unknown").astype(str)
    df["Transliteration"] = df["Transliteration"].fillna("").astype(str)
    df["Translation"] = df["Translation"].fillna("").astype(str)
    return df[EXPECTED_COLS]

def load_dataset() -> pd.DataFrame | None:
    if RIGVEDA_CSV.exists():
        try:
            df = pd.read_csv(RIGVEDA_CSV)
            return normalize_df(df)
        except Exception as e:
            print(f"[utils.load_dataset] failed to read {RIGVEDA_CSV}: {e}")
    # Fallback disabled by default; rely on Scripts/aggregate_griffith.py
    return None
