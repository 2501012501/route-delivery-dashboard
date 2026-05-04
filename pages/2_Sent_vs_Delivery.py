"""Sent vs Delivery — warehouse units vs driver-recorded bunches."""
import streamlit as st

from lib.compute import latest_per
from lib.filters import apply_filters, routes_for_day
from lib.shell import setup
from lib.theme import (eyebrow_title, kpi, kpi_grid,
                        panel_close, panel_open)

st.set_page_config(page_title="Sent vs Delivery", layout="wide", page_icon="📦")
(inv, dlv, vis, sm, rm, sent), route_cols, f = setup()

eyebrow_title("Sent vs Delivery", f"Warehouse vs driver totals · {f['target_date'].strftime('%a %b %d, %Y')}")

if sent is None:
    panel_open()
    st.info(
        "ℹ️ Cannot find `data/deliveries.parquet`. Click **📦 Sent** "
        "in the sidebar (runs `extract.py --deliveries` + `Transform.py`)."
    )
    panel_close()
    st.stop()

vis_d = apply_filters(vis[vis['Visit_Date']   == f['target_date']], f, also_activity=True).copy()
dlv_d = apply_filters(dlv[dlv['Created_Date'] == f['target_date']], f).copy()
dlv_latest = latest_per(dlv_d, ['Store_Number','Product_EAN','Document_Type_Name'], 'Created_Time')

sent_d = sent[sent['DATE'] == f['target_date']].copy()
sent_d = sent_d.rename(columns={'STORE NUMBER WF': 'Store_Number'})
sent_d = apply_filters(sent_d, f)

routes_today = routes_for_day(
    rm,
    target_date=f['target_date'],
    cluster_filter=f['cluster_filter'],
    route_filter=f['route_filter'],
    route_cols=route_cols,
    show_all_routes=f['show_all_routes'],
    vis_d=vis_d, dlv_d=dlv_d, sent_d=sent_d,
)

sent_by_route = sent_d.groupby('Route_ID_AFS', dropna=False)['DELIVERY UNITS'].sum().rename('Sent')
delivered_by_route = (
    dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery']
    .groupby('Route_ID_AFS', dropna=False)['DeliveredBunches'].sum().rename('Delivered')
)

routes_short = routes_today[[route_cols['route_no'], route_cols['route_afs'], route_cols['cluster']]].rename(
    columns={
        route_cols['route_no']:  'Route No.',
        route_cols['route_afs']: 'Route_ID_AFS',
        route_cols['cluster']:   'Cluster',
    }
)
comp = (routes_short
        .merge(sent_by_route,      on='Route_ID_AFS', how='left')
        .merge(delivered_by_route, on='Route_ID_AFS', how='left'))
comp[['Sent', 'Delivered']] = comp[['Sent', 'Delivered']].fillna(0)
comp['Diff'] = comp['Delivered'] - comp['Sent']
comp['Compliance'] = comp.apply(
    lambda r: (r['Delivered'] / r['Sent'] * 100) if r['Sent'] > 0 else 0, axis=1
)

total_sent      = int(comp['Sent'].sum())
total_delivered = int(comp['Delivered'].sum())
variance        = total_delivered - total_sent

kpi_grid(
    kpi("Sent (units)", f"{total_sent:,}"),
    kpi("Delivered",    f"{total_delivered:,}", accent=True),
    kpi("Variance",     f"{variance:+,}"),
)

if comp[['Sent', 'Delivered']].sum().sum() == 0:
    panel_open()
    st.warning(
        f"No sent/delivered data for {f['target_date'].strftime('%a %b %d')}. "
        "If the date is very recent, refresh **📦 Sent**."
    )
    panel_close()
else:
    panel_open("Per route")
    comp_show = comp.sort_values('Compliance', ascending=False)
    st.dataframe(
        comp_show, use_container_width=True, hide_index=True,
        column_config={
            "Compliance": st.column_config.ProgressColumn(
                "Compliance", format="%.0f%%", min_value=0, max_value=100
            ),
            "Sent":      st.column_config.NumberColumn(format="%d"),
            "Delivered": st.column_config.NumberColumn(format="%d"),
            "Diff":      st.column_config.NumberColumn(format="%+d"),
        },
    )
    panel_close()
