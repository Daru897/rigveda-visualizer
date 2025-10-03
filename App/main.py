# App/main.py
import sys
from pathlib import Path

# Ensure project root is importable whether run via `streamlit run App/main.py` or opened directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
from App.utils import load_dataset, normalize_df

st.set_page_config(page_title="Rig Veda Visualizer — Verse Browser", layout="wide")

# Load normalized dataset from a single canonical source (Data/rigveda.csv via App.utils)
df = load_dataset()
if df is None or df.empty:
    st.error("No dataset found. Build it with: `python Scripts/aggregate_griffith.py` (writes Data/rigveda.csv).")
    st.stop()
df = normalize_df(df)

# Sidebar: data summary + filters
st.sidebar.header("Verse Browser Controls")
st.sidebar.markdown(f"**Rows loaded:** {len(df)}")

# Mandalas sorted (drop NAs, cast to int for stable sorting/labels)
mandalas = sorted([int(x) for x in df["Mandala"].dropna().unique().tolist()]) if not df["Mandala"].dropna().empty else []
mandala_choice = st.sidebar.selectbox("Mandala", options=["All"] + mandalas, index=0)

# Filter by Mandala -> Sukta options
if mandala_choice == "All":
    df_m = df
else:
    df_m = df[df["Mandala"] == int(mandala_choice)]

suktas = sorted([int(x) for x in df_m["Sukta"].dropna().unique().tolist()]) if not df_m["Sukta"].dropna().empty else []
sukta_choice = st.sidebar.selectbox("Sukta", options=["All"] + suktas, index=0)

if sukta_choice == "All":
    df_ms = df_m
else:
    df_ms = df_m[df_m["Sukta"] == int(sukta_choice)]

verses = sorted([int(x) for x in df_ms["Verse"].dropna().unique().tolist()]) if not df_ms["Verse"].dropna().empty else []
verse_choice = st.sidebar.selectbox("Verse", options=["Select"] + verses, index=0)

# Deity filter
deities_all = sorted(df["Deity"].dropna().unique().tolist()) if "Deity" in df.columns else []
deity_filter = st.sidebar.multiselect("Filter by Deity (optional)", options=deities_all, default=[])

# Confidence slider (robust defaults when column has NaNs)
if "Confidence" in df.columns and df["Confidence"].notna().any():
    min_conf = float(df["Confidence"].min())
    max_conf = float(df["Confidence"].max())
else:
    min_conf, max_conf = 0.0, 1.0
conf_range = st.sidebar.slider("Confidence range", min_value=0.0, max_value=1.0,
                               value=(min_conf, max_conf), step=0.01)

# Apply filters
working = df.copy()
if mandala_choice != "All":
    working = working[working["Mandala"] == int(mandala_choice)]
if sukta_choice != "All":
    working = working[working["Sukta"] == int(sukta_choice)]
if verse_choice != "Select":
    working = working[working["Verse"] == int(verse_choice)]
if deity_filter:
    working = working[working["Deity"].isin(deity_filter)]
if "Confidence" in working.columns:
    working = working[(working["Confidence"] >= conf_range[0]) & (working["Confidence"] <= conf_range[1])]

working = working.sort_values(["Mandala", "Sukta", "Verse"]).reset_index(drop=True)

# Header
st.title("Rig Veda Visualizer — Verse Browser")
st.markdown("Browse verses by Mandala, Sukta and Verse. Use Next / Previous to navigate through the filtered result set.")

# Session state: index across current filtered dataframe
if "idx" not in st.session_state:
    st.session_state.idx = 0

# Reset index when any filter signature changes
signature_parts = [
    str(mandala_choice),
    str(sukta_choice),
    str(verse_choice),
    ",".join(deity_filter) if deity_filter else "",
    f"{conf_range[0]:.2f}-{conf_range[1]:.2f}",
]
current_signature = "|".join(signature_parts)
if st.session_state.get("prev_signature") != current_signature:
    st.session_state.idx = 0
    st.session_state.prev_signature = current_signature

# Navigation + count
total = len(working)
col1, col2, col3 = st.columns([1, 6, 1])
with col1:
    if st.button("Previous", use_container_width=True):
        if total > 0:
            st.session_state.idx = max(0, st.session_state.idx - 1)
with col3:
    if st.button("Next", use_container_width=True):
        if total > 0:
            st.session_state.idx = min(total - 1, st.session_state.idx + 1)
with col2:
    st.markdown(f"**Verse {0 if total == 0 else st.session_state.idx + 1} of {total}**")

# Display
if total == 0:
    st.warning("No verses match the current filters.")
else:
    row = working.iloc[st.session_state.idx]
    st.subheader(f"Mandala {int(row['Mandala']) if pd.notna(row['Mandala']) else '-'} · "
                 f"Sukta {int(row['Sukta']) if pd.notna(row['Sukta']) else '-'} · "
                 f"Verse {int(row['Verse']) if pd.notna(row['Verse']) else '-'}")
    st.write(f"**Deity:** {row.get('Deity','-')}    ·    **Confidence:** "
             f"{row['Confidence']:.2f}" if pd.notna(row.get('Confidence', pd.NA)) else "**Confidence:** —")
    st.markdown("---")
    left, right = st.columns([1, 2])
    with left:
        st.markdown("**Transliteration**")
        st.code(row["Transliteration"] if pd.notna(row.get("Transliteration")) else "—")
    with right:
        st.markdown("**Translation**")
        st.write(row["Translation"] if pd.notna(row.get("Translation")) else "—")

with st.expander("Show filtered verse list (table)"):
    display_cols = [c for c in ["Mandala", "Sukta", "Verse", "Deity", "Confidence", "Transliteration", "Translation"] if c in working.columns]
    st.dataframe(working[display_cols], use_container_width=True)

st.markdown("---")
st.markdown("Run from project root. Build dataset with `python Scripts/aggregate_griffith.py` which writes `Data/rigveda.csv`. Launch: `streamlit run App/main.py`.")
