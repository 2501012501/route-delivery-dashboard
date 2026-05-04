"""Refresh buttons + cloud publish + public-link sharing. Refresh hidden on cloud."""
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Public Streamlit Cloud deployment — anyone with this URL can view the
# dashboard from any browser (read-only view, no VPN required).
PUBLIC_URL = "https://route-delivery-dashboard.streamlit.app"

# Data files that count as "the data" — newest mtime across these is shown
# as the last-refresh timestamp.
_DATA_PATHS = [
    Path("Route To Delivery Data") / "inventory.parquet",
    Path("Route To Delivery Data") / "delivery.parquet",
    Path("Route To Delivery Data") / "visits.parquet",
    Path("data") / "deliveries.parquet",
]


def _last_data_refresh():
    """Newest mtime across the parquet data files, as a pd.Timestamp (or None)."""
    mtimes = [p.stat().st_mtime for p in _DATA_PATHS if p.exists()]
    if not mtimes:
        return None
    return pd.Timestamp.fromtimestamp(max(mtimes))


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
    last_refresh = _last_data_refresh()
    if last_refresh is not None:
        delta = pd.Timestamp.now() - last_refresh
        mins = int(delta.total_seconds() // 60)
        if mins < 60:
            ago = f"{mins} min ago"
        elif mins < 60 * 24:
            ago = f"{mins // 60} h ago"
        else:
            ago = f"{mins // (60 * 24)} d ago"
        st.caption(f"Last refresh: **{last_refresh.strftime('%Y-%m-%d %H:%M')}** · _{ago}_")
    if pd.notna(last_visit):
        st.caption(f"Last visit in data: **{last_visit.strftime('%Y-%m-%d %H:%M')}**")
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

    with st.expander("🌐 Public link"):
        st.caption("Send this link to your team — works from any browser, no VPN needed:")
        st.code(PUBLIC_URL, language=None)
        st.caption(
            "ℹ️ The cloud version updates automatically when Auto-publish is on "
            "and you click any of the refresh buttons above."
        )
