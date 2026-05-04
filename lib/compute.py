"""Data aggregation helpers used by 2+ pages. No Streamlit calls."""
import pandas as pd


def latest_per(df: pd.DataFrame, key_cols: list, time_col: str) -> pd.DataFrame:
    """For each unique combination of key_cols, keep the row with the latest time_col."""
    if df.empty: return df
    df = df.sort_values(time_col)
    return df.drop_duplicates(subset=key_cols, keep='last')


def store_day_summary(*, target_route_ids, sm, vis_d, dlv_latest, inv_latest,
                      cluster_filter: str, customer_filter: str,
                      store_filter: str) -> pd.DataFrame:
    """Per-store summary for the selected routes on the day.

    customer_filter / store_filter are single strings; '(All)' = no filter.
    """
    stores = sm[sm['Route_ID_AFS'].isin(target_route_ids)].copy()
    if cluster_filter != '(All)':
        stores = stores[stores['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    if customer_filter != '(All)':
        stores = stores[stores['CUSTOMER'] == customer_filter]
    if store_filter != '(All)':
        stores = stores[stores['Store_Number'] == store_filter]

    dur_col = 'Actual_duration' if 'Actual_duration' in vis_d.columns else 'CostCenter_Duration'

    if not vis_d.empty:
        agg_kwargs = dict(
            Visited=('Visit_DateTime', 'count'),
            First_Visit=('Visit_DateTime', 'min'),
            Last_Visit=('Visit_DateTime', 'max'),
            Avg_Duration_min=(dur_col, 'mean') if dur_col in vis_d.columns else ('Visit_DateTime', 'count'),
            Order_Count=('Order_Count', 'sum'),
            Total_Ordered=('Total_Ordered', 'sum'),
            Total_Delivered=('Total_Delivered', 'sum'),
        )
        vis_grp = vis_d.groupby('Store_Number').agg(**agg_kwargs).reset_index()
    else:
        vis_grp = pd.DataFrame(columns=['Store_Number','Visited','First_Visit','Last_Visit',
                                         'Avg_Duration_min','Order_Count','Total_Ordered','Total_Delivered'])
    stores = stores.merge(vis_grp, on='Store_Number', how='left')
    stores['Visited'] = stores['Visited'].fillna(0).astype(int)

    deliv_only = dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery']
    deliv_grp = deliv_only.groupby('Store_Number')['DeliveredBunches'].sum().rename('Bunches_Delivered')
    stores = stores.merge(deliv_grp, on='Store_Number', how='left')
    stores['Bunches_Delivered'] = stores['Bunches_Delivered'].fillna(0)

    credits_only = dlv_latest[dlv_latest['Document_Type_Name'] == 'Credits (RTV)']
    cred_grp = credits_only.groupby('Store_Number')['DeliveredBunches'].sum().rename('Bunches_Credit')
    stores = stores.merge(cred_grp, on='Store_Number', how='left')
    stores['Bunches_Credit'] = stores['Bunches_Credit'].fillna(0)

    init = inv_latest[inv_latest['Monitoring_Name'] == 'Initial Inventory']
    init_grp = init.groupby('Store_Number')['QTYInventory'].sum().rename('Initial_Inv')
    final = inv_latest[inv_latest['Monitoring_Name'] == 'Front']
    final_grp = final.groupby('Store_Number')['QTYInventory'].sum().rename('Final_Inv')
    stores = stores.merge(init_grp, on='Store_Number', how='left')
    stores = stores.merge(final_grp, on='Store_Number', how='left')
    stores['Initial_Inv'] = stores['Initial_Inv'].fillna(0)
    stores['Final_Inv']   = stores['Final_Inv'].fillna(0)

    stores['Errors'] = (stores['Initial_Inv'] + stores['Bunches_Delivered']
                        - stores['Bunches_Credit'] - stores['Final_Inv'])
    return stores


def store_status(row) -> str:
    """Plain-text status, no emoji. 'Visited' / 'In progress' / 'Pending'."""
    visited   = row.get('Visited', 0) > 0
    delivered = row.get('Bunches_Delivered', 0) > 0
    if visited and delivered:
        return "Visited"
    if visited and not delivered:
        return "In progress"
    return "Pending"


def cluster_compliance_data(*, routes_today, sm, vis_d, route_cols,
                             customer_filter: str, store_filter: str) -> pd.DataFrame:
    """Per-cluster compliance for routes_today. Columns: Cluster, Visited, Planned, Pct.

    customer_filter / store_filter are single strings; '(All)' = no filter.
    """
    if routes_today.empty:
        return pd.DataFrame()
    rows = []
    cluster_col = route_cols['cluster']
    grouped = routes_today.groupby(cluster_col, dropna=False) if cluster_col else [(None, routes_today)]
    for cluster_name, group in grouped:
        rids = group[route_cols['route_afs']].dropna().unique()
        stores = sm[sm['Route_ID_AFS'].isin(rids)]
        if customer_filter != '(All)':
            stores = stores[stores['CUSTOMER'] == customer_filter]
        if store_filter != '(All)':
            stores = stores[stores['Store_Number'] == store_filter]
        planned = stores['Store_Number'].nunique()
        visited = vis_d[vis_d['Store_Number'].isin(stores['Store_Number'])]['Store_Number'].nunique()
        pct = (visited / planned) if planned else 0
        rows.append({
            'Cluster': str(cluster_name).strip().title() if cluster_name else '—',
            'Visited': visited,
            'Planned': planned,
            'Pct':     pct,
        })
    return pd.DataFrame(rows).sort_values('Pct', ascending=False)
