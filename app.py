import streamlit as st

st.set_page_config(page_title="AEMO Dashboard", page_icon="⚡", layout="wide")

st.markdown(
    """<style>
    div[data-testid="stAppViewContainer"] > section:first-child { padding-top: 1rem; }
    div[data-testid="stAppViewBlockContainer"] { max-width: 100%; padding-left: 1rem; padding-right: 1rem; }
    </style>""",
    unsafe_allow_html=True,
)

pg = st.navigation([
    st.Page("pages/predispatch.py", title="Pre-Dispatch", icon="⚡"),
    st.Page("pages/stpasa.py",      title="Short Term PASA", icon="📊"),
    st.Page("pages/mtpasa.py",      title="Medium Term PASA", icon="📅"),
])
pg.run()
