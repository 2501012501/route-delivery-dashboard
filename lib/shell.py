"""Shared dashboard shell.

setup() is called at the top of every page (Home + pages/*). It loads
data, renders the sidebar (refresh + filters), and returns the data
tuple, route columns, and filter selections. Because the sidebar widgets
are rendered on every page, the filters are editable from anywhere.
Streamlit's default widget-state-by-key keeps the values consistent as
the user navigates.
"""
import streamlit as st

from lib.data import load_data
from lib.filters import render_sidebar_filters
from lib.refresh import render_refresh_section
from lib.routes import annotate_service_days, detect_route_columns
from lib.theme import inject_css


def setup():
    """Returns ((inv, dlv, vis, sm, rm, sent), route_cols, filters).

    Stops the app with a friendly error if required data is missing.
    """
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

    return (inv, dlv, vis, sm, rm, sent), route_cols, filters
