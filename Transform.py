import os
import pandas as pd
from dotenv import load_dotenv
 
load_dotenv()
 
# ── Cargar data extraída ──────────────────────────────────────────────────────
print("Loading raw data...")
deliveries_raw = pd.read_parquet("data/deliveries_raw.parquet")
store_df       = pd.read_parquet("data/store_master.parquet")
product_df     = pd.read_parquet("data/product_master.parquet")
print(f"Raw SP Rows loaded: {len(deliveries_raw)}")

# ── Transformaciones Deliveries ───────────────────────────────────────────────
print("Transforming Deliveries...")
deliveries_df = deliveries_raw[[
    'FechaTransaccion', 'Devuelto', 'InventarioFinal', 'Facturado',
    'ValorFacturado', 'ValorDevuelto', 'Store', 'NombreGrupo',
    'UPC11', 'InventarioRack'
]].copy()
 
deliveries_df[['CUSTOMER_RAW', 'CLUSTER XXX']] = deliveries_df['NombreGrupo'].str.split('-', n=1, expand=True)
deliveries_df['CUSTOMER_RAW'] = deliveries_df['CUSTOMER_RAW'].str.strip()
deliveries_df['CLUSTER XXX']  = deliveries_df['CLUSTER XXX'].str.strip()
 
deliveries_df['CUSTOMER'] = deliveries_df['CUSTOMER_RAW'].replace({
    'WLG': 'Walgreens',
    'QKT': 'Quiktrip'
})
 
deliveries_df = deliveries_df.rename(columns={
    'Facturado'     : 'DELIVERY UNITS',
    'ValorFacturado': 'DELIVERIES $FPC',
    'Devuelto'      : 'SHRINK UNITS',
    'ValorDevuelto' : 'SHRINK $FPC',
    'UPC11'         : 'UPC'
})
 
deliveries_df['KEY']             = (deliveries_df['CUSTOMER'] + '-' +
                                    deliveries_df['CLUSTER XXX'] + '-' +
                                    deliveries_df['UPC'].astype(str))
deliveries_df['STORE NUMBER WF'] = deliveries_df['Store'] + deliveries_df['CUSTOMER']
deliveries_df['DATE']            = pd.to_datetime(deliveries_df['FechaTransaccion']).dt.date
 
cluster_exclude = ['DSD', 'DSD ARIZONA', 'DSD HOUSTON', 'DSD TEXAS']
deliveries_df = deliveries_df[
    deliveries_df['CLUSTER XXX'].notna() &
    ~deliveries_df['CLUSTER XXX'].isin(cluster_exclude)
]
deliveries_df = deliveries_df[deliveries_df['DATE'] > pd.Timestamp('2022-12-31').date()]
 
deliveries_df = deliveries_df[[
    'DATE', 'STORE NUMBER WF', 'CUSTOMER', 'CLUSTER XXX', 'UPC',
    'SHRINK UNITS', 'DELIVERY UNITS', 'SHRINK $FPC', 'DELIVERIES $FPC',
    'InventarioFinal', 'InventarioRack', 'KEY'
]]
 
# Merge con Store Master
deliveries_df = deliveries_df.merge(
    store_df[['Store Number WF', 'Cluster', 'Cluster xxx', 'Route', 'Route_ID_WF',
              'Route_ID_AFS', 'Display Type (AB) - Sales', 'Same Store', 'VIP ', 'Store Type ']],
    left_on='STORE NUMBER WF',
    right_on='Store Number WF',
    how='left'
).drop(columns=['Store Number WF']).rename(columns={
    'Cluster'    : 'CLUSTER FULL',
    'Cluster xxx': 'CLUSTER XXX MASTER',
    'VIP '       : 'VIP',
    'Store Type ': 'Store Type'
})

for col in ['Route', 'Route_ID_WF', 'Route_ID_AFS', 'Display Type (AB) - Sales',
            'Same Store', 'VIP', 'Store Type']:
    deliveries_df[col] = deliveries_df[col].fillna('')

# Merge con Product Master
deliveries_df = deliveries_df.merge(
    product_df[['Key2', 'Transfer Price']],
    left_on='KEY',
    right_on='Key2',
    how='left'
)
 
deliveries_df['Transfer Price'] = pd.to_numeric(deliveries_df['Transfer Price'], errors='coerce')
deliveries_df['Flower cost']    = deliveries_df['DELIVERY UNITS'] * deliveries_df['Transfer Price']
deliveries_df = deliveries_df.sort_values('DATE', ascending=False)
 
print(f"Deliveries Final Rows: {len(deliveries_df)}")
print(deliveries_df.head())
 
deliveries_df['DATE'] = pd.to_datetime(deliveries_df['DATE']).dt.date
for col in deliveries_df.columns:
    if deliveries_df[col].dtype == object:
        deliveries_df[col] = deliveries_df[col].astype(str)
 
deliveries_df.to_parquet("data/deliveries.parquet", index=False)
deliveries_df.to_csv("data/deliveries_final.csv", index=False, na_rep='')
print("Deliveries saved!")
