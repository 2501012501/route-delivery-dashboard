# Dashboard Redesign — Route to Delivery

**Date:** 2026-05-04
**Status:** Design approved, awaiting user review before implementation plan
**Owner:** Gabriela Sanchez

## Goal

Rebuild the Streamlit dashboard with a minimalist visual style and split the
current single-page tabs into separate pages, plus add a new 7-day executive
summary page. Same data, same filters, same refresh capabilities — just a
cleaner shell and one extra view.

## Scope

**In scope:**

- Visual restyle to **McKinsey blue + white** minimalist theme.
- Convert from one-page-with-tabs to **Streamlit native multipage** (`pages/`).
- Add a new **7-Day Summary** page with combined KPIs across the 3 existing
  views (compliance, delivery, errors).
- Move shared logic (data loading, filters, refresh buttons) into reusable
  modules so each page imports the same shell.

**Out of scope:**

- Changes to data sources or the refresh pipelines (`RouteToDelivery.py`,
  `extract.py`, `Transform.py`, `Deliveries.sql`).
- Changes to filter semantics (date, cluster, customer, route, store,
  activity type, "scheduled-only" flag).
- New metrics beyond what already exists in inventory/delivery/visits/sent
  data.

## Visual Style

**Palette:**

| Role            | Hex       | Use                                                       |
|-----------------|-----------|-----------------------------------------------------------|
| Deep navy       | `#051C2C` | Brand mark, page titles, primary text                     |
| Bright blue     | `#2251FF` | KPI accent, active sidebar item, links, chart bars        |
| Pale blue       | `#EDF2FE` | Status pills, compliance bar background, hover states     |
| Slate text      | `#64748B` | Secondary text, eyebrow labels, table header              |
| Page background | `#FAFBFC` | Body background                                           |
| Card surface    | `#FFFFFF` | KPI cards, panels, tables                                 |
| Border          | `#E5E7EB` | Card and panel borders                                    |
| Warning (amber) | `#FEF3C7` / `#92400E` | "In progress" pills, "Review" pills                |

**Typography:** system stack (`-apple-system, "Segoe UI", system-ui, sans-serif`),
no custom web fonts. Page titles 22 px / weight 600. KPI values 24 px /
weight 700. Eyebrow labels 11 px uppercase, letter-spacing 1.2 px, in
bright blue.

**Components:** Each page uses three primitives:

- **Eyebrow + Title** at the top (small uppercase blue label, then big
  navy title in one line).
- **KPI strip** (3-4 cards in a grid; the "primary" KPI gets a 2 px bright-blue
  left border + bright-blue value).
- **Panels** (white card, 1 px border, 10 px radius, 16-18 px padding) for
  tables, bars, and charts.

Status pills come in three flavors: blue (done/positive variance), amber
(in progress / review), gray (pending).

## Architecture

### File structure (after redesign)

```
Route to delivery/
├── Home.py                       ← entry point, redirects to Daily Follow
├── pages/
│   ├── 1_Daily_Follow.py         ← visit compliance today
│   ├── 2_Sent_vs_Delivery.py     ← warehouse vs driver totals
│   ├── 3_Errors.py               ← inventory mismatches
│   └── 4_7_Day_Summary.py        ← executive trend view
├── lib/
│   ├── __init__.py
│   ├── data.py                   ← load_data() + cluster aliasing
│   ├── filters.py                ← shared sidebar filter widgets + apply_filters
│   ├── refresh.py                ← refresh buttons + cloud publish
│   ├── routes.py                 ← parse_service_days + route master helpers
│   └── theme.py                  ← color tokens + reusable st components (KPI card, pill, panel)
├── .streamlit/
│   └── config.toml               ← Streamlit theme config (colors)
├── dashboard.py                  ← legacy entry; prints deprecation pointer to `streamlit run Home.py`
├── RouteToDelivery.py
├── extract.py
├── Transform.py
└── ... (data loaders unchanged)
```

**Why `lib/`:** the current `dashboard.py` is 1,199 lines mixing data
loading, filter logic, refresh handlers, and three tabs of rendering. Each
new page would re-implement the same setup, so the shell needs to be
extracted exactly once.

**Why keep `dashboard.py`:** preserves a graceful path for users who run
`streamlit run dashboard.py` from muscle memory or `start-dashboard.bat`.
The file becomes a 5-line stub that prints "Use `streamlit run Home.py`"
and stops. `start-dashboard.bat` is updated to call `Home.py`.

### Page flow

1. **`Home.py`** runs `lib.data.load_data()` once (cached), renders the
   sidebar via `lib.filters.render_sidebar()` (which also renders refresh
   buttons via `lib.refresh.render`), then redirects to Daily Follow.
2. **Each page in `pages/`** does the same setup: load data, render
   sidebar, then renders its own body.
3. **Sidebar order (top → bottom):** Logo + "Route to Delivery" wordmark,
   page navigation (Streamlit's auto-injected page list, restyled), data
   freshness caption, refresh buttons (or read-only banner on cloud), then
   filters (date, cluster, customer, route, store, activity type,
   scheduled-only checkbox).
4. **Filters live in `st.session_state`** so they persist as the user
   navigates between pages.

### Theme application

- `.streamlit/config.toml` sets `primaryColor = "#2251FF"`,
  `backgroundColor = "#FAFBFC"`, `secondaryBackgroundColor = "#FFFFFF"`,
  `textColor = "#051C2C"`, `font = "sans serif"`.
- A small CSS injection in `lib/theme.py` (`st.markdown(..., unsafe_allow_html=True)`)
  styles the sidebar nav active state, KPI card borders, panel radius, and
  pill component since Streamlit's theme config alone doesn't reach those.
- KPI card and pill render as helper functions returning HTML —
  `theme.kpi(label, value, accent=False)` and `theme.pill(text, kind="ok")`.

## Page Specs

### Page 1 · Daily Follow

**Eyebrow:** "Daily Follow" · **Title:** "Visit compliance · today"

**KPI strip (4):** Planned · Visited (accent) · In progress · Pending

**Panel — Compliance bar:** progress bar per selected cluster (or "All"
if no cluster filter), showing % visited.

**Panel — Stores table:** one row per store in scope, columns: status pill
(Done/In prog./Pending), store id + city, route id, visit time. Color-coded
by visit status (replaces the current emoji 🟢🟡🔴 system).

**Data sources:** `vis` (visits), `rm` (route master) for "what was planned",
`sm` (store master) for store names.

### Page 2 · Sent vs Delivery

**Eyebrow:** "Sent vs Delivery" · **Title:** "Warehouse vs driver totals"

**KPI strip (3):** Sent (units) · Delivered (accent, in DeliveredBunches) ·
Variance.

**Panel — Per-route table:** route id, customer + cluster label, sent units,
variance pill (blue if 0/+, amber if negative).

**Data sources:** `sent` (data/deliveries.parquet) and `dlv` (delivery.parquet
from API). Same comparison logic as today's tab — Sent = warehouse units,
Delivered = driver-recorded bunches.

### Page 3 · Errors

**Eyebrow:** "Errors" · **Title:** "Inventory mismatches"

**KPI strip (3):** Errors (accent) · Stores affected · Units off (sum of
absolute deltas).

**Panel — Mismatch table:** for each store where
`Initial + Delivery − Credits − Final ≠ 0`, columns: store id, delta value,
"REVIEW" pill. Subhead reminds the user of the formula.

**Data sources:** `inv` (inventory) — same calculation as today's "Errores"
tab.

### Page 4 · 7-Day Summary (NEW)

**Eyebrow:** "7-Day Summary" · **Title:** "Last 7 days · executive view"

**Panel — Compliance trend:** bar chart, % visited per day for the last 7
days, respecting the cluster + customer filters (date filter is overridden
to the 7-day window on this page only).

**Panel — Sent vs Delivered trend:** grouped bar chart, sent units vs
delivered units per day for the last 7 days.

**Panel — Top stores · most errors:** small table of the top N stores
(N=10) with most mismatch incidents over the last 7 days, count column in
bright blue.

**Date handling:** This page ignores the sidebar's single-date input and
uses the last 7 calendar days ending at the latest data date. A small
caption shows "May 4 – April 28" so users know the window.

**Data sources:** all four (vis, sent + dlv, inv) over a 7-day window.

## Route Inclusion Logic

The dashboard's notion of "which routes show up for a given date" is
**`scheduled ∪ active`**:

- **Scheduled routes** — routes whose Service Days include the target
  date's day-of-week. Always shown, even if 0 visits (so missed days are
  visible as "Pending").
- **Active routes** — routes that had at least one visit, delivery, or
  sent record on the target date, regardless of schedule. Shown so that
  ad-hoc schedule changes don't silently disappear from the dashboard.

A route in the plan with no activity → appears with 0 visited / 0
delivered. A route NOT in the plan but with activity → appears with its
real numbers. The cluster, customer, route, and store filters still apply
on top of this union.

The sidebar has one override: a checkbox **"Show all routes (even without
schedule or activity)"** — default OFF. When ON, every route in the route
master is shown after applying the other filters. This is the legacy
behavior of today's "Show only routes scheduled for this day" checkbox,
inverted so the new default is the smarter union.

This logic lives in `lib.filters.routes_for_day(...)`, which accepts the
day-filtered fact frames (vis_d, dlv_d, sent_d) and computes the active
route id set internally.

## Data Flow

Unchanged from today. Same parquets, same masters, same refresh scripts.
The only new data behaviors are: (1) Page 4 aggregates across 7 days, and
(2) the route inclusion logic above replaces the old "show only scheduled"
checkbox with a "scheduled ∪ active" union.

## Error Handling

Same as today — if `route_master.parquet` is missing, show the existing
"Run `python extract.py --route-master`" message and stop.

If `data/deliveries.parquet` is missing, Page 2 (Sent vs Delivery) shows
an info box telling the user to run `python extract.py --deliveries &&
python Transform.py`. The other 3 pages keep working.

If a parquet exists but is empty for the chosen filters, the page shows
"No data for this selection" centered in the body — no crash.

## Cloud Behavior

`IS_CLOUD` detection is unchanged. On cloud:

- Refresh buttons replaced with a small "Read-only view" caption (same as
  today).
- The "Share with team" expander is hidden (same as today).
- `_publish_to_cloud()` lives in `lib/refresh.py` and is wired only on
  local installs.

## Testing

Manual acceptance test plan after implementation:

1. Local: `streamlit run Home.py` starts on port 8501 and lands on Daily
   Follow.
2. All 4 pages render with no console errors.
3. Filters persist when navigating between pages.
4. Each refresh button still works and triggers the cache clear + rerun.
5. The 3 original pages show identical numbers to the current dashboard's
   3 tabs for the same date + filters (regression check).
6. Page 4 shows 7 bars in each trend panel and a top-stores list.
7. Cloud deploy renders correctly with refresh buttons hidden.

No automated tests — the project doesn't have a test harness today, and
adding one isn't part of this redesign.

## Migration

- `dashboard.py` becomes a deprecation stub (5 lines).
- `start-dashboard.bat` updated to invoke `Home.py`.
- README updated: "Cómo correr" section points to `streamlit run Home.py`.
- README's "Tabs" section becomes "Pages" with the 4 entries.

## Risks

- **Streamlit page navigation styling is limited.** The active-page
  highlight and sidebar header come from Streamlit internals. Mitigation:
  use targeted CSS overrides; if a particular detail can't be styled,
  document it and live with the small visual gap.
- **Filter session-state coupling.** Moving filters into a shared module
  means a bug there breaks all 4 pages. Mitigation: filter widgets are
  thin wrappers over `st.selectbox` / `st.multiselect`; the apply logic
  is the same as today (lifted, not rewritten).
- **OneDrive path with spaces.** Already works today; no change expected.

## Open Questions

None at this stage. All design decisions are locked. If anything surfaces
during implementation, it goes back through this doc.
