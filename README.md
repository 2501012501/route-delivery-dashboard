# Route to Delivery — Dashboard

Dashboard de seguimiento diario de rutas para CVS / Walgreens / Quiktrip.
Muestra cumplimiento de visitas, entregas vs envíos, y reporte de errores
de inventario por tienda.

## Estructura

```
Route to delivery/
├── Home.py                   ← App Streamlit principal (entry)
├── pages/                    ← Páginas (Daily Follow, Sent vs Delivery, Errors, 7-Day)
├── lib/                      ← Módulos compartidos (data, filters, refresh, theme)
├── .streamlit/config.toml    ← Tema McKinsey blue
├── dashboard.py              ← Stub legacy → redirige a Home.py
├── RouteToDelivery.py        ← Baja inventory/delivery/visits de Retex API
├── extract.py                ← Baja masters de SharePoint y SQL on-prem
├── Transform.py              ← Procesa raw SQL → parquets finales
├── Deliveries.sql            ← Query SQL on-prem
├── Sales_Query_Connection.sql
├── DSD_Tbl_Orders.sql
├── data/                     ← Data del SQL on-prem + masters
│   ├── deliveries.parquet           ← lo lee dashboard.py
│   ├── sales.parquet                ← lo lee RouteToDelivery.py
│   ├── sales_raw.parquet            ← input de Transform.py
│   ├── deliveries_raw.parquet       ← input de Transform.py
│   ├── orders_raw.parquet           ← input de Transform.py
│   ├── store_master.parquet         ← input de Transform.py
│   └── product_master.parquet       ← input de Transform.py
└── Route To Delivery Data/   ← Data del API Retex (la que muestra el dashboard)
    ├── inventory.parquet
    ├── delivery.parquet
    ├── visits.parquet
    ├── store_master.parquet
    └── route_master.parquet
```

## Setup (primera vez)

1. Instalar Python 3.11 o 3.12.
2. Instalar dependencias:
   ```powershell
   pip install streamlit==1.40.0 pandas pyodbc sqlalchemy msal msal-extensions python-dotenv requests openpyxl pyarrow
   ```
3. Copiar `.env.example` a `.env` y llenar con las credenciales reales.
4. (Solo Windows) Verificar que esté instalado el driver "ODBC Driver 17 for SQL Server".

## Cómo correr

```powershell
python -m streamlit run Home.py
```

Se abre en `http://localhost:8501`. `Ctrl+C` para detener.

## Refrescar datos desde la sidebar

| Botón | Qué hace | Tiempo |
|---|---|---|
| 🔁 API | Re-baja inventory/delivery/visits de Retex (últimos 7 días) | 1-2 min |
| 📋 Masters | Re-baja Route Master de SharePoint | <30 seg |
| 📦 Enviado | Corre `extract.py --deliveries` + `Transform.py` (SQL on-prem) | 30-60 seg |

## Refrescar manualmente desde terminal

```powershell
python RouteToDelivery.py                         # API Retex
python extract.py --route-master                  # SharePoint route master
python extract.py --deliveries && python Transform.py   # SQL on-prem
```

## Filtros del sidebar

- **Fecha** — qué día revisar
- **Cluster** — Miami, Dallas, Orlando, etc. (10 clusters con rutas planeadas)
- **Customer** — CVS, Walgreens, Quiktrip
- **Ruta** — Route_ID_AFS específico (cascada por cluster + customer)
- **Tienda** — Store_Number específico
- **Activity Type** — Driver Merchandiser Visit / Supervisor Visit
- **Solo rutas programadas** — usa Service Days del route master

## Páginas

Las páginas viven en `pages/` y se ven en el sidebar:

- **Daily Follow** — cumplimiento de visitas del día por cluster y por ruta.
  Detalle por ruta con tiendas marcadas como Visited / In progress / Pending.
- **Sent vs Delivery** — compara DELIVERY UNITS (warehouse) vs
  DeliveredBunches (driver) por ruta.
- **Errors** — diferencias de inventario:
  `Initial + Delivery − Credits − Final ≠ 0`.
- **7-Day Summary** — vista ejecutiva: tendencia de cumplimiento, sent vs
  delivered, top tiendas con más errores en los últimos 7 días.

### Lógica de inclusión de rutas

Por defecto la dashboard muestra:
- Rutas **programadas** para el día (Service Days) — aunque no hayan sido
  visitadas (aparecen como Pending).
- Más rutas con **actividad** (visitas / deliveries) ese día — aunque no
  estén programadas (caso de cambio de horario).

El checkbox **"Show all routes"** del sidebar permite ver todas las rutas
del route master sin filtrar.
