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
    """Header pill shows the LATEST VISIT in the data ('Last visit N min ago').
    That's the operationally relevant signal — it answers "how current are
    the realized visits?". The sync time is still shown inside the Data
    expander (refresh.py) for users who want to see when we last pulled.
    """
    epoch = _data_freshness_epoch(vis=vis)
    if epoch is not None:
        return f"Last visit {_format_ago(epoch)}"
    # Fallback: if no visit data yet, show sync time so the pill isn't blank.
    epoch = _last_synced_epoch()
    if epoch is None:
        return None
    return f"Synced {_format_ago(epoch)}"


def setup():
    """Returns ((inv, dlv, vis, sm, rm, sent), route_cols, filters).

    Stops the app with a friendly error if required data is missing.
    Renders the persistent top header (brand + freshness pill).
    """
    inject_css()

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
