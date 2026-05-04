"""Visual tokens and HTML helpers for the redesigned dashboard.

All HTML uses st.markdown(..., unsafe_allow_html=True). The CSS injection
happens once per session via inject_css(); pages call the helpers
(kpi, pill, panel, eyebrow_title) to render consistent UI.
"""
import streamlit as st

# Palette (McKinsey blue)
NAVY      = "#051C2C"
BLUE      = "#2251FF"
PALE_BLUE = "#EDF2FE"
SLATE     = "#64748B"
PAGE_BG   = "#FAFBFC"
SURFACE   = "#FFFFFF"
BORDER    = "#E5E7EB"
AMBER_BG  = "#FEF3C7"
AMBER_FG  = "#92400E"
GRAY_BG   = "#F1F5F9"


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
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  .rtd-pill.ok    {{ background: {PALE_BLUE}; color: {BLUE}; }}
  .rtd-pill.warn  {{ background: {AMBER_BG}; color: {AMBER_FG}; }}
  .rtd-pill.pend  {{ background: {GRAY_BG}; color: {SLATE}; }}

  /* ── Sidebar headers uniform (UPPERCASE small caps style) ── */
  section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3 {{
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-size: 12px;
    font-weight: 700;
    color: {NAVY};
    margin-top: 8px;
  }}
  /* Sidebar widget labels (Date, Cluster, Customer, ...) uppercase too */
  section[data-testid="stSidebar"] label p {{
    text-transform: uppercase;
    letter-spacing: 0.6px;
    font-size: 10px;
    font-weight: 600;
    color: {SLATE};
  }}
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
    """Returns inline HTML for a status pill. kind in {'ok','warn','pend'}."""
    return f'<span class="rtd-pill {kind}">{text}</span>'


def panel_open(title: str | None = None):
    """Open a panel with optional title. Pair with panel_close()."""
    head = f'<div class="rtd-panel-title">{title}</div>' if title else ''
    st.markdown(f'<div class="rtd-panel">{head}', unsafe_allow_html=True)


def panel_close():
    st.markdown('</div>', unsafe_allow_html=True)
