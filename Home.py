"""Route Delivery Dashboard - entry point.
Launch with:  streamlit run Home.py
"""
import streamlit as st

from lib.data import load_data
from lib.routes import detect_route_columns, annotate_service_days
from lib.refresh import render_refresh_section
from lib.filters import render_sidebar_filters
from lib.theme import inject_css, eyebrow_title, panel_open, panel_close

st.set_page_config(
    page_title="Route Delivery",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="expanded",
)
inject_css()

inv, dlv, vis, sm, rm, rm_error, sent = load_data()

if rm is None:
    st.error(
        "Cannot find `Route To Delivery Data/route_master.parquet`. "
        "Run first:  `python extract.py --route-master`. "
        + (f"Error: {rm_error}" if rm_error else "")
    )
    st.stop()

route_cols = detect_route_columns(rm)
if route_cols['service'] is None or route_cols['route_afs'] is None:
    st.error(
        f"Required columns not found in route master. "
        f"Detected: {list(rm.columns)}. "
        "Need at least 'Route_ID_AFS' and 'Service Days'."
    )
    st.stop()
rm = annotate_service_days(rm, route_cols['service'])

with st.sidebar:
    last_visit = vis['Visit_DateTime'].max() if not vis.empty else None
    render_refresh_section(last_visit)
    st.divider()
    filters = render_sidebar_filters(
        sm=sm, vis=vis, inv=inv, dlv=dlv, rm=rm, route_cols=route_cols,
    )

st.session_state['_rtd_data']    = (inv, dlv, vis, sm, rm, sent)
st.session_state['_rtd_routes']  = route_cols
st.session_state['_rtd_filters'] = filters

eyebrow_title("Route to Delivery", "Welcome")
panel_open()
st.markdown(
    "Choose a page from the sidebar:\n\n"
    "- **Daily Follow** — visit compliance for the selected date\n"
    "- **Sent vs Delivery** — warehouse units vs driver-recorded bunches\n"
    "- **Errors** — inventory mismatches: `Initial + Delivery − Credits − Final ≠ 0`\n"
    "- **7-Day Summary** — executive trend across the last 7 days"
)
panel_close()
