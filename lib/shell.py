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
from lib.refresh import (_data_freshness_epoch, _format_ago,
                          _last_synced_epoch, render_refresh_section)
from lib.routes import annotate_service_days, detect_route_columns
from lib.theme import inject_css, top_header


def _format_freshness(vis=None) -> str | None:
    """Header pill shows 'Last activity N min ago' from Sys_LastChange (Retex's
    row-level last-modified). That advances within minutes of real-time as
    drivers complete and update visits. Sync time is shown inside the Data
    expander as a secondary 'is the pipeline alive' indicator.
    """
    epoch = _data_freshness_epoch(vis=vis)
    if epoch is not None:
        return f"Last activity {_format_ago(epoch)}"
    # Fallback: if no visit data yet, show sync time so the pill isn't blank.
    epoch = _last_synced_epoch()
    if epoch is None:
        return None
    return f"Synced {_format_ago(epoch)}"


def _render_sidebar_toggle():
    """Custom toggle button (☰ / ✕) pinned top-left to hide/show the sidebar.
    Replaces Streamlit's built-in collapse/expand which doesn't render its
    expand arrow correctly on Streamlit 1.57+. Uses session_state so the
    state persists across reruns within a session.
    """
    if 'sidebar_hidden' not in st.session_state:
        st.session_state.sidebar_hidden = False

    # Wrap the button in a keyed container so we can pin it via CSS.
    # Streamlit adds a class `st-key-rtd-sidebar-toggle` to the wrapper.
    with st.container(key="rtd-sidebar-toggle"):
        label = "☰" if st.session_state.sidebar_hidden else "✕"
        if st.button(label, key="rtd_sb_toggle_btn",
                     help="Show / hide the sidebar"):
            st.session_state.sidebar_hidden = not st.session_state.sidebar_hidden
            st.rerun()

    if st.session_state.sidebar_hidden:
        st.markdown(
            '<style>'
            'section[data-testid="stSidebar"]{display:none !important;}'
            '[data-testid="stAppViewContainer"] > section.main,'
            '[data-testid="stAppViewContainer"] > div.main {'
            'margin-left:0 !important;max-width:100% !important;'
            '}'
            '</style>',
            unsafe_allow_html=True,
        )


def setup():
    """Returns ((inv, dlv, vis, sm, rm, sent), route_cols, filters).

    Stops the app with a friendly error if required data is missing.
    Renders the persistent top header (brand + freshness pill).
    """
    inject_css()
    _render_sidebar_toggle()

    inv, dlv, vis, sm, rm, rm_error, sent = load_data()
    # Compute freshness from data content (same on local + Cloud) before rendering header
    top_header(_format_freshness(vis=vis))

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
        render_refresh_section(last_visit, vis=vis)
        st.divider()
        filters = render_sidebar_filters(
            sm=sm, vis=vis, inv=inv, dlv=dlv, rm=rm, route_cols=route_cols,
        )

    return (inv, dlv, vis, sm, rm, sent), route_cols, filters
