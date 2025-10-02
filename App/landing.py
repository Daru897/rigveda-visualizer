# App/landing.py
"""
Landing page for Rig Veda Visualizer

Features:
- Centered title + tagline
- CTA button "Explore Mantras" that navigates to the Verse Browser page
- Minimalistic background, optional logo if App/assets/logo.png exists
- Small CSS to keep layout tidy
"""
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Rig Veda Visualizer", layout="wide", initial_sidebar_state="collapsed")

# --- simple styling (center layout, minimal background) ---
st.markdown(
    """
    <style>
    /* Page background */
    .stApp {
        background: linear-gradient(0deg, rgba(255,255,255,0.02), rgba(255,255,255,0.02));
        min-height:100vh;
    }
    /* Center the main block */
    .landing-container{
        display:flex;
        align-items:center;
        justify-content:center;
        min-height:60vh;
        padding:40px;
    }
    .card {
        max-width:900px;
        width:100%;
        text-align:center;
        padding:36px 48px;
        border-radius:16px;
        box-shadow: 0 6px 24px rgba(14,30,37,0.08);
        background: rgba(255,255,255,0.02);
        backdrop-filter: blur(4px);
    }
    .title {
        font-size:42px;
        font-weight:700;
        margin-bottom:6px;
    }
    .tagline {
        font-size:18px;
        color: #666;
        margin-bottom:22px;
    }
    .cta {
        display:inline-block;
        padding:12px 26px;
        border-radius:10px;
        font-weight:600;
        text-decoration:none;
    }
    .logo {
        max-height:84px;
        margin-bottom:18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Optional logo (App/assets/logo.png) ---
logo_path = Path(__file__).parent / "Assests" / "logo.png"
logo_tag = ""
if logo_path.exists():
    # display centered logo
    st.markdown(f"<div style='text-align:center'><img src='assets/logo.png' class='logo' alt='Rig Veda Logo' /></div>", unsafe_allow_html=True)
else:
    # small decorative placeholder (no image)
    st.write("")  # keep spacing

# --- Main landing card ---
st.markdown("<div class='landing-container'><div class='card'>", unsafe_allow_html=True)

st.markdown("<div class='title'>Rig Veda Visualizer</div>", unsafe_allow_html=True)
st.markdown("<div class='tagline'>Explore the sacred mantras with search, navigation, and insights.</div>", unsafe_allow_html=True)

# CTA button: try to navigate to the Verse Browser page by setting query param 'page'
# (Streamlit multi-page apps respond to '?page=<name>' in many setups).
cta_clicked = st.button("Explore Mantras", key="cta_explore")

if cta_clicked:
    # set the page query parameter to 'main' (the filename without .py for your Verse Browser)
    # then rerun so Streamlit switches to that page if multipage is enabled.
    try:
        st.experimental_set_query_params(page="main")
    except Exception:
        # older/newer Streamlit versions may differ; fallback to a link that user can click
        st.markdown("Could not auto-navigate. Use the left page selector or click this link: [Go to Verse Browser](?page=main)")
    st.experimental_rerun()

# Friendly small-note under CTA
st.markdown("<div style='margin-top:14px; color:#888;'>Start browsing by selecting a Mandala, Sukta & Verse.</div>", unsafe_allow_html=True)

st.markdown("</div></div>", unsafe_allow_html=True)

# Footer quick links (small)
with st.container():
    cols = st.columns([1,1,1])
    with cols[0]:
        st.markdown("**Get started**")
        st.markdown("- Explore Mantras")
    with cols[1]:
        st.markdown("**Data**")
        st.markdown("- Aggregated: Data/rigveda.csv")
    with cols[2]:
        st.markdown("**Help**")
        st.markdown("- Run `python Scripts/aggregate_griffith.py` if data missing")
