"""Sidebar filter widgets + apply_filters helper + route-day selection.

The filter widgets store their selections in st.session_state via Streamlit's
default key-by-label behavior. apply_filters() reads the current selections
from the dict returned by render_sidebar_filters() — so each page calls
both, in order.
"""
from datetime import date

import pandas as pd
import streamlit as st


def render_sidebar_filters(*, sm, vis, inv, dlv, rm, route_cols) -> dict:
    """Render the filter widgets in st.sidebar and return the selections.

    `route_cols` is the dict returned by lib.routes.detect_route_columns(rm).
    """
    st.header("Filters")

    available_dates = sorted(
        set(inv['Answer_Date']) | set(dlv['Created_Date']) | set(vis['Visit_Date'].dropna())
    )
    default_date = max(available_dates) if available_dates else date.today()
    target_date = st.date_input(
        "Date", value=default_date,
        min_value=min(available_dates) if available_dates else None,
        max_value=max(available_dates) if available_dates else None,
    )

    rm_clusters = (rm[route_cols['cluster']].dropna().astype(str).str.strip().str.upper().unique()
                   if route_cols['cluster'] else [])
    sm_full = sm['CLUSTER FULL'].dropna().astype(str).str.strip().str.upper().unique()
    cluster_options = ['(All)'] + sorted(set(rm_clusters) & set(sm_full))
    cluster_filter = st.selectbox("Cluster", cluster_options)

    customer_options = sorted(sm['CUSTOMER'].dropna().unique().tolist())
    customer_filter = st.multiselect("Customer", customer_options, default=customer_options)

    sm_filtered = sm.copy()
    if cluster_filter != '(All)':
        sm_filtered = sm_filtered[
            sm_filtered['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter
        ]
    if customer_filter:
        sm_filtered = sm_filtered[sm_filtered['CUSTOMER'].isin(customer_filter)]
    route_options = sorted(sm_filtered['Route_ID_AFS'].dropna().unique().tolist())
    route_filter = st.multiselect(
        "Route (Route_ID_AFS)", route_options,
        help="Empty = all routes matching the other filters",
    )

    if route_filter:
        sm_filtered = sm_filtered[sm_filtered['Route_ID_AFS'].isin(route_filter)]
    store_options = sorted(sm_filtered['Store_Number'].dropna().unique().tolist())
    store_filter = st.multiselect(
        "Store (Store_Number)", store_options, help="Empty = all stores",
    )

    KNOWN_ACTIVITIES = ['Driver Merchandiser Visit', 'Supervisor Visit']
    if 'Activity_Type' in vis.columns:
        at_options = sorted(set(vis['Activity_Type'].dropna().unique().tolist()) | set(KNOWN_ACTIVITIES))
    else:
        at_options = KNOWN_ACTIVITIES
    activity_filter = st.multiselect(
        "Activity Type", at_options, default=at_options,
        help="If filtering shows no change, refresh the API (🔁) — the field isn't in the loaded data yet.",
    )

    show_all_routes = st.checkbox(
        "Show all routes (even without schedule or activity)",
        value=False,
        help="When OFF (default), the dashboard shows routes scheduled for the day "
             "PLUS routes that had activity (visits/deliveries) — even if not scheduled. "
             "Turn ON to see every route in the route master regardless.",
    )

    return {
        'target_date':     target_date,
        'cluster_filter':  cluster_filter,
        'customer_filter': customer_filter,
        'route_filter':    route_filter,
        'store_filter':    store_filter,
        'activity_filter': activity_filter,
        'show_all_routes': show_all_routes,
    }


def apply_filters(df: pd.DataFrame, f: dict, *, also_activity: bool = False) -> pd.DataFrame:
    """Apply the selections from render_sidebar_filters(...) to a fact dataframe."""
    if f['cluster_filter'] != '(All)' and 'CLUSTER FULL' in df.columns:
        df = df[df['CLUSTER FULL'].astype(str).str.strip().str.upper() == f['cluster_filter']]
    if f['customer_filter'] and 'CUSTOMER' in df.columns:
        df = df[df['CUSTOMER'].isin(f['customer_filter'])]
    if f['route_filter'] and 'Route_ID_AFS' in df.columns:
        df = df[df['Route_ID_AFS'].isin(f['route_filter'])]
    if f['store_filter'] and 'Store_Number' in df.columns:
        df = df[df['Store_Number'].isin(f['store_filter'])]
    if also_activity and f['activity_filter'] and 'Activity_Type' in df.columns:
        df = df[df['Activity_Type'].isin(f['activity_filter'])]
    return df


def _active_route_ids(*frames) -> set:
    """Collect Route_ID_AFS values that appear in any of the given (day-filtered) frames."""
    ids = set()
    for df in frames:
        if df is None or df.empty or 'Route_ID_AFS' not in df.columns:
            continue
        ids |= set(df['Route_ID_AFS'].dropna().unique())
    return ids


def routes_for_day(rm: pd.DataFrame, *, target_date, cluster_filter, route_filter,
                   route_cols: dict, show_all_routes: bool,
                   vis_d=None, dlv_d=None, sent_d=None) -> pd.DataFrame:
    """Subset of rm to show on the page for target_date.

    Default (show_all_routes=False):
        scheduled-for-day ∪ active-on-day
        — scheduled = `_days` contains today's dow
        — active    = Route_ID_AFS appears in vis_d / dlv_d / sent_d

    Override (show_all_routes=True):
        every route in rm.

    Cluster + route filters always apply on top.
    """
    routes_today = rm.copy()

    if not show_all_routes:
        dow = target_date.strftime('%a')
        scheduled_mask = routes_today['_days'].apply(lambda s: dow in s)
        active_ids = _active_route_ids(vis_d, dlv_d, sent_d)
        if active_ids:
            active_mask = routes_today[route_cols['route_afs']].isin(active_ids)
            routes_today = routes_today[scheduled_mask | active_mask]
        else:
            routes_today = routes_today[scheduled_mask]

    if cluster_filter != '(All)' and route_cols['cluster']:
        routes_today = routes_today[
            routes_today[route_cols['cluster']].astype(str).str.strip().str.upper() == cluster_filter
        ]
    if route_filter:
        routes_today = routes_today[routes_today[route_cols['route_afs']].isin(route_filter)]
    return routes_today
