import streamlit as st

st.set_page_config(page_title="AEMO Dashboard", page_icon="⚡", layout="wide")

st.markdown(
    """<style>
    div[data-testid="stAppViewContainer"] > section:first-child { padding-top: 1rem; }
    section[data-testid="stMain"] > div:first-child {
        max-width: 100% !important;
        width: 100% !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        box-sizing: border-box !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

pg = st.navigation([
    st.Page("pages/predispatch.py", title="Pre-Dispatch", icon="⚡"),
    st.Page("pages/stpasa.py",      title="Short Term PASA", icon="📊"),
    st.Page("pages/mtpasa.py",      title="Medium Term PASA", icon="📅"),
])
pg.run()
