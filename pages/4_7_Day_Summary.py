"""7-Day Summary — executive trend across the last 7 days.

This page ignores the sidebar's single Date input and uses the 7-day window
ending at the selected date.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

from lib.filters import apply_filters
from lib.shell import setup
from lib.theme import (SLATE, eyebrow_title, kpi, kpi_grid,
                        panel_close, panel_open)

st.set_page_config(page_title="7-Day Summary", layout="wide", page_icon="📊")
(inv, dlv, vis, sm, rm, sent), route_cols, f = setup()

target_date = f['target_date']
week_start  = target_date - timedelta(days=6)

eyebrow_title("7-Day Summary", "Last 7 days · executive view")
st.markdown(
    f'<div style="font-size:12px;color:{SLATE};margin-bottom:12px;">'
    f'Period: <b>{week_start.strftime("%a %b %d")}</b> → <b>{target_date.strftime("%a %b %d")}</b> '
    f'· Sidebar filters apply (Date is replaced by this 7-day window).'
    f'</div>',
    unsafe_allow_html=True,
)

# 1) Filter all sources to the 7-day window
inv_w = apply_filters(inv[(inv['Answer_Date']  >= week_start) & (inv['Answer_Date']  <= target_date)], f).copy()
dlv_w = apply_filters(dlv[(dlv['Created_Date'] >= week_start) & (dlv['Created_Date'] <= target_date)], f).copy()
vis_w = apply_filters(vis[(vis['Visit_Date']   >= week_start) & (vis['Visit_Date']   <= target_date)], f, also_activity=True).copy()
sent_w = None
if sent is not None:
    sent_w = sent[(sent['DATE'] >= week_start) & (sent['DATE'] <= target_date)].copy()
    sent_w = sent_w.rename(columns={'STORE NUMBER WF': 'Store_Number'})
    sent_w = apply_filters(sent_w, f)

inv_w_latest = (inv_w.sort_values('Answer_Time')
                    .drop_duplicates(subset=['Store_Number','Product_EAN','Monitoring_Name','Answer_Date'],
                                     keep='last')) if not inv_w.empty else inv_w
dlv_w_latest = (dlv_w.sort_values('Created_Time')
                    .drop_duplicates(subset=['Store_Number','Product_EAN','Document_Type_Name','Created_Date'],
                                     keep='last')) if not dlv_w.empty else dlv_w

# 2) Per (store, day) aggregates
init_g = (inv_w_latest[inv_w_latest['Monitoring_Name'] == 'Initial Inventory']
          .groupby(['Store_Number','Answer_Date'])['QTYInventory'].sum().rename('Initial')
          .reset_index().rename(columns={'Answer_Date': 'Date'}))
final_g = (inv_w_latest[inv_w_latest['Monitoring_Name'] == 'Front']
           .groupby(['Store_Number','Answer_Date'])['QTYInventory'].sum().rename('Final')
           .reset_index().rename(columns={'Answer_Date': 'Date'}))
deliv_g = (dlv_w_latest[dlv_w_latest['Document_Type_Name'] == 'Delivery']
           .groupby(['Store_Number','Created_Date'])['DeliveredBunches'].sum().rename('Delivery')
           .reset_index().rename(columns={'Created_Date': 'Date'}))
cred_g = (dlv_w_latest[dlv_w_latest['Document_Type_Name'] == 'Credits (RTV)']
          .groupby(['Store_Number','Created_Date'])['DeliveredBunches'].sum().rename('Credits')
          .reset_index().rename(columns={'Created_Date': 'Date'}))

err_w = (init_g
         .merge(deliv_g, on=['Store_Number','Date'], how='outer')
         .merge(cred_g,  on=['Store_Number','Date'], how='outer')
         .merge(final_g, on=['Store_Number','Date'], how='outer'))
for c in ['Initial','Delivery','Credits','Final']:
    err_w[c] = err_w[c].fillna(0) if c in err_w.columns else 0
err_w['Difference'] = err_w['Initial'] + err_w['Delivery'] - err_w['Credits'] - err_w['Final']
err_w['IsError'] = (err_w['Difference'].abs() >= 1).astype(int)

err_w = err_w.merge(
    sm[['Store_Number','Route_ID_AFS','CUSTOMER','CLUSTER FULL']],
    on='Store_Number', how='left',
)
err_w = err_w.merge(
    rm[[route_cols['route_afs'], route_cols['route_no']]].rename(
        columns={route_cols['route_afs']:'Route_ID_AFS',
                 route_cols['route_no']:'Route No.'}
    ),
    on='Route_ID_AFS', how='left',
)

# 3) Daily compliance per day. Routes for each day = scheduled ∪ active
#    (or all routes when "Show all routes" is on).
daily_compliance = []
for d in pd.date_range(week_start, target_date, freq='D'):
    d_date = d.date()
    d_dow  = d.strftime('%a')

    if f['show_all_routes']:
        routes_d = rm.copy()
    else:
        scheduled_mask = rm['_days'].apply(lambda s: d_dow in s)
        active_ids_d = set()
        if 'Route_ID_AFS' in vis_w.columns:
            active_ids_d |= set(vis_w.loc[vis_w['Visit_Date']   == d_date, 'Route_ID_AFS'].dropna().unique())
        if 'Route_ID_AFS' in dlv_w.columns:
            active_ids_d |= set(dlv_w.loc[dlv_w['Created_Date'] == d_date, 'Route_ID_AFS'].dropna().unique())
        if sent_w is not None and 'Route_ID_AFS' in sent_w.columns:
            active_ids_d |= set(sent_w.loc[sent_w['DATE'] == d_date, 'Route_ID_AFS'].dropna().unique())
        if active_ids_d:
            active_mask = rm[route_cols['route_afs']].isin(active_ids_d)
            routes_d = rm[scheduled_mask | active_mask]
        else:
            routes_d = rm[scheduled_mask]

    if f['cluster_filter'] != '(All)' and route_cols['cluster']:
        routes_d = routes_d[
            routes_d[route_cols['cluster']].astype(str).str.strip().str.upper() == f['cluster_filter']
        ]
    if f['route_filter'] != '(All)':
        routes_d = routes_d[routes_d[route_cols['route_afs']] == f['route_filter']]
    rids_d = routes_d[route_cols['route_afs']].dropna().unique()
    stores_d = sm[sm['Route_ID_AFS'].isin(rids_d)]
    if f['customer_filter'] != '(All)':
        stores_d = stores_d[stores_d['CUSTOMER'] == f['customer_filter']]
    if f['store_filter'] != '(All)':
        stores_d = stores_d[stores_d['Store_Number'] == f['store_filter']]
    planned = stores_d['Store_Number'].nunique()
    visited = vis_w[vis_w['Visit_Date'] == d_date]['Store_Number'].nunique()
    sent_units = float(sent_w[sent_w['DATE'] == d_date]['DELIVERY UNITS'].sum()) if sent_w is not None else 0.0
    delivered_units = float(err_w[err_w['Date'] == d_date]['Delivery'].sum())
    errors_count = int(err_w[err_w['Date'] == d_date]['IsError'].sum())
    daily_compliance.append({
        'Date': d_date, 'Day': d.strftime('%a'),
        'Planned': planned, 'Visited': visited,
        'Visit %': (visited / planned) if planned else 0,
        'Sent': sent_units, 'Delivered': delivered_units,
        'Deliv %': (delivered_units / sent_units) if sent_units else 0,
        'Errors': errors_count,
    })
daily_df = pd.DataFrame(daily_compliance)

total_planned     = int(daily_df['Planned'].sum())
total_visited     = int(daily_df['Visited'].sum())
visit_pct         = (total_visited / total_planned) if total_planned else 0
total_sent_w      = float(daily_df['Sent'].sum())
total_delivered_w = float(daily_df['Delivered'].sum())
deliv_pct         = (total_delivered_w / total_sent_w) if total_sent_w else 0
total_credits_w   = float(err_w['Credits'].sum())
total_errors_w    = int(err_w['IsError'].sum())
stores_w_errors   = err_w.loc[err_w['IsError'] == 1, 'Store_Number'].nunique()

dur_col = 'Actual_duration' if 'Actual_duration' in vis_w.columns else (
          'CostCenter_Duration' if 'CostCenter_Duration' in vis_w.columns else None)
avg_duration = float(vis_w[dur_col].mean()) if dur_col and not vis_w.empty else None

# 4) KPIs
kpi_grid(
    kpi("Visit compliance",    f"{visit_pct:.0%}", accent=True),
    kpi("Delivery compliance", f"{deliv_pct:.0%}"),
    kpi("Stores w/ errors",    f"{stores_w_errors:,}"),
    kpi("Avg visit duration",  f"{avg_duration:.0f} min" if avg_duration else "—"),
    kpi("Stores visited",      f"{vis_w['Store_Number'].nunique():,}"),
)
total_store_days = max(int((err_w['Initial'] + err_w['Delivery'] + err_w['Credits'] + err_w['Final']).gt(0).sum()), 1)
error_rate = total_errors_w / total_store_days
kpi_grid(
    kpi("Bunches delivered",   f"{int(total_delivered_w):,}"),
    kpi("Units sent",          f"{int(total_sent_w):,}"),
    kpi("Credits / RTV",       f"{int(total_credits_w):,}"),
    kpi("Total visits",        f"{len(vis_w):,}"),
    kpi("Error rate",          f"{error_rate:.0%}"),
)

# 5) Daily trend
panel_open("Daily trend")
trend_view = daily_df.copy()
trend_view['Visit %'] = (trend_view['Visit %'] * 100).round(0)
trend_view['Deliv %'] = (trend_view['Deliv %'] * 100).round(0)
st.dataframe(
    trend_view, use_container_width=True, hide_index=True,
    column_config={
        'Visit %':  st.column_config.ProgressColumn('Visit %', format="%.0f%%", min_value=0, max_value=100),
        'Deliv %':  st.column_config.ProgressColumn('Deliv %', format="%.0f%%", min_value=0, max_value=100),
        'Sent':     st.column_config.NumberColumn(format="%d"),
        'Delivered':st.column_config.NumberColumn(format="%d"),
        'Errors':   st.column_config.NumberColumn(format="%d"),
    },
)
chart_df = daily_df.set_index('Date')[['Visit %', 'Deliv %']].copy()
if not chart_df.empty:
    st.line_chart(chart_df, height=240)
panel_close()

# 6) Breakdown
panel_open("Breakdown")
breakdown_dim = st.radio(
    "Group by", ["Cluster", "Route", "Customer"],
    horizontal=True, key="week_breakdown_dim",
)
dim_col = {'Cluster': 'CLUSTER FULL', 'Route': 'Route No.', 'Customer': 'CUSTOMER'}[breakdown_dim]

if dim_col not in err_w.columns:
    st.warning(f"Column {dim_col} missing — re-check store master.")
else:
    sent_by_dim = pd.Series(dtype=float)
    if sent_w is not None and not sent_w.empty:
        sw = sent_w.merge(
            sm[['Store_Number','CLUSTER FULL','CUSTOMER','Route_ID_AFS']],
            on='Store_Number', how='left', suffixes=('','_sm'),
        ).merge(
            rm[[route_cols['route_afs'], route_cols['route_no']]].rename(
                columns={route_cols['route_afs']:'Route_ID_AFS',
                         route_cols['route_no']:'Route No.'}
            ),
            on='Route_ID_AFS', how='left',
        )
        if dim_col in sw.columns:
            sent_by_dim = sw.groupby(dim_col, dropna=False)['DELIVERY UNITS'].sum()

    agg = err_w.groupby(dim_col, dropna=False).agg(
        Delivered=('Delivery', 'sum'),
        Credits=('Credits', 'sum'),
        Errors=('IsError', 'sum'),
        Stores_with_Error=('Store_Number', lambda x: x[err_w.loc[x.index, 'IsError'] == 1].nunique()),
    ).reset_index()
    agg['Sent'] = agg[dim_col].map(sent_by_dim).fillna(0)

    if not vis_w.empty:
        vw = vis_w.merge(
            sm[['Store_Number','CLUSTER FULL','CUSTOMER','Route_ID_AFS']],
            on='Store_Number', how='left', suffixes=('','_sm2'),
        ).merge(
            rm[[route_cols['route_afs'], route_cols['route_no']]].rename(
                columns={route_cols['route_afs']:'Route_ID_AFS',
                         route_cols['route_no']:'Route No.'}
            ),
            on='Route_ID_AFS', how='left',
        )
        vis_agg = vw.groupby(dim_col, dropna=False).agg(
            Visits=('Store_Number', 'count'),
            Stores_Visited=('Store_Number', 'nunique'),
            Avg_Duration=(dur_col, 'mean') if dur_col and dur_col in vw.columns else ('Store_Number', 'count'),
        ).reset_index()
        agg = agg.merge(vis_agg, on=dim_col, how='left')

    agg['Compliance'] = (agg['Delivered'] / agg['Sent'].replace(0, pd.NA)).fillna(0) * 100
    agg = agg.sort_values('Compliance', ascending=False)
    cols_order = [dim_col, 'Compliance', 'Sent', 'Delivered', 'Credits',
                  'Stores_Visited', 'Visits', 'Avg_Duration', 'Stores_with_Error', 'Errors']
    agg = agg[[c for c in cols_order if c in agg.columns]]
    st.dataframe(
        agg, use_container_width=True, hide_index=True,
        column_config={
            'Compliance':         st.column_config.ProgressColumn('Compliance', format="%.0f%%", min_value=0, max_value=100),
            'Sent':               st.column_config.NumberColumn(format="%d"),
            'Delivered':          st.column_config.NumberColumn(format="%d"),
            'Credits':            st.column_config.NumberColumn(format="%d"),
            'Avg_Duration':       st.column_config.NumberColumn(format="%.0f min"),
            'Stores_with_Error':  st.column_config.NumberColumn(format="%d"),
            'Errors':             st.column_config.NumberColumn(format="%d"),
        },
    )
panel_close()

# 7) Top 10 problematic stores
panel_open("Top 10 stores · most errors (last 7 days)")
top_err = (err_w[err_w['IsError'] == 1]
           .groupby(['Store_Number','CUSTOMER','CLUSTER FULL','Route No.'], dropna=False)
           .agg(Error_Days=('IsError', 'sum'),
                Total_Diff=('Difference', lambda x: x.abs().sum()))
           .reset_index()
           .sort_values(['Error_Days','Total_Diff'], ascending=False)
           .head(10))
if top_err.empty:
    st.success("No errors in the last 7 days — well done!")
else:
    st.dataframe(
        top_err, use_container_width=True, hide_index=True,
        column_config={
            'Error_Days': st.column_config.NumberColumn('Days w/ Error', format="%d",
                                                         help="Number of days with at least one error"),
            'Total_Diff': st.column_config.NumberColumn('Total Diff (units)', format="%d"),
        },
    )
panel_close()
