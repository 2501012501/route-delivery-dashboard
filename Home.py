"""Route Delivery Dashboard - entry point.
Launch with:  streamlit run Home.py
Lands the user on the Daily Follow page.
"""
import streamlit as st

st.set_page_config(
    page_title="Route Delivery",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="expanded",
)
st.switch_page("pages/1_Daily_Follow.py")
