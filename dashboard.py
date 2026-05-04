"""Route Delivery Dashboard - entry point (legacy filename).
Lands the user on the Daily Follow page.

Streamlit Cloud is configured to run this file. Locally, prefer
`streamlit run Home.py` — both end up on the Daily Follow page.
"""
import streamlit as st

st.set_page_config(
    page_title="Route Delivery",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="expanded",
)
st.switch_page("pages/1_Daily_Follow.py")
