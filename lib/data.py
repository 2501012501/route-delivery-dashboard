"""Data loading and normalization for the dashboard.

Single source of truth for reading parquet files. Cached with
@st.cache_data so it runs once per session; pages just call load_data().
"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path("Route To Delivery Data")
SENT_PATH = Path("data") / "deliveries.parquet"

# Cluster aliases — store master uses different names than route master
# for some clusters. Apply as `value.upper().strip() -> canonical name`.
CLUSTER_ALIAS = {
    'DFW': 'DALLAS',
}


def normalize_cluster(value):
    if pd.isna(value):
        return value
    s = str(value).strip().upper()
    return CLUSTER_ALIAS.get(s, s)


@st.cache_data(show_spinner="Loading data...")
def load_data():
    """Returns (inv, dlv, vis, sm, rm, rm_error, sent).

    rm may be None if route_master.parquet is missing (rm_error explains why).
    sent may be None if data/deliveries.parquet is missing.
    """
    inv = pd.read_parquet(DATA_DIR / "inventory.parquet")
    dlv = pd.read_parquet(DATA_DIR / "delivery.parquet")
    vis = pd.read_parquet(DATA_DIR / "visits.parquet")
    sm  = pd.read_parquet(DATA_DIR / "store_master.parquet")

    for _df in (sm, inv, dlv, vis):
        if 'CLUSTER FULL' in _df.columns:
            _df['CLUSTER FULL'] = _df['CLUSTER FULL'].apply(normalize_cluster)

    sent = pd.read_parquet(SENT_PATH) if SENT_PATH.exists() else None
    if sent is not None:
        sent['DATE'] = pd.to_datetime(sent['DATE'], errors='coerce').dt.date
        sent['DELIVERY UNITS'] = pd.to_numeric(sent['DELIVERY UNITS'], errors='coerce').fillna(0)
        if 'CLUSTER FULL' in sent.columns:
            sent['CLUSTER FULL'] = sent['CLUSTER FULL'].apply(normalize_cluster)
        cutoff = (pd.Timestamp.now() - pd.Timedelta(days=14)).date()
        sent = sent[sent['DATE'] >= cutoff]

    inv['Answer_Date']          = pd.to_datetime(inv['Answer_Date']).dt.date
    dlv['Created_Date']         = pd.to_datetime(dlv['Created_Date']).dt.date
    vis['Appointment_DateTime'] = pd.to_datetime(vis['Appointment_DateTime'], errors='coerce', utc=True).dt.tz_localize(None)

    if 'First_Realization_DateTime' in vis.columns:
        vis['First_Realization_DateTime'] = pd.to_datetime(vis['First_Realization_DateTime'], errors='coerce')
        if 'Last_Realization_DateTime' in vis.columns:
            vis['Last_Realization_DateTime'] = pd.to_datetime(vis['Last_Realization_DateTime'], errors='coerce')
        vis = vis[vis['First_Realization_DateTime'].notna()].copy()
        vis['Visit_DateTime'] = vis['First_Realization_DateTime']
    else:
        vis = vis[vis['Appointment_DateTime'] <= pd.Timestamp.now()].copy()
        vis['Visit_DateTime'] = vis['Appointment_DateTime']

    vis['Visit_Date'] = vis['Visit_DateTime'].dt.date

    rm_path = DATA_DIR / "route_master.parquet"
    rm = None
    rm_error = None
    if rm_path.exists():
        try:
            rm = pd.read_parquet(rm_path)
            rm.columns = [str(c).strip() for c in rm.columns]
        except Exception as e:
            rm_error = str(e)
    return inv, dlv, vis, sm, rm, rm_error, sent
