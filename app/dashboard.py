"""
ORBITWATCH – app/dashboard.py
Phase 9: Operational Space Domain Awareness & Atmospheric Drag Dashboard.

Reads dimensional warehouse tables in PostgreSQL schema "dw"
using read-only "dashboard_user" credentials from settings.

Components:
  1. Summary KPI metrics (Satellites, GP snapshots, Solar history, Decays, Connected role)
  2. Orbit regime distribution (Visual bar breakdown)
  3. Space Weather vs. Orbital Decay (Dual-axis time series chart, Pearson correlation r, causation caveat)
  4. Latest GP snapshot summary by regime (Table with motion, eccentricity, inclination)
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from orbitwatch.common.db import get_postgres_engine

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ORBITWATCH | Space Domain & Drag Intelligence",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for Rich Aesthetics & Dark Theme ──────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .metric-card {
        background: rgba(22, 27, 34, 0.75);
        border: 1px solid rgba(56, 139, 253, 0.25);
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    }
    .metric-val {
        font-size: 2.1rem;
        font-weight: 700;
        color: #58a6ff;
        margin: 4px 0;
    }
    .metric-lbl {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #8b949e;
    }
    .auth-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 12px;
        background-color: rgba(46, 160, 67, 0.15);
        border: 1px solid #2ea043;
        color: #3fb950;
        font-size: 0.82rem;
        font-weight: 600;
    }
    .caveat-box {
        padding: 12px 18px;
        background: rgba(210, 153, 34, 0.12);
        border-left: 4px solid #d29922;
        border-radius: 4px;
        font-size: 0.9rem;
        color: #e3b341;
        margin: 15px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_db_engine():
    """Obtain SQLAlchemy engine using read-only dashboard role."""
    return get_postgres_engine("dashboard")


def load_data():
    """Query dimensional warehouse tables as dashboard_user."""
    engine = get_db_engine()
    with engine.connect() as conn:
        # Verify authenticated session user
        user_row = conn.execute(text("SELECT current_user, session_user")).fetchone()
        connected_user = user_row[0] if user_row else "unknown"

        # Summary KPIs
        summary_query = text("""
            SELECT 
                (SELECT COUNT(*) FROM dw.dim_satellite) AS total_satellites,
                (SELECT COUNT(*) FROM dw.fact_gp_snapshot) AS total_snapshots,
                (SELECT COUNT(*) FROM dw.fact_space_weather_month) AS total_weather_months,
                (SELECT SUM(decay_count) FROM dw.fact_decay_month) AS total_decays
        """)
        summary_df = pd.read_sql(summary_query, conn)

        # Orbit regime distribution
        regime_query = text("""
            SELECT 
                COALESCE(r.regime_code, 'UNKNOWN') AS regime_code,
                COALESCE(r.regime_name, 'Unknown Regime') AS regime_name,
                COUNT(*) AS satellite_count
            FROM dw.dim_satellite s
            LEFT JOIN dw.dim_orbit_regime r ON s.orbit_regime_id = r.regime_id
            GROUP BY r.regime_code, r.regime_name
            ORDER BY satellite_count DESC
        """)
        regime_df = pd.read_sql(regime_query, conn)

        # Weather vs Decay monthly series
        weather_decay_query = text("""
            SELECT 
                d.calendar_date,
                w.date_key,
                d.year,
                d.month,
                w.f107 AS f107_solar_flux,
                w.ssn AS sunspot_number,
                m.total_decays
            FROM dw.fact_space_weather_month w
            JOIN dw.dim_date d ON w.date_key = d.date_key
            INNER JOIN (
                SELECT date_key, SUM(decay_count) AS total_decays
                FROM dw.fact_decay_month
                GROUP BY date_key
            ) m ON w.date_key = m.date_key
            ORDER BY w.date_key ASC
        """)
        series_df = pd.read_sql(weather_decay_query, conn)
        series_df["calendar_date"] = pd.to_datetime(series_df["calendar_date"])

        # Latest GP snapshots by regime
        gp_regime_query = text("""
            SELECT 
                COALESCE(r.regime_code, 'UNKNOWN') AS regime_code,
                COALESCE(r.regime_name, 'Unknown Regime') AS regime_name,
                COUNT(*) AS snapshot_count,
                ROUND(AVG(f.mean_motion)::numeric, 4) AS avg_mean_motion,
                ROUND(AVG(f.eccentricity)::numeric, 5) AS avg_eccentricity,
                ROUND(AVG(f.inclination)::numeric, 3) AS avg_inclination
            FROM dw.fact_gp_snapshot f
            LEFT JOIN dw.dim_orbit_regime r ON f.orbit_regime_id = r.regime_id
            GROUP BY r.regime_code, r.regime_name
            ORDER BY snapshot_count DESC
        """)
        gp_regime_df = pd.read_sql(gp_regime_query, conn)

    return connected_user, summary_df.iloc[0], regime_df, series_df, gp_regime_df


def main():
    # ── Header ───────────────────────────────────────────────────────────────
    col_title, col_auth = st.columns([3, 1])
    with col_title:
        st.title("🛰️ ORBITWATCH Operational Intelligence")
        st.caption("Phase 9: Space Domain Awareness, Atmospheric Drag, and Solar Weather Telemetry")
    
    connected_user, summary, regime_df, series_df, gp_regime_df = load_data()
    
    with col_auth:
        st.markdown("<div style='text-align: right; margin-top: 15px;'>", unsafe_allow_html=True)
        st.markdown(
            f"<span class='auth-badge'>🔒 Role: <strong>{connected_user}</strong></span>",
            unsafe_allow_html=True,
        )
        st.caption("dw Schema (SELECT Granted)")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Summary Metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""<div class='metric-card'>
                <div class='metric-lbl'>Catalogued Satellites</div>
                <div class='metric-val'>{int(summary['total_satellites']):,}</div>
                <div style='font-size:0.8rem; color:#8b949e;'>dim_satellite</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""<div class='metric-card'>
                <div class='metric-lbl'>Active GP Snapshots</div>
                <div class='metric-val'>{int(summary['total_snapshots']):,}</div>
                <div style='font-size:0.8rem; color:#8b949e;'>fact_gp_snapshot</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""<div class='metric-card'>
                <div class='metric-lbl'>Solar History Months</div>
                <div class='metric-val'>{int(summary['total_weather_months']):,}</div>
                <div style='font-size:0.8rem; color:#8b949e;'>fact_space_weather_month</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"""<div class='metric-card'>
                <div class='metric-lbl'>Atmospheric Decays</div>
                <div class='metric-val'>{int(summary['total_decays']):,}</div>
                <div style='font-size:0.8rem; color:#8b949e;'>fact_decay_month</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section: Orbit Regime Distribution ────────────────────────────────────
    st.subheader("🌐 Orbit Regime Distribution")
    col_reg_chart, col_reg_tbl = st.columns([2, 1])

    with col_reg_chart:
        fig_bar, ax_bar = plt.subplots(figsize=(8, 3.2), facecolor="#0d1117")
        ax_bar.set_facecolor("#0d1117")
        bars = ax_bar.bar(
            regime_df["regime_code"],
            regime_df["satellite_count"],
            color=["#58a6ff", "#3fb950", "#d29922", "#f85149", "#8b949e"],
            edgecolor="#30363d",
            width=0.55,
        )
        ax_bar.set_ylabel("Satellite Count", color="#8b949e", fontsize=10)
        ax_bar.tick_params(colors="#c9d1d9", labelsize=9)
        ax_bar.grid(axis="y", linestyle="--", alpha=0.25, color="#8b949e")
        for bar in bars:
            height = bar.get_height()
            ax_bar.annotate(
                f"{int(height):,}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                color="#f0f6fc",
                fontsize=8.5,
                fontweight="bold",
            )
        for spine in ax_bar.spines.values():
            spine.set_color("#30363d")
        st.pyplot(fig_bar)
        plt.close(fig_bar)

    with col_reg_tbl:
        regime_display = regime_df.rename(
            columns={
                "regime_code": "Code",
                "regime_name": "Regime",
                "satellite_count": "Satellites",
            }
        )
        st.dataframe(regime_display, hide_index=True, width="stretch")

    st.markdown("---")

    # ── Section: Solar Activity vs Atmospheric Decays (Dual Axis) ─────────────
    st.subheader("☀️ Solar Radio Flux (F10.7) vs. Monthly Satellite Decays")

    # Calculate Pearson correlation coefficient
    corr_coef = series_df["f107_solar_flux"].corr(series_df["total_decays"])

    col_stat1, col_stat2 = st.columns([1, 3])
    with col_stat1:
        st.metric(
            label="Pearson Correlation (r)",
            value=f"{corr_coef:.4f}",
            delta="Strong Positive" if corr_coef > 0.5 else "Moderate",
        )
    with col_stat2:
        st.markdown(
            """<div class='caveat-box'>
            <strong>Caveat:</strong> Correlation does not imply causation — solar activity increases upper-atmosphere density 
            causing orbital decay drag, but launch volume, mega-constellation deployments, and tracking coverage also modulate decay rates.
            </div>""",
            unsafe_allow_html=True,
        )

    # Dual-axis line plot
    fig_dual, ax1 = plt.subplots(figsize=(12, 4.2), facecolor="#0d1117")
    ax1.set_facecolor("#0d1117")

    # Primary axis: Solar Flux F10.7
    line1 = ax1.plot(
        series_df["calendar_date"],
        series_df["f107_solar_flux"],
        color="#e3b341",
        linewidth=1.8,
        label="F10.7 Solar Flux (sfu)",
    )
    ax1.set_xlabel("Year", color="#8b949e", fontsize=10)
    ax1.set_ylabel("F10.7 Solar Radio Flux (sfu)", color="#e3b341", fontsize=10)
    ax1.tick_params(axis="y", labelcolor="#e3b341", colors="#c9d1d9")
    ax1.tick_params(axis="x", colors="#c9d1d9")
    ax1.grid(True, linestyle=":", alpha=0.25, color="#8b949e")

    # Secondary axis: Monthly Decays
    ax2 = ax1.twinx()
    line2 = ax2.plot(
        series_df["calendar_date"],
        series_df["total_decays"],
        color="#58a6ff",
        linewidth=1.6,
        alpha=0.85,
        label="Monthly Decays",
    )
    ax2.set_ylabel("Atmospheric Re-entries / Decays", color="#58a6ff", fontsize=10)
    ax2.tick_params(axis="y", labelcolor="#58a6ff", colors="#c9d1d9")

    # Unified Legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", facecolor="#161b22", edgecolor="#30363d", labelcolor="#c9d1d9")

    for spine in ax1.spines.values():
        spine.set_color("#30363d")
    for spine in ax2.spines.values():
        spine.set_color("#30363d")

    st.pyplot(fig_dual)
    plt.close(fig_dual)

    st.markdown("---")

    # ── Section: Latest GP Snapshot Counts by Regime ──────────────────────────
    st.subheader("📡 Latest GP Snapshot Metrics by Orbit Regime")
    st.caption("Aggregated from dw.fact_gp_snapshot with orbital mechanics metrics")

    gp_display = gp_regime_df.rename(
        columns={
            "regime_code": "Regime Code",
            "regime_name": "Regime Name",
            "snapshot_count": "Active Snapshots",
            "avg_mean_motion": "Avg Mean Motion (rev/day)",
            "avg_eccentricity": "Avg Eccentricity",
            "avg_inclination": "Avg Inclination (°)",
        }
    )
    st.dataframe(
        gp_display,
        hide_index=True,
        width="stretch",
    )


if __name__ == "__main__":
    main()
