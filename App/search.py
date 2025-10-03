# App/search.py
import sys
from pathlib import Path

# Ensure project root is on sys.path so "from App..." works when running the file directly
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
from App.utils import load_dataset, normalize_df, EXPECTED_COLS


st.set_page_config(page_title="Rig Veda Visualizer — Search", layout="wide")

st.title("Search & Filter — Rig Veda Visualizer")
st.markdown("Search transliteration/translation, filter by Mandala/Sukta/Deity and confidence. Click a row to preview.")

# Load dataset
df = load_dataset()
if df is None or df.shape[0] == 0:
    st.warning("No dataset found. Please run `Scripts/aggregate_griffith.py` to build Data/rigveda.csv, or place a CSV at Data/rigveda.csv.")
    st.stop()

# ensure normalized
df = normalize_df(df)

# Sidebar filters
st.sidebar.header("Search Controls")
query = st.sidebar.text_input("Keyword search (transliteration / translation)", "")
show_partial = st.sidebar.checkbox("Use partial matches (case-insensitive)", value=True)

mandala_opts = ["All"] + sorted([int(x) for x in df["Mandala"].dropna().unique().tolist()]) if not df["Mandala"].dropna().empty else ["All"]
mandala_sel = st.sidebar.selectbox("Mandala", options=mandala_opts, index=0)

# Sukta depends on mandala selection
if mandala_sel == "All":
    sukta_list = sorted([int(x) for x in df["Sukta"].dropna().unique().tolist()]) if not df["Sukta"].dropna().empty else []
else:
    sukta_list = sorted([int(x) for x in df[df["Mandala"] == int(mandala_sel)]["Sukta"].dropna().unique().tolist()]) if not df[df["Mandala"] == int(mandala_sel)]["Sukta"].dropna().empty else []
sukta_opts = ["All"] + sukta_list
sukta_sel = st.sidebar.selectbox("Sukta", options=sukta_opts, index=0)

deity_opts = ["All"] + sorted(df["Deity"].dropna().unique().tolist())
deity_sel = st.sidebar.multiselect("Deity (multi-select)", options=deity_opts, default=["All"])

min_conf = float(df["Confidence"].min()) if not df["Confidence"].isna().all() else 0.0
max_conf = float(df["Confidence"].max()) if not df["Confidence"].isna().all() else 1.0
conf_range = st.sidebar.slider("Confidence range", min_value=0.0, max_value=1.0, value=(min_conf, max_conf), step=0.01)

# Apply filters
tmp = df.copy()

# Mandala filter
if mandala_sel != "All":
    tmp = tmp[tmp["Mandala"] == int(mandala_sel)]

# Sukta filter
if sukta_sel != "All":
    tmp = tmp[tmp["Sukta"] == int(sukta_sel)]

# Deity filter
if deity_sel and "All" not in deity_sel:
    tmp = tmp[tmp["Deity"].isin(deity_sel)]

# Confidence filter
tmp = tmp[(tmp["Confidence"] >= conf_range[0]) & (tmp["Confidence"] <= conf_range[1])]

# Search
if query:
    q = str(query).strip()
    if show_partial:
        mask = tmp["Transliteration"].str.contains(q, case=False, na=False) | tmp["Translation"].str.contains(q, case=False, na=False)
    else:
        mask = (tmp["Transliteration"].str.lower() == q.lower()) | (tmp["Translation"].str.lower() == q.lower())
    tmp = tmp[mask]

# Results count & simple pagination
total = len(tmp)
st.markdown(f"**Results:** {total}")

# Sort results for stable ordering
tmp = tmp.sort_values(["Mandala", "Sukta", "Verse"]).reset_index(drop=True)

# Pagination controls
per_page = st.selectbox("Rows per page", options=[10, 20, 50, 100], index=0)
page = st.number_input("Page", min_value=1, max_value=max(1, (total // per_page) + (1 if total % per_page else 0)), value=1, step=1)
start = (page - 1) * per_page
end = start + per_page
page_slice = tmp.iloc[start:end]

# Display results table (selectable)
if total == 0:
    st.info("No rows match the current filters/search.")
else:
    # Build display columns
    display_cols = [c for c in ["Mandala", "Sukta", "Verse", "Deity", "Confidence", "Transliteration"] if c in page_slice.columns]
    st.dataframe(page_slice[display_cols], use_container_width=True)

    st.markdown("---")
    st.subheader("Preview selected verse")
    # Allow user to pick an index from the current page to preview
    idx_options = list(range(start, min(end, total)))
    default_idx = idx_options[0] if idx_options else 0
    sel_idx = st.selectbox("Select row index to preview (global index)", options=idx_options, index=0 if idx_options else 0, format_func=lambda x: f"{x+1}/{total}")
    if idx_options:
        row = tmp.iloc[sel_idx]
        st.markdown(f"**Mandala {int(row['Mandala']) if pd.notna(row['Mandala']) else '-'} · Sukta {int(row['Sukta']) if pd.notna(row['Sukta']) else '-'} · Verse {int(row['Verse']) if pd.notna(row['Verse']) else '-'}**")
        st.write(f"**Deity:** {row['Deity']} · **Confidence:** {row['Confidence']:.2f}")
        st.markdown("**Transliteration**")
        st.code(row["Transliteration"] if row["Transliteration"] else "—")
        st.markdown("**Translation**")
        st.write(row["Translation"] if row["Translation"] else "—")

# Helpful tips
st.sidebar.markdown("---")
st.sidebar.markdown("Tips:\n- Use a short keyword (2–4 letters) for quick search.\n- Narrow with Mandala/Sukta to reduce false positives.\n- If results seem wrong, run `python ../Scripts/aggregate_griffith.py` to rebuild Data/rigveda.csv.")
