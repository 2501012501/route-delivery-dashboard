"""Daily Follow — visit compliance for the selected date."""
import pandas as pd
import streamlit as st

from lib.compute import (cluster_compliance_data, latest_per,
                          store_day_summary, store_status)
from lib.filters import apply_filters, routes_for_day
from lib.shell import setup
from lib.theme import (NAVY, BLUE, PALE_BLUE, BORDER, SLATE,
                        kpi, kpi_grid, page_header,
                        panel_close, panel_open, pill)

# Status -> emoji mapping for visual indicators in tables and filters.
# Plain-text status is the source of truth (computed by store_status / below);
# emojis are added at render time only.
_STATUS_EMOJI = {
    'Visited':     '🟢 Visited',
    'In progress': '🟡 In progress',
    'Pending':     '⚪ Pending',
}


def _route_status(compliance_pct: float, planned: int) -> str:
    """Derive a route-level status from its compliance percentage.
    Pending if no stores planned or no visits; Visited at 100%; In progress otherwise.
    """
    if planned == 0 or compliance_pct == 0:
        return 'Pending'
    if compliance_pct >= 100:
        return 'Visited'
    return 'In progress'


def _status_filter(key: str) -> str:
    """Render a horizontal radio for filtering by status.
    Returns the selected plain status, or '(All)'.
    """
    choice = st.radio(
        "Status",
        ['(All)', '🟢 Visited', '🟡 In progress', '⚪ Pending'],
        horizontal=True, key=key, label_visibility="collapsed",
    )
    return '(All)' if choice == '(All)' else choice.split(' ', 1)[1]

st.set_page_config(page_title="Daily Follow", layout="wide", page_icon="📅")
(inv, dlv, vis, sm, rm, sent), route_cols, f = setup()

# Day-filtered fact frames first (needed to compute "active" routes).
inv_d = apply_filters(inv[inv['Answer_Date']  == f['target_date']], f).copy()
dlv_d = apply_filters(dlv[dlv['Created_Date'] == f['target_date']], f).copy()
vis_d = apply_filters(vis[vis['Visit_Date']   == f['target_date']], f, also_activity=True).copy()

routes_today = routes_for_day(
    rm,
    target_date=f['target_date'],
    cluster_filter=f['cluster_filter'],
    route_filter=f['route_filter'],
    route_cols=route_cols,
    show_all_routes=f['show_all_routes'],
    vis_d=vis_d, dlv_d=dlv_d,
)

inv_latest = latest_per(inv_d, ['Store_Number','Product_EAN','Monitoring_Name'], 'Answer_Time')
dlv_latest = latest_per(dlv_d, ['Store_Number','Product_EAN','Document_Type_Name'], 'Created_Time')

# KPIs — "Planned" = stores attached to the routes_today set
visited_stores = vis_d['Store_Number'].nunique()
expected_route_ids = routes_today[route_cols['route_afs']].dropna().unique().tolist()
expected_stores = sm[sm['Route_ID_AFS'].isin(expected_route_ids)]
if f['cluster_filter'] != '(All)':
    expected_stores = expected_stores[
        expected_stores['CLUSTER FULL'].astype(str).str.strip().str.upper() == f['cluster_filter']
    ]
if f['customer_filter'] != '(All)':
    expected_stores = expected_stores[expected_stores['CUSTOMER'] == f['customer_filter']]
total_expected = expected_stores['Store_Number'].nunique()

in_progress_count = 0
pending_count = 0
if not routes_today.empty:
    s_all = store_day_summary(
        target_route_ids=routes_today[route_cols['route_afs']].dropna().unique().tolist(),
        sm=sm, vis_d=vis_d, dlv_latest=dlv_latest, inv_latest=inv_latest,
        cluster_filter=f['cluster_filter'],
        customer_filter=f['customer_filter'],
        store_filter=f['store_filter'],
    )
    s_all['Status'] = s_all.apply(store_status, axis=1)
    in_progress_count = int((s_all['Status'] == 'In progress').sum())
    pending_count     = int((s_all['Status'] == 'Pending').sum())

page_header(
    eyebrow="Daily Follow",
    title="Visit Compliance",
    badge=f['target_date'].strftime('%a · %b %d, %Y'),
    subtitle="Per-route and per-store compliance for the selected day.",
)

kpi_grid(
    kpi("Planned",      f"{total_expected:,}"),
    kpi("Visited",      f"{visited_stores:,}", accent=True),
    kpi("In progress",  f"{in_progress_count:,}"),
    kpi("Pending",      f"{pending_count:,}"),
)

# Cluster compliance panel
cl_df = cluster_compliance_data(
    routes_today=routes_today, sm=sm, vis_d=vis_d, route_cols=route_cols,
    customer_filter=f['customer_filter'], store_filter=f['store_filter'],
)
panel_open("Cluster compliance")
if cl_df.empty:
    st.caption("No routes matching filters.")
else:
    for _, row in cl_df.iterrows():
        pct = float(row['Pct'])
        c1, c2, c3 = st.columns([1.5, 4, 1])
        c1.markdown(
            f'<div style="font-weight:600;color:{NAVY};">{row["Cluster"]}'
            f'<span style="color:{SLATE};font-weight:500;font-size:11px;margin-left:6px;">'
            f'{int(row["Visited"])}/{int(row["Planned"])}</span></div>',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f'<div style="background:{PALE_BLUE};border-radius:999px;height:14px;overflow:hidden;">'
            f'<div style="background:{BLUE};height:100%;width:{min(pct,1)*100:.1f}%;"></div></div>',
            unsafe_allow_html=True,
        )
        c3.markdown(f'<div style="text-align:right;font-weight:700;color:{NAVY};">{pct:.0%}</div>',
                    unsafe_allow_html=True)
panel_close()

# Route summary / detail toggle
if routes_today.empty:
    panel_open()
    st.info("No routes scheduled with the selected filters.")
    panel_close()
else:
    view_mode = st.radio(
        "View", ["Route summary", "Route detail"],
        horizontal=True, key="view_mode_dia", label_visibility="collapsed",
    )

    if view_mode == "Route summary":
        rows = []
        for _, r in routes_today.iterrows():
            rid = r[route_cols['route_afs']]
            s = store_day_summary(
                target_route_ids=[rid], sm=sm, vis_d=vis_d,
                dlv_latest=dlv_latest, inv_latest=inv_latest,
                cluster_filter=f['cluster_filter'],
                customer_filter=f['customer_filter'],
                store_filter=f['store_filter'],
            )
            planned = len(s)
            visited = int((s['Visited'] > 0).sum())
            compliance = (visited / planned * 100) if planned else 0
            rows.append({
                'Status':       _route_status(compliance, planned),
                'Route No.':    r[route_cols['route_no']] if route_cols['route_no'] else '',
                'Route_ID_AFS': rid,
                'Cluster':      r[route_cols['cluster']] if route_cols['cluster'] else '',
                'Compliance':   compliance,
                'Visited':      visited,
                'Planned':      planned,
                'Bunches':      int(s['Bunches_Delivered'].sum()),
                'Credits':      int(s['Bunches_Credit'].sum()),
                'Errors':       int(s['Errors'].sum()),
            })
        df_routes = pd.DataFrame(rows).sort_values('Compliance', ascending=False)
        panel_open("Routes")
        sel_status = _status_filter("rs_status_filter")
        if sel_status != '(All)':
            df_routes = df_routes[df_routes['Status'] == sel_status]
        df_display = df_routes.copy()
        df_display['Status'] = df_display['Status'].map(_STATUS_EMOJI).fillna(df_display['Status'])
        st.dataframe(
            df_display,
            use_container_width=True, hide_index=True,
            column_config={
                "Status":     st.column_config.TextColumn("Status", width="small"),
                "Compliance": st.column_config.ProgressColumn(
                    "Compliance", format="%.0f%%", min_value=0, max_value=100
                ),
            },
        )
        panel_close()
    else:
        route_options = routes_today[route_cols['route_afs']].dropna().unique().tolist()
        chosen = st.selectbox("Route", route_options, key="route_detail_select")
        s = store_day_summary(
            target_route_ids=[chosen], sm=sm, vis_d=vis_d,
            dlv_latest=dlv_latest, inv_latest=inv_latest,
            cluster_filter=f['cluster_filter'],
            customer_filter=f['customer_filter'],
            store_filter=f['store_filter'],
        )
        s['Status'] = s.apply(store_status, axis=1)

        kpi_grid(
            kpi("Visited",     f"{int((s['Status']=='Visited').sum())} / {len(s)}", accent=True),
            kpi("In progress", f"{int((s['Status']=='In progress').sum())}"),
            kpi("Pending",     f"{int((s['Status']=='Pending').sum())}"),
        )

        cols_show = ['Status', 'Store_Number', 'CUSTOMER', 'CLUSTER FULL',
                     'First_Visit', 'Last_Visit', 'Avg_Duration_min',
                     'Bunches_Delivered', 'Bunches_Credit',
                     'Initial_Inv', 'Final_Inv', 'Errors']
        display = s[[c for c in cols_show if c in s.columns]].copy()
        panel_open(f"Stores · {chosen}")
        sel_status = _status_filter("rd_status_filter")
        if sel_status != '(All)':
            display = display[display['Status'] == sel_status]
        display['Status'] = display['Status'].map(_STATUS_EMOJI).fillna(display['Status'])
        st.dataframe(display, use_container_width=True, hide_index=True)
        panel_close()
