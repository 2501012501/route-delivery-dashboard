# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Route to Delivery Streamlit dashboard with a McKinsey-blue minimalist theme and split the single 1,199-line `dashboard.py` (4 tabs) into a multipage app with one file per page, sharing a `lib/` shell.

**Architecture:** Streamlit native multipage app. `Home.py` is the entry point that loads data, renders the shared sidebar (data freshness, refresh buttons, filters), and lands on the Daily Follow page. Four files in `pages/` render the bodies. A new `lib/` package owns data loading, filter widgets + apply logic, refresh + cloud-publish handlers, route master parsing, and theme tokens / HTML helpers (KPI card, status pill, panel).

**Tech Stack:** Python 3.11/3.12, Streamlit 1.40, pandas, pyarrow. No new runtime dependencies. Theming via `.streamlit/config.toml` + targeted CSS injection. No automated test harness exists — verification is manual smoke-runs of the dashboard and a final numbers-regression check against the old `dashboard.py`.

**Reference:** [Spec](../specs/2026-05-04-dashboard-redesign-design.md) · current dashboard is at `dashboard.py` (1199 lines).

**Verification model:** Each task ends with a smoke-run step (`streamlit run Home.py` and check a specific behavior) plus a commit. Final task is a regression check that compares numbers against the original `dashboard.py` for the same date + filters.

---

## File Structure

After this plan executes, the repo looks like:

```
Route to delivery/
├── Home.py                            ← NEW — entry, loads data + sidebar, lands on Daily Follow
├── pages/                             ← NEW
│   ├── 1_Daily_Follow.py
│   ├── 2_Sent_vs_Delivery.py
│   ├── 3_Errors.py
│   └── 4_7_Day_Summary.py
├── lib/                               ← NEW
│   ├── __init__.py
│   ├── data.py                        ← load_data(), CLUSTER_ALIAS, _normalize_cluster
│   ├── routes.py                      ← parse_service_days, find_col, route master columns
│   ├── filters.py                     ← render_sidebar_filters(), apply_filters(), routes_for_day()
│   ├── refresh.py                     ← render_refresh_section(), _publish_to_cloud(), _run_script(), _run_chain()
│   ├── compute.py                     ← latest_per(), store_day_summary(), cluster_compliance_data()
│   └── theme.py                       ← color tokens, inject_css(), kpi(), pill(), panel(), eyebrow_title()
├── .streamlit/
│   └── config.toml                    ← NEW — McKinsey-blue theme config
├── dashboard.py                       ← REPLACED with 5-line deprecation stub
├── start-dashboard.bat                ← MODIFIED — points to Home.py
├── README.md                          ← MODIFIED — Cómo correr + Pages section
├── RouteToDelivery.py                 ← unchanged
├── extract.py                         ← unchanged
├── Transform.py                       ← unchanged
├── Deliveries.sql                     ← unchanged
└── ... (data folders unchanged)
```

**Why split this way:**

- `lib/data.py` holds everything that reads parquet files. Stays cached so it runs once per session.
- `lib/routes.py` is pure utilities for the route master (column tolerance, day parsing). No Streamlit calls.
- `lib/filters.py` owns the sidebar filter widgets and the `apply_filters` helper. Reads/writes `st.session_state` so filters persist across pages.
- `lib/refresh.py` owns the refresh + cloud publish + share-with-team UI block. Hidden on cloud.
- `lib/compute.py` holds the data aggregation helpers (`latest_per`, `store_day_summary`, `cluster_compliance_data`) used by 2+ pages.
- `lib/theme.py` is the only place that knows the palette hex codes + HTML for KPI cards, pills, panels.
- Each `pages/N_<name>.py` only handles its body rendering; everything shared comes from `lib/`.

---

## Task 0: Branch + safety net

**Files:**
- None (git only)

- [ ] **Step 1: Create a feature branch from main**

```bash
git checkout -b dashboard-redesign
```

- [ ] **Step 2: Verify current state runs and capture baseline screenshots/numbers**

```bash
python -m streamlit run dashboard.py
```

Open `http://localhost:8501`. Pick **today's date**, **All clusters**, **all customers**. For each tab, write down:
- Tab 1 (Daily Follow-up): the 5 metric values (Day, Routes, Visited, Bunches, Credits/RTV) and global compliance %.
- Tab 2 (Sent vs Delivered): total Sent and Delivered units, global %.
- Tab 3 (Errors): Shortage sum, Overage sum, Stores with error, Routes with error.
- Tab 4 (7-Day Summary): all 10 KPIs (k1..k10).

Save those numbers to a scratchpad — they're the regression target for Task 17.

Stop the dashboard with `Ctrl+C`.

- [ ] **Step 3: Commit baseline note**

```bash
git commit --allow-empty -m "chore: start dashboard redesign branch"
```

---

## Task 1: Create the Streamlit theme config

**Files:**
- Create: `.streamlit/config.toml`

- [ ] **Step 1: Check if `.streamlit/` already has a config.toml**

```bash
ls .streamlit/
```

If `config.toml` exists, read it first — don't blow away other config (e.g., `server.port`).

- [ ] **Step 2: Write `.streamlit/config.toml`**

If the file doesn't exist, create it with:

```toml
[theme]
base = "light"
primaryColor = "#2251FF"
backgroundColor = "#FAFBFC"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#051C2C"
font = "sans serif"

[client]
toolbarMode = "minimal"
```

If it already has `[server]` or other sections, prepend the `[theme]` block at the top and keep the rest.

- [ ] **Step 3: Smoke-run**

```bash
python -m streamlit run dashboard.py
```

Open http://localhost:8501. Verify the existing dashboard now uses the blue + light-gray background (Streamlit will pick up the config). Stop with `Ctrl+C`. Don't fix any visual issues yet — old dashboard is the reference; we'll replace it.

- [ ] **Step 4: Commit**

```bash
git add .streamlit/config.toml
git commit -m "feat(theme): add McKinsey-blue Streamlit theme config"
```

---

## Task 2: Create `lib/__init__.py` and the theme module

**Files:**
- Create: `lib/__init__.py`
- Create: `lib/theme.py`

- [ ] **Step 1: Create `lib/__init__.py` (empty)**

```python
```

(zero bytes — just makes `lib` a package).

- [ ] **Step 2: Create `lib/theme.py`**

```python
"""Visual tokens and HTML helpers for the redesigned dashboard.

All HTML uses st.markdown(..., unsafe_allow_html=True). The CSS injection
happens once per session via inject_css(); pages call the helpers
(kpi, pill, panel, eyebrow_title) to render consistent UI.
"""
import streamlit as st

# Palette (McKinsey blue)
NAVY        = "#051C2C"
BLUE        = "#2251FF"
PALE_BLUE   = "#EDF2FE"
SLATE       = "#64748B"
PAGE_BG     = "#FAFBFC"
SURFACE     = "#FFFFFF"
BORDER      = "#E5E7EB"
AMBER_BG    = "#FEF3C7"
AMBER_FG    = "#92400E"
GRAY_BG     = "#F1F5F9"


_CSS = f"""
<style>
  /* ── Sidebar ────────────────────────────────────────────── */
  section[data-testid="stSidebar"] {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: {PALE_BLUE};
    color: {BLUE};
    font-weight: 600;
    border-radius: 6px;
  }}

  /* ── Eyebrow + title ─────────────────────────────────────── */
  .rtd-eyebrow {{
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-size: 11px;
    color: {BLUE};
    font-weight: 600;
  }}
  .rtd-title {{
    margin: 6px 0 16px 0;
    color: {NAVY};
    font-weight: 600;
    font-size: 22px;
  }}

  /* ── KPI cards ──────────────────────────────────────────── */
  .rtd-kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin: 8px 0 16px 0;
  }}
  .rtd-kpi {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 14px;
  }}
  .rtd-kpi.accent {{ border-left: 3px solid {BLUE}; }}
  .rtd-kpi-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: {SLATE};
  }}
  .rtd-kpi-value {{
    font-size: 24px;
    font-weight: 700;
    color: {NAVY};
    margin-top: 4px;
  }}
  .rtd-kpi.accent .rtd-kpi-value {{ color: {BLUE}; }}

  /* ── Panels ─────────────────────────────────────────────── */
  .rtd-panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 18px;
    margin: 8px 0;
  }}
  .rtd-panel-title {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: {SLATE};
    margin-bottom: 8px;
  }}

  /* ── Pills ──────────────────────────────────────────────── */
  .rtd-pill {{
    display: inline-block;
    padding: 3px 9px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
  }}
  .rtd-pill.ok    {{ background: {PALE_BLUE}; color: {BLUE}; }}
  .rtd-pill.warn  {{ background: {AMBER_BG}; color: {AMBER_FG}; }}
  .rtd-pill.pend  {{ background: {GRAY_BG}; color: {SLATE}; }}
</style>
"""


def inject_css():
    """Call once at the top of every page (Home + pages/*) to apply the theme."""
    st.markdown(_CSS, unsafe_allow_html=True)


def eyebrow_title(eyebrow: str, title: str):
    """Renders the page header pair: small uppercase blue eyebrow + big navy title."""
    st.markdown(
        f'<div class="rtd-eyebrow">{eyebrow}</div>'
        f'<div class="rtd-title">{title}</div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, accent: bool = False) -> str:
    """Returns the HTML for a single KPI card. Use in a kpi_grid()."""
    cls = "rtd-kpi accent" if accent else "rtd-kpi"
    return (
        f'<div class="{cls}">'
        f'<div class="rtd-kpi-label">{label}</div>'
        f'<div class="rtd-kpi-value">{value}</div>'
        f'</div>'
    )


def kpi_grid(*kpi_html: str):
    """Renders a row of KPIs. Pass HTML strings produced by kpi()."""
    body = '<div class="rtd-kpi-grid">' + ''.join(kpi_html) + '</div>'
    st.markdown(body, unsafe_allow_html=True)


def pill(text: str, kind: str = "ok") -> str:
    """Returns inline HTML for a status pill. kind ∈ {'ok','warn','pend'}."""
    return f'<span class="rtd-pill {kind}">{text}</span>'


def panel_open(title: str | None = None):
    """Open a panel with optional title. Pair with panel_close().
    Usage: panel_open("Stores"); st.write(...); panel_close()
    """
    head = f'<div class="rtd-panel-title">{title}</div>' if title else ''
    st.markdown(f'<div class="rtd-panel">{head}', unsafe_allow_html=True)


def panel_close():
    st.markdown('</div>', unsafe_allow_html=True)
```

- [ ] **Step 3: Smoke-run import**

```bash
python -c "from lib import theme; print(theme.BLUE)"
```

Expected: `#2251FF`.

- [ ] **Step 4: Commit**

```bash
git add lib/__init__.py lib/theme.py
git commit -m "feat(lib): theme tokens + HTML helpers (kpi, pill, panel, eyebrow_title)"
```

---

## Task 3: Extract data loading into `lib/data.py`

**Files:**
- Create: `lib/data.py`
- Reference: `dashboard.py:16-93` (existing `load_data` and cluster aliasing)

- [ ] **Step 1: Create `lib/data.py`**

```python
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
# for some clusters. Apply as `value.upper().strip() → canonical name`.
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
```

- [ ] **Step 2: Smoke-run**

```bash
python -c "from lib.data import load_data; r = load_data(); print('shapes:', [None if x is None else getattr(x,'shape','-') for x in r])"
```

Expected: prints 7 shapes (or `None` for `rm_error` and possibly `sent`). No exceptions.

- [ ] **Step 3: Commit**

```bash
git add lib/data.py
git commit -m "feat(lib): extract data loading into lib/data.py"
```

---

## Task 4: Extract route-master helpers into `lib/routes.py`

**Files:**
- Create: `lib/routes.py`
- Reference: `dashboard.py:107-172`

- [ ] **Step 1: Create `lib/routes.py`**

```python
"""Route master parsing helpers. No Streamlit calls — pure pandas/regex."""
import re
from typing import Optional

import pandas as pd

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
_LETTER_MAP = {'M':'Mon','T':'Tue','W':'Wed','R':'Thu','F':'Fri','S':'Sat','U':'Sun'}


def parse_service_days(value) -> set:
    """Returns {'Mon','Wed',...} from any free-form text in the Service Days column."""
    if pd.isna(value): return set()
    s = str(value).strip()
    if not s: return set()
    out = set()
    for tok in re.split(r'[,;/\s|+]+', s.lower()):
        if tok in _DAY_MAP:
            out.add(_DAY_MAP[tok])
    if out: return out
    for tok in re.findall(r'\b(Mo|Tu|We|Th|Fr|Sa|Su)\b', s, flags=re.I):
        out.add({'mo':'Mon','tu':'Tue','we':'Wed','th':'Thu','fr':'Fri','sa':'Sat','su':'Sun'}[tok.lower()])
    if out: return out
    s2 = s.replace('Th','R').replace('Su','U')
    for ch in s2:
        if ch in _LETTER_MAP:
            out.add(_LETTER_MAP[ch])
    return out


def find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Find a column whose normalized name matches any of `candidates`.
    Tolerant to case, accents, spaces, dots, dashes, underscores.
    """
    norm = {c: re.sub(r'[\s\.\-_]+','', c).lower() for c in df.columns}
    for cand in candidates:
        cand_n = re.sub(r'[\s\.\-_]+','', cand).lower()
        for c, n in norm.items():
            if n == cand_n: return c
        for c, n in norm.items():
            if cand_n in n: return c
    return None


def detect_route_columns(rm: pd.DataFrame) -> dict:
    """Returns dict with detected column names for the route master.
    Keys: route_no, route_afs, cluster, service, stops, cost_stop.
    Values may be None (caller decides which are required).
    """
    return {
        'route_no':  find_col(rm, 'Route No', 'Route Number', 'Route'),
        'route_afs': find_col(rm, 'Route_ID_AFS', 'Route ID AFS'),
        'cluster':   find_col(rm, 'Cluster'),
        'service':   find_col(rm, 'Service Days', 'ServiceDays', 'Days'),
        'stops':     find_col(rm, 'Stops'),
        'cost_stop': find_col(rm, 'Cost/Stop', 'CostPerStop', 'Cost/stop'),
    }


def annotate_service_days(rm: pd.DataFrame, service_col: str) -> pd.DataFrame:
    """Mutates rm by adding a `_days` column with set[str]. Returns rm."""
    rm['_days'] = rm[service_col].apply(parse_service_days)
    return rm
```

- [ ] **Step 2: Smoke-run**

```bash
python -c "from lib.routes import parse_service_days; print(parse_service_days('Mon, Wed, Fri'), parse_service_days('MWF'))"
```

Expected: `{'Mon', 'Wed', 'Fri'} {'Mon', 'Wed', 'Fri'}` (set order may vary).

- [ ] **Step 3: Commit**

```bash
git add lib/routes.py
git commit -m "feat(lib): extract route master helpers (parse_service_days, find_col, detect_route_columns)"
```

---

## Task 5: Extract refresh + cloud-publish UI into `lib/refresh.py`

**Files:**
- Create: `lib/refresh.py`
- Reference: `dashboard.py:174-247, 249-307` (the refresh helpers and the sidebar refresh block)

- [ ] **Step 1: Create `lib/refresh.py`**

```python
"""Refresh buttons + cloud publish + share-with-team. Hidden on cloud."""
import os
import socket
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


def is_cloud() -> bool:
    """True when running on Streamlit Community Cloud (no VPN, no on-prem SQL)."""
    return ('/mount/src/' in os.getcwd()) or bool(os.environ.get('STREAMLIT_RUNTIME'))


def _publish_to_cloud() -> bool:
    """Stage data files, commit, push to GitHub so Streamlit Cloud redeploys."""
    project_dir = Path(__file__).parent.parent
    with st.spinner("Publishing to cloud..."):
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
    project_dir = Path(__file__).parent.parent
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
    project_dir = Path(__file__).parent.parent
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


def render_refresh_section(last_visit):
    """Render the data section of the sidebar: freshness + refresh buttons + share link.

    `last_visit` is a Timestamp (or NaT) — passed in so we don't re-import data here.
    Hidden on cloud (read-only banner only).
    """
    st.header("📡 Data")
    if pd.notna(last_visit):
        st.caption(f"Last visit recorded: **{last_visit.strftime('%Y-%m-%d %H:%M')}**")
    else:
        st.caption("No visits recorded yet")

    if is_cloud():
        st.caption("🌐 **Read-only view** — refresh disabled in cloud. "
                   "Data updated when the owner pushes new files.")
        return

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
```

- [ ] **Step 2: Smoke-run import**

```bash
python -c "from lib.refresh import is_cloud, render_refresh_section; print(is_cloud())"
```

Expected: `False` (when run locally).

- [ ] **Step 3: Commit**

```bash
git add lib/refresh.py
git commit -m "feat(lib): extract refresh + cloud-publish UI into lib/refresh.py"
```

---

## Task 6: Extract sidebar filters into `lib/filters.py`

**Files:**
- Create: `lib/filters.py`
- Reference: `dashboard.py:307-393` (filter widgets + apply_filters)

- [ ] **Step 1: Create `lib/filters.py`**

```python
"""Sidebar filter widgets + apply_filters helper.

The filter widgets store their selections in st.session_state via Streamlit's
default key-by-label behavior. apply_filters() reads the current selections
from the dict returned by render_sidebar_filters() — so each page calls
both, in order.
"""
from datetime import date

import pandas as pd
import streamlit as st


def render_sidebar_filters(*, sm, vis, inv, dlv, rm, route_cols) -> dict:
    """Render the filter widgets in st.sidebar and return the selections.

    `route_cols` is the dict returned by lib.routes.detect_route_columns(rm).
    """
    st.header("Filters")

    available_dates = sorted(
        set(inv['Answer_Date']) | set(dlv['Created_Date']) | set(vis['Visit_Date'].dropna())
    )
    default_date = max(available_dates) if available_dates else date.today()
    target_date = st.date_input(
        "Date", value=default_date,
        min_value=min(available_dates) if available_dates else None,
        max_value=max(available_dates) if available_dates else None,
    )

    rm_clusters = (rm[route_cols['cluster']].dropna().astype(str).str.strip().str.upper().unique()
                   if route_cols['cluster'] else [])
    sm_full = sm['CLUSTER FULL'].dropna().astype(str).str.strip().str.upper().unique()
    cluster_options = ['(All)'] + sorted(set(rm_clusters) & set(sm_full))
    cluster_filter = st.selectbox("Cluster", cluster_options)

    customer_options = sorted(sm['CUSTOMER'].dropna().unique().tolist())
    customer_filter = st.multiselect("Customer", customer_options, default=customer_options)

    sm_filtered = sm.copy()
    if cluster_filter != '(All)':
        sm_filtered = sm_filtered[
            sm_filtered['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter
        ]
    if customer_filter:
        sm_filtered = sm_filtered[sm_filtered['CUSTOMER'].isin(customer_filter)]
    route_options = sorted(sm_filtered['Route_ID_AFS'].dropna().unique().tolist())
    route_filter = st.multiselect(
        "Route (Route_ID_AFS)", route_options,
        help="Empty = all routes matching the other filters",
    )

    if route_filter:
        sm_filtered = sm_filtered[sm_filtered['Route_ID_AFS'].isin(route_filter)]
    store_options = sorted(sm_filtered['Store_Number'].dropna().unique().tolist())
    store_filter = st.multiselect(
        "Store (Store_Number)", store_options, help="Empty = all stores",
    )

    KNOWN_ACTIVITIES = ['Driver Merchandiser Visit', 'Supervisor Visit']
    if 'Activity_Type' in vis.columns:
        at_options = sorted(set(vis['Activity_Type'].dropna().unique().tolist()) | set(KNOWN_ACTIVITIES))
    else:
        at_options = KNOWN_ACTIVITIES
    activity_filter = st.multiselect(
        "Activity Type", at_options, default=at_options,
        help="If filtering shows no change, refresh the API (🔁) — the field isn't in the loaded data yet.",
    )

    show_all_routes = st.checkbox(
        "Show all routes (even without schedule or activity)",
        value=False,
        help="When OFF (default), the dashboard shows routes scheduled for the day "
             "PLUS routes that had activity (visits/deliveries) — even if not scheduled. "
             "Turn ON to see every route in the route master regardless.",
    )

    return {
        'target_date':     target_date,
        'cluster_filter':  cluster_filter,
        'customer_filter': customer_filter,
        'route_filter':    route_filter,
        'store_filter':    store_filter,
        'activity_filter': activity_filter,
        'show_all_routes': show_all_routes,
    }


def apply_filters(df: pd.DataFrame, f: dict, *, also_activity: bool = False) -> pd.DataFrame:
    """Apply the selections from render_sidebar_filters(...) to a fact dataframe."""
    if f['cluster_filter'] != '(All)' and 'CLUSTER FULL' in df.columns:
        df = df[df['CLUSTER FULL'].astype(str).str.strip().str.upper() == f['cluster_filter']]
    if f['customer_filter'] and 'CUSTOMER' in df.columns:
        df = df[df['CUSTOMER'].isin(f['customer_filter'])]
    if f['route_filter'] and 'Route_ID_AFS' in df.columns:
        df = df[df['Route_ID_AFS'].isin(f['route_filter'])]
    if f['store_filter'] and 'Store_Number' in df.columns:
        df = df[df['Store_Number'].isin(f['store_filter'])]
    if also_activity and f['activity_filter'] and 'Activity_Type' in df.columns:
        df = df[df['Activity_Type'].isin(f['activity_filter'])]
    return df


def _active_route_ids(*frames) -> set:
    """Collect Route_ID_AFS values that appear in any of the given (day-filtered) frames."""
    ids = set()
    for df in frames:
        if df is None or df.empty or 'Route_ID_AFS' not in df.columns:
            continue
        ids |= set(df['Route_ID_AFS'].dropna().unique())
    return ids


def routes_for_day(rm: pd.DataFrame, *, target_date, cluster_filter, route_filter,
                   route_cols: dict, show_all_routes: bool,
                   vis_d=None, dlv_d=None, sent_d=None) -> pd.DataFrame:
    """Subset of rm to show on the page for target_date.

    Default (show_all_routes=False):
        scheduled-for-day ∪ active-on-day
        — scheduled = `_days` contains today's dow
        — active    = Route_ID_AFS appears in vis_d / dlv_d / sent_d

    Override (show_all_routes=True):
        every route in rm.

    Cluster + route filters always apply on top.
    """
    routes_today = rm.copy()

    if not show_all_routes:
        dow = target_date.strftime('%a')
        scheduled_mask = routes_today['_days'].apply(lambda s: dow in s)
        active_ids = _active_route_ids(vis_d, dlv_d, sent_d)
        if active_ids:
            active_mask = routes_today[route_cols['route_afs']].isin(active_ids)
            routes_today = routes_today[scheduled_mask | active_mask]
        else:
            routes_today = routes_today[scheduled_mask]

    if cluster_filter != '(All)' and route_cols['cluster']:
        routes_today = routes_today[
            routes_today[route_cols['cluster']].astype(str).str.strip().str.upper() == cluster_filter
        ]
    if route_filter:
        routes_today = routes_today[routes_today[route_cols['route_afs']].isin(route_filter)]
    return routes_today
```

- [ ] **Step 2: Smoke-run import**

```bash
python -c "from lib.filters import render_sidebar_filters, apply_filters, routes_for_day; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add lib/filters.py
git commit -m "feat(lib): extract sidebar filters + apply_filters into lib/filters.py"
```

---

## Task 7: Extract data aggregation helpers into `lib/compute.py`

**Files:**
- Create: `lib/compute.py`
- Reference: `dashboard.py:397-412` (latest_per), `dashboard.py:474-549` (cluster compliance), `dashboard.py:553-619` (store_day_summary, status_emoji)

- [ ] **Step 1: Create `lib/compute.py`**

```python
"""Data aggregation helpers used by 2+ pages. No Streamlit calls."""
import pandas as pd


def latest_per(df: pd.DataFrame, key_cols: list, time_col: str) -> pd.DataFrame:
    """For each unique combination of key_cols, keep the row with the latest time_col."""
    if df.empty: return df
    df = df.sort_values(time_col)
    return df.drop_duplicates(subset=key_cols, keep='last')


def store_day_summary(*, target_route_ids, sm, vis_d, dlv_latest, inv_latest,
                      cluster_filter: str, customer_filter, store_filter) -> pd.DataFrame:
    """Per-store summary for the selected routes on the day."""
    stores = sm[sm['Route_ID_AFS'].isin(target_route_ids)].copy()
    if cluster_filter != '(All)':
        stores = stores[stores['CLUSTER FULL'].astype(str).str.strip().str.upper() == cluster_filter]
    if customer_filter:
        stores = stores[stores['CUSTOMER'].isin(customer_filter)]
    if store_filter:
        stores = stores[stores['Store_Number'].isin(store_filter)]

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
                             customer_filter, store_filter) -> pd.DataFrame:
    """Per-cluster compliance for routes_today. Columns: Cluster, Visited, Planned, Pct."""
    if routes_today.empty:
        return pd.DataFrame()
    rows = []
    cluster_col = route_cols['cluster']
    grouped = routes_today.groupby(cluster_col, dropna=False) if cluster_col else [(None, routes_today)]
    for cluster_name, group in grouped:
        rids = group[route_cols['route_afs']].dropna().unique()
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
```

- [ ] **Step 2: Smoke-run import**

```bash
python -c "from lib.compute import latest_per, store_day_summary, store_status, cluster_compliance_data; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add lib/compute.py
git commit -m "feat(lib): extract aggregation helpers (latest_per, store_day_summary, cluster_compliance_data)"
```

---

## Task 8: Build `Home.py` entry point

**Files:**
- Create: `Home.py`

`Home.py` is the new entry. It loads data, renders the sidebar, and shows a small landing message that points the user at the first page. Streamlit's native page nav appears automatically because we'll create `pages/` next.

- [ ] **Step 1: Create `Home.py`**

```python
"""Route Delivery Dashboard — entry point.
Launch with:  streamlit run Home.py
"""
import pandas as pd
import streamlit as st

from lib.data import load_data
from lib.routes import detect_route_columns, annotate_service_days
from lib.refresh import render_refresh_section
from lib.filters import render_sidebar_filters
from lib.theme import inject_css, eyebrow_title, panel_open, panel_close

st.set_page_config(
    page_title="Route Delivery",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="expanded",
)
inject_css()

inv, dlv, vis, sm, rm, rm_error, sent = load_data()

if rm is None:
    st.error(
        "Cannot find `Route To Delivery Data/route_master.parquet`. "
        "Run first:  `python extract.py --route-master`. "
        + (f"Error: {rm_error}" if rm_error else "")
    )
    st.stop()

route_cols = detect_route_columns(rm)
if route_cols['service'] is None or route_cols['route_afs'] is None:
    st.error(
        f"Required columns not found in route master. "
        f"Detected: {list(rm.columns)}. "
        "Need at least 'Route_ID_AFS' and 'Service Days'."
    )
    st.stop()
rm = annotate_service_days(rm, route_cols['service'])

with st.sidebar:
    last_visit = vis['Visit_DateTime'].max() if not vis.empty else None
    render_refresh_section(last_visit)
    st.divider()
    filters = render_sidebar_filters(
        sm=sm, vis=vis, inv=inv, dlv=dlv, rm=rm, route_cols=route_cols,
    )

# Stash on session_state so pages can read everything without re-running setup.
st.session_state['_rtd_data']    = (inv, dlv, vis, sm, rm, sent)
st.session_state['_rtd_routes']  = route_cols
st.session_state['_rtd_filters'] = filters

eyebrow_title("Route to Delivery", "Welcome")
panel_open()
st.markdown(
    "Choose a page from the sidebar:\n\n"
    "- **Daily Follow** — visit compliance for the selected date\n"
    "- **Sent vs Delivery** — warehouse units vs driver-recorded bunches\n"
    "- **Errors** — inventory mismatches: `Initial + Delivery − Credits − Final ≠ 0`\n"
    "- **7-Day Summary** — executive trend across the last 7 days"
)
panel_close()
```

- [ ] **Step 2: Smoke-run**

```bash
python -m streamlit run Home.py
```

Open http://localhost:8501. Verify:
1. Sidebar shows: "📡 Data" header + last-visit caption + auto-publish checkbox + 3 refresh buttons + share-with-team expander, then a divider, then "Filters" with date/cluster/customer/route/store/activity/checkbox.
2. Main body shows "Route to Delivery / Welcome" header in the new theme + a panel listing the 4 pages.
3. The sidebar nav (top of sidebar) is still empty because `pages/` doesn't exist yet — that's expected.

Stop with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add Home.py
git commit -m "feat(pages): add Home.py entry — loads data, renders shared sidebar"
```

---

## Task 9: Build `pages/1_Daily_Follow.py`

**Files:**
- Create: `pages/1_Daily_Follow.py`
- Reference: `dashboard.py:443-470` (top metrics), `dashboard.py:643-731` (Tab 1 body)

- [ ] **Step 1: Create `pages/1_Daily_Follow.py`**

```python
"""Daily Follow — visit compliance for the selected date."""
import pandas as pd
import streamlit as st

from lib.compute import (cluster_compliance_data, latest_per,
                          store_day_summary, store_status)
from lib.filters import apply_filters, routes_for_day
from lib.theme import (NAVY, BLUE, PALE_BLUE, BORDER, SLATE,
                        eyebrow_title, inject_css, kpi, kpi_grid,
                        panel_close, panel_open, pill)

st.set_page_config(page_title="Daily Follow", layout="wide", page_icon="📅")
inject_css()

if '_rtd_data' not in st.session_state:
    st.error("Open from the Home page first (`streamlit run Home.py`).")
    st.stop()

inv, dlv, vis, sm, rm, sent = st.session_state['_rtd_data']
route_cols = st.session_state['_rtd_routes']
f          = st.session_state['_rtd_filters']

# Day-filtered fact frames first (needed to compute "active" routes).
inv_d = apply_filters(inv[inv['Answer_Date']  == f['target_date']], f).copy()
dlv_d = apply_filters(dlv[dlv['Created_Date'] == f['target_date']], f).copy()
vis_d = apply_filters(vis[vis['Visit_Date']   == f['target_date']], f, also_activity=True).copy()

routes_today = routes_for_day(
    rm,
    target_date=f['target_date'],
    cluster_filter=f['cluster_filter'],
    route_filter=f['route_filter'],
    route_cols=route_cols,
    show_all_routes=f['show_all_routes'],
    vis_d=vis_d, dlv_d=dlv_d,
)

inv_latest = latest_per(inv_d, ['Store_Number','Product_EAN','Monitoring_Name'], 'Answer_Time')
dlv_latest = latest_per(dlv_d, ['Store_Number','Product_EAN','Document_Type_Name'], 'Created_Time')

# KPIs — "Planned" = stores attached to the routes_today set
# (planned-for-day ∪ active-today, after cluster/customer filters).
visited_stores = vis_d['Store_Number'].nunique()
expected_route_ids = routes_today[route_cols['route_afs']].dropna().unique().tolist()
expected_stores = sm[sm['Route_ID_AFS'].isin(expected_route_ids)]
if f['cluster_filter'] != '(All)':
    expected_stores = expected_stores[
        expected_stores['CLUSTER FULL'].astype(str).str.strip().str.upper() == f['cluster_filter']
    ]
if f['customer_filter']:
    expected_stores = expected_stores[expected_stores['CUSTOMER'].isin(f['customer_filter'])]
total_expected = expected_stores['Store_Number'].nunique()

in_progress_count = 0
pending_count = 0
if not routes_today.empty:
    s_all = store_day_summary(
        target_route_ids=routes_today[route_cols['route_afs']].dropna().unique().tolist(),
        sm=sm, vis_d=vis_d, dlv_latest=dlv_latest, inv_latest=inv_latest,
        cluster_filter=f['cluster_filter'],
        customer_filter=f['customer_filter'],
        store_filter=f['store_filter'],
    )
    s_all['Status'] = s_all.apply(store_status, axis=1)
    in_progress_count = int((s_all['Status'] == 'In progress').sum())
    pending_count     = int((s_all['Status'] == 'Pending').sum())

eyebrow_title("Daily Follow", f"Visit compliance · {f['target_date'].strftime('%a %b %d, %Y')}")

kpi_grid(
    kpi("Planned",      f"{total_expected:,}"),
    kpi("Visited",      f"{visited_stores:,}", accent=True),
    kpi("In progress",  f"{in_progress_count:,}"),
    kpi("Pending",      f"{pending_count:,}"),
)

# Cluster compliance panel
cl_df = cluster_compliance_data(
    routes_today=routes_today, sm=sm, vis_d=vis_d, route_cols=route_cols,
    customer_filter=f['customer_filter'], store_filter=f['store_filter'],
)
panel_open("Cluster compliance")
if cl_df.empty:
    st.caption("No routes matching filters.")
else:
    for _, row in cl_df.iterrows():
        pct = float(row['Pct'])
        c1, c2, c3 = st.columns([1.5, 4, 1])
        c1.markdown(
            f'<div style="font-weight:600;color:{NAVY};">{row["Cluster"]}'
            f'<span style="color:{SLATE};font-weight:500;font-size:11px;margin-left:6px;">'
            f'{int(row["Visited"])}/{int(row["Planned"])}</span></div>',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f'<div style="background:{PALE_BLUE};border-radius:999px;height:14px;overflow:hidden;">'
            f'<div style="background:{BLUE};height:100%;width:{min(pct,1)*100:.1f}%;"></div></div>',
            unsafe_allow_html=True,
        )
        c3.markdown(f'<div style="text-align:right;font-weight:700;color:{NAVY};">{pct:.0%}</div>',
                    unsafe_allow_html=True)
panel_close()

# Route summary / detail toggle
if routes_today.empty:
    panel_open()
    st.info("No routes scheduled with the selected filters.")
    panel_close()
else:
    view_mode = st.radio(
        "View", ["Route summary", "Route detail"],
        horizontal=True, key="view_mode_dia", label_visibility="collapsed",
    )

    if view_mode == "Route summary":
        rows = []
        for _, r in routes_today.iterrows():
            rid = r[route_cols['route_afs']]
            s = store_day_summary(
                target_route_ids=[rid], sm=sm, vis_d=vis_d,
                dlv_latest=dlv_latest, inv_latest=inv_latest,
                cluster_filter=f['cluster_filter'],
                customer_filter=f['customer_filter'],
                store_filter=f['store_filter'],
            )
            planned = len(s)
            visited = int((s['Visited'] > 0).sum())
            rows.append({
                'Route No.':    r[route_cols['route_no']] if route_cols['route_no'] else '',
                'Route_ID_AFS': rid,
                'Cluster':      r[route_cols['cluster']] if route_cols['cluster'] else '',
                'Compliance':   (visited / planned * 100) if planned else 0,
                'Visited':      visited,
                'Planned':      planned,
                'Bunches':      int(s['Bunches_Delivered'].sum()),
                'Credits':      int(s['Bunches_Credit'].sum()),
                'Errors':       int(s['Errors'].sum()),
            })
        df_routes = pd.DataFrame(rows).sort_values('Compliance', ascending=False)
        panel_open("Routes")
        st.dataframe(
            df_routes,
            use_container_width=True, hide_index=True,
            column_config={
                "Compliance": st.column_config.ProgressColumn(
                    "Compliance", format="%.0f%%", min_value=0, max_value=100
                ),
            },
        )
        panel_close()
    else:
        route_options = routes_today[route_cols['route_afs']].dropna().unique().tolist()
        chosen = st.selectbox("Route", route_options, key="route_detail_select")
        s = store_day_summary(
            target_route_ids=[chosen], sm=sm, vis_d=vis_d,
            dlv_latest=dlv_latest, inv_latest=inv_latest,
            cluster_filter=f['cluster_filter'],
            customer_filter=f['customer_filter'],
            store_filter=f['store_filter'],
        )
        s['Status'] = s.apply(store_status, axis=1)

        kpi_grid(
            kpi("Visited",     f"{int((s['Status']=='Visited').sum())} / {len(s)}", accent=True),
            kpi("In progress", f"{int((s['Status']=='In progress').sum())}"),
            kpi("Pending",     f"{int((s['Status']=='Pending').sum())}"),
        )

        cols_show = ['Status', 'Store_Number', 'CUSTOMER', 'CLUSTER FULL',
                     'First_Visit', 'Last_Visit', 'Avg_Duration_min',
                     'Bunches_Delivered', 'Bunches_Credit',
                     'Initial_Inv', 'Final_Inv', 'Errors']
        display = s[[c for c in cols_show if c in s.columns]].copy()
        panel_open(f"Stores · {chosen}")
        st.dataframe(display, use_container_width=True, hide_index=True)
        panel_close()
```

- [ ] **Step 2: Smoke-run**

```bash
python -m streamlit run Home.py
```

Open http://localhost:8501. Click "Daily Follow" in the sidebar nav (it should now appear at the top of the sidebar, above "📡 Data"). Verify:
1. Eyebrow + title shows "DAILY FOLLOW · Visit compliance · {today}".
2. 4 KPI cards in a row: Planned, Visited (blue accent), In progress, Pending.
3. Cluster compliance panel shows one row per cluster with a blue progress bar.
4. Toggle between "Route summary" and "Route detail" — both render without errors.

Stop with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add pages/1_Daily_Follow.py
git commit -m "feat(pages): add Daily Follow page with new theme"
```

---

## Task 10: Build `pages/2_Sent_vs_Delivery.py`

**Files:**
- Create: `pages/2_Sent_vs_Delivery.py`
- Reference: `dashboard.py:734-802` (Tab 2 body)

- [ ] **Step 1: Create `pages/2_Sent_vs_Delivery.py`**

```python
"""Sent vs Delivery — warehouse units vs driver-recorded bunches."""
import pandas as pd
import streamlit as st

from lib.compute import latest_per
from lib.filters import apply_filters, routes_for_day
from lib.theme import (eyebrow_title, inject_css, kpi, kpi_grid,
                        panel_close, panel_open)

st.set_page_config(page_title="Sent vs Delivery", layout="wide", page_icon="📦")
inject_css()

if '_rtd_data' not in st.session_state:
    st.error("Open from the Home page first (`streamlit run Home.py`).")
    st.stop()

inv, dlv, vis, sm, rm, sent = st.session_state['_rtd_data']
route_cols = st.session_state['_rtd_routes']
f          = st.session_state['_rtd_filters']

eyebrow_title("Sent vs Delivery", f"Warehouse vs driver totals · {f['target_date'].strftime('%a %b %d, %Y')}")

if sent is None:
    panel_open()
    st.info(
        "ℹ️ Cannot find `data/deliveries.parquet`. Click **📦 Sent** "
        "in the sidebar (runs `extract.py --deliveries` + `Transform.py`)."
    )
    panel_close()
    st.stop()

vis_d = apply_filters(vis[vis['Visit_Date']   == f['target_date']], f, also_activity=True).copy()
dlv_d = apply_filters(dlv[dlv['Created_Date'] == f['target_date']], f).copy()
dlv_latest = latest_per(dlv_d, ['Store_Number','Product_EAN','Document_Type_Name'], 'Created_Time')

sent_d = sent[sent['DATE'] == f['target_date']].copy()
sent_d = sent_d.rename(columns={'STORE NUMBER WF': 'Store_Number'})
sent_d = apply_filters(sent_d, f)

routes_today = routes_for_day(
    rm,
    target_date=f['target_date'],
    cluster_filter=f['cluster_filter'],
    route_filter=f['route_filter'],
    route_cols=route_cols,
    show_all_routes=f['show_all_routes'],
    vis_d=vis_d, dlv_d=dlv_d, sent_d=sent_d,
)

sent_by_route = sent_d.groupby('Route_ID_AFS', dropna=False)['DELIVERY UNITS'].sum().rename('Sent')
delivered_by_route = (
    dlv_latest[dlv_latest['Document_Type_Name'] == 'Delivery']
    .groupby('Route_ID_AFS', dropna=False)['DeliveredBunches'].sum().rename('Delivered')
)

routes_short = routes_today[[route_cols['route_no'], route_cols['route_afs'], route_cols['cluster']]].rename(
    columns={
        route_cols['route_no']:  'Route No.',
        route_cols['route_afs']: 'Route_ID_AFS',
        route_cols['cluster']:   'Cluster',
    }
)
comp = (routes_short
        .merge(sent_by_route,      on='Route_ID_AFS', how='left')
        .merge(delivered_by_route, on='Route_ID_AFS', how='left'))
comp[['Sent', 'Delivered']] = comp[['Sent', 'Delivered']].fillna(0)
comp['Diff'] = comp['Delivered'] - comp['Sent']
comp['Compliance'] = comp.apply(
    lambda r: (r['Delivered'] / r['Sent'] * 100) if r['Sent'] > 0 else 0, axis=1
)

total_sent      = int(comp['Sent'].sum())
total_delivered = int(comp['Delivered'].sum())
variance        = total_delivered - total_sent

kpi_grid(
    kpi("Sent (units)", f"{total_sent:,}"),
    kpi("Delivered",    f"{total_delivered:,}", accent=True),
    kpi("Variance",     f"{variance:+,}"),
)

if comp[['Sent', 'Delivered']].sum().sum() == 0:
    panel_open()
    st.warning(
        f"No sent/delivered data for {f['target_date'].strftime('%a %b %d')}. "
        "If the date is very recent, refresh **📦 Sent**."
    )
    panel_close()
else:
    panel_open("Per route")
    comp_show = comp.sort_values('Compliance', ascending=False)
    st.dataframe(
        comp_show, use_container_width=True, hide_index=True,
        column_config={
            "Compliance": st.column_config.ProgressColumn(
                "Compliance", format="%.0f%%", min_value=0, max_value=100
            ),
            "Sent":      st.column_config.NumberColumn(format="%d"),
            "Delivered": st.column_config.NumberColumn(format="%d"),
            "Diff":      st.column_config.NumberColumn(format="%+d"),
        },
    )
    panel_close()
```

- [ ] **Step 2: Smoke-run**

```bash
python -m streamlit run Home.py
```

Open http://localhost:8501, click "Sent vs Delivery" in the sidebar. Verify:
1. Eyebrow + title shows the page name and date.
2. 3 KPIs: Sent · Delivered (blue accent) · Variance (with `+`/`−` sign).
3. "Per route" panel shows the table with a blue progress column for Compliance.
4. If no `data/deliveries.parquet` exists, the info box shows instead — and the rest of the page is skipped.

Stop with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add pages/2_Sent_vs_Delivery.py
git commit -m "feat(pages): add Sent vs Delivery page with new theme"
```

---

## Task 11: Build `pages/3_Errors.py`

**Files:**
- Create: `pages/3_Errors.py`
- Reference: `dashboard.py:806-921` (Tab 3 body)

- [ ] **Step 1: Create `pages/3_Errors.py`**

```python
"""Errors — inventory mismatches: Initial + Delivery − Credits − Final ≠ 0."""
import pandas as pd
import streamlit as st

from lib.compute import latest_per
from lib.filters import apply_filters
from lib.theme import (SLATE, eyebrow_title, inject_css, kpi, kpi_grid,
                        panel_close, panel_open)

st.set_page_config(page_title="Errors", layout="wide", page_icon="⚠️")
inject_css()

if '_rtd_data' not in st.session_state:
    st.error("Open from the Home page first (`streamlit run Home.py`).")
    st.stop()

inv, dlv, vis, sm, rm, sent = st.session_state['_rtd_data']
route_cols = st.session_state['_rtd_routes']
f          = st.session_state['_rtd_filters']

eyebrow_title("Errors", f"Inventory mismatches · {f['target_date'].strftime('%a %b %d, %Y')}")
st.markdown(
    f'<div style="font-size:12px;color:{SLATE};margin-bottom:12px;">'
    f'Difference = Initial Inventory + Delivered − Credits − Final Inventory'
    f'</div>',
    unsafe_allow_html=True,
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
if f['customer_filter']:
    err = err[err['CUSTOMER'].isin(f['customer_filter'])]
if f['route_filter']:
    err = err[err['Route_ID_AFS'].isin(f['route_filter'])]
if f['store_filter']:
    err = err[err['Store_Number'].isin(f['store_filter'])]

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
    pos       = int(err.loc[err['Difference'] > 0, 'Difference'].sum())
    neg       = int(err.loc[err['Difference'] < 0, 'Difference'].sum())
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
```

- [ ] **Step 2: Smoke-run**

```bash
python -m streamlit run Home.py
```

Open http://localhost:8501, click "Errors" in the sidebar. Verify:
1. Title + formula caption.
2. Search input + sign-filter dropdown.
3. KPI strip with "Errors (rows)" in blue accent + Stores + Units off + Routes.
4. Mismatches panel with the dataframe.
5. With `prod_search="cvs"` (or any partial store match), the table filters to rows containing that string.

Stop with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add pages/3_Errors.py
git commit -m "feat(pages): add Errors page with new theme"
```

---

## Task 12: Build `pages/4_7_Day_Summary.py`

**Files:**
- Create: `pages/4_7_Day_Summary.py`
- Reference: `dashboard.py:925-1187` (Tab 4 body)

This is the largest page — keep all the existing logic but render with the new theme. The KPI grid stays at 10 metrics (5 per row × 2 rows), the daily trend table + line chart stays, the breakdown radio + table stays, and top-10 problematic stores stays.

- [ ] **Step 1: Create `pages/4_7_Day_Summary.py`**

```python
"""7-Day Summary — executive trend across the last 7 days.

This page ignores the sidebar's single Date input and uses the 7-day window
ending at the selected date.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

from lib.filters import apply_filters
from lib.theme import (SLATE, eyebrow_title, inject_css, kpi, kpi_grid,
                        panel_close, panel_open)

st.set_page_config(page_title="7-Day Summary", layout="wide", page_icon="📊")
inject_css()

if '_rtd_data' not in st.session_state:
    st.error("Open from the Home page first (`streamlit run Home.py`).")
    st.stop()

inv, dlv, vis, sm, rm, sent = st.session_state['_rtd_data']
route_cols = st.session_state['_rtd_routes']
f          = st.session_state['_rtd_filters']

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
        active_ids_d |= set(vis_w.loc[vis_w['Visit_Date']   == d_date, 'Route_ID_AFS'].dropna().unique()) \
            if 'Route_ID_AFS' in vis_w.columns else set()
        active_ids_d |= set(dlv_w.loc[dlv_w['Created_Date'] == d_date, 'Route_ID_AFS'].dropna().unique()) \
            if 'Route_ID_AFS' in dlv_w.columns else set()
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
    if f['route_filter']:
        routes_d = routes_d[routes_d[route_cols['route_afs']].isin(f['route_filter'])]
    rids_d = routes_d[route_cols['route_afs']].dropna().unique()
    stores_d = sm[sm['Route_ID_AFS'].isin(rids_d)]
    if f['customer_filter']:
        stores_d = stores_d[stores_d['CUSTOMER'].isin(f['customer_filter'])]
    if f['store_filter']:
        stores_d = stores_d[stores_d['Store_Number'].isin(f['store_filter'])]
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

# 4) KPIs (10 in two rows)
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
```

- [ ] **Step 2: Smoke-run**

```bash
python -m streamlit run Home.py
```

Open http://localhost:8501, click "7-Day Summary" in the sidebar. Verify:
1. Title + period caption.
2. 10 KPIs split into 2 rows of 5 (first card "Visit compliance" has the blue accent).
3. "Daily trend" panel with table + line chart.
4. "Breakdown" panel with a "Cluster / Route / Customer" radio + table.
5. "Top 10 stores · most errors" panel with the ranking.

Stop with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add pages/4_7_Day_Summary.py
git commit -m "feat(pages): add 7-Day Summary page with new theme"
```

---

## Task 13: Replace `dashboard.py` with deprecation stub

**Files:**
- Modify: `dashboard.py` (replace entire file content)

- [ ] **Step 1: Overwrite `dashboard.py`**

```python
"""Deprecated entry point. Use Home.py instead."""
import streamlit as st

st.set_page_config(page_title="Route Delivery (legacy)", page_icon="🚚")
st.error(
    "This entry point is deprecated. Run the dashboard with:\n\n"
    "```\n"
    "python -m streamlit run Home.py\n"
    "```"
)
st.stop()
```

- [ ] **Step 2: Smoke-run**

```bash
python -m streamlit run dashboard.py
```

Open http://localhost:8501. Verify the red error message appears with the new instruction. Stop with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "refactor: replace dashboard.py with deprecation stub pointing to Home.py"
```

---

## Task 14: Update `start-dashboard.bat`

**Files:**
- Modify: `start-dashboard.bat:9`

- [ ] **Step 1: Replace `dashboard.py` with `Home.py` in the batch file**

Open `start-dashboard.bat`. Change line 9 from:

```bat
python -m streamlit run dashboard.py
```

to:

```bat
python -m streamlit run Home.py
```

- [ ] **Step 2: Smoke-run**

Double-click `start-dashboard.bat` (or run from a separate cmd window). The browser should open and land on the new Home page. Close the cmd window to stop.

- [ ] **Step 3: Commit**

```bash
git add start-dashboard.bat
git commit -m "chore: point start-dashboard.bat to Home.py"
```

---

## Task 15: Update `README.md`

**Files:**
- Modify: `README.md`

The README has a `## Cómo correr` section that says `streamlit run dashboard.py`, and a `## Tabs` section with the 3 old tabs. Update both.

- [ ] **Step 1: In the "Estructura" code block**

Change the structure listing to reflect the new layout (replace the existing `dashboard.py ← App Streamlit principal` line with the new entry + pages + lib).

Replace:

```
├── dashboard.py              ← App Streamlit principal
```

with:

```
├── Home.py                   ← App Streamlit principal (entry)
├── pages/                    ← Páginas (Daily Follow, Sent vs Delivery, Errors, 7-Day)
├── lib/                      ← Módulos compartidos (data, filters, refresh, theme)
├── .streamlit/config.toml    ← Tema McKinsey blue
├── dashboard.py              ← Stub legacy → redirige a Home.py
```

- [ ] **Step 2: In the "Cómo correr" section**

Change:

```powershell
python -m streamlit run dashboard.py
```

to:

```powershell
python -m streamlit run Home.py
```

- [ ] **Step 3: Replace the "## Tabs" section heading and contents**

Old:

```markdown
## Tabs

- **📅 Follow del Día** — cumplimiento por cluster y por ruta. Detalle por
  ruta con tiendas color-coded (🟢 visitada · 🟡 en proceso · 🔴 pendiente).
- **📦 Enviado vs Entregado** — compara DELIVERY UNITS (warehouse) vs
  DeliveredBunches (driver) por ruta.
- **⚠️ Errores** — diferencias de inventario:
  `Initial + Delivery − Credits − Final ≠ 0`.
```

New:

```markdown
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
```

- [ ] **Step 4: Verify rendering**

Open `README.md` in a markdown previewer (VS Code → "Open Preview to the Side"). Make sure code blocks and lists render correctly.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: update README for multipage redesign (Home.py + pages/)"
```

---

## Task 16: Numbers regression check

**Files:**
- None (verification only)

- [ ] **Step 1: Run the new dashboard**

```bash
python -m streamlit run Home.py
```

Use the same date + filters as Task 0 baseline (today, all clusters, all customers).

- [ ] **Step 2: Compare KPIs**

For each page, compare the visible numbers against the baseline you wrote down in Task 0:

| Page                | What to compare                                                                |
|---------------------|--------------------------------------------------------------------------------|
| Daily Follow        | Visited count and Planned (= old Visited / Total in tab 1).                    |
| Sent vs Delivery    | total Sent and Delivered, plus Variance (= old "Delivered vs Sent" totals).    |
| Errors              | Stores count, Routes count, Units off (= sum of |Difference|).                 |
| 7-Day Summary       | All 10 KPIs (visit pct, delivery pct, stores w/ errors, etc.).                 |

**Tolerance:** they should match exactly. The only acceptable difference is on Errors page where old shows "Shortage sum" + "Overage sum" separately (we replaced with "Units off" = `|sum|` of all). Confirm `units_off ≈ |shortage| + |overage|`.

If any number differs, find the source-of-truth comparison: open the old `dashboard.py` (use `git show main:dashboard.py`) and trace the calculation. Most likely cause: a missing filter or a `.fillna(0)` step left out during the migration.

- [ ] **Step 3: Verify filter persistence between pages**

Set a non-default filter (e.g., Cluster = "DALLAS"). Click each of the 4 pages in the sidebar in order. The filter should remain set on every page.

- [ ] **Step 3.1: Verify route inclusion logic (planned ∪ active)**

This is the core behavior change — verify it on Daily Follow.

1. Pick a date where you know at least one route had visits/deliveries even though it wasn't on the schedule for that day-of-week (the user can confirm a known case from operations). Example: a Sunday where a Monday-only route was visited because the schedule was changed.
2. With "Show all routes" checkbox **OFF** (default), confirm:
   - Routes scheduled for that day-of-week appear, even if 0 visits (Pending count > 0).
   - The off-schedule route that had visits also appears, with its real numbers.
3. Toggle "Show all routes" **ON** — every route in the route master appears (planned count goes way up).
4. Toggle back OFF — the union view returns.

If no real-world example is handy, simulate by: pick a route with `Service Days = "Mon"` and a visit on a Tuesday in the visits parquet. With the date set to that Tuesday and "Show all routes" OFF, confirm the route appears.

- [ ] **Step 4: Verify refresh buttons (local only)**

Click 🔁 API. Wait for the spinner to finish. Confirm: success toast, data reloaded.

- [ ] **Step 5: Verify cloud-mode hides refresh**

```bash
STREAMLIT_RUNTIME=cloud python -m streamlit run Home.py
```

(On Windows PowerShell: `$env:STREAMLIT_RUNTIME = "cloud"; python -m streamlit run Home.py`).

Verify: the refresh buttons section shows the read-only banner instead. The "Share with team" expander is hidden.

Unset the env var:

```powershell
Remove-Item Env:STREAMLIT_RUNTIME
```

- [ ] **Step 6: Final commit if any fixes were needed**

If you found and fixed any regression issues:

```bash
git add <files>
git commit -m "fix: <specific regression>"
```

If everything passed first try, just continue.

---

## Task 17: Open the PR and merge

**Files:**
- None (git only)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin dashboard-redesign
```

- [ ] **Step 2: Open a PR via gh CLI**

```bash
gh pr create --title "Dashboard redesign — McKinsey blue, multipage layout" --body "$(cat <<'EOF'
## Summary
- Splits the 1199-line single-page `dashboard.py` (4 tabs) into a multipage app: `Home.py` + 4 files in `pages/`.
- New McKinsey-blue minimalist theme via `.streamlit/config.toml` + `lib/theme.py` HTML helpers.
- Shared logic extracted to `lib/`: `data`, `filters`, `refresh`, `compute`, `routes`, `theme`.
- `dashboard.py` becomes a 5-line deprecation stub; `start-dashboard.bat` and README updated.

## Test plan
- [x] `streamlit run Home.py` lands on the welcome page; sidebar shows refresh + filters.
- [x] All 4 pages render with no console errors.
- [x] Filters persist when navigating between pages.
- [x] Refresh buttons still work and trigger cache clear + rerun.
- [x] KPIs match old dashboard for the same date + filters (regression check).
- [x] Cloud mode (STREAMLIT_RUNTIME=cloud) hides refresh buttons.
EOF
)"
```

- [ ] **Step 3: Review the PR**

Open the PR URL printed by `gh`. Review the diff visually.

- [ ] **Step 4: Merge**

Once approved:

```bash
gh pr merge --squash --delete-branch
```

---

## Self-Review Checklist

Run after writing the plan, before handing off.

**Spec coverage:**

- ✅ Visual style — Task 1 (theme config) + Task 2 (theme.py tokens & helpers).
- ✅ File structure — Tasks 2-7 build all of `lib/`; Tasks 8-12 build `Home.py` + `pages/`.
- ✅ Page 1 (Daily Follow) — Task 9.
- ✅ Page 2 (Sent vs Delivery) — Task 10.
- ✅ Page 3 (Errors) — Task 11.
- ✅ Page 4 (7-Day Summary) — Task 12.
- ✅ Migration of `dashboard.py` — Task 13.
- ✅ `start-dashboard.bat` update — Task 14.
- ✅ README update — Task 15.
- ✅ Acceptance test (regression + filter persistence + cloud mode) — Task 16.

**Placeholder scan:** No "TBD", "implement later", "add error handling", or "similar to Task N" placeholders. Every code block is complete and self-contained.

**Type/name consistency:**

- `route_cols` is the dict from `detect_route_columns(rm)` everywhere it's used.
- `filters` (`f` for short) is the dict from `render_sidebar_filters(...)` everywhere.
- `apply_filters(df, f, also_activity=...)` signature is consistent across pages.
- `latest_per` signature and use is consistent.
- `store_day_summary(...)` keyword args match the function definition.
- `kpi(label, value, accent=False)` and `kpi_grid(*kpi_html)` consistent everywhere.

**Note about the spec:** the spec called Page 4 "(NEW)" but the existing `dashboard.py` already has Tab 4 (7-Day Summary). The plan acknowledges this — the redesign preserves all logic, just restyles and routes it to its own page. No design change needed.

**Route inclusion logic (added 2026-05-04):** the spec's "Route Inclusion Logic" subsection is implemented via:
- `lib/filters.py` — `routes_for_day(...)` accepts `vis_d / dlv_d / sent_d` and unions scheduled-for-day with routes appearing in those frames. The sidebar's old "Show only routes scheduled for this day" checkbox is replaced by a new **"Show all routes"** checkbox (default OFF). When OFF (default), the union behavior is active.
- `pages/1_Daily_Follow.py` and `pages/2_Sent_vs_Delivery.py` pass the day-filtered fact frames into `routes_for_day(...)`.
- `pages/4_7_Day_Summary.py` applies the same union per-day inside the daily-compliance loop.
- Verified in Task 16, Step 3.1.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-dashboard-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for a 17-task plan like this since each subagent gets clean context for its task.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
