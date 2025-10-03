#!/usr/bin/env python3
"""
app/main.py - RigVeda Visualizer (Streamlit)

Usage (from project root):
    streamlit run app/main.py

This app expects the merged dataset at:
  data/processed/rigveda_with_translations.jsonl

If not present it will try:
  data/processed/rigveda_mandalas_1-10.jsonl

Requirements:
  streamlit
  pandas
  orjson (optional - faster JSON)
"""

from pathlib import Path
import streamlit as st
import pandas as pd
import json
import orjson
import textwrap
from typing import List, Dict, Any
import io
import random

# ---------- Config ----------
DEFAULT_DATA_PATHS = [
    Path("data/processed/rigveda_with_translations.jsonl"),
    Path("data/processed/rigveda_mandalas_1-10.jsonl")
]

st.set_page_config(page_title="Rig Veda Visualizer — Verse Browser", layout="wide")

# ---------- Helpers ----------

@st.cache_data(ttl=3600)
def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load newline-delimited JSON into a list of dicts. Use orjson for speed."""
    records = []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    with p.open("rb") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = orjson.loads(raw)
            except Exception:
                try:
                    obj = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
                except Exception:
                    # Last resort: decode bytes and try
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
            records.append(obj)
    return records

def to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create dataframe with normalized columns and safe defaults."""
    df = pd.json_normalize(records)
    # ensure required columns exist
    for c in ["id","mandala","sukta","verse_index","verse_id","deity","rishi","sanskrit",
              "transliteration","translation","metre","source_file","page_number","notes"]:
        if c not in df.columns:
            df[c] = None
    # Coerce types where sensible
    df["mandala"] = pd.to_numeric(df["mandala"], errors="coerce").fillna(0).astype(int)
    df["sukta"] = pd.to_numeric(df["sukta"], errors="coerce").fillna(0).astype(int)
    df["verse_index"] = pd.to_numeric(df["verse_index"], errors="coerce").fillna(0).astype(int)
    return df

def filter_df_by_selection(df: pd.DataFrame, mandala: int, sukta: int, verse_index: int):
    q = df
    if mandala is not None:
        q = q[q["mandala"] == int(mandala)]
    if sukta is not None:
        q = q[q["sukta"] == int(sukta)]
    if verse_index is not None:
        q = q[q["verse_index"] == int(verse_index)]
    return q

def paragraphify(s: str, n=80):
    if not s:
        return ""
    return "\n".join(textwrap.wrap(s, width=n))

def download_bytes(content: bytes, filename: str, mime: str):
    st.download_button(label=f"Download {filename}", data=content, file_name=filename, mime=mime)

# ---------- Load data ----------

def find_dataset() -> Path:
    for p in DEFAULT_DATA_PATHS:
        if p.exists():
            return p
    return None

DATA_PATH = find_dataset()
if DATA_PATH is None:
    st.error("No dataset found. Place rigveda_with_translations.jsonl (or rigveda_mandalas_1-10.jsonl) in data/processed/.")
    st.stop()

with st.sidebar:
    st.header("Rig Veda Visualizer")
    st.markdown(f"**Dataset:** `{DATA_PATH}`")
    if st.button("Reload dataset"):
        st.cache_data.clear()
        st.experimental_rerun()
    st.markdown("---")
    st.markdown("Usage tips:")
    st.markdown("- Use search to find verses.\n- Export filtered results.\n- Toggle raw JSON for debugging.")

# Load records (cached)
with st.spinner("Loading dataset..."):
    records = load_jsonl(str(DATA_PATH))
df = to_dataframe(records)

# ---------- Controls / Filters ----------

st.header("Rig Veda — Verse Browser")
col1, col2 = st.columns([1,3])

with col1:
    st.subheader("Browse")
    mandalas = sorted(df["mandala"].unique())
    mandala_sel = st.selectbox("Mandala", options=[None]+mandalas, format_func=lambda x: "All" if x is None else f"Mandala {x}")
    sukta_opts = []
    if mandala_sel is not None:
        sukta_opts = sorted(df[df["mandala"]==mandala_sel]["sukta"].unique())
    else:
        sukta_opts = sorted(df["sukta"].unique())
    sukta_sel = st.selectbox("Sukta (Hymn)", options=[None]+sukta_opts, format_func=lambda x: "All" if x is None else f"Sukta {x}")

    verse_opts = []
    if mandala_sel is not None and sukta_sel is not None:
        verse_opts = sorted(df[(df["mandala"]==mandala_sel) & (df["sukta"]==sukta_sel)]["verse_index"].unique())
    elif mandala_sel is not None and sukta_sel is None:
        verse_opts = sorted(df[df["mandala"]==mandala_sel]["verse_index"].unique())
    else:
        verse_opts = sorted(df["verse_index"].unique())
    verse_sel = st.selectbox("Verse index", options=[None]+verse_opts, format_func=lambda x: "All" if x is None else f"Verse {x}")

    st.markdown("---")
    st.subheader("Search")
    q_text = st.text_input("Text search (Sanskrit or English)", value="")
    q_deity = st.text_input("Filter by deity (e.g., Agni, Indra)", value="")
    quick_btns = st.columns(3)
    if quick_btns[0].button("Random verse"):
        # pick a random row from current filtered set
        candidates = filter_df_by_selection(df, mandala_sel, sukta_sel, None)
        if not candidates.empty:
            r = candidates.sample(1).iloc[0]
            mandala_sel = int(r["mandala"]); sukta_sel = int(r["sukta"]); verse_sel = int(r["verse_index"])
            st.experimental_rerun()
    if quick_btns[1].button("First verse of Mandala"):
        if mandalas:
            mandala_sel = mandalas[0]
            st.experimental_rerun()
    if quick_btns[2].button("Stats"):
        st.metric("Total verses in dataset", len(df))

with col2:
    # placeholder for main content
    pass

# ---------- Apply filters & search ----------

filtered = df.copy()
if mandala_sel is not None:
    filtered = filtered[filtered["mandala"] == mandala_sel]
if sukta_sel is not None:
    filtered = filtered[filtered["sukta"] == sukta_sel]
if verse_sel is not None:
    filtered = filtered[filtered["verse_index"] == verse_sel]
if q_deity:
    # fuzzy-ish filter on deity column
    filtered = filtered[filtered["deity"].fillna("").str.contains(q_deity, case=False, na=False)]
if q_text:
    # search in Sanskrit or translation; handle NaN and case-insensitive
    mask = filtered["sanskrit"].fillna("").str.contains(q_text, case=False, na=False) | \
           filtered["translation"].fillna("").str.contains(q_text, case=False, na=False)
    filtered = filtered[mask]

# Sort by mandala/sukta/verse_index for stable ordering
filtered = filtered.sort_values(by=["mandala","sukta","verse_index"]).reset_index(drop=True)

# ---------- Main view: show one verse at a time and a table of results ----------

main_col, side_col = st.columns([3,1])

with main_col:
    st.subheader("Verse viewer")

    if filtered.empty:
        st.warning("No verses match your filters/search.")
    else:
        # pager state
        if "viewer_idx" not in st.session_state:
            st.session_state.viewer_idx = 0

        # clamp viewer_idx
        st.session_state.viewer_idx = max(0, min(st.session_state.viewer_idx, len(filtered)-1))

        idx = st.session_state.viewer_idx
        rec = filtered.iloc[idx].to_dict()

        # header with nav
        nav_col1, nav_col2, nav_col3 = st.columns([1,6,1])
        with nav_col1:
            if st.button("← Prev") and st.session_state.viewer_idx > 0:
                st.session_state.viewer_idx -= 1
                st.experimental_rerun()
        with nav_col3:
            if st.button("Next →") and st.session_state.viewer_idx < len(filtered)-1:
                st.session_state.viewer_idx += 1
                st.experimental_rerun()

        with st.expander(f"Verse: Mandala {rec.get('mandala')} • Sukta {rec.get('sukta')} • Verse {rec.get('verse_index')}"):
            # display metadata
            md = {
                "ID": rec.get("id"),
                "Deity": rec.get("deity"),
                "Rishi": rec.get("rishi"),
                "Metre": rec.get("metre"),
                "Source file": rec.get("source_file"),
                "Page number": rec.get("page_number"),
                "Notes": rec.get("notes")
            }
            st.json({k:v for k,v in md.items() if v is not None})

        # Sanskrit column and translation column
        sanskrit = rec.get("sanskrit") or ""
        translit = rec.get("transliteration")
        translation = rec.get("translation") or ""

        text_col1, text_col2 = st.columns([1,1])
        with text_col1:
            st.markdown("**Sanskrit (original)**")
            if translit:
                st.caption("Transliteration available")
            # Preserve formatting using st.code (monospace) or st.write with markdown triple-backtick?
            st.code(sanskrit, language=None)
            if translit:
                st.markdown("**Transliteration**")
                st.write(translit)
        with text_col2:
            st.markdown("**Griffith translation (English)**")
            if translation:
                st.write(paragraphify(translation, n=100))
            else:
                st.info("Translation missing for this verse.")

        # Actions: copy JSON, download verse JSON/CSV
        actions_col1, actions_col2, actions_col3 = st.columns([1,1,1])
        verse_json_bytes = json.dumps(rec, ensure_ascii=False, indent=2).encode("utf-8")
        with actions_col1:
            st.download_button("Download verse (JSON)", data=verse_json_bytes, file_name=f"{rec.get('id')}.json", mime="application/json")
        with actions_col2:
            csv_buf = io.StringIO()
            pd.DataFrame([rec]).to_csv(csv_buf, index=False)
            st.download_button("Download verse (CSV)", data=csv_buf.getvalue().encode("utf-8"), file_name=f"{rec.get('id')}.csv", mime="text/csv")
        with actions_col3:
            st.button("Copy JSON to clipboard")  # small UX; actual copy requires JS; leave as placeholder

        # Raw JSON viewer toggle
        if st.checkbox("Show raw JSON of this verse", False):
            st.json(rec)

with side_col:
    st.subheader("Filtered results")
    st.write(f"Matching verses: **{len(filtered)}**")
    # show a small table and let user pick a row to jump
    table = filtered[["mandala","sukta","verse_index","id","deity"]].copy()
    table["label"] = table.apply(lambda r: f"M{r['mandala']} S{r['sukta']} V{r['verse_index']}", axis=1)
    st.dataframe(table.rename(columns={"mandala":"Mandala","sukta":"Sukta","verse_index":"Verse","id":"ID","deity":"Deity"}), height=360)

    # Jump to a selected row
    sel_idx = st.number_input("Jump to result index (0-based)", min_value=0, max_value=max(0, len(filtered)-1), value=st.session_state.get("viewer_idx",0))
    if st.button("Go to index"):
        st.session_state.viewer_idx = int(sel_idx)
        st.experimental_rerun()

    st.markdown("---")
    st.subheader("Export")
    if st.button("Export filtered as JSONL"):
        out_buf = io.BytesIO()
        for _, r in filtered.iterrows():
            out_buf.write(orjson.dumps(r.to_dict()))
            out_buf.write(b"\n")
        out_buf.seek(0)
        st.download_button("Download JSONL", data=out_buf.getvalue(), file_name="filtered_verses.jsonl", mime="application/json")
    if st.button("Export filtered as CSV"):
        csv_buf = filtered.to_csv(index=False)
        st.download_button("Download CSV", data=csv_buf.encode("utf-8"), file_name="filtered_verses.csv", mime="text/csv")

# ---------- Footer / Stats ----------

st.sidebar.markdown("---")
st.sidebar.subheader("Dataset stats")
st.sidebar.write(f"Total verses (rows): **{len(df)}**")
st.sidebar.write("Mandala counts:")
mandala_counts = df["mandala"].value_counts().sort_index()
st.sidebar.dataframe(mandala_counts.rename_axis("mandala").reset_index(name="count"), height=200)

st.markdown("---")
st.markdown("Powered by your local dataset. For issues, check `data/schema.md` and `scripts/` for parsing/cleaning tools.")

