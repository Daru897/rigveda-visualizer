# App/verse_browser.py
"""
Verse Browser (Streamlit page)
- Cascading dropdowns: Mandala -> Sukta -> Verse
- Next / Previous navigation
- Styled with Indra Palette and font hooks:
    - Inter for UI (Google fallback)
    - Noto Serif for translations (Google fallback)
    - Siddhanta for transliteration if available locally (fallback to monospace)
- Looks for local fonts in App/Assests/fonts/ (recommended)
- Uses shared loader: App._utils.load_dataset()
"""
from pathlib import Path
import sys

# --- Robust import path so this file can be run by Streamlit from project root ---
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now import utilities
try:
    from App.utils import load_dataset, normalize_df
except Exception:
    # fallback if App package not available (best-effort)
    def load_dataset():
        import pandas as pd
        return pd.DataFrame([])
    def normalize_df(df):
        return df

import streamlit as st
import pandas as pd

# Page config
st.set_page_config(page_title="Rig Veda Visualizer — Verse Browser", layout="wide", initial_sidebar_state="expanded")

# --- Theme & Fonts / CSS ---
# Colors (Indra Palette)
STORM_BLUE = "#1E3A8A"
LIGHTNING_YELLOW = "#FACC15"
RAIN_GRAY = "#9CA3AF"
TEXT_ON_DARK = "#FFFFFF"

# Font files location (if you placed local fonts)
LOCAL_FONT_DIR = SCRIPT_PATH.parent / "Assests" / "fonts"  # note: you used "Assests" in tree
siddhanta_path = LOCAL_FONT_DIR / "Siddhanta-Regular.ttf"   # optional
noto_serif_path = LOCAL_FONT_DIR / "NotoSerif-Regular.ttf"
inter_path = LOCAL_FONT_DIR / "Inter-Regular.ttf"

# Build CSS: try local fonts first, else load from Google Fonts for Inter + Noto Serif.
css_parts = []

# Font-face local loading if files exist
if siddhanta_path.exists():
    css_parts.append(f"""
    @font-face {{
      font-family: 'SiddhantaLocal';
      src: url('Assests/fonts/{siddhanta_path.name}') format('truetype');
      font-weight: normal;
      font-style: normal;
    }}
    """)
    siddhanta_css_family = "SiddhantaLocal"
else:
    siddhanta_css_family = "monospace"

if noto_serif_path.exists():
    css_parts.append(f"""
    @font-face {{
      font-family: 'NotoSerifLocal';
      src: url('Assests/fonts/{noto_serif_path.name}') format('truetype');
      font-weight: normal;
      font-style: normal;
    }}
    """)
    noto_css_family = "NotoSerifLocal"
else:
    noto_css_family = "'Noto Serif', serif"

if inter_path.exists():
    css_parts.append(f"""
    @font-face {{
      font-family: 'InterLocal';
      src: url('Assests/fonts/{inter_path.name}') format('truetype');
      font-weight: 400 700;
      font-style: normal;
    }}
    """)
    inter_css_family = "InterLocal"
else:
    # Load Google fonts for Inter and Noto Serif if local not present
    css_parts.append("@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Noto+Serif:ital@0;1&display=swap');")
    inter_css_family = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial"

# Main CSS styling (palette, layout, font usage)
css_parts.append(f"""
:root {{
  --storm-blue: {STORM_BLUE};
  --lightning-yellow: {LIGHTNING_YELLOW};
  --rain-gray: {RAIN_GRAY};
  --text-on-dark: {TEXT_ON_DARK};
}}

body .stApp {{
  background: var(--storm-blue);
  color: var(--text-on-dark);
}}

.main-card {{
  background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.02));
  border-radius: 12px;
  padding: 22px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.25);
}}

.title {{
  font-family: {inter_css_family};
  font-size: 34px;
  font-weight: 700;
  color: var(--text-on-dark);
  margin-bottom: 6px;
}}

.subtitle {{
  font-family: {inter_css_family};
  color: rgba(255,255,255,0.9);
  margin-bottom: 14px;
}}

.tag {{
  font-family: {inter_css_family};
  font-size: 13px;
  color: var(--rain-gray);
}}

.btn-primary {{
  background: linear-gradient(90deg, var(--lightning-yellow), #facc40);
  color: #000;
  padding: 10px 18px;
  border-radius: 8px;
  font-weight: 700;
  border: none;
  cursor: pointer;
}}

.nav-btn {{
  background: transparent;
  color: var(--lightning-yellow);
  border: 1px solid rgba(250,250,250,0.08);
  padding: 8px 12px;
  border-radius: 8px;
}}

.transliteration {{
  font-family: {siddhanta_css_family};
  font-size: 16px;
  white-space: pre-wrap;
  line-height: 1.6;
  color: #fff;
  background: rgba(255,255,255,0.03);
  padding: 12px;
  border-radius: 8px;
}}

.translation {{
  font-family: {noto_css_family};
  font-style: italic;
  font-size: 15px;
  color: #f0f4ff;
  padding: 12px;
  border-radius: 8px;
  background: rgba(0,0,0,0.05);
}}
.sidebar .sidebar-content {{
  background: rgba(255,255,255,0.02);
}}
""")

# Inject CSS
st.markdown("<style>{}</style>".format("\n".join(css_parts)), unsafe_allow_html=True)

# --- Load dataset using shared utils ---
df = load_dataset()
if df is None or df.shape[0] == 0:
    st.warning("No dataset found. Run `python Scripts/aggregate_griffith.py` to build Data/rigveda.csv or place a CSV at Data/rigveda.csv.")
    st.stop()

df = normalize_df(df)

# Ensure core columns exist
for col in ["Mandala", "Sukta", "Verse", "Deity", "Transliteration", "Translation", "Confidence"]:
    if col not in df.columns:
        df[col] = pd.NA

# Sidebar controls (styled by CSS above)
st.sidebar.header("Browse Mantras")
st.sidebar.markdown("Select Mandala → Sukta → Verse")

# Mandala dropdown
mandala_values = sorted([int(x) for x in df["Mandala"].dropna().unique().tolist()]) if not df["Mandala"].dropna().empty else []
mandala_choice = st.sidebar.selectbox("Mandala", options=["All"] + mandala_values, index=0)

# Filter df by mandala
if mandala_choice == "All":
    df_m = df.copy()
else:
    df_m = df[df["Mandala"] == int(mandala_choice)]

# Sukta dropdown depending on mandala
sukta_values = sorted([int(x) for x in df_m["Sukta"].dropna().unique().tolist()]) if not df_m["Sukta"].dropna().empty else []
sukta_choice = st.sidebar.selectbox("Sukta", options=["All"] + sukta_values, index=0)

# Verse dropdown depending on sukta
if sukta_choice == "All":
    df_ms = df_m.copy()
else:
    df_ms = df_m[df_m["Sukta"] == int(sukta_choice)]

verse_values = sorted([int(x) for x in df_ms["Verse"].dropna().unique().tolist()]) if not df_ms["Verse"].dropna().empty else []
verse_choice = st.sidebar.selectbox("Verse", options=["Select"] + verse_values, index=0)

# Deity filter & confidence
deities = sorted(df["Deity"].dropna().unique().tolist())
deity_filter = st.sidebar.multiselect("Deity (optional)", options=deities, default=None)

min_conf = float(df["Confidence"].min()) if not df["Confidence"].isna().all() else 0.0
max_conf = float(df["Confidence"].max()) if not df["Confidence"].isna().all() else 1.0
conf_range = st.sidebar.slider("Confidence range", min_value=0.0, max_value=1.0, value=(min_conf, max_conf), step=0.01)

# Apply filters & build working set
working = df.copy()
if mandala_choice != "All":
    working = working[working["Mandala"] == int(mandala_choice)]
if sukta_choice != "All":
    working = working[working["Sukta"] == int(sukta_choice)]
if verse_choice != "Select":
    working = working[working["Verse"] == int(verse_choice)]
if deity_filter:
    working = working[working["Deity"].isin(deity_filter)]
working = working[(working["Confidence"] >= conf_range[0]) & (working["Confidence"] <= conf_range[1])]
working = working.sort_values(["Mandala", "Sukta", "Verse"]).reset_index(drop=True)

# Header / main card
st.markdown("<div class='main-card'>", unsafe_allow_html=True)
st.markdown("<div style='display:flex; justify-content:space-between; align-items:center;'>", unsafe_allow_html=True)
st.markdown(f"<div><div class='title'>Rig Veda Visualizer</div><div class='subtitle'>Explore mantras by Mandala, Sukta & Verse</div></div>", unsafe_allow_html=True)
# small action on right
st.markdown(f"<div><button class='btn-primary' onclick=\"(function(){{window.location.search='?page=landing';}})()\">Home</button></div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# session state index for navigation within working set
if "vb_idx" not in st.session_state:
    st.session_state.vb_idx = 0
# reset index if filters changed
sig = f"{mandala_choice}|{sukta_choice}|{verse_choice}|{','.join(deity_filter or [])}|{conf_range}"
if st.session_state.get("vb_prev_sig") != sig:
    st.session_state.vb_idx = 0
    st.session_state.vb_prev_sig = sig

total = len(working)
col1, col2, col3 = st.columns([1, 6, 1])
with col1:
    if st.button("Previous", key="prev_btn"):
        if total > 0:
            st.session_state.vb_idx = max(0, st.session_state.vb_idx - 1)
with col3:
    if st.button("Next", key="next_btn"):
        if total > 0:
            st.session_state.vb_idx = min(total - 1, st.session_state.vb_idx + 1)
with col2:
    st.markdown(f"**Verse {st.session_state.vb_idx + 1} of {total}**")

st.markdown("---")

if total == 0:
    st.warning("No verses found for current filters.")
else:
    row = working.iloc[st.session_state.vb_idx]
    mand = int(row["Mandala"]) if pd.notna(row["Mandala"]) else "-"
    suk = int(row["Sukta"]) if pd.notna(row["Sukta"]) else "-"
    ver = int(row["Verse"]) if pd.notna(row["Verse"]) else "-"
    deity = row["Deity"] if pd.notna(row["Deity"]) else "Unknown"
    conf = float(row["Confidence"]) if pd.notna(row["Confidence"]) else 0.0

    st.markdown(f"### Mandala {mand} · Sukta {suk} · Verse {ver}")
    st.markdown(f"**Deity:** {deity}    ·    **Confidence:** {conf:.2f}")
    st.markdown("---")
    left_col, right_col = st.columns([1, 2])
    with left_col:
        st.markdown("**Transliteration**")
        st.markdown(f"<div class='transliteration'>{row['Transliteration'] if row['Transliteration'] else '—'}</div>", unsafe_allow_html=True)
    with right_col:
        st.markdown("**Translation**")
        st.markdown(f"<div class='translation'>{row['Translation'] if row['Translation'] else '—'}</div>", unsafe_allow_html=True)

# Expander to show a small table of the filtered set
with st.expander("Show filtered verse list (table)"):
    show_cols = [c for c in ["Mandala", "Sukta", "Verse", "Deity", "Confidence", "Transliteration"] if c in working.columns]
    st.dataframe(working[show_cols], use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

# Footer hints
st.markdown(
    f"""
    <div style='margin-top:12px; color:#e6eefc;'>
      <small>Tip: Use the sidebar to narrow results. Theme: Storm Blue background · Lightning Yellow CTAs · Rain Gray accents.</small>
    </div>
    """,
    unsafe_allow_html=True,
)
