"""Errors — inventory mismatches: Initial + Delivery − Credits − Final ≠ 0."""
import streamlit as st

from lib.compute import latest_per
from lib.filters import apply_filters
from lib.shell import setup
from lib.theme import (SLATE, kpi, kpi_grid, page_header,
                        panel_close, panel_open)

st.set_page_config(page_title="Errors", layout="wide", page_icon="⚠️")
(inv, dlv, vis, sm, rm, sent), route_cols, f = setup()

page_header(
    eyebrow="Errors",
    title="Inventory Mismatches",
    badge=f['target_date'].strftime('%a · %b %d, %Y'),
    subtitle="Difference = Initial Inventory + Delivered − Credits − Final Inventory.",
)

inv_d = apply_filters(inv[inv['Answer_Date']  == f['target_date']], f).copy()
dlv_d = apply_filters(dlv[dlv['Created_Date'] == f['target_date']], f).copy()
vis_d = apply_filters(vis[vis['Visit_Date']   == f['target_date']], f, also_activity=True).copy()

inv_latest = latest_per(inv_d, ['Store_Number','Product_EAN','Monitoring_Name'], 'Answer_Time')
dlv_latest = latest_per(dlv_d, ['Store_Number','Product_EAN','Document_Type_Name'], 'Created_Time')

# Page-local filters (search + sign)
fc1, fc2 = st.columns([2, 1])
with fc1:
    prod_search = st.text_input("Search store or user", "",
                                 placeholder="Store_Number or User_Name",
                                 key="err_prod_search")
with fc2:
    only_pos = st.selectbox("Type", ["All", "Shortages only (+)", "Overages only (−)"],
                             key="err_sign_filter")

init_grp  = (inv_latest[inv_latest['Monitoring_Name'] == 'Initial Inventory']
             .groupby('Store_Number', dropna=False)['QTYInventory'].sum()
             .rename('Initial Inventory').reset_index())
final_grp = (inv_latest[inv_latest['Monitoring_Name'] == 'Front']
             .groupby('Store_Number', dropna=False)['QTYInventory'].sum()
             .rename('Final Inventory').reset_index())
deliv_grp = (dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery']
             .groupby('Store_Number', dropna=False)['DeliveredBunches'].sum()
             .rename('Delivery').reset_index())
cred_grp  = (dlv_latest[dlv_latest['Document_Type_Name'] == 'Credits (RTV)']
             .groupby('Store_Number', dropna=False)['DeliveredBunches'].sum()
             .rename('Credits').reset_index())

err = (init_grp
       .merge(deliv_grp, on='Store_Number', how='outer')
       .merge(cred_grp,  on='Store_Number', how='outer')
       .merge(final_grp, on='Store_Number', how='outer'))
for c in ['Initial Inventory', 'Delivery', 'Credits', 'Final Inventory']:
    err[c] = err.get(c, 0).fillna(0)
err['Difference'] = (err['Initial Inventory'] + err['Delivery']
                     - err['Credits'] - err['Final Inventory'])

if not vis_d.empty:
    vis_grp = vis_d.groupby('Store_Number', dropna=False).agg(
        User_Name=('User_Name', lambda x: ', '.join(sorted(set(x.dropna().astype(str))))),
        Activity_Type=('Activity_Type', lambda x: ', '.join(sorted(set(x.dropna().astype(str))))),
    ).reset_index()
    err = err.merge(vis_grp, on='Store_Number', how='left')
else:
    err['User_Name'] = ''
    err['Activity_Type'] = ''

err = err.merge(
    sm[['Store_Number', 'Route_ID_AFS', 'CUSTOMER', 'CLUSTER FULL']],
    on='Store_Number', how='left',
)
rm_route_no = rm[[route_cols['route_afs'], route_cols['route_no']]].rename(
    columns={route_cols['route_afs']: 'Route_ID_AFS',
             route_cols['route_no']:  'Route No.'}
)
err = err.merge(rm_route_no, on='Route_ID_AFS', how='left')

if f['cluster_filter'] != '(All)':
    err = err[err['CLUSTER FULL'].astype(str).str.strip().str.upper() == f['cluster_filter']]
if f['customer_filter'] != '(All)':
    err = err[err['CUSTOMER'] == f['customer_filter']]
if f['route_filter'] != '(All)':
    err = err[err['Route_ID_AFS'] == f['route_filter']]
if f['store_filter'] != '(All)':
    err = err[err['Store_Number'] == f['store_filter']]

err = err[err['Difference'].abs() >= 1]

if prod_search:
    ps = prod_search.lower()
    err = err[
        err['Store_Number'].astype(str).str.lower().str.contains(ps, na=False) |
        err['User_Name'].astype(str).str.lower().str.contains(ps, na=False)
    ]
if only_pos == "Shortages only (+)":
    err = err[err['Difference'] > 0]
elif only_pos == "Overages only (−)":
    err = err[err['Difference'] < 0]

err = err.sort_values('Difference', key=lambda x: x.abs(), ascending=False)

if err.empty:
    panel_open()
    st.success("No significant errors for the selected filters and date.")
    panel_close()
else:
    n_stores  = err['Store_Number'].nunique()
    n_routes  = err['Route No.'].nunique()
    units_off = int(err['Difference'].abs().sum())

    kpi_grid(
        kpi("Errors (rows)", f"{len(err):,}", accent=True),
        kpi("Stores",        f"{n_stores:,}"),
        kpi("Units off",     f"{units_off:,}"),
        kpi("Routes",        f"{n_routes:,}"),
    )

    show_cols = ['Route No.', 'Store_Number', 'CLUSTER FULL', 'User_Name', 'Activity_Type',
                 'Initial Inventory', 'Delivery', 'Credits', 'Final Inventory', 'Difference']
    panel_open("Mismatches")
    st.dataframe(
        err[[c for c in show_cols if c in err.columns]],
        use_container_width=True, hide_index=True,
        column_config={
            'Initial Inventory': st.column_config.NumberColumn(format="%d"),
            'Delivery':          st.column_config.NumberColumn(format="%d"),
            'Credits':           st.column_config.NumberColumn(format="%d"),
            'Final Inventory':   st.column_config.NumberColumn(format="%d"),
            'Difference':        st.column_config.NumberColumn(
                format="%+d", help="Positive = shortage · Negative = overage"
            ),
        },
    )
    panel_close()
