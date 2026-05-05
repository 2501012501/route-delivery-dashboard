"""Refresh buttons + cloud publish + public-link sharing. Refresh hidden on cloud."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

# Public Streamlit Cloud deployment — anyone with this URL can view the
# dashboard from any browser (read-only view, no VPN required).
PUBLIC_URL = "https://route-delivery-dashboard.streamlit.app"

# Business timezone — used to display all timestamps consistently regardless
# of where the server runs (Cloud is UTC, local Windows is Central). Chosen
# as the Falcon Farms operations timezone.
BUSINESS_TZ = "America/Chicago"

# Data files that count as "the data" — newest mtime across these is shown
# as the last-refresh timestamp.
_DATA_PATHS = [
    Path("Route To Delivery Data") / "inventory.parquet",
    Path("Route To Delivery Data") / "delivery.parquet",
    Path("Route To Delivery Data") / "visits.parquet",
    Path("data") / "deliveries.parquet",
]

# Sync marker written by RouteToDelivery.py at end of run. Travels with the
# parquets through git so Cloud sees the same value as local.
SYNC_MARKER_PATH = Path("Route To Delivery Data") / "last_synced.txt"


def _file_mtime_epoch():
    """Newest filesystem mtime across data files. On Cloud this reflects the
    last deploy, not the data content — use _data_freshness_epoch() instead
    for an indicator that's consistent between local and Cloud.
    """
    mtimes = [p.stat().st_mtime for p in _DATA_PATHS if p.exists()]
    return max(mtimes) if mtimes else None


def _last_synced_epoch() -> float | None:
    """Read the sync marker written by RouteToDelivery.py at end of its run.
    Returns epoch seconds, or None if the marker is missing/unreadable.
    Same value on local and Cloud since the file is committed to git.
    """
    try:
        if not SYNC_MARKER_PATH.exists():
            return None
        text = SYNC_MARKER_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return None
        # Strip the trailing 'Z' (UTC) and parse as naive UTC.
        if text.endswith("Z"):
            text = text[:-1]
        return pd.Timestamp(text).tz_localize('UTC').timestamp()
    except Exception:
        return None


def _data_freshness_epoch(*, vis=None) -> float | None:
    """Newest record timestamp inside the loaded data, as epoch seconds.

    Prefers `Sys_LastChange` — Retex's row-level last-modified timestamp,
    which advances as the day's activity flows in (within minutes of real
    time). Falls back to `Visit_DateTime` (= First_Realization) for
    parquets written before Sys_LastChange was added to the keep list,
    or to file mtime as last resort.
    """
    if vis is None or vis.empty:
        return _file_mtime_epoch()

    if 'Sys_LastChange' in vis.columns:
        m = vis['Sys_LastChange'].max()
        if pd.notna(m):
            # Naive UTC (parsed with utc=True then tz_localize(None))
            return m.tz_localize('UTC').timestamp()

    if 'Visit_DateTime' in vis.columns:
        m = vis['Visit_DateTime'].max()
        if pd.notna(m):
            return m.tz_localize('UTC').timestamp()

    return _file_mtime_epoch()


# Back-compat aliases
_last_data_refresh_epoch = _file_mtime_epoch


def _last_data_refresh():
    """File mtime as naive pd.Timestamp in BUSINESS_TZ — kept for the local
    'when did I last click refresh' caption."""
    epoch = _file_mtime_epoch()
    if epoch is None:
        return None
    return (pd.Timestamp(epoch, unit='s', tz='UTC')
              .tz_convert(BUSINESS_TZ)
              .tz_localize(None))


def _data_freshness_ts(*, vis=None):
    """Latest in-data timestamp as a naive pd.Timestamp in BUSINESS_TZ."""
    epoch = _data_freshness_epoch(vis=vis)
    if epoch is None:
        return None
    return (pd.Timestamp(epoch, unit='s', tz='UTC')
              .tz_convert(BUSINESS_TZ)
              .tz_localize(None))


def _format_ago(epoch: float) -> str:
    """Returns 'just now' / 'N min ago' / 'N h ago' / 'N d ago' from epoch seconds."""
    mins = int((time.time() - epoch) // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 60 * 24:
        return f"{mins // 60} h ago"
    return f"{mins // (60 * 24)} d ago"


def _to_business_tz(ts):
    """Convert a naive UTC timestamp into a naive timestamp in BUSINESS_TZ.
    Returns the input unchanged if it's None/NaT.
    """
    if ts is None or pd.isna(ts):
        return ts
    return ts.tz_localize('UTC').tz_convert(BUSINESS_TZ).tz_localize(None)


def is_cloud() -> bool:
    """True when running on Streamlit Community Cloud (no VPN, no on-prem SQL)."""
    return ('/mount/src/' in os.getcwd()) or bool(os.environ.get('STREAMLIT_RUNTIME'))


def _log(msg: str):
    """Append a line to logs/auto-refresh.log so we have evidence of what
    happened even if the Streamlit UI cleared the message on rerun."""
    log_path = Path(__file__).parent.parent / "logs" / "auto-refresh.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass  # logging must never break the app


def _stash_publish_status(kind: str, msg: str):
    """Persist the publish outcome across st.rerun() via session_state."""
    st.session_state['_rtd_publish_status'] = {'kind': kind, 'msg': msg}


def render_publish_status():
    """Display the persisted publish status (if any) and clear it. Call this
    inside render_refresh_section so the user sees feedback that survives reruns.
    """
    s = st.session_state.pop('_rtd_publish_status', None)
    if not s:
        return
    if s['kind'] == 'success':
        st.success(s['msg'])
    elif s['kind'] == 'info':
        st.info(s['msg'])
    else:
        st.error(s['msg'])


def _publish_to_cloud() -> bool:
    """Stage data files, commit, push to GitHub so Streamlit Cloud redeploys.
    Persists the outcome to session_state so the user sees it after st.rerun().
    """
    project_dir = Path(__file__).parent.parent
    with st.spinner("Publishing to cloud..."):
        r = subprocess.run(
            ["git", "add", "data", "Route To Delivery Data"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if r.returncode != 0:
            err = f"git add failed:\n{r.stderr or r.stdout}"
            _log("ERROR: " + err.replace("\n", " | "))
            _stash_publish_status('error', err)
            return False

        ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
        r = subprocess.run(
            ["git", "commit", "-m", f"Auto: data update {ts}"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if r.returncode != 0:
            combined = (r.stdout + r.stderr).lower()
            if "nothing to commit" in combined or "nothing added" in combined:
                _log("INFO: no data changes to publish")
                _stash_publish_status('info', "ℹ️ No data changes to publish.")
                return True
            err = f"git commit failed:\n{r.stderr or r.stdout}"
            _log("ERROR: " + err.replace("\n", " | "))
            _stash_publish_status('error', err)
            return False

        r = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if r.returncode != 0:
            err = f"git push failed:\n{r.stderr or r.stdout}"
            _log("ERROR: " + err.replace("\n", " | "))
            _stash_publish_status('error', err)
            return False

    _log(f"OK: published Auto: data update {ts}")
    _stash_publish_status('success', "☁️ Published to cloud — Streamlit will update in ~1 min")
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


def render_refresh_section(last_visit, *, vis=None):
    """Render the entire Data section as a SINGLE collapsible row in the sidebar.

    Collapsed label: '📡 Data · Updated N min ago'
    Expanded body:   data timestamps + refresh controls + public link.

    `vis` is the visits dataframe — used to compute the data-content freshness
    indicator that's consistent between local and Cloud.
    """
    epoch_sync  = _last_synced_epoch()       # when we pulled from Retex API
    epoch_data  = _data_freshness_epoch(vis=vis)  # latest visit recorded in data

    # If a recent publish errored, surface it OUTSIDE the expander so the
    # user notices without having to open the Data section.
    pending = st.session_state.get('_rtd_publish_status')
    if pending and pending['kind'] == 'error':
        st.error(f"⚠️ Auto-publish failed:\n{pending['msg']}")

    # The collapsed label leads with "Last activity" (Sys_LastChange) — that's
    # the freshness signal the user watches throughout the day. Sync time is
    # shown second as a "is our pipeline alive" indicator.
    if epoch_data is not None:
        label = f"📡 Data · Last activity {_format_ago(epoch_data)}"
    elif epoch_sync is not None:
        label = f"📡 Data · Synced {_format_ago(epoch_sync)}"
    else:
        label = "📡 Data"
    if pending and pending['kind'] == 'error':
        label = "📡 Data · ⚠️ publish failed"

    with st.expander(label, expanded=False):
        # Show any non-error publish status (success / info) that survived the rerun
        render_publish_status()

        # Last activity (Sys_LastChange) shown first — it's what the user
        # watches. Sync time second as the "pipeline healthy?" check.
        if epoch_data is not None:
            ts = (pd.Timestamp(epoch_data, unit='s', tz='UTC')
                    .tz_convert(BUSINESS_TZ)
                    .tz_localize(None))
            st.caption(f"📍 **Last activity:** {ts.strftime('%Y-%m-%d %H:%M')} · _{_format_ago(epoch_data)}_")

        if epoch_sync is not None:
            ts = (pd.Timestamp(epoch_sync, unit='s', tz='UTC')
                    .tz_convert(BUSINESS_TZ)
                    .tz_localize(None))
            st.caption(f"☁️ **Synced:** {ts.strftime('%Y-%m-%d %H:%M')} · _{_format_ago(epoch_sync)}_")

        if is_cloud():
            st.caption("🌐 **Read-only view** — refresh disabled in cloud. "
                       "Data updated when the owner pushes new files.")
            st.caption("Public link:")
            st.code(PUBLIC_URL, language=None)
            return

        st.markdown("**Refresh data**")
        auto_publish = st.checkbox(
            "☁️ Auto-publish to cloud after refresh", value=True,
            help="After refreshing, push data to GitHub so the Streamlit Cloud "
                 "link updates automatically for everyone.",
        )

        rb1, rb2, rb3 = st.columns(3)
        if rb1.button("API", use_container_width=True,
                      help="Re-download inventory/delivery/visits from Retex (~1-2 min)"):
            _run_script(["RouteToDelivery.py"], "API", publish=auto_publish)
        if rb2.button("Masters", use_container_width=True,
                      help="Re-download Route Master from SharePoint"):
            _run_script(["extract.py", "--route-master"], "Route Master", publish=auto_publish)
        if rb3.button("Sent", use_container_width=True,
                      help="Re-download deliveries from on-prem SQL and run Transform.py"):
            _run_chain([
                (["extract.py", "--deliveries"], "Deliveries SQL"),
                (["Transform.py"],               "Transform"),
            ], publish=auto_publish)

        st.markdown("**🌐 Public link**")
        st.caption("Send this link to your team — works from any browser, no VPN needed:")
        st.code(PUBLIC_URL, language=None)
