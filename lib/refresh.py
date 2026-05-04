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
