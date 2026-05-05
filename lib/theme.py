"""Visual tokens and HTML helpers for the redesigned dashboard.

All HTML uses st.markdown(..., unsafe_allow_html=True). The CSS injection
happens once per session via inject_css(); pages call the helpers
(page_header, kpi, pill, panel) to render consistent UI.
"""
import streamlit as st

# ── Palette (McKinsey blue) ──────────────────────────────────────────────────
NAVY       = "#051C2C"   # primary text, page titles
NAVY_DEEP  = "#020E16"   # darker for headers
BLUE       = "#2251FF"   # accent
BLUE_DARK  = "#1A3FCC"   # accent-hover
PALE_BLUE  = "#EDF2FE"   # pill backgrounds, hover tints
SOFT_BLUE  = "#F7F9FF"   # very subtle accent area
SIDEBAR_BG = "#DCE6FA"   # sidebar background — distinctly blue, still readable
SLATE      = "#64748B"   # secondary text, eyebrow labels
SLATE_LIGHT = "#94A3B8"  # tertiary text
PAGE_BG    = "#F6F7F9"   # body background (slightly more contrast than before)
SURFACE    = "#FFFFFF"   # cards, panels
BORDER     = "#E5E7EB"   # default borders
BORDER_SOFT = "#EEF1F4"  # softer dividers
AMBER_BG   = "#FEF3C7"
AMBER_FG   = "#92400E"
GRAY_BG    = "#F1F5F9"

# Shadows — layered for realistic depth
SHADOW_SM = "0 1px 2px rgba(5,28,44,0.05)"
SHADOW_MD = "0 1px 3px rgba(5,28,44,0.05), 0 4px 12px rgba(5,28,44,0.04)"
SHADOW_LG = "0 4px 16px rgba(5,28,44,0.08), 0 1px 3px rgba(5,28,44,0.04)"


_CSS = f"""
<style>
  /* ── App background slightly warmer for card contrast ─────────────── */
  .stApp {{
    background: {PAGE_BG};
  }}

  /* Hide Streamlit's default top header for a cleaner webapp feel. The
     sidebar is locked open below, so we don't need its collapse controls. */
  header[data-testid="stHeader"] {{
    display: none;
  }}

  /* SIDEBAR LOCKED OPEN — no way for the user to collapse it. This avoids
     a long-standing Streamlit bug where the expand arrow disappears
     after collapse. Hide every collapse / expand control selector. */
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"],
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stSidebarCloseButton"],
  [data-testid="stExpandSidebarButton"],
  [aria-label="Open sidebar"],
  [aria-label="Close sidebar"],
  [aria-label="open sidebar"],
  [aria-label="close sidebar"],
  button[kind="header"],
  button[kind="headerNoPadding"] {{
    display: none !important;
  }}

  /* Constrain content width so it reads like a real webapp */
  .block-container {{
    max-width: 1280px;
    padding-top: 1.5rem;
    padding-bottom: 4rem;
  }}

  /* ── Top header bar (app shell) ───────────────────────────────────── */
  .rtd-top-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 14px 22px;
    margin-bottom: 22px;
    box-shadow: {SHADOW_SM};
  }}
  .rtd-brand {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .rtd-brand-logo {{
    width: 38px;
    height: 38px;
    background: {NAVY};
    color: {SURFACE};
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 18px;
    letter-spacing: -0.5px;
  }}
  .rtd-brand-name {{
    font-size: 14px;
    font-weight: 700;
    color: {NAVY};
    line-height: 1.2;
  }}
  .rtd-brand-tag {{
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: {SLATE};
    font-weight: 700;
    margin-top: 2px;
  }}
  .rtd-top-meta {{
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .rtd-fresh-pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: {PALE_BLUE};
    border: 1px solid {PALE_BLUE};
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: {BLUE};
    font-weight: 700;
  }}
  .rtd-fresh-pill .dot {{
    width: 7px;
    height: 7px;
    background: {BLUE};
    border-radius: 50%;
    box-shadow: 0 0 0 3px rgba(34, 81, 255, 0.15);
  }}

  /* ── Sidebar polish ───────────────────────────────────────────────── */
  /* Locked-open: width fixed, can't be collapsed (collapse buttons hidden
     above). Soft blue tint differentiates the navigation column from the
     content area. The override has to win against Streamlit's inline
     transform/width that triggers when collapsed state is stored in
     localStorage from a previous session. */
  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"][aria-expanded="false"],
  section[data-testid="stSidebar"][aria-expanded="true"],
  div[data-testid="stSidebar"],
  [data-testid="stSidebar"] {{
    background: {SIDEBAR_BG} !important;
    border-right: 1px solid {BORDER};
    box-shadow: {SHADOW_SM};
    min-width: 244px !important;
    max-width: 244px !important;
    width: 244px !important;
    transform: translateX(0) !important;
    visibility: visible !important;
    display: block !important;
    margin-left: 0 !important;
    left: 0 !important;
  }}
  /* Hide the drag-to-resize handle since width is fixed */
  [data-testid="stSidebarResizer"],
  [data-testid="stSidebarResizeHandle"] {{
    display: none !important;
  }}

  /* ── Sidebar nav (page menu at the top) ───────────────────────────── */
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
    background: {SOFT_BLUE};
    padding: 14px 10px 12px 10px;
    margin: -4px -16px 12px -16px;
    border-bottom: 1px solid {BORDER_SOFT};
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"]::before {{
    content: 'Pages';
    display: block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: {SLATE};
    padding: 0 8px 8px 8px;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] ul {{
    padding: 0;
  }}
  /* Hide the Home redirect entry — it's noise, dashboard lands on Daily Follow directly */
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li:first-child {{
    display: none;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
    text-transform: uppercase;
    letter-spacing: 0.7px;
    font-size: 11px;
    font-weight: 700;
    color: {SLATE};
    border-radius: 8px;
    padding: 10px 12px;
    margin: 2px 0;
    border-left: 3px solid transparent;
    transition: background .15s ease, color .15s ease, border-color .15s ease;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span {{
    color: inherit !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{
    background: {PALE_BLUE};
    color: {NAVY};
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: {PALE_BLUE};
    color: {BLUE};
    border-left-color: {BLUE};
  }}
  section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3 {{
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-size: 11px;
    font-weight: 700;
    color: {SLATE};
    margin: 16px 0 6px 0;
  }}
  section[data-testid="stSidebar"] label p {{
    text-transform: uppercase;
    letter-spacing: 0.6px;
    font-size: 10px;
    font-weight: 600;
    color: {SLATE};
  }}
  section[data-testid="stSidebar"] hr {{
    border-color: {BORDER_SOFT};
    margin: 14px 0;
  }}

  /* ── Page header ──────────────────────────────────────────────────── */
  .rtd-page-header {{
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    padding: 4px 0 18px 0;
    margin-bottom: 18px;
    border-bottom: 1px solid {BORDER};
  }}
  .rtd-page-header-left {{ flex: 1; min-width: 0; }}
  .rtd-eyebrow {{
    display: inline-block;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    font-size: 11px;
    color: {BLUE};
    font-weight: 700;
    background: {PALE_BLUE};
    padding: 4px 10px;
    border-radius: 6px;
    margin-bottom: 10px;
  }}
  .rtd-title {{
    margin: 0;
    color: {NAVY};
    font-weight: 700;
    font-size: 28px;
    letter-spacing: -0.4px;
    line-height: 1.2;
  }}
  .rtd-subtitle {{
    margin: 6px 0 0 0;
    color: {SLATE};
    font-size: 13px;
    font-weight: 500;
  }}
  .rtd-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 999px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
    color: {NAVY};
    text-transform: uppercase;
    letter-spacing: 0.6px;
    box-shadow: {SHADOW_SM};
    white-space: nowrap;
  }}
  .rtd-badge .dot {{
    width: 6px; height: 6px; background: {BLUE};
    border-radius: 50%;
  }}

  /* ── KPI cards ────────────────────────────────────────────────────── */
  .rtd-kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin: 8px 0 20px 0;
  }}
  .rtd-kpi {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: {SHADOW_SM};
    transition: box-shadow .2s ease, transform .2s ease, border-color .2s ease;
    position: relative;
  }}
  .rtd-kpi:hover {{
    box-shadow: {SHADOW_LG};
    transform: translateY(-1px);
    border-color: {BORDER};
  }}
  .rtd-kpi.accent {{
    border-color: {BLUE};
    background: linear-gradient(180deg, {SOFT_BLUE} 0%, {SURFACE} 70%);
  }}
  .rtd-kpi.accent::before {{
    content: '';
    position: absolute;
    top: 0; left: 18px; right: 18px;
    height: 3px;
    background: {BLUE};
    border-radius: 0 0 3px 3px;
  }}
  .rtd-kpi-label {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: {SLATE};
    font-weight: 700;
  }}
  .rtd-kpi-value {{
    font-size: 28px;
    font-weight: 700;
    color: {NAVY};
    margin-top: 6px;
    letter-spacing: -0.6px;
    line-height: 1.1;
  }}
  .rtd-kpi.accent .rtd-kpi-value {{ color: {BLUE}; }}

  /* ── Panels ──────────────────────────────────────────────────────── */
  .rtd-panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 22px;
    margin: 14px 0;
    box-shadow: {SHADOW_MD};
  }}
  .rtd-panel-title {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: {SLATE};
    font-weight: 700;
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid {BORDER_SOFT};
  }}

  /* ── Pills ───────────────────────────────────────────────────────── */
  .rtd-pill {{
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.7px;
  }}
  .rtd-pill.ok    {{ background: {PALE_BLUE}; color: {BLUE}; }}
  .rtd-pill.warn  {{ background: {AMBER_BG}; color: {AMBER_FG}; }}
  .rtd-pill.pend  {{ background: {GRAY_BG}; color: {SLATE}; }}

  /* ── Streamlit dataframe polish ───────────────────────────────────── */
  [data-testid="stDataFrame"] {{
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid {BORDER};
  }}

  /* ── Streamlit metric polish (used in older areas) ────────────────── */
  [data-testid="stMetric"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 14px;
    box-shadow: {SHADOW_SM};
  }}

  /* ── Sidebar refresh buttons (API / Masters / Sent) ───────────────── */
  section[data-testid="stSidebar"] [data-testid="stButton"] button {{
    text-transform: uppercase;
    letter-spacing: 0.2px;
    font-size: 9px;
    font-weight: 700;
    padding: 5px 2px;
    min-height: 0;
    border-radius: 6px;
    border: 1px solid {BORDER};
    background: {SURFACE};
    color: {NAVY};
    white-space: nowrap;
    transition: background .15s ease, border-color .15s ease, color .15s ease;
  }}
  section[data-testid="stSidebar"] [data-testid="stButton"] button:hover {{
    background: {PALE_BLUE};
    border-color: {BLUE};
    color: {BLUE};
  }}
  /* Tighten the gap between the 3 buttons so they have more room */
  section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {{
    gap: 4px !important;
  }}
</style>
"""


def inject_css():
    """Call once at the top of every page (Home + pages/*) to apply the theme."""
    st.markdown(_CSS, unsafe_allow_html=True)


def top_header(fresh_text: str | None = None):
    """Renders the persistent app header: brand on the left, optional
    'data freshness' pill on the right. Call from setup() so it appears
    on every page.
    """
    fresh_html = ''
    if fresh_text:
        fresh_html = (
            f'<div class="rtd-top-meta">'
            f'<span class="rtd-fresh-pill">'
            f'<span class="dot"></span>{fresh_text}'
            f'</span>'
            f'</div>'
        )
    st.markdown(
        f'<div class="rtd-top-header">'
        f'  <div class="rtd-brand">'
        f'    <div class="rtd-brand-logo">R</div>'
        f'    <div>'
        f'      <div class="rtd-brand-name">Route to Delivery</div>'
        f'      <div class="rtd-brand-tag">Operations Dashboard</div>'
        f'    </div>'
        f'  </div>'
        f'  {fresh_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, badge: str | None = None,
                 subtitle: str | None = None):
    """Renders the unified page header: eyebrow chip + Title Case title +
    optional date badge on the right + optional subtitle below.
    """
    badge_html = ''
    if badge:
        badge_html = f'<span class="rtd-badge"><span class="dot"></span>{badge}</span>'
    subtitle_html = f'<div class="rtd-subtitle">{subtitle}</div>' if subtitle else ''
    st.markdown(
        f'<div class="rtd-page-header">'
        f'  <div class="rtd-page-header-left">'
        f'    <span class="rtd-eyebrow">{eyebrow}</span>'
        f'    <div class="rtd-title">{title}</div>'
        f'    {subtitle_html}'
        f'  </div>'
        f'  {badge_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def eyebrow_title(eyebrow: str, title: str):
    """Backwards-compatible alias for page_header without badge."""
    page_header(eyebrow, title)


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
    """Returns inline HTML for a status pill. kind in {'ok','warn','pend'}."""
    return f'<span class="rtd-pill {kind}">{text}</span>'


def panel_open(title: str | None = None):
    """Open a panel with optional title. Pair with panel_close()."""
    head = f'<div class="rtd-panel-title">{title}</div>' if title else ''
    st.markdown(f'<div class="rtd-panel">{head}', unsafe_allow_html=True)


def panel_close():
    st.markdown('</div>', unsafe_allow_html=True)
