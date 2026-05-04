import os
import struct
import sys
import argparse
import pandas as pd
from sqlalchemy import create_engine
import urllib
import requests
import io
import msal
from msal_extensions import PersistedTokenCache, FilePersistenceWithDataProtection
from msal_extensions.persistence import PersistenceDecryptionError
from dotenv import load_dotenv

load_dotenv()


# ── SQL ───────────────────────────────────────────────────────────────────────
def connect_sql():
    params = urllib.parse.quote_plus(
        f"DRIVER={{SQL Server}};SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_UID']};PWD={os.environ['SQL_PWD']}"
    )
    print("Connecting to SQL...")
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
    print("Connected!")
    return engine


def refresh_deliveries(engine):
    with open("Deliveries.sql", "r") as f:
        query = f.read()
    df = pd.read_sql(query, engine)
    df.to_parquet("data/deliveries_raw.parquet", index=False)
    print(f"Deliveries: {len(df)} rows saved to data/deliveries_raw.parquet")


# ── SharePoint ────────────────────────────────────────────────────────────────
def get_sharepoint_token():
    CLIENT_ID  = os.environ["AZURE_CLIENT_ID"]
    TENANT     = os.environ["AZURE_TENANT"]
    USERNAME   = os.environ["AZURE_USERNAME"]
    CACHE_PATH = os.environ.get("TOKEN_CACHE_PATH", "token_cache.bin")
    SCOPES     = ["https://graph.microsoft.com/.default"]

    print("Authenticating with SharePoint...")
    persistence = FilePersistenceWithDataProtection(CACHE_PATH)
    cache       = PersistedTokenCache(persistence)
    app         = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT}",
        token_cache=cache,
    )

    result = None
    try:
        accounts = app.get_accounts(username=USERNAME)
    except PersistenceDecryptionError:
        print("Token cache corrupted — clearing and re-authenticating...")
        os.remove(CACHE_PATH)
        persistence     = FilePersistenceWithDataProtection(CACHE_PATH)
        cache           = PersistedTokenCache(persistence)
        app.token_cache = cache
        accounts        = []

    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result:
        result = app.acquire_token_interactive(scopes=SCOPES, login_hint=USERNAME)

    if not result or "access_token" not in result:
        print("Auth failed:")
        print("  error            :", result.get("error") if result else "None")
        print("  error_description:", result.get("error_description") if result else "N/A")
        raise SystemExit(1)

    print("Authenticated!")
    return {"Authorization": f"Bearer {result['access_token']}"}


def _download_excel(headers, site_path, file_path, sheet_name):
    site_hostname = "falconfarmsusa.sharepoint.com"
    site_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_hostname}:{site_path}",
        headers=headers,
    )
    site_id   = site_resp.json()["id"]
    file_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:{file_path}",
        headers=headers,
    )
    url      = file_resp.json()["@microsoft.graph.downloadUrl"]
    resp     = requests.get(url)
    print(f"  Downloaded {file_path.split('/')[-1]}: {len(resp.content):,} bytes")
    return pd.read_excel(io.BytesIO(resp.content), sheet_name=sheet_name, engine="openpyxl")


def refresh_masters(headers):
    site_path = "/sites/WalgreensDSD-OrderAlgorithm"

    print("Downloading Store Master...")
    store_df = _download_excel(headers, site_path,
                               "/General/Masters/Convenience_Store_Master.xlsx",
                               "StoreMaster")
    for col in store_df.columns:
        if store_df[col].dtype == object:
            store_df[col] = store_df[col].astype(str)
    store_df.to_parquet("data/store_master.parquet", index=False)
    print(f"Store Master: {len(store_df)} rows saved")

    print("Downloading Product Master...")
    product_df = _download_excel(headers, site_path,
                                 "/General/Masters/Convenience_Product_Master.xlsx",
                                 "Pdt_Master_A")
    for col in product_df.columns:
        if product_df[col].dtype == object:
            product_df[col] = product_df[col].astype(str)
    product_df.to_parquet("data/product_master.parquet", index=False)
    print(f"Product Master: {len(product_df)} rows saved")


# ── Azure SQL Gold (Azure AD auth) ────────────────────────────────────────────
def _get_msal_app():
    CLIENT_ID  = os.environ["AZURE_CLIENT_ID"]
    TENANT     = os.environ["AZURE_TENANT"]
    CACHE_PATH = os.environ.get("TOKEN_CACHE_PATH", "token_cache.bin")
    persistence = FilePersistenceWithDataProtection(CACHE_PATH)
    cache = PersistedTokenCache(persistence)
    return msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT}",
        token_cache=cache,
    )


def get_sql_token():
    """Token de Azure AD para autenticarse contra Azure SQL."""
    USERNAME = os.environ["AZURE_USERNAME"]
    SCOPES   = ["https://database.windows.net/.default"]
    app = _get_msal_app()
    accounts = app.get_accounts(username=USERNAME)
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result:
        result = app.acquire_token_interactive(scopes=SCOPES, login_hint=USERNAME)
    if not result or "access_token" not in result:
        raise SystemExit(f"SQL token auth failed: {result}")
    return result["access_token"]


def connect_sql_gold():
    """Conecta a Azure SQL Gold usando token de Azure AD (sin password)."""
    import pyodbc
    server   = "sql-dsd-replica-gold.database.windows.net"
    database = "sqldb-dsd-gold"
    print(f"Connecting to Gold SQL ({database})...")
    token    = get_sql_token()
    expanded = b"".join(bytes([c, 0]) for c in token.encode("utf-8"))
    token_struct = struct.pack("=i", len(expanded)) + expanded
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};"

    def _create_conn():
        return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

    engine = create_engine("mssql+pyodbc://", creator=_create_conn)
    print("Connected!")
    return engine


def refresh_delivery_details(engine):
    """tblDeliveryDetails — entregas planeadas vs reales por tienda+UPC.
    Filtra retailers no objetivo y agrega por tienda/categoría/UPC."""
    with open("Delivery_Details.sql", "r") as f:
        query = f.read()

    print("Querying tblDeliveryDetails...")
    df = pd.read_sql(query, engine)
    print(f"  Raw: {len(df):,} rows")

    df['ArrivalDate'] = pd.to_datetime(df['ArrivalDate']).dt.date

    # Filtra retailers no objetivo (igual al M de Power Query)
    blocked_retailers = ['Costco', 'Sprouts', 'Tawa', 'Bravo', 'ElSuper', 'Fiesta', 'Michaels']
    pat = '|'.join(blocked_retailers)
    df = df[~df['StoreNumber'].astype(str).str.contains(pat, case=False, na=False)]

    # Filtra tiendas específicas
    blocked_stores = {'1BRAVO', '301SGROCERS', '304SGROCERS', '308SGROCERS', '309SGROCERS',
                      '310SGROCERS', '312SGROCERS', '314SGROCERS', '323SGROCERS',
                      '1LATINFM', '1SUPERKF', '1Liborios Latin Market'}
    df = df[~df['StoreNumber'].isin(blocked_stores)]

    # Yr corregido (semana 52/53 de enero pertenece al año anterior)
    df['Yr'] = df.apply(
        lambda r: r['Year']-1 if r['Month'] == 1 and r['ISOWk'] > 50 else r['Year'],
        axis=1
    )

    # Últimos 7 días
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=7)).date()
    df = df[df['ArrivalDate'] >= cutoff]

    # Agrupa por ArrivalDate + Store + Categoria + UPC
    grp = df.groupby(
        ['ArrivalDate', 'CompanyCode', 'StoreNumber', 'CategoryItemName', 'UPC'],
        dropna=False
    ).agg(Quantity=('Quantity', 'sum')).reset_index()

    out_dir = "Route To Delivery Data"
    os.makedirs(out_dir, exist_ok=True)
    out = f"{out_dir}/delivery_details.parquet"
    grp.to_parquet(out, index=False)
    print(f"Delivery Details: {len(grp):,} rows saved to {out}")


def refresh_route_master(headers):
    """Descarga Convenience_Route_Master.xlsx (rango A1:G142) y lo guarda en
    Route To Delivery Data/route_master.parquet."""
    site_hostname = "falconfarmsusa.sharepoint.com"
    site_path     = "/sites/WalgreensDSD-OrderAlgorithm"
    file_path     = "/General/Masters/Convenience_Route_Master.xlsx"

    print("Downloading Route Master...")
    site_id = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_hostname}:{site_path}",
        headers=headers,
    ).json()["id"]
    file_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:{file_path}",
        headers=headers,
    )
    url  = file_resp.json()["@microsoft.graph.downloadUrl"]
    resp = requests.get(url)
    print(f"  Downloaded {file_path.split('/')[-1]}: {len(resp.content):,} bytes")

    # Rango A1:G142 → 7 columnas, 141 filas de datos + header
    df = pd.read_excel(io.BytesIO(resp.content), usecols="A:G", nrows=141, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str)

    out_dir = "Route To Delivery Data"
    os.makedirs(out_dir, exist_ok=True)
    out = f"{out_dir}/route_master.parquet"
    df.to_parquet(out, index=False)
    print(f"Route Master: {len(df)} rows, {df.shape[1]} cols saved to {out}")
    print(f"  Columns: {list(df.columns)}")


def refresh_date_master(headers):
    site_hostname = "falconfarmsusa.sharepoint.com"
    site_path     = "/sites/CostcoDSDBusinessAnalysis473"
    filename      = "Date Master.xlsx"

    print("Downloading Date Master...")

    # Resolve the file's drive path via search (folder location unknown from URL)
    site_id = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_hostname}:{site_path}",
        headers=headers,
    ).json()["id"]

    items = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/search(q='{filename}')",
        headers=headers,
    ).json().get("value", [])

    match = next((i for i in items if i["name"] == filename), None)
    if not match:
        raise FileNotFoundError(f"'{filename}' not found in {site_path}")

    # Fetch the driveItem explicitly to get the download URL
    item_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{match['id']}",
        params={"select": "@microsoft.graph.downloadUrl,name"},
        headers=headers,
    )
    item_resp.raise_for_status()
    download_url = item_resp.json()["@microsoft.graph.downloadUrl"]

    resp = requests.get(download_url)
    resp.raise_for_status()
    print(f"  Downloaded {filename}: {len(resp.content):,} bytes")
    date_df = pd.read_excel(io.BytesIO(resp.content), sheet_name="Date Master", engine="openpyxl")
    for col in date_df.columns:
        if date_df[col].dtype == object:
            date_df[col] = date_df[col].astype(str)
    date_df.to_parquet("data/date_master.parquet", index=False)
    print(f"Date Master: {len(date_df)} rows saved to data/date_master.parquet")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    parser = argparse.ArgumentParser(description="Extract data from SQL and SharePoint")
    parser.add_argument("--deliveries",   action="store_true", help="Refresh deliveries data")
    parser.add_argument("--masters",      action="store_true", help="Refresh Store & Product masters from SharePoint")
    parser.add_argument("--date-master",  action="store_true", help="Refresh Date Master from SharePoint")
    parser.add_argument("--route-master",     action="store_true", help="Refresh Route Master from SharePoint")
    parser.add_argument("--delivery-details", action="store_true", help="Refresh tblDeliveryDetails from gold DB (Azure AD)")
    args = parser.parse_args()

    run_all = not any(vars(args).values())

    if run_all or args.deliveries:
        engine = connect_sql()
        refresh_deliveries(engine)

    if run_all or args.masters or args.date_master or args.route_master:
        headers = get_sharepoint_token()
        if run_all or args.masters:
            refresh_masters(headers)
        if run_all or args.date_master:
            refresh_date_master(headers)
        if run_all or args.route_master:
            refresh_route_master(headers)

    if args.delivery_details:
        engine_gold = connect_sql_gold()
        refresh_delivery_details(engine_gold)

    print("\nDone!")
