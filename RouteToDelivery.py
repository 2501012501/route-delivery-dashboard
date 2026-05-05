"""
RouteToDelivery.py
Carga Inventario, Delivery y Visitas desde la API de Retex/AFS (últimos 7 días),
filtra a CVS, Walgreens y Quiktrip, y le pega los atributos del store master
(CLUSTER, Route, Route_ID_AFS, CUSTOMER) tomado de sales.parquet.

Salidas: parquet en la carpeta "Route To Delivery Data".

Optimizaciones:
- Las dimensiones (Customer, Product, User, etc.) se cachean en .cache/dims/
  con TTL de 24 h para evitar re-descargarlas en cada refresh.
- Las 7 dimensiones se descargan en paralelo (ThreadPoolExecutor).
- Inventory / Delivery / Visits también se descargan en paralelo.
"""
import os
import time
import urllib3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

# Dimension cache: small dim tables are saved here so repeated refreshes
# in the same 24 h window skip the API entirely.
CACHE_DIR     = Path(".cache") / "dims"
CACHE_TTL_H   = 24
DIM_WORKERS   = 4   # parallel HTTP for dimensions
FACT_WORKERS  = 3   # parallel HTTP for inv/dlv/vis

# Incremental refresh: how many days of overlap to refetch each run, to
# catch late-arriving rows or in-place updates from Retex. The stable
# portion of the existing parquet (date < cutoff) is kept untouched.
INCREMENTAL_OVERLAP_DAYS = 1

STORE_MASTER_COLS = [
    'STORE NUMBER WF', 'CUSTOMER', 'CLUSTER FULL', 'CLUSTER XXX',
    'Route', 'Route_ID_WF', 'Route_ID_AFS',
]

# ── Session helper ────────────────────────────────────────────────────────────
# requests.Session is not reliably thread-safe across many concurrent calls,
# so we make a thin factory that returns one session per call site.
def _new_session():
    s = requests.Session()
    s.auth = HTTPBasicAuth(USER, PASSWORD)
    s.verify = False
    s.headers.update({"Accept": "application/json"})
    return s


# A single shared session is fine for SEQUENTIAL fetches (legacy behaviour).
session = _new_session()


def fetch_all(url, *, sess=None, label=""):
    """OData paginated fetch — sigue @odata.nextLink hasta agotar."""
    sess = sess or session
    rows = []
    next_url = url
    page = 0
    while next_url:
        page += 1
        r = sess.get(next_url, timeout=180)
        r.raise_for_status()
        data = r.json()
        rows.extend(data.get("value", []))
        next_url = data.get("@odata.nextLink") or data.get("odata.nextLink")
        if page % 5 == 0:
            print(f"     ...{label} page {page}, {len(rows):,} rows so far")
    return pd.DataFrame(rows)


# ── Dimension cache ───────────────────────────────────────────────────────────
def _cache_path(name):
    return CACHE_DIR / f"{name}.parquet"


def _cache_fresh(name) -> bool:
    p = _cache_path(name)
    if not p.exists():
        return False
    age_h = (time.time() - p.stat().st_mtime) / 3600
    return age_h < CACHE_TTL_H


def fetch_with_cache(name, url, columns, *, sess=None, label=None):
    """Try cache; on miss, fetch from API + save to cache."""
    cache_path = _cache_path(name)
    if _cache_fresh(name):
        df = pd.read_parquet(cache_path)
        print(f"  [cache] {name} ({len(df):,} rows, fresh)")
        return df
    print(f"  [api]   {name}...")
    df = fetch_all(url, sess=sess, label=label or name)[columns]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


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


# ── Incremental refresh helpers ───────────────────────────────────────────────
def _now_utc_naive():
    """Tz-naive UTC 'now' — for comparisons against parsed datetime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _incremental_cutoff(parquet_path: str, date_col: str, fallback_days: int,
                         *, is_int_date: bool = False):
    """Return the API cutoff datetime to use for fetching this fact.

    If the parquet exists and has data: max(date) - INCREMENTAL_OVERLAP_DAYS.
    Otherwise (or if the existing data is older than the rolling window):
    `now - fallback_days` so we do a full pull.

    Always tz-naive UTC. Clamped to `now - fallback_days` to bound API load
    in case the existing parquet has a corrupted/very-old max date.
    """
    floor = _now_utc_naive() - timedelta(days=fallback_days)
    p = Path(parquet_path)
    if not p.exists():
        return floor
    try:
        df = pd.read_parquet(p, columns=[date_col])
    except Exception:
        return floor
    if df.empty:
        return floor

    if is_int_date:
        try:
            max_int = int(df[date_col].max())
            max_dt = datetime.strptime(str(max_int), '%Y%m%d')
        except Exception:
            return floor
    else:
        ts = pd.to_datetime(df[date_col], errors='coerce', utc=True).max()
        if pd.isna(ts):
            return floor
        max_dt = ts.tz_convert('UTC').tz_localize(None).to_pydatetime()

    incremental = max_dt - timedelta(days=INCREMENTAL_OVERLAP_DAYS)
    # Never go further back than the rolling window — bounds API load and
    # guarantees we re-pull at least the last `fallback_days` days if the
    # existing parquet has aged out.
    return max(incremental, floor)


def _slide_window(parquet_path: str, new_df: pd.DataFrame, *,
                   date_col: str, api_cutoff, days_window: int,
                   is_int_date: bool = False) -> pd.DataFrame:
    """Combine fresh API rows with the stable portion of the existing parquet.

    stable = rows in existing parquet with date < api_cutoff (won't be re-fetched)
    new_df = freshly fetched rows (date >= api_cutoff per API filter)
    Final  = stable + new_df, restricted to last `days_window` days.

    No dedupe needed: the two partitions are disjoint by date.
    """
    rolling_cutoff = _now_utc_naive() - timedelta(days=days_window)

    p = Path(parquet_path)
    existing = pd.read_parquet(p) if p.exists() else pd.DataFrame()

    if existing.empty:
        merged = new_df.copy()
    elif new_df.empty:
        merged = existing.copy()
    else:
        if is_int_date:
            cutoff_int = int(api_cutoff.strftime('%Y%m%d'))
            stable = existing[existing[date_col].astype(int) < cutoff_int]
        else:
            ex_dates = pd.to_datetime(existing[date_col], errors='coerce',
                                      utc=True).dt.tz_localize(None)
            stable = existing[ex_dates < pd.Timestamp(api_cutoff)]
        merged = pd.concat([stable, new_df], ignore_index=True, sort=False)

    if merged.empty:
        return merged

    if is_int_date:
        rolling_int = int(rolling_cutoff.strftime('%Y%m%d'))
        merged = merged[merged[date_col].astype(int) >= rolling_int]
    else:
        m_dates = pd.to_datetime(merged[date_col], errors='coerce',
                                 utc=True).dt.tz_localize(None)
        merged = merged[m_dates >= pd.Timestamp(rolling_cutoff)]

    return merged.reset_index(drop=True)


# ── Dimensiones (parallel + cached) ───────────────────────────────────────────
# NOTE: actdef (DActivityDefinition) is intentionally NOT in this list. Its
# First_Realization_Date / _Time columns change throughout the day as drivers
# complete visits, so caching it for hours means missing today's data. It is
# fetched separately in load_actdef() with a date filter (~9 sec instead of
# ~5 min for the full 2M-row pull).
_DIM_SPECS = [
    ('cust',    f"{BASE}/BaseDimensions/DCustomer",
     ['CUS_ID', 'Customer_Name', 'Customer_Name2']),
    ('cust_st', f"{BASE}/BaseDimensions/DCustomerSt",
     ['CUS_ST_ID', 'CUS_ID']),
    ('prod',    f"{BASE}/BaseDimensions/DProduct",
     ['PRD_ID', 'Product_EAN', 'Product_Name', 'Product_LongName']),
    ('user',    f"{BASE}/BaseDimensions/DUser",
     ['USR_ID', 'User_Name']),
    ('user_st', f"{BASE}/BaseDimensions/DUserSt",
     ['USR_ST_ID', 'USR_ID']),
    ('mdef',    f"{BASE}/MonitoringDomain/DMonitoringDefinition",
     ['MTD_MTDR_ID', 'Monitoring_Name']),
]


def _fetch_one_dim(name, url, columns):
    sess = _new_session()
    return name, fetch_with_cache(name, url, columns, sess=sess, label=name)


def load_dims():
    """Fetch the 6 stable dimension tables in parallel, using the 24h on-disk
    cache. actdef is fetched separately by load_actdef() — see the note above
    _DIM_SPECS for why.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=DIM_WORKERS) as pool:
        futures = [pool.submit(_fetch_one_dim, *spec) for spec in _DIM_SPECS]
        for fut in futures:
            name, df = fut.result()
            results[name] = df
    return (
        results['cust'], results['cust_st'], results['prod'],
        results['user'], results['user_st'], results['mdef'],
    )


def load_actdef(*, since=None):
    """Fetch DActivityDefinition rows realized in the last `DAYS` days.

    Pulled fresh on every run because First_Realization_Date / _Time update
    throughout the day as drivers complete visits — caching even briefly
    causes the dashboard to miss today's activity. The date filter keeps the
    payload small (~17k rows / ~9 sec instead of 1.9M rows / ~5 min).
    """
    if since is None:
        since = _now_utc_naive() - timedelta(days=DAYS)
    cutoff = since.strftime("%Y-%m-%d")
    flt = f"First_Realization_Date ge {cutoff}"
    print(f"  [actdef] Filter: {flt}")
    url = f"{BASE}/ActivityDomain/DActivityDefinition?$filter={flt}"
    df = fetch_all(url, sess=_new_session(), label="actdef")
    cols = ['APP_ID', 'Activity_Type', 'Planned_duration', 'Actual_duration',
            'First_Realization_Date', 'First_Realization_Time',
            'Last_Realization_Date',  'Last_Realization_Time']
    return df[[c for c in cols if c in df.columns]] if not df.empty else df


def _retailer_mask(series):
    pat = '|'.join(RETAILERS)
    return series.astype(str).str.contains(pat, case=False, na=False)


# ── Inventario (FMonitoringAnswer) ────────────────────────────────────────────
def load_inventory(cust, prod, user, mdef, *, since=None):
    if since is None:
        since = _now_utc_naive() - timedelta(days=DAYS)
    cutoff = since.strftime("%Y-%m-%dT00:00:00Z")
    print(f"  [INVENTORY] Filter: Answer_Date ge {cutoff}")
    url = f"{BASE}/MonitoringDomain/FMonitoringAnswer?$filter=Answer_Date ge {cutoff}"
    df = fetch_all(url, sess=_new_session(), label="inv")
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
def load_delivery(cust, prod, user, *, since=None):
    if since is None:
        since = _now_utc_naive() - timedelta(days=DAYS)
    cutoff = since.strftime("%Y-%m-%dT00:00:00Z")
    flt = f"(Document_Type_ID eq 'CREDITS' or Document_Type_ID eq 'DEL') and Created_Date ge {cutoff}"
    print(f"  [DELIVERY] Filter: {flt}")
    url = f"{BASE}/OrderSalesDomain/FOrderSale?$filter={flt}"
    df = fetch_all(url, sess=_new_session(), label="dlv")
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
def load_visits(cust, cust_st, user, user_st, actdef, *, since=None):
    if since is None:
        since = _now_utc_naive() - timedelta(days=DAYS)
    cutoff_int = int(since.strftime("%Y%m%d"))
    flt = f"Date_Int ge {cutoff_int}"
    print(f"  [VISITS] Filter: {flt}")
    url = f"{BASE}/ActivityDomain/FActivitySt?$filter={flt}"
    df = fetch_all(url, sess=_new_session(), label="vis")
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
    started = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Building store master from sales.parquet...")
    store_master = build_store_master()
    print(f"  {len(store_master)} stores")
    store_master.to_parquet(f"{OUT_DIR}/store_master.parquet", index=False)
    store_master.to_csv(f"{OUT_DIR}/store_master.csv", index=False)

    print("\nLoading dimensions from Retex API (parallel + cached)...")
    cust, cust_st, prod, user, user_st, mdef = load_dims()

    print("\nLoading actdef (date-filtered, fresh each run)...")
    actdef = load_actdef()

    # ── Incremental: compute API cutoff per fact from existing parquets ──
    inv_path = f"{OUT_DIR}/inventory.parquet"
    dlv_path = f"{OUT_DIR}/delivery.parquet"
    vis_path = f"{OUT_DIR}/visits.parquet"

    inv_since = _incremental_cutoff(inv_path, 'Answer_Date',  DAYS)
    dlv_since = _incremental_cutoff(dlv_path, 'Created_Date', DAYS)
    vis_since = _incremental_cutoff(vis_path, 'Date_Int',     DAYS, is_int_date=True)

    full_floor = (_now_utc_naive() - timedelta(days=DAYS)).date()
    inv_mode = "full" if inv_since.date() <= full_floor else "incremental"
    dlv_mode = "full" if dlv_since.date() <= full_floor else "incremental"
    vis_mode = "full" if vis_since.date() <= full_floor else "incremental"
    print(
        f"\nLoading INVENTORY ({inv_mode} since {inv_since.date()}) / "
        f"DELIVERY ({dlv_mode} since {dlv_since.date()}) / "
        f"VISITS ({vis_mode} since {vis_since.date()}) in parallel..."
    )

    with ThreadPoolExecutor(max_workers=FACT_WORKERS) as pool:
        f_inv   = pool.submit(load_inventory, cust, prod, user, mdef, since=inv_since)
        f_deliv = pool.submit(load_delivery,  cust, prod, user,       since=dlv_since)
        f_vis   = pool.submit(load_visits,    cust, cust_st, user, user_st, actdef,
                              since=vis_since)
        new_inv   = f_inv.result()
        new_deliv = f_deliv.result()
        new_vis   = f_vis.result()

    # Merge new rows with store_master (matches old behavior — store_master
    # columns end up in the parquet and stay through the slide_window concat).
    if not new_inv.empty:
        new_inv = new_inv.merge(store_master, on='Store_Number', how='left')
    if not new_deliv.empty:
        new_deliv = new_deliv.merge(store_master, on='Store_Number', how='left')
    if not new_vis.empty:
        new_vis = new_vis.merge(store_master, on='Store_Number', how='left')

    # Combine fresh rows with the stable portion of each existing parquet.
    inv = _slide_window(inv_path, new_inv,
                        date_col='Answer_Date',  api_cutoff=inv_since,
                        days_window=DAYS)
    deliv = _slide_window(dlv_path, new_deliv,
                          date_col='Created_Date', api_cutoff=dlv_since,
                          days_window=DAYS)
    vis = _slide_window(vis_path, new_vis,
                        date_col='Date_Int',     api_cutoff=vis_since,
                        days_window=DAYS, is_int_date=True)

    print(f"  Inventory: {len(inv):,} total rows  (fetched {len(new_inv):,} new/updated)")
    inv.to_parquet(inv_path, index=False)
    inv.to_csv(f"{OUT_DIR}/inventory.csv", index=False)

    print(f"  Delivery:  {len(deliv):,} total rows  (fetched {len(new_deliv):,} new/updated)")
    deliv.to_parquet(dlv_path, index=False)
    deliv.to_csv(f"{OUT_DIR}/delivery.csv", index=False)

    print(f"  Visits:    {len(vis):,} total rows  (fetched {len(new_vis):,} new/updated)")
    vis.to_parquet(vis_path, index=False)
    vis.to_csv(f"{OUT_DIR}/visits.csv", index=False)

    # Write a sync marker so the dashboard can show "Synced: <time>"
    # separately from "Latest visit". This file travels with the parquets
    # through git, so Cloud sees the same value as local.
    sync_marker = pd.Timestamp.now(tz='UTC').tz_localize(None).isoformat() + "Z"
    with open(f"{OUT_DIR}/last_synced.txt", "w", encoding="utf-8") as fh:
        fh.write(sync_marker)

    elapsed = time.time() - started
    print(f"\nDone in {elapsed:.0f}s. Files saved to '{OUT_DIR}/'")


if __name__ == "__main__":
    main()
