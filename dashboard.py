"""
Route and day activity dashboard.
Launch with:  streamlit run dashboard.py
"""
import os
import re
import socket
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path("Route To Delivery Data")

# Detect if running on Streamlit Community Cloud (no VPN, no on-prem SQL access)
IS_CLOUD = ('/mount/src/' in os.getcwd()) or bool(os.environ.get('STREAMLIT_RUNTIME'))

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Route Delivery Dashboard", layout="wide", page_icon="🚚")
st.title("🚚 Route Delivery Dashboard")
st.caption("Retex/AFS data · last 7 days · CVS / Walgreens / Quiktrip")


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading data...")
def load_data():
    inv = pd.read_parquet(DATA_DIR / "inventory.parquet")
    dlv = pd.read_parquet(DATA_DIR / "delivery.parquet")
    vis = pd.read_parquet(DATA_DIR / "visits.parquet")
    sm  = pd.read_parquet(DATA_DIR / "store_master.parquet")

    # "Sent" = data/deliveries.parquet (extract --deliveries + Transform.py)
    sent_path = Path("data") / "deliveries.parquet"
    sent = pd.read_parquet(sent_path) if sent_path.exists() else None
    if sent is not None:
        sent['DATE'] = pd.to_datetime(sent['DATE'], errors='coerce').dt.date
        sent['DELIVERY UNITS'] = pd.to_numeric(sent['DELIVERY UNITS'], errors='coerce').fillna(0)
        # Keep only the last 14 days (enough to compare and stay lightweight)
        cutoff = (pd.Timestamp.now() - pd.Timedelta(days=14)).date()
        sent = sent[sent['DATE'] >= cutoff]

    inv['Answer_Date']         = pd.to_datetime(inv['Answer_Date']).dt.date
    dlv['Created_Date']        = pd.to_datetime(dlv['Created_Date']).dt.date
    vis['Appointment_DateTime'] = pd.to_datetime(vis['Appointment_DateTime'], errors='coerce', utc=True).dt.tz_localize(None)

    # "Real" visit = the person actually showed up.
    #   If we have First_Realization_DateTime (new loader) we use it directly.
    #   Otherwise fallback: Appointment_DateTime <= now (excludes future appointments).
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


inv, dlv, vis, sm, rm, rm_error, sent = load_data()

if rm is None:
    st.error(
        f"Cannot find `{DATA_DIR / 'route_master.parquet'}`. "
        "Run first:  `python extract.py --route-master`. "
        + (f"Error: {rm_error}" if rm_error else "")
    )
    st.stop()


# ── Service Days parser ───────────────────────────────────────────────────────
# Maps any common day spelling → "Mon".."Sun"
_DAY_MAP = {
    'mon': 'Mon', 'monday': 'Mon', 'lun': 'Mon', 'lunes': 'Mon',
    'tue': 'Tue', 'tues': 'Tue', 'tuesday': 'Tue', 'mar': 'Tue', 'martes': 'Tue',
    'wed': 'Wed', 'weds': 'Wed', 'wednesday': 'Wed', 'mie': 'Wed', 'mié': 'Wed', 'miercoles': 'Wed', 'miércoles': 'Wed',
    'thu': 'Thu', 'thur': 'Thu', 'thurs': 'Thu', 'thursday': 'Thu', 'jue': 'Thu', 'jueves': 'Thu',
    'fri': 'Fri', 'friday': 'Fri', 'vie': 'Fri', 'viernes': 'Fri',
    'sat': 'Sat', 'saturday': 'Sat', 'sab': 'Sat', 'sáb': 'Sat', 'sabado': 'Sat', 'sábado': 'Sat',
    'sun': 'Sun', 'sunday': 'Sun', 'dom': 'Sun', 'domingo': 'Sun',
}
# Unambiguous short letters
_LETTER_MAP = {'M':'Mon','T':'Tue','W':'Wed','R':'Thu','F':'Fri','S':'Sat','U':'Sun'}


def parse_service_days(value):
    """Returns set of days {'Mon','Wed',...} from free-form text."""
    if pd.isna(value): return set()
    s = str(value).strip()
    if not s: return set()
    out = set()
    # 1) words (Mon, Lun, Wednesday, etc.)
    for tok in re.split(r'[,;/\s|+]+', s.lower()):
        if tok in _DAY_MAP:
            out.add(_DAY_MAP[tok])
    if out: return out
    # 2) two-letter abbreviations like "Mo Tu We Th Fr Sa Su"
    for tok in re.findall(r'\b(Mo|Tu|We|Th|Fr|Sa|Su)\b', s, flags=re.I):
        out.add({'mo':'Mon','tu':'Tue','we':'Wed','th':'Thu','fr':'Fri','sa':'Sat','su':'Sun'}[tok.lower()])
    if out: return out
    # 3) concatenated letters like "MWF" / "MTWThF"
    s2 = s.replace('Th','R').replace('Su','U')
    for ch in s2:
        if ch in _LETTER_MAP:
            out.add(_LETTER_MAP[ch])
    return out


# Identify route master columns (tolerant to case/accents/spaces)
def find_col(df, *candidates):
    norm = {c: re.sub(r'[\s\.\-_]+','', c).lower() for c in df.columns}
    for cand in candidates:
        cand_n = re.sub(r'[\s\.\-_]+','', cand).lower()
        for c, n in norm.items():
            if n == cand_n: return c
        for c, n in norm.items():
            if cand_n in n: return c
    return None


col_route_no   = find_col(rm, 'Route No', 'Route Number', 'Route')
col_route_afs  = find_col(rm, 'Route_ID_AFS', 'Route ID AFS')
col_cluster    = find_col(rm, 'Cluster')
col_service    = find_col(rm, 'Service Days', 'ServiceDays', 'Days')
col_stops      = find_col(rm, 'Stops')
col_cost_stop  = find_col(rm, 'Cost/Stop', 'CostPerStop', 'Cost/stop')

if col_service is None or col_route_afs is None:
    st.error(
        f"Required columns not found in route_master.xlsx. "
        f"Detected: {list(rm.columns)}. "
        "Need at least 'Route_ID_AFS' and 'Service Days'."
    )
    st.stop()

rm['_days'] = rm[col_service].apply(parse_service_days)

# ── Refresh helpers ──────────────────────────────────────────────────────────
def _publish_to_cloud():
    """Stage data files, commit, and push to GitHub so Streamlit Cloud redeploys."""
    project_dir = Path(__file__).parent
    with st.spinner("Publishing to cloud..."):
        # Stage data folders (.gitignore filters out CSVs and legacy files)
        r = subprocess.run(
            ["git", "add", "data", "Route To Delivery Data"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if r.returncode != 0:
            st.error(f"git add failed:\n```\n{r.stderr or r.stdout}\n```")
            return False

        ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
        r = subprocess.run(
            ["git", "commit", "-m", f"Auto: data update {ts}"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if r.returncode != 0:
            combined = (r.stdout + r.stderr).lower()
            if "nothing to commit" in combined or "nothing added" in combined:
                st.info("ℹ️ No data changes to publish.")
                return True
            st.error(f"git commit failed:\n```\n{r.stderr or r.stdout}\n```")
            return False

        r = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if r.returncode != 0:
            st.error(f"git push failed:\n```\n{r.stderr or r.stdout}\n```")
            return False
    st.success("☁️ Published to cloud — Streamlit will update in ~1 min")
    return True


def _run_script(args, label, publish=False):
    """Run a Python script. Optionally publish to cloud after success."""
    project_dir = Path(__file__).parent
    with st.spinner(f"Refreshing {label}..."):
        r = subprocess.run(
            [sys.executable, *args],
            capture_output=True, text=True, cwd=project_dir,
        )
    if r.returncode != 0:
        st.error(f"Error refreshing {label}:\n```\n{(r.stderr or r.stdout)[-1000:]}\n```")
        return
    st.success(f"{label} refreshed ✓")
    if publish:
        _publish_to_cloud()
    st.cache_data.clear()
    st.rerun()


def _run_chain(steps, publish=False):
    """Run several scripts in order. Optionally publish to cloud after success."""
    project_dir = Path(__file__).parent
    for args, label in steps:
        with st.spinner(f"Refreshing {label}..."):
            r = subprocess.run(
                [sys.executable, *args],
                capture_output=True, text=True, cwd=project_dir,
            )
        if r.returncode != 0:
            st.error(f"{label} failed:\n```\n{(r.stderr or r.stdout)[-1500:]}\n```")
            return
    st.success("Refreshed ✓")
    if publish:
        _publish_to_cloud()
    st.cache_data.clear()
    st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Last recorded visit (freshness proxy)
    last_visit = vis['Visit_DateTime'].max() if not vis.empty else None
    st.header("📡 Data")
    if pd.notna(last_visit):
        st.caption(f"Last visit recorded: **{last_visit.strftime('%Y-%m-%d %H:%M')}**")
    else:
        st.caption("No visits recorded yet")

    if IS_CLOUD:
        st.caption("🌐 **Read-only view** — refresh disabled in cloud. "
                   "Data updated when the owner pushes new files.")
    else:
        auto_publish = st.checkbox(
            "☁️ Auto-publish to cloud after refresh", value=True,
            help="After refreshing, push data to GitHub so the Streamlit Cloud "
                 "link updates automatically for everyone.",
        )

        rb1, rb2, rb3 = st.columns(3)
        if rb1.button("🔁 API", use_container_width=True,
                      help="Re-download inventory/delivery/visits from Retex (~1-2 min)"):
            _run_script(["RouteToDelivery.py"], "API", publish=auto_publish)
        if rb2.button("📋 Masters", use_container_width=True,
                      help="Re-download Route Master from SharePoint"):
            _run_script(["extract.py", "--route-master"], "Route Master", publish=auto_publish)
        if rb3.button("📦 Sent", use_container_width=True,
                      help="Re-download deliveries from on-prem SQL and run Transform.py"):
            _run_chain([
                (["extract.py", "--deliveries"], "Deliveries SQL"),
                (["Transform.py"],               "Transform"),
            ], publish=auto_publish)

        # ── Share link with team (LAN) ───────────────────────────────────────
        try:
            port = int(st.get_option('server.port'))
        except Exception:
            port = 8501
        hostname = socket.gethostname().lower()
        local_ips = []
        try:
            local_ips = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                         if not ip.startswith('127.')]
        except Exception:
            pass

        with st.expander("🔗 Share with team"):
            st.caption("Send this link to your team (must be on the Falcon VPN):")
            st.code(f"http://{hostname}:{port}", language=None)
            if local_ips:
                st.caption("Or use IP directly:")
                for ip in local_ips:
                    st.code(f"http://{ip}:{port}", language=None)
            st.caption(
                "ℹ️ Your laptop must stay on and connected to the Falcon VPN "
                "for the link to work."
            )

    st.divider()
    st.header("Filters")

    available_dates = sorted(set(inv['Answer_Date']) | set(dlv['Created_Date']) | set(vis['Visit_Date'].dropna()))
    default_date = max(available_dates) if available_dates else date.today()
    target_date = st.date_input(
        "Date", value=default_date,
        min_value=min(available_dates) if available_dates else None,
        max_value=max(available_dates) if available_dates else None,
    )

    # Cluster: only those present in route master
    rm_clusters = rm[col_cluster].dropna().astype(str).str.strip().str.upper().unique() if col_cluster else []
    sm_full     = sm['CLUSTER FULL'].dropna().astype(str).str.strip().str.upper().unique()
    cluster_options = ['(All)'] + sorted(set(rm_clusters) & set(sm_full))
    cluster_filter  = st.selectbox("Cluster", cluster_options)

    # Customer multiselect
    customer_options = sorted(sm['CUSTOMER'].dropna().unique().tolist())
    customer_filter  = st.multiselect("Customer", customer_options, default=customer_options)

    # Route multiselect — limited by cluster + customer when applied
    sm_filtered = sm.copy()
    if cluster_filter != '(All)':
        sm_filtered = sm_filtered[sm_filtered['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    if customer_filter:
        sm_filtered = sm_filtered[sm_filtered['CUSTOMER'].isin(customer_filter)]
    route_options = sorted(sm_filtered['Route_ID_AFS'].dropna().unique().tolist())
    route_filter  = st.multiselect("Route (Route_ID_AFS)", route_options,
                                    help="Empty = all routes matching the other filters")

    # Store multiselect — limited by previous filters
    if route_filter:
        sm_filtered = sm_filtered[sm_filtered['Route_ID_AFS'].isin(route_filter)]
    store_options = sorted(sm_filtered['Store_Number'].dropna().unique().tolist())
    store_filter  = st.multiselect("Store (Store_Number)", store_options,
                                    help="Empty = all stores")

    # Activity_Type — uses values from the parquet if present, otherwise the known ones
    KNOWN_ACTIVITIES = ['Driver Merchandiser Visit', 'Supervisor Visit']
    if 'Activity_Type' in vis.columns:
        at_options = sorted(set(vis['Activity_Type'].dropna().unique().tolist()) | set(KNOWN_ACTIVITIES))
    else:
        at_options = KNOWN_ACTIVITIES
    activity_filter = st.multiselect("Activity Type", at_options, default=at_options,
                                      help="If filtering shows no change, refresh the API (🔁) — the field isn't in the loaded data yet.")

    show_only_route_day = st.checkbox(
        "Show only routes scheduled for this day (Service Days)",
        value=True,
        help="Disable to see every route with activity that day even if it's not in the calendar."
    )

# ── Day-of-week filter on routes ──────────────────────────────────────────────
dow = target_date.strftime('%a')   # Mon, Tue, Wed, Thu, Fri, Sat, Sun

routes_today = rm.copy()
if show_only_route_day:
    routes_today = routes_today[routes_today['_days'].apply(lambda s: dow in s)]

if cluster_filter != '(All)' and col_cluster:
    routes_today = routes_today[
        routes_today[col_cluster].astype(str).str.strip().str.upper() == cluster_filter
    ]
if route_filter:
    routes_today = routes_today[routes_today[col_route_afs].isin(route_filter)]


# ── Apply filters to fact tables ─────────────────────────────────────────────
def apply_filters(df, *, also_activity=False):
    if cluster_filter != '(All)' and 'CLUSTER FULL' in df.columns:
        df = df[df['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    if customer_filter and 'CUSTOMER' in df.columns:
        df = df[df['CUSTOMER'].isin(customer_filter)]
    if route_filter and 'Route_ID_AFS' in df.columns:
        df = df[df['Route_ID_AFS'].isin(route_filter)]
    if store_filter and 'Store_Number' in df.columns:
        df = df[df['Store_Number'].isin(store_filter)]
    if also_activity and activity_filter and 'Activity_Type' in df.columns:
        df = df[df['Activity_Type'].isin(activity_filter)]
    return df


inv_d = apply_filters(inv[inv['Answer_Date']  == target_date]).copy()
dlv_d = apply_filters(dlv[dlv['Created_Date'] == target_date]).copy()
vis_d = apply_filters(vis[vis['Visit_Date']   == target_date], also_activity=True).copy()


# ── Deduplication: keep the last record of the day ───────────────────────────
def latest_per(df, key_cols, time_col):
    if df.empty: return df
    df = df.sort_values(time_col)
    return df.drop_duplicates(subset=key_cols, keep='last')


inv_latest = latest_per(
    inv_d,
    key_cols=['Store_Number', 'Product_EAN', 'Monitoring_Name'],
    time_col='Answer_Time',
)
dlv_latest = latest_per(
    dlv_d,
    key_cols=['Store_Number', 'Product_EAN', 'Document_Type_Name'],
    time_col='Created_Time',
)


# ── Top metrics ───────────────────────────────────────────────────────────────
total_bunches = dlv_latest.loc[dlv_latest['Document_Type_Name'] == 'Delivery', 'DeliveredBunches'].sum()
total_credits = dlv_latest.loc[dlv_latest['Document_Type_Name'] == 'Credits (RTV)', 'DeliveredBunches'].sum()
visited_stores = vis_d['Store_Number'].nunique()

if show_only_route_day:
    expected_route_ids = routes_today[col_route_afs].dropna().unique().tolist()
    expected_stores = sm[sm['Route_ID_AFS'].isin(expected_route_ids)]
    if cluster_filter != '(All)':
        expected_stores = expected_stores[expected_stores['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    total_expected = expected_stores['Store_Number'].nunique()
else:
    total_expected = sm[sm['Route_ID_AFS'].isin(routes_today[col_route_afs].dropna().unique())]['Store_Number'].nunique()

# Banner: last data load timestamp
last_visit_main = vis['Visit_DateTime'].max() if not vis.empty else None
if pd.notna(last_visit_main):
    delta = pd.Timestamp.now() - last_visit_main
    mins = int(delta.total_seconds() // 60)
    if mins < 60:
        ago = f"{mins} min ago"
    elif mins < 60*24:
        ago = f"{mins//60} h ago"
    else:
        ago = f"{mins//(60*24)} d ago"
    st.info(f"📡 **Last visit recorded:** {last_visit_main.strftime('%Y-%m-%d %H:%M')}  ·  _{ago}_")

# Main metrics with short date
compliance_pct = (visited_stores / total_expected) if total_expected else 0
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📅 Day", target_date.strftime("%a %b %d"))
c2.metric("🛣️ Routes", len(routes_today))
c3.metric("🏪 Visited", f"{visited_stores} / {total_expected}",
          delta=f"{compliance_pct:.0%}", delta_color="off")
c4.metric("💐 Bunches", f"{int(total_bunches):,}")
c5.metric("↩️ Credits/RTV", f"{int(total_credits):,}")

# Global compliance bar
if total_expected:
    bar_color = "#22c55e" if compliance_pct >= 0.9 else "#f59e0b" if compliance_pct >= 0.6 else "#ef4444"
    pct_text = f"{compliance_pct:.0%}"
    st.markdown(
        f"""
        <div style="margin: 8px 0 4px 0; font-weight: 600;">Visit compliance</div>
        <div style="background:#e5e7eb;border-radius:8px;height:24px;width:100%;position:relative;overflow:hidden;">
          <div style="background:{bar_color};width:{compliance_pct*100:.1f}%;height:100%;
                      transition:width .5s ease;"></div>
          <div style="position:absolute;top:0;left:0;width:100%;height:100%;
                      display:flex;align-items:center;justify-content:center;
                      font-weight:700;color:#111827;font-size:13px;">
            {visited_stores} / {total_expected}  ·  {pct_text}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Cluster compliance (horizontal bars) ─────────────────────────────────────
def _cluster_compliance_data():
    """Returns a DataFrame with Cluster, Visited, Planned, Pct for the clusters
    present in routes_today. Respects sidebar filters."""
    if routes_today.empty:
        return pd.DataFrame()
    rows = []
    grouped = routes_today.groupby(col_cluster, dropna=False) if col_cluster else [(None, routes_today)]
    for cluster_name, group in grouped:
        rids = group[col_route_afs].dropna().unique()
        stores = sm[sm['Route_ID_AFS'].isin(rids)]
        if customer_filter:
            stores = stores[stores['CUSTOMER'].isin(customer_filter)]
        if store_filter:
            stores = stores[stores['Store_Number'].isin(store_filter)]
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


def _render_cluster_bars(df):
    """Modern horizontal bars with red/amber/green color coding."""
    if df.empty:
        return
    css = """
    <style>
      .cb-wrap { display: flex; flex-direction: column; gap: 12px; padding: 4px 0 8px 0; }
      .cb-row  { display: grid; grid-template-columns: 140px 1fr 70px;
                 align-items: center; gap: 14px; }
      .cb-label { font-weight: 600; color: #1f2937; font-size: 14px;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .cb-track { background: #f3f4f6; border-radius: 999px; height: 16px;
                  position: relative; box-shadow: inset 0 1px 2px rgba(0,0,0,.06);
                  overflow: hidden; }
      .cb-fill  { height: 100%; border-radius: 999px;
                  background-image: linear-gradient(180deg, rgba(255,255,255,.15), rgba(0,0,0,0));
                  animation: cb-grow .9s cubic-bezier(.4,0,.2,1) both;
                  transition: width .6s cubic-bezier(.4,0,.2,1); }
      @keyframes cb-grow { from { width: 0; } }
      .cb-pct  { font-weight: 700; color: #111827; font-size: 13px;
                 text-align: right; font-variant-numeric: tabular-nums; }
      .cb-sub  { font-size: 11px; color: #6b7280; font-weight: 500; margin-left: 6px; }
      @media (max-width: 700px) {
        .cb-row { grid-template-columns: 100px 1fr 60px; gap: 8px; }
        .cb-label { font-size: 12px; }
      }
    </style>
    """
    body = '<div class="cb-wrap">'
    for _, r in df.iterrows():
        pct = float(r['Pct'])
        if pct < 0.40:
            color = "#E53935"   # red
        elif pct < 0.70:
            color = "#FBC02D"   # amber
        else:
            color = "#43A047"   # green
        body += (
            f'<div class="cb-row">'
            f'  <div class="cb-label">{r["Cluster"]}'
            f'    <span class="cb-sub">{int(r["Visited"])}/{int(r["Planned"])}</span>'
            f'  </div>'
            f'  <div class="cb-track">'
            f'    <div class="cb-fill" style="width:{min(pct,1.0)*100:.1f}%;background:{color};"></div>'
            f'  </div>'
            f'  <div class="cb-pct">{pct:.0%}</div>'
            f'</div>'
        )
    body += '</div>'
    st.markdown(css + body, unsafe_allow_html=True)


# ── Reusable functions for the tabs ──────────────────────────────────────────
def store_day_summary(target_route_ids):
    """Per-store summary for the selected routes on the day."""
    stores = sm[sm['Route_ID_AFS'].isin(target_route_ids)].copy()
    if cluster_filter != '(All)':
        stores = stores[stores['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    if customer_filter:
        stores = stores[stores['CUSTOMER'].isin(customer_filter)]
    if store_filter:
        stores = stores[stores['Store_Number'].isin(store_filter)]

    # Duration: prefer Actual_duration (real), otherwise CostCenter_Duration (legacy)
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
        vis_grp = pd.DataFrame(columns=['Store_Number','Visited','First_Visit','Last_Visit','Avg_Duration_min','Order_Count','Total_Ordered','Total_Delivered'])
    stores = stores.merge(vis_grp, on='Store_Number', how='left')
    stores['Visited'] = stores['Visited'].fillna(0).astype(int)

    # Bunches delivered (Delivery only, no Credits) — sum the day's latest per product
    deliv_only = dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery']
    deliv_grp = deliv_only.groupby('Store_Number')['DeliveredBunches'].sum().rename('Bunches_Delivered')
    stores = stores.merge(deliv_grp, on='Store_Number', how='left')
    stores['Bunches_Delivered'] = stores['Bunches_Delivered'].fillna(0)

    # Credits
    credits_only = dlv_latest[dlv_latest['Document_Type_Name'] == 'Credits (RTV)']
    cred_grp = credits_only.groupby('Store_Number')['DeliveredBunches'].sum().rename('Bunches_Credit')
    stores = stores.merge(cred_grp, on='Store_Number', how='left')
    stores['Bunches_Credit'] = stores['Bunches_Credit'].fillna(0)

    # Inventory: Initial vs Final (last Front of the day)
    init = inv_latest[inv_latest['Monitoring_Name'] == 'Initial Inventory']
    init_grp = init.groupby('Store_Number')['QTYInventory'].sum().rename('Initial_Inv')
    final = inv_latest[inv_latest['Monitoring_Name'] == 'Front']
    final_grp = final.groupby('Store_Number')['QTYInventory'].sum().rename('Final_Inv')
    stores = stores.merge(init_grp, on='Store_Number', how='left')
    stores = stores.merge(final_grp, on='Store_Number', how='left')
    stores['Initial_Inv'] = stores['Initial_Inv'].fillna(0)
    stores['Final_Inv']   = stores['Final_Inv'].fillna(0)

    # Errors = Initial + Delivery − Credits − Final  (in bunches/units)
    stores['Errors'] = (stores['Initial_Inv'] + stores['Bunches_Delivered']
                        - stores['Bunches_Credit'] - stores['Final_Inv'])

    return stores


def status_emoji(row):
    """🟢 visited and delivered · 🟡 visit in progress (no delivery) · 🔴 pending"""
    visited   = row.get('Visited', 0) > 0
    delivered = row.get('Bunches_Delivered', 0) > 0
    if visited and delivered:
        return "🟢 Visited"
    if visited and not delivered:
        return "🟡 In progress"
    return "🔴 Pending"


def style_status(row):
    """Background color by status for the dataframe."""
    s = row.get('Status', '')
    if s.startswith("🟢"):
        return ['background-color: #dcfce7'] * len(row)
    if s.startswith("🟡"):
        return ['background-color: #fef3c7'] * len(row)
    if s.startswith("🔴"):
        return ['background-color: #fee2e2'] * len(row)
    return [''] * len(row)


# ── Main tabs ────────────────────────────────────────────────────────────────
tab_dia, tab_envio, tab_err, tab_week = st.tabs([
    "📅 Daily Follow-up",
    "📦 Sent vs Delivered",
    "⚠️ Errors",
    "📊 7-Day Summary",
])


# ============================ TAB 1: DAILY FOLLOW-UP ==========================
with tab_dia:
    cl_df = _cluster_compliance_data()
    if not cl_df.empty:
        st.markdown("##### 📊 Cluster Compliance")
        _render_cluster_bars(cl_df)

    st.subheader(f"Active routes — {target_date.strftime('%A')} ({dow})")

    if routes_today.empty:
        st.info("No routes scheduled with the selected filters.")
    else:
        view_mode = st.radio(
            "View", ["📋 Route summary", "🔍 Route detail"],
            horizontal=True, key="view_mode_dia",
        )

        if view_mode == "📋 Route summary":
            rows = []
            for _, r in routes_today.iterrows():
                rid = r[col_route_afs]
                s = store_day_summary([rid])
                planned = len(s)
                visited = int((s['Visited'] > 0).sum())
                pct = (visited / planned) if planned else 0
                rows.append({
                    'Route No.':    r[col_route_no] if col_route_no else '',
                    'Route_ID_AFS': rid,
                    'Cluster':      r[col_cluster] if col_cluster else '',
                    'Compliance':   pct,
                    'Visited':      visited,
                    'Planned':      planned,
                    'Bunches':      int(s['Bunches_Delivered'].sum()),
                    'Credits':      int(s['Bunches_Credit'].sum()),
                    'Errors':       int(s['Errors'].sum()),
                    'Service Days': r[col_service],
                })
            df_routes = pd.DataFrame(rows).sort_values('Compliance', ascending=False)
            df_routes['Compliance'] = df_routes['Compliance'] * 100
            st.dataframe(
                df_routes,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Compliance": st.column_config.ProgressColumn(
                        "Compliance", format="%.0f%%", min_value=0, max_value=100
                    ),
                    "Bunches": st.column_config.NumberColumn(format="%d 💐"),
                    "Credits": st.column_config.NumberColumn(format="%d ↩️"),
                }
            )
        else:
            route_options = routes_today[col_route_afs].dropna().unique().tolist()
            chosen = st.selectbox("Route", route_options, key="route_detail_select")
            s = store_day_summary([chosen])
            s['Status'] = s.apply(status_emoji, axis=1)

            # Header metrics for the route
            r1, r2, r3 = st.columns(3)
            r1.metric("🟢 Visited", f"{int((s['Status'].str.startswith('🟢')).sum())} / {len(s)}")
            r2.metric("🟡 In progress", int((s['Status'].str.startswith('🟡')).sum()))
            r3.metric("🔴 Pending", int((s['Status'].str.startswith('🔴')).sum()))

            cols_show = ['Status', 'Store_Number', 'CUSTOMER', 'CLUSTER XXX',
                         'First_Visit', 'Last_Visit', 'Avg_Duration_min',
                         'Bunches_Delivered', 'Bunches_Credit',
                         'Initial_Inv', 'Final_Inv', 'Errors']
            display = s[[c for c in cols_show if c in s.columns]].copy()

            # Color by status (green / yellow / red)
            styled = display.style.apply(style_status, axis=1).format({
                'Avg_Duration_min':  '{:.1f}',
                'Bunches_Delivered': '{:.0f}',
                'Bunches_Credit':    '{:.0f}',
                'Initial_Inv':       '{:.0f}',
                'Final_Inv':         '{:.0f}',
                'Errors':            '{:+.0f}',
            }, na_rep='')
            st.dataframe(styled, use_container_width=True, hide_index=True)

            st.markdown("### Delivered products detail")
            detail = dlv_latest[
                dlv_latest['Route_ID_AFS'] == chosen
            ][['Store_Number','Created_Time','Document_Type_Name','Product_Name','Product_EAN','DeliveredBunches']]
            st.dataframe(
                detail.sort_values(['Store_Number','Created_Time']),
                use_container_width=True, hide_index=True,
            )


# ====================== TAB 2: SENT VS DELIVERED ==============================
with tab_envio:
    st.subheader("📦 Sent vs Delivered by route")

    if sent is None:
        st.info(
            "ℹ️ Cannot find `data/deliveries.parquet`. Click **📦 Sent** "
            "in the sidebar (runs `extract.py --deliveries` + `Transform.py`)."
        )
    else:
        sent_d = sent[sent['DATE'] == target_date].copy()
        sent_d = sent_d.rename(columns={'STORE NUMBER WF': 'Store_Number'})
        sent_d = apply_filters(sent_d)

        sent_by_route = sent_d.groupby('Route_ID_AFS', dropna=False)['DELIVERY UNITS'].sum().rename('Sent')
        delivered_by_route = dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery'].groupby(
            'Route_ID_AFS', dropna=False
        )['DeliveredBunches'].sum().rename('Delivered')

        routes_short = routes_today[[col_route_no, col_route_afs, col_cluster]].rename(
            columns={col_route_no: 'Route No.', col_route_afs: 'Route_ID_AFS', col_cluster: 'Cluster'}
        )
        comp = routes_short.merge(sent_by_route,      on='Route_ID_AFS', how='left')
        comp = comp.merge(delivered_by_route,         on='Route_ID_AFS', how='left')
        comp[['Sent', 'Delivered']] = comp[['Sent', 'Delivered']].fillna(0)
        comp['Compliance'] = comp.apply(
            lambda r: (r['Delivered'] / r['Sent']) if r['Sent'] > 0 else 0, axis=1
        )
        comp['Diff'] = comp['Delivered'] - comp['Sent']

        if comp[['Sent', 'Delivered']].sum().sum() == 0:
            st.warning(
                f"No sent/delivered data for {target_date.strftime('%a %b %d')}. "
                "If the date is very recent, refresh **📦 Sent**."
            )
        else:
            total_sent      = comp['Sent'].sum()
            total_delivered = comp['Delivered'].sum()
            global_pct = (total_delivered / total_sent) if total_sent else 0
            bar_color = "#22c55e" if global_pct >= 0.9 else "#f59e0b" if global_pct >= 0.6 else "#ef4444"
            st.markdown(
                f"""
                <div style="margin: 8px 0 4px 0; font-weight: 600;">
                    Delivered vs Sent: {int(total_delivered):,} / {int(total_sent):,} units
                </div>
                <div style="background:#e5e7eb;border-radius:8px;height:24px;width:100%;position:relative;overflow:hidden;">
                  <div style="background:{bar_color};width:{min(global_pct,1.0)*100:.1f}%;height:100%;"></div>
                  <div style="position:absolute;top:0;left:0;width:100%;height:100%;
                              display:flex;align-items:center;justify-content:center;
                              font-weight:700;color:#111827;font-size:13px;">{global_pct:.0%}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            comp_show = comp.sort_values('Compliance', ascending=False).copy()
            comp_show['Compliance'] = comp_show['Compliance'] * 100
            st.dataframe(
                comp_show,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Compliance": st.column_config.ProgressColumn(
                        "Compliance", format="%.0f%%", min_value=0, max_value=100
                    ),
                    "Sent":       st.column_config.NumberColumn(format="%d 📦"),
                    "Delivered":  st.column_config.NumberColumn(format="%d 💐"),
                    "Diff":       st.column_config.NumberColumn(format="%+d"),
                }
            )


# =========================== TAB 3: ERRORS ====================================
with tab_err:
    st.subheader("⚠️ Error Report")
    st.caption("Difference = Initial Inventory + Delivered − Credits − Final Inventory")

    # Tab-specific filters
    fc1, fc2 = st.columns([2, 1])
    with fc1:
        prod_search = st.text_input("🔎 Search store or user", "",
                                     placeholder="Store_Number or User_Name",
                                     key="err_prod_search")
    with fc2:
        only_pos = st.selectbox("Type", ["All", "Shortages only (+)", "Overages only (−)"],
                                 key="err_sign_filter")

    # Inventory and deliveries grouped at STORE level (summing products)
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

    # Visits per store → User_Name + Activity_Type (comma-separated if multiple)
    if not vis_d.empty:
        vis_grp = vis_d.groupby('Store_Number', dropna=False).agg(
            User_Name=('User_Name', lambda x: ', '.join(sorted(set(x.dropna().astype(str))))),
            Activity_Type=('Activity_Type', lambda x: ', '.join(sorted(set(x.dropna().astype(str))))),
        ).reset_index()
        err = err.merge(vis_grp, on='Store_Number', how='left')
    else:
        err['User_Name'] = ''
        err['Activity_Type'] = ''

    # Attach Route No. and store attributes
    err = err.merge(
        sm[['Store_Number', 'Route_ID_AFS', 'CUSTOMER', 'CLUSTER FULL']],
        on='Store_Number', how='left',
    )
    # Bring in "Route No." from route_master
    rm_route_no = rm[[col_route_afs, col_route_no]].rename(
        columns={col_route_afs: 'Route_ID_AFS', col_route_no: 'Route No.'}
    )
    err = err.merge(rm_route_no, on='Route_ID_AFS', how='left')

    # Apply sidebar filters
    if cluster_filter != '(All)':
        err = err[err['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    if customer_filter:
        err = err[err['CUSTOMER'].isin(customer_filter)]
    if route_filter:
        err = err[err['Route_ID_AFS'].isin(route_filter)]
    if store_filter:
        err = err[err['Store_Number'].isin(store_filter)]

    # Only rows with Difference != 0
    err = err[err['Difference'].abs() >= 1]

    # Tab-specific filters
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
        st.success("✅ No significant errors for the selected filters and date.")
    else:
        pos = err.loc[err['Difference'] > 0, 'Difference'].sum()
        neg = err.loc[err['Difference'] < 0, 'Difference'].sum()
        n_stores = err['Store_Number'].nunique()
        n_routes = err['Route No.'].nunique()

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("📉 Shortage (sum)", f"{int(pos):,}")
        e2.metric("📈 Overage (sum)", f"{int(neg):,}")
        e3.metric("🏪 Stores with error", f"{n_stores:,}")
        e4.metric("🛣️ Routes with error",   f"{n_routes:,}")

        show_cols = ['Route No.', 'CLUSTER FULL', 'User_Name', 'Activity_Type',
                     'Initial Inventory', 'Delivery', 'Credits', 'Final Inventory',
                     'Difference']
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


# ====================== TAB 4: 7-DAY SUMMARY ==================================
with tab_week:
    st.subheader("📊 Last 7 Days Summary")
    week_start = target_date - timedelta(days=6)
    st.caption(
        f"Period: **{week_start.strftime('%a %b %d')}** → **{target_date.strftime('%a %b %d')}** "
        "· Sidebar filters apply (Date is replaced by this 7-day window). "
        "Goal: drive towards 100% compliance."
    )

    # ── 1) Filter all sources to the 7-day window ────────────────────────────
    inv_w = apply_filters(inv[(inv['Answer_Date']  >= week_start) & (inv['Answer_Date']  <= target_date)]).copy()
    dlv_w = apply_filters(dlv[(dlv['Created_Date'] >= week_start) & (dlv['Created_Date'] <= target_date)]).copy()
    vis_w = apply_filters(vis[(vis['Visit_Date']   >= week_start) & (vis['Visit_Date']   <= target_date)],
                          also_activity=True).copy()
    sent_w = None
    if sent is not None:
        sent_w = sent[(sent['DATE'] >= week_start) & (sent['DATE'] <= target_date)].copy()
        sent_w = sent_w.rename(columns={'STORE NUMBER WF': 'Store_Number'})
        sent_w = apply_filters(sent_w)

    # Latest record per (store, product, day) for inventory & deliveries
    inv_w_latest = (inv_w.sort_values('Answer_Time')
                        .drop_duplicates(subset=['Store_Number','Product_EAN','Monitoring_Name','Answer_Date'],
                                         keep='last')) if not inv_w.empty else inv_w
    dlv_w_latest = (dlv_w.sort_values('Created_Time')
                        .drop_duplicates(subset=['Store_Number','Product_EAN','Document_Type_Name','Created_Date'],
                                         keep='last')) if not dlv_w.empty else dlv_w

    # ── 2) Per (store, day) aggregates ───────────────────────────────────────
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
    # A store-day with diff != 0 counts as one error
    err_w['IsError'] = (err_w['Difference'].abs() >= 1).astype(int)

    # Attach store metadata (cluster, customer, route)
    err_w = err_w.merge(
        sm[['Store_Number','Route_ID_AFS','CUSTOMER','CLUSTER FULL']],
        on='Store_Number', how='left',
    )
    err_w = err_w.merge(
        rm[[col_route_afs, col_route_no]].rename(columns={col_route_afs:'Route_ID_AFS', col_route_no:'Route No.'}),
        on='Route_ID_AFS', how='left',
    )

    # ── 3) Visit compliance per day (planned vs visited stores) ──────────────
    daily_compliance = []
    for d in pd.date_range(week_start, target_date, freq='D'):
        d_date = d.date()
        d_dow  = d.strftime('%a')
        routes_d = rm[rm['_days'].apply(lambda s: d_dow in s)]
        if cluster_filter != '(All)' and col_cluster:
            routes_d = routes_d[routes_d[col_cluster].astype(str).str.strip().str.upper() == cluster_filter]
        if route_filter:
            routes_d = routes_d[routes_d[col_route_afs].isin(route_filter)]
        rids_d = routes_d[col_route_afs].dropna().unique()
        stores_d = sm[sm['Route_ID_AFS'].isin(rids_d)]
        if customer_filter:
            stores_d = stores_d[stores_d['CUSTOMER'].isin(customer_filter)]
        if store_filter:
            stores_d = stores_d[stores_d['Store_Number'].isin(store_filter)]
        planned = stores_d['Store_Number'].nunique()
        visited = vis_w[vis_w['Visit_Date'] == d_date]['Store_Number'].nunique()
        sent_units = float(sent_w[sent_w['DATE'] == d_date]['DELIVERY UNITS'].sum()) if sent_w is not None else 0.0
        delivered_units = float(err_w[err_w['Date'] == d_date]['Delivery'].sum())
        errors_count = int(err_w[err_w['Date'] == d_date]['IsError'].sum())
        daily_compliance.append({
            'Date': d_date,
            'Day': d.strftime('%a'),
            'Planned': planned,
            'Visited': visited,
            'Visit %':  (visited / planned) if planned else 0,
            'Sent':     sent_units,
            'Delivered': delivered_units,
            'Deliv %':  (delivered_units / sent_units) if sent_units else 0,
            'Errors':   errors_count,
        })
    daily_df = pd.DataFrame(daily_compliance)

    total_planned     = int(daily_df['Planned'].sum())
    total_visited     = int(daily_df['Visited'].sum())
    visit_pct         = (total_visited / total_planned) if total_planned else 0
    total_sent_w      = float(daily_df['Sent'].sum())
    total_delivered_w = float(daily_df['Delivered'].sum())
    deliv_pct         = (total_delivered_w / total_sent_w) if total_sent_w else 0
    total_credits_w   = float(err_w['Credits'].sum())
    total_errors_w    = int(err_w['IsError'].sum())            # store-day events
    stores_w_errors   = err_w.loc[err_w['IsError'] == 1, 'Store_Number'].nunique()

    dur_col = 'Actual_duration' if 'Actual_duration' in vis_w.columns else (
              'CostCenter_Duration' if 'CostCenter_Duration' in vis_w.columns else None)
    avg_duration = float(vis_w[dur_col].mean()) if dur_col and not vis_w.empty else None

    # ── 4) KPI cards ─────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("✅ Visit Compliance", f"{visit_pct:.0%}",
              help=f"{total_visited:,} of {total_planned:,} expected store-days")
    k2.metric("📦 Delivery Compliance", f"{deliv_pct:.0%}",
              help=f"{int(total_delivered_w):,} delivered / {int(total_sent_w):,} sent")
    k3.metric("⚠️ Stores w/ Errors", f"{stores_w_errors:,}",
              help=f"{total_errors_w:,} store-day error events")
    k4.metric("⏱️ Avg Visit Duration", f"{avg_duration:.0f} min" if avg_duration else "—")
    k5.metric("🏪 Unique Stores Visited", f"{vis_w['Store_Number'].nunique():,}")

    k6, k7, k8, k9, k10 = st.columns(5)
    k6.metric("💐 Bunches Delivered",   f"{int(total_delivered_w):,}")
    k7.metric("📦 Units Sent",          f"{int(total_sent_w):,}")
    k8.metric("↩️ Credits/RTV",          f"{int(total_credits_w):,}")
    k9.metric("📋 Total Visits",        f"{len(vis_w):,}")
    # Error rate = % of store-days with an error vs all store-days observed
    total_store_days = max(int((err_w['Initial'] + err_w['Delivery'] + err_w['Credits'] + err_w['Final']).gt(0).sum()), 1)
    error_rate = total_errors_w / total_store_days
    k10.metric("📊 Error Rate", f"{error_rate:.0%}",
               help="Store-days with error / store-days with activity")

    st.divider()

    # ── 5) Daily trend ──────────────────────────────────────────────────────
    st.markdown("##### 📈 Daily Trend")
    trend_view = daily_df.copy()
    trend_view['Visit %'] = (trend_view['Visit %'] * 100).round(0)
    trend_view['Deliv %'] = (trend_view['Deliv %'] * 100).round(0)
    st.dataframe(
        trend_view,
        use_container_width=True, hide_index=True,
        column_config={
            'Visit %':  st.column_config.ProgressColumn('Visit %',  format="%.0f%%", min_value=0, max_value=100),
            'Deliv %':  st.column_config.ProgressColumn('Deliv %',  format="%.0f%%", min_value=0, max_value=100),
            'Sent':     st.column_config.NumberColumn(format="%d"),
            'Delivered':st.column_config.NumberColumn(format="%d 💐"),
            'Errors':   st.column_config.NumberColumn(format="%d"),
        },
    )

    # Quick chart: visit & delivery compliance over the week
    chart_df = daily_df.set_index('Date')[['Visit %', 'Deliv %']].copy()
    if not chart_df.empty:
        st.line_chart(chart_df, height=240)

    st.divider()

    # ── 6) Breakdown by Cluster / Route / Customer ──────────────────────────
    st.markdown("##### 🔍 Breakdown")
    breakdown_dim = st.radio(
        "Group by", ["Cluster", "Route", "Customer"],
        horizontal=True, key="week_breakdown_dim",
    )

    dim_col = {'Cluster': 'CLUSTER FULL', 'Route': 'Route No.', 'Customer': 'CUSTOMER'}[breakdown_dim]

    # Aggregate sent/delivered/errors by dim
    if dim_col not in err_w.columns:
        st.warning(f"Column {dim_col} missing — re-check store master.")
    else:
        # Sent units by dim (need to attach dim to sent_w)
        sent_by_dim = pd.Series(dtype=float)
        if sent_w is not None and not sent_w.empty:
            sw = sent_w.merge(
                sm[['Store_Number','CLUSTER FULL','CUSTOMER','Route_ID_AFS']],
                on='Store_Number', how='left', suffixes=('','_sm'),
            )
            sw = sw.merge(
                rm[[col_route_afs, col_route_no]].rename(columns={col_route_afs:'Route_ID_AFS', col_route_no:'Route No.'}),
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

        # Visits by dim
        if not vis_w.empty:
            vw = vis_w.merge(
                sm[['Store_Number','CLUSTER FULL','CUSTOMER','Route_ID_AFS']],
                on='Store_Number', how='left', suffixes=('','_sm2'),
            ).merge(
                rm[[col_route_afs, col_route_no]].rename(columns={col_route_afs:'Route_ID_AFS', col_route_no:'Route No.'}),
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
        # Reorder/format
        cols_order = [dim_col, 'Compliance', 'Sent', 'Delivered', 'Credits',
                      'Stores_Visited', 'Visits', 'Avg_Duration', 'Stores_with_Error', 'Errors']
        agg = agg[[c for c in cols_order if c in agg.columns]]
        st.dataframe(
            agg, use_container_width=True, hide_index=True,
            column_config={
                'Compliance':         st.column_config.ProgressColumn('Compliance', format="%.0f%%", min_value=0, max_value=100),
                'Sent':               st.column_config.NumberColumn(format="%d 📦"),
                'Delivered':          st.column_config.NumberColumn(format="%d 💐"),
                'Credits':            st.column_config.NumberColumn(format="%d"),
                'Avg_Duration':       st.column_config.NumberColumn(format="%.0f min"),
                'Stores_with_Error':  st.column_config.NumberColumn(format="%d"),
                'Errors':             st.column_config.NumberColumn(format="%d"),
            },
        )

    st.divider()

    # ── 7) Top 10 problematic stores (most error events) ────────────────────
    st.markdown("##### 🚨 Top 10 stores with the most errors (last 7 days)")
    top_err = (err_w[err_w['IsError'] == 1]
               .groupby(['Store_Number','CUSTOMER','CLUSTER FULL','Route No.'], dropna=False)
               .agg(Error_Days=('IsError', 'sum'),
                    Total_Diff=('Difference', lambda x: x.abs().sum()))
               .reset_index()
               .sort_values(['Error_Days','Total_Diff'], ascending=False)
               .head(10))
    if top_err.empty:
        st.success("✅ No errors in the last 7 days — well done!")
    else:
        st.dataframe(
            top_err, use_container_width=True, hide_index=True,
            column_config={
                'Error_Days': st.column_config.NumberColumn('Days w/ Error', format="%d", help="Number of days with at least one error"),
                'Total_Diff': st.column_config.NumberColumn('Total Diff (units)', format="%d"),
            },
        )

    st.divider()

    # ── 8) Suggested next-step metrics ──────────────────────────────────────
    with st.expander("💡 Suggested metrics to add (towards 100% compliance)"):
        st.markdown("""
- **First-Visit Punctuality** — % of stores where the first realized visit happens before the planned cutoff.
- **Same-Day Recovery** — % of stores with an error on day N that show no error on day N+1 (proxy for follow-up).
- **Repeat-Offender Stores** — stores with errors on ≥3 of the last 7 days (chronic issues).
- **Driver/Merchandiser Ranking** — visits, errors, avg duration grouped by `User_Name`.
- **Coverage Gap** — stores that should have been visited (per Service Days) but weren't, broken down by cluster.
- **Delivery Variance** — `Sent − Delivered` per route to flag chronic over/under-delivery.
- **Time-of-Day Heatmap** — visits per hour vs day-of-week to spot bottlenecks.
""")


# ── Footer info ──────────────────────────────────────────────────────────────
with st.expander("ℹ️ Notes / Definitions"):
    st.markdown("""
- **Bunches Delivered** = sum of `DeliveredBunches` where `Document_Type_Name = 'Delivery'` (last record of the day per store+product).
- **Bunches Credit** = same but `Document_Type_Name = 'Credits (RTV)'`.
- **Initial Inv** = inventory on arrival (`Monitoring_Name = 'Initial Inventory'`, last of the day per store+product).
- **Final Inv** = last `Front` reading of the day per store+product.
- **Errors** = `Initial + Delivered − Credits − Final` (in units).
- **Status**: 🟢 visited (with delivery) · 🟡 in progress (visited, no delivery yet) · 🔴 pending.
""")
