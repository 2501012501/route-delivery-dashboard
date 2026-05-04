"""
RouteToDelivery.py
Carga Inventario, Delivery y Visitas desde la API de Retex/AFS (últimos 7 días),
filtra a CVS, Walgreens y Quiktrip, y le pega los atributos del store master
(CLUSTER, Route, Route_ID_AFS, CUSTOMER) tomado de sales.parquet.

Salidas: parquet en la carpeta "Route To Delivery Data".
"""
import os
import urllib3
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ────────────────────────────────────────────────────────────────────
BASE     = "https://apps-us.retex.afsi.com/218/AnalyticalReportingAPI"
USER     = os.environ['RETEX_USER']
PASSWORD = os.environ['RETEX_PASSWORD']

DAYS      = 7
RETAILERS = ["CVS", "Walgreens", "Quiktrip"]

OUT_DIR       = "Route To Delivery Data"
SALES_PARQUET = "data/sales.parquet"

STORE_MASTER_COLS = [
    'STORE NUMBER WF', 'CUSTOMER', 'CLUSTER FULL', 'CLUSTER XXX',
    'Route', 'Route_ID_WF', 'Route_ID_AFS',
]

# ── Session ───────────────────────────────────────────────────────────────────
session = requests.Session()
session.auth = HTTPBasicAuth(USER, PASSWORD)
session.verify = False
session.headers.update({"Accept": "application/json"})


def fetch_all(url):
    """OData paginated fetch — sigue @odata.nextLink hasta agotar."""
    rows = []
    next_url = url
    page = 0
    while next_url:
        page += 1
        r = session.get(next_url, timeout=180)
        r.raise_for_status()
        data = r.json()
        rows.extend(data.get("value", []))
        next_url = data.get("@odata.nextLink") or data.get("odata.nextLink")
        if page % 5 == 0:
            print(f"     ...page {page}, {len(rows):,} rows so far")
    return pd.DataFrame(rows)


# ── Store master desde sales.parquet ──────────────────────────────────────────
def build_store_master():
    df = pd.read_parquet(SALES_PARQUET)
    cols = [c for c in STORE_MASTER_COLS if c in df.columns]
    sm = (
        df[cols]
        .drop_duplicates(subset=['STORE NUMBER WF'])
        .reset_index(drop=True)
        .rename(columns={'STORE NUMBER WF': 'Store_Number'})
    )
    return sm


# ── Dimensiones ───────────────────────────────────────────────────────────────
def load_dims():
    print("  DCustomer...")
    cust = fetch_all(f"{BASE}/BaseDimensions/DCustomer")[
        ['CUS_ID', 'Customer_Name', 'Customer_Name2']
    ]
    print("  DCustomerSt...")
    cust_st = fetch_all(f"{BASE}/BaseDimensions/DCustomerSt")[['CUS_ST_ID', 'CUS_ID']]
    print("  DProduct...")
    prod = fetch_all(f"{BASE}/BaseDimensions/DProduct")[
        ['PRD_ID', 'Product_EAN', 'Product_Name', 'Product_LongName']
    ]
    print("  DUser...")
    user = fetch_all(f"{BASE}/BaseDimensions/DUser")[['USR_ID', 'User_Name']]
    print("  DUserSt...")
    user_st = fetch_all(f"{BASE}/BaseDimensions/DUserSt")[['USR_ST_ID', 'USR_ID']]
    print("  DMonitoringDefinition...")
    mdef = fetch_all(f"{BASE}/MonitoringDomain/DMonitoringDefinition")[
        ['MTD_MTDR_ID', 'Monitoring_Name']
    ]
    print("  DActivityDefinition...")
    actdef = fetch_all(f"{BASE}/ActivityDomain/DActivityDefinition")[
        ['APP_ID', 'Activity_Type',
         'Planned_duration', 'Actual_duration',
         'First_Realization_Date', 'First_Realization_Time',
         'Last_Realization_Date',  'Last_Realization_Time']
    ]
    return cust, cust_st, prod, user, user_st, mdef, actdef


def _retailer_mask(series):
    pat = '|'.join(RETAILERS)
    return series.astype(str).str.contains(pat, case=False, na=False)


# ── Inventario (FMonitoringAnswer) ────────────────────────────────────────────
def load_inventory(cust, prod, user, mdef):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    print(f"  Filter: Answer_Date ge {cutoff}")
    url = f"{BASE}/MonitoringDomain/FMonitoringAnswer?$filter=Answer_Date ge {cutoff}"
    df = fetch_all(url)
    if df.empty:
        return df
    df = df.drop(columns=[c for c in ['User_Name', 'Customer_Name', 'Customer_Name2', 'Product_EAN', 'Product_Name', 'Monitoring_Name'] if c in df.columns])
    df = df.merge(user, on='USR_ID', how='left')
    df = df.merge(cust, on='CUS_ID', how='left')
    df = df.merge(prod, on='PRD_ID', how='left')
    df = df.merge(mdef, on='MTD_MTDR_ID', how='left')
    df = df.rename(columns={
        'Answer_As_Number': 'QTYInventory',
        'Customer_Name2':   'Store_Number',
    })
    df = df[_retailer_mask(df['Store_Number'])].copy()
    keep = [
        'Answer_Date', 'Answer_Time', 'User_Name', 'Store_Number',
        'Product_EAN', 'Product_Name', 'Monitoring_Name', 'QTYInventory',
    ]
    return df[[c for c in keep if c in df.columns]]


# ── Delivery (FOrderSale) ─────────────────────────────────────────────────────
def load_delivery(cust, prod, user):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    flt = f"(Document_Type_ID eq 'CREDITS' or Document_Type_ID eq 'DEL') and Created_Date ge {cutoff}"
    print(f"  Filter: {flt}")
    url = f"{BASE}/OrderSalesDomain/FOrderSale?$filter={flt}"
    df = fetch_all(url)
    if df.empty:
        return df
    # FOrderSale ya trae Product_EAN/Product_Name/User_Name propios — quítalos antes del merge
    df = df.drop(columns=[c for c in ['Product_EAN', 'Product_Name', 'Product_LongName', 'User_Name', 'Customer_Name', 'Customer_Name2'] if c in df.columns])
    df = df.merge(cust, on='CUS_ID', how='left')
    df = df.merge(prod, on='PRD_ID', how='left')
    df = df.merge(user, on='USR_ID', how='left')
    df = df.rename(columns={'Customer_Name2': 'Store_Number'})
    df = df[_retailer_mask(df['Store_Number'])].copy()
    grp = df.groupby(
        ['Created_Date', 'Created_Time', 'User_Name', 'Store_Number',
         'Document_Type_Name', 'Product_Name', 'Product_EAN'],
        dropna=False
    ).agg(DeliveredBunches=('Qty_in_Eaches', 'sum')).reset_index()
    return grp


# ── Visitas (FActivitySt + DActivityDefinition) ───────────────────────────────
def load_visits(cust, cust_st, user, user_st, actdef):
    cutoff_int = int((datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y%m%d"))
    flt = f"Date_Int ge {cutoff_int}"
    print(f"  Filter: {flt}")
    url = f"{BASE}/ActivityDomain/FActivitySt?$filter={flt}"
    df = fetch_all(url)
    if df.empty:
        return df
    df = df.drop(columns=[c for c in ['User_Name', 'Customer_Name', 'Customer_Name2', 'CUS_ID', 'USR_ID'] if c in df.columns])
    df = df.merge(cust_st, on='CUS_ST_ID', how='left')
    df = df.merge(cust,    on='CUS_ID',    how='left')
    df = df.merge(user_st, on='USR_ST_ID', how='left')
    df = df.merge(user,    on='USR_ID',    how='left')
    df = df.merge(actdef,  on='APP_ID',    how='left')
    df = df.rename(columns={'Customer_Name2': 'Store_Number'})
    df = df[_retailer_mask(df['Store_Number'])].copy()

    # Solo visitas que realmente se realizaron (no agendas futuras sin llegar)
    df = df[df['First_Realization_Date'].notna()].copy()

    # Construir First/Last Realization DateTime
    def _join_dt(d, t):
        try:
            d = pd.to_datetime(d, errors='coerce').dt.date
            t = t.fillna('00:00:00').astype(str).str[:8]
            return pd.to_datetime(d.astype(str) + ' ' + t, errors='coerce')
        except Exception:
            return pd.NaT
    df['First_Realization_DateTime'] = _join_dt(df['First_Realization_Date'], df['First_Realization_Time'])
    df['Last_Realization_DateTime']  = _join_dt(df['Last_Realization_Date'],  df['Last_Realization_Time'])

    keep = [
        'Appointment_DateTime', 'Date_Int', 'User_Name', 'Store_Number',
        'Activity_Type',
        'First_Realization_DateTime', 'Last_Realization_DateTime',
        'Planned_duration', 'Actual_duration',
        'Order_Count', 'Deliveries_Count', 'Returns_Count', 'Form_Count',
        'Monitoring_Count', 'Payment_Count',
        'Total_Ordered', 'Total_Delivered', 'Total_Returned',
        'Store_Rating',
    ]
    return df[[c for c in keep if c in df.columns]]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Building store master from sales.parquet...")
    store_master = build_store_master()
    print(f"  {len(store_master)} stores")
    store_master.to_parquet(f"{OUT_DIR}/store_master.parquet", index=False)
    store_master.to_csv(f"{OUT_DIR}/store_master.csv", index=False)

    print("\nLoading dimensions from Retex API...")
    cust, cust_st, prod, user, user_st, mdef, actdef = load_dims()

    print("\nLoading INVENTORY...")
    inv = load_inventory(cust, prod, user, mdef)
    if not inv.empty:
        inv = inv.merge(store_master, on='Store_Number', how='left')
    print(f"  Inventory rows: {len(inv):,}")
    inv.to_parquet(f"{OUT_DIR}/inventory.parquet", index=False)
    inv.to_csv(f"{OUT_DIR}/inventory.csv", index=False)

    print("\nLoading DELIVERY...")
    deliv = load_delivery(cust, prod, user)
    if not deliv.empty:
        deliv = deliv.merge(store_master, on='Store_Number', how='left')
    print(f"  Delivery rows: {len(deliv):,}")
    deliv.to_parquet(f"{OUT_DIR}/delivery.parquet", index=False)
    deliv.to_csv(f"{OUT_DIR}/delivery.csv", index=False)

    print("\nLoading VISITS...")
    vis = load_visits(cust, cust_st, user, user_st, actdef)
    if not vis.empty:
        vis = vis.merge(store_master, on='Store_Number', how='left')
    print(f"  Visits rows: {len(vis):,}")
    vis.to_parquet(f"{OUT_DIR}/visits.parquet", index=False)
    vis.to_csv(f"{OUT_DIR}/visits.csv", index=False)

    print(f"\nDone. Files saved to '{OUT_DIR}/'")


if __name__ == "__main__":
    main()
