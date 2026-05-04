"""Deprecated entry point. Use Home.py instead."""
import streamlit as st

st.set_page_config(page_title="Route Delivery (legacy)", page_icon="🚚")
st.error(
    "This entry point is deprecated. Run the dashboard with:\n\n"
    "```\n"
    "python -m streamlit run Home.py\n"
    "```"
)
st.stop()
