"""Sent vs Delivery — warehouse units vs driver-recorded bunches."""
import pandas as pd
import streamlit as st

from lib.compute import latest_per
from lib.filters import apply_filters, routes_for_day
from lib.shell import setup
from lib.theme import (kpi, kpi_grid, page_header,
                        panel_close, panel_open)

st.set_page_config(page_title="Sent vs Delivery", layout="wide", page_icon="📦")
(inv, dlv, vis, sm, rm, sent), route_cols, f = setup()

page_header(
    eyebrow="Sent vs Delivery",
    title="Warehouse vs Driver Totals",
    badge=f['target_date'].strftime('%a · %b %d, %Y'),
    subtitle="DELIVERY UNITS sent from warehouse vs DeliveredBunches recorded by drivers.",
)

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

    # Per-store breakdown — same comparison, store granularity
    sent_by_store = sent_d.groupby('Store_Number', dropna=False)['DELIVERY UNITS'].sum().rename('Sent')
    delivered_by_store = (
        dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery']
        .groupby('Store_Number', dropna=False)['DeliveredBunches'].sum().rename('Delivered')
    )
    store_meta = sm[['Store_Number', 'Route_ID_AFS', 'CUSTOMER', 'CLUSTER FULL']].copy()
    store_meta = store_meta.merge(
        rm[[route_cols['route_afs'], route_cols['route_no']]].rename(
            columns={route_cols['route_afs']: 'Route_ID_AFS',
                     route_cols['route_no']:  'Route No.'}
        ),
        on='Route_ID_AFS', how='left',
    )

    store_comp = (
        pd.concat([sent_by_store, delivered_by_store], axis=1)
          .reset_index()
          .merge(store_meta, on='Store_Number', how='left')
    )
    store_comp[['Sent', 'Delivered']] = store_comp[['Sent', 'Delivered']].fillna(0)
    store_comp = store_comp[(store_comp['Sent'] > 0) | (store_comp['Delivered'] > 0)]
    store_comp['Diff'] = store_comp['Delivered'] - store_comp['Sent']
    store_comp['Compliance'] = store_comp.apply(
        lambda r: (r['Delivered'] / r['Sent'] * 100) if r['Sent'] > 0 else 0, axis=1
    )

    # Apply sidebar filters at the store level too
    if f['cluster_filter'] != '(All)':
        store_comp = store_comp[
            store_comp['CLUSTER FULL'].astype(str).str.strip().str.upper() == f['cluster_filter']
        ]
    if f['customer_filter'] != '(All)':
        store_comp = store_comp[store_comp['CUSTOMER'] == f['customer_filter']]
    if f['route_filter'] != '(All)':
        store_comp = store_comp[store_comp['Route_ID_AFS'] == f['route_filter']]
    if f['store_filter'] != '(All)':
        store_comp = store_comp[store_comp['Store_Number'] == f['store_filter']]

    def _store_status(row):
        """Traffic-light status for a per-store row.
        🟢 = delivered ≥ sent (full)         compliance ≥ 100%
        🟡 = partial delivery                  60% ≤ compliance < 100%
        🔴 = below 60% delivered               compliance < 60%
        ⚪ = no sent units recorded            sent = 0
        """
        if row['Sent'] == 0:
            return '⚪ No sent'
        pct = row['Compliance']
        if pct >= 100:
            return '🟢 Full'
        if pct >= 60:
            return '🟡 Partial'
        return '🔴 Short'

    store_comp['Status'] = store_comp.apply(_store_status, axis=1)

    store_show = store_comp[
        ['Status', 'Store_Number', 'Route No.', 'CLUSTER FULL', 'CUSTOMER',
         'Sent', 'Delivered', 'Diff', 'Compliance']
    ].sort_values('Diff', key=lambda x: x.abs(), ascending=False)

    panel_open("Per store")
    if store_show.empty:
        st.caption("No stores match the current filters.")
    else:
        # Counts for the legend
        n_full    = int((store_comp['Status'] == '🟢 Full').sum())
        n_partial = int((store_comp['Status'] == '🟡 Partial').sum())
        n_short   = int((store_comp['Status'] == '🔴 Short').sum())
        n_no_sent = int((store_comp['Status'] == '⚪ No sent').sum())
        st.caption(
            f"🟢 Full: **{n_full:,}**  ·  🟡 Partial: **{n_partial:,}**  ·  "
            f"🔴 Short: **{n_short:,}**  ·  ⚪ No sent: **{n_no_sent:,}**"
        )
        st.dataframe(
            store_show, use_container_width=True, hide_index=True,
            column_config={
                "Status":    st.column_config.TextColumn("Status", width="small"),
                "Compliance": st.column_config.ProgressColumn(
                    "Compliance", format="%.0f%%", min_value=0, max_value=100
                ),
                "Sent":      st.column_config.NumberColumn(format="%d"),
                "Delivered": st.column_config.NumberColumn(format="%d"),
                "Diff":      st.column_config.NumberColumn(
                    format="%+d", help="Delivered − Sent. Negative = under-delivery"
                ),
            },
        )
    panel_close()
