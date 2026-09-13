"""
Sentinel Omega — Command Dashboard
Precursor detection platform for natural events.
Launch: streamlit run sentinel_omega/infrastructure/dashboard/app.py
"""

import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Ensure workspace root is importable (like launcher.py) - fixes ModuleNotFoundError
import sys
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from sentinel_omega.config.sentinel_config import SentinelOmegaConfig
from sentinel_omega.core.snt_engine.satellization import SatellizationEngine, DominanceRegime
from sentinel_omega.core.snt_engine.friction import InstitutionalFrictionCalculator, FrictionLevel
from sentinel_omega.core.snt_engine.asi import AtomicSovereigntyIndex
from sentinel_omega.core.snt_engine.nbody import NBodyMatrix
from sentinel_omega.core.shared.agent_base import SignalType
from sentinel_omega.core.precursor.risk_calculator import (
    PrecursorRisk,
    classify_risk,
    RISK_THRESHOLDS,
)
from sentinel_omega.core.precursor.precursor_types import (
    PrecursorType,
    PRECURSOR_DISPLAY_NAMES,
)
from sentinel_omega.core.precursor.muro_cinco_eventos import (
    WALL_GEOFISICO,
    WALL_ATMOSFERICO,
    WALL_OCEANICO,
    WALL_SOLAR,
    WALL_FINANCIERO,
    WALL_MEMBERS,
)
from sentinel_omega.infrastructure.database.schema import get_connection
from sentinel_omega.infrastructure.database.repository import SentinelRepository
try:
    from sentinel_omega.infrastructure.dashboard.agent_tab import render_agent_tab
    HAS_AGENT_TAB = True
except Exception:
    HAS_AGENT_TAB = False
    def render_agent_tab():
        st.error("agent_tab no disponible")
from sentinel_omega.infrastructure.database.seed_nodos import SEED_NODOS

# ── Page Config ──────────────────────────────────────────────────────


# ── Linear Theme (popular-web-designs/linear.app) ────────────────────
LINEAR_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#08090a;--panel:#0f1011;--card:#191a1b;--text:#f7f8f8;--muted:#8a8f98;--border:rgba(255,255,255,0.08);--accent:#5e6ad2;--acc2:#7170ff}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg) !important}
[data-testid="stHeader"]{background:rgba(8,9,10,0.85) !important;backdrop-filter:blur(10px);border-bottom:1px solid rgba(255,255,255,0.05)}
[data-testid="stSidebar"]{background:var(--panel) !important;border-right:1px solid rgba(255,255,255,0.05)}
h1,h2,h3{font-family:Inter,sans-serif !important;letter-spacing:-0.02em}
.mono{font-family:JetBrains Mono,monospace}
div[data-testid="stMetric"]{background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:8px;padding:12px}
div[data-testid="stTabs"] button{font-family:Inter,sans-serif !important;font-weight:500 !important}
div[data-testid="stTabs"] button[aria-selected="true"]{color:var(--text) !important;background:rgba(255,255,255,0.05) !important}
</style>
"""
st.set_page_config(
    page_title="Sentinel Omega",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(LINEAR_CSS, unsafe_allow_html=True)

SIGNAL_COLORS = {
    "BULLISH": "#00c853",
    "bullish": "#00c853",
    "BEARISH": "#ff1744",
    "bearish": "#ff1744",
    "NEUTRAL": "#ffc107",
    "neutral": "#ffc107",
    "WATCH": "#ff9100",
    "watch": "#ff9100",
    "ALERT": "#d500f9",
    "alert": "#d500f9",
    "NO_SIGNAL": "#757575",
    "no_signal": "#757575",
}

RISK_COLORS = {
    "LOW": "#00c853",
    "MODERATE": "#ffc107",
    "HIGH": "#ff9100",
    "CRITICAL": "#ff1744",
}

WALL_ICONS = {
    WALL_GEOFISICO: "🌋",
    WALL_ATMOSFERICO: "🌩️",
    WALL_OCEANICO: "🌊",
    WALL_SOLAR: "☀️",
    WALL_FINANCIERO: "📊",
}

REGIME_COLORS = {
    DominanceRegime.CONVERGENCE: "#00c853",
    DominanceRegime.EQUILIBRIUM: "#ffc107",
    DominanceRegime.SATELLIZATION_GRADUAL: "#ffab40",
    DominanceRegime.SATELLIZATION_ACTIVE: "#ff9100",
    DominanceRegime.ROCHE_RADIUS: "#ff1744",
    DominanceRegime.EXTREME: "#d50000",
    DominanceRegime.LEAPFROG: "#2979ff",
}

# ── Session State ────────────────────────────────────────────────────

if "config" not in st.session_state:
    st.session_state.config = SentinelOmegaConfig()
if "snt" not in st.session_state:
    st.session_state.snt = SatellizationEngine()
if "friction_calc" not in st.session_state:
    st.session_state.friction_calc = InstitutionalFrictionCalculator()
if "asi_calc" not in st.session_state:
    st.session_state.asi_calc = AtomicSovereigntyIndex()
if "nbody" not in st.session_state:
    st.session_state.nbody = NBodyMatrix()
if "repo" not in st.session_state:
    st.session_state.repo = SentinelRepository()


def get_repo() -> SentinelRepository:
    return st.session_state.repo


# ── Sidebar ──────────────────────────────────────────────────────────

def render_sidebar():
    cfg = st.session_state.config
    st.sidebar.title("⚡ Sentinel Omega")
    st.sidebar.caption(f"v{cfg.version} — Precursor Detection Platform")
    st.sidebar.caption(f"{cfg.author}")
    st.sidebar.divider()

    st.sidebar.subheader("Active Layers")
    active = {k: v for k, v in cfg.layers.items() if v.enabled}
    for name, layer_cfg in active.items():
        emoji = {"geodynamic": "🌍"}.get(name, "⚡")
        st.sidebar.markdown(f"{emoji} **{name.upper()}** — {layer_cfg.refresh_interval_s}s")

    st.sidebar.divider()
    st.sidebar.subheader("Location")
    st.sidebar.markdown(f"📍 {cfg.coordinates.get('location', 'Unknown')}")
    st.sidebar.markdown(f"Lat: {cfg.coordinates.get('lat')}, Lon: {cfg.coordinates.get('lon')}")

    st.sidebar.divider()
    st.sidebar.subheader("SNT Parameters")
    st.sidebar.markdown(f"**Roche**: b ≥ {cfg.snt.roche_threshold}")
    st.sidebar.markdown(f"**Equilibrium**: ±{cfg.snt.equilibrium_band}")

    return list(active.keys())


# ══════════════════════════════════════════════════════════════════════
# TAB 1: Precursor Risk (Fantasma)
# ══════════════════════════════════════════════════════════════════════

def render_precursor_risk():
    st.subheader("Índice Fantasma — TITAN V32 Precursor Risk")

    repo = get_repo()
    records = repo.get_precursores_cosmicos(limit=50)

    if not records:
        st.info("No hay datos de precursores cósmicos registrados. Ejecuta un ciclo del orquestador para alimentar la DB.")
        _render_fantasma_demo()
        return

    latest = records[0]
    fantasma = latest["fantasma"]
    risk_level = latest["nivel_riesgo"]
    risk_color = RISK_COLORS.get(risk_level, "#757575")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fantasma Index", f"{fantasma:.2f}")
    col2.metric("Risk Level", risk_level)
    col3.metric("Schumann", f"{latest['schumann_hz']:.2f} Hz")
    col4.metric("Kp", f"{latest['kp']:.1f}")

    c1, c2 = st.columns([2, 1])

    with c1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=fantasma,
            title={"text": "Fantasma Risk Index"},
            gauge={
                "axis": {"range": [0, 50], "tickwidth": 1},
                "bar": {"color": risk_color},
                "steps": [
                    {"range": [0, 5], "color": "#e8f5e9"},
                    {"range": [5, 15], "color": "#fff9c4"},
                    {"range": [15, 30], "color": "#ffe0b2"},
                    {"range": [30, 50], "color": "#ffcdd2"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 4},
                    "thickness": 0.75,
                    "value": 30,
                },
            },
        ))
        fig.update_layout(height=300, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("**Componentes:**")
        st.markdown(f"- **Bz²**: {latest['bz_nT']:.1f} nT")
        st.markdown(f"- **Viento**: {latest['viento_km_s']:.0f} km/s")
        st.markdown(f"- **Schumann**: {latest['schumann_hz']:.2f} Hz ({latest['schumann_activity']:.0f}%)")
        st.markdown(f"- **Presión**: {latest['presion_hpa']:.0f} hPa")
        st.markdown(f"- **LOD**: {latest['lod_ms']:.2f} ms")
        st.markdown(f"- **Fase Lunar**: {latest['fase_lunar']:.2f}")
        st.markdown(f"- **Protones**: {latest['protones']:.1f}")

    if len(records) > 1:
        st.markdown("---")
        st.markdown("**Historial Fantasma (últimos 50 ciclos)**")
        df = pd.DataFrame(records)
        df["time"] = pd.to_datetime(df["timestamp"], unit="s")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["time"], y=df["fantasma"],
            mode="lines+markers", name="Fantasma",
            line=dict(color="#d500f9"),
        ))
        fig.add_hline(y=5, line_dash="dot", line_color="#ffc107", annotation_text="MODERATE")
        fig.add_hline(y=15, line_dash="dot", line_color="#ff9100", annotation_text="HIGH")
        fig.add_hline(y=30, line_dash="dash", line_color="#ff1744", annotation_text="CRITICAL")
        fig.update_layout(
            yaxis_title="Fantasma Index",
            height=300, template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    _render_fantasma_waterfall(repo)
    _render_risk_distribution(repo)


def _render_fantasma_waterfall(repo: SentinelRepository):
    breakdown = repo.fantasma_component_breakdown(limit=1)
    if not breakdown:
        return

    st.markdown("---")
    st.markdown("**Descomposición del Fantasma (Waterfall)**")

    r = breakdown[0]
    bz_c = abs(r["bz_nT"]) ** 2
    wind_c = r["viento_km_s"] * 0.02
    sch_c = (r["schumann_activity"] / 100.0) * 1.5
    pressure_mod = 0.0
    if r["presion_hpa"] < 1008.0:
        pressure_mod = min(3.0, (1008.0 - r["presion_hpa"]) / 5.0)
    kp_mod_factor = 1.0
    if r["kp"] >= 5.0:
        base = bz_c + wind_c + sch_c + pressure_mod
        kp_mod_factor = 1.0 + (r["kp"] - 5.0) * 0.1
        kp_effect = base * (kp_mod_factor - 1.0)
    else:
        kp_effect = 0.0
    lod_mod = 0.0
    if abs(r["lod_ms"]) > 0.5:
        lod_mod = min(2.0, abs(r["lod_ms"]) * 0.5)

    labels = ["Bz²", "Viento", "Schumann", "Presión", "Kp Storm", "LOD", "Total"]
    values = [bz_c, wind_c, sch_c, pressure_mod, kp_effect, lod_mod, r["fantasma"]]
    measures = ["relative", "relative", "relative", "relative", "relative", "relative", "total"]
    colors = ["#2979ff", "#00c853", "#d500f9", "#ff9100", "#ff1744", "#ffc107", RISK_COLORS.get(r["nivel_riesgo"], "#757575")]

    fig = go.Figure(go.Waterfall(
        x=labels, y=values,
        measure=measures,
        textposition="outside",
        text=[f"{v:.2f}" for v in values],
        connector=dict(line=dict(color="#555")),
        increasing=dict(marker=dict(color="#2979ff")),
        decreasing=dict(marker=dict(color="#ff1744")),
        totals=dict(marker=dict(color=colors[-1])),
    ))
    fig.update_layout(
        title="Contribución de Cada Componente al Fantasma",
        yaxis_title="Puntos",
        height=350, template="plotly_dark",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_risk_distribution(repo: SentinelRepository):
    dist = repo.risk_distribution()
    if not dist:
        return

    st.markdown("---")
    st.markdown("**Distribución de Niveles de Riesgo**")

    levels = ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    values = [dist.get(l, 0) for l in levels]
    colors = [RISK_COLORS.get(l, "#757575") for l in levels]

    fig = go.Figure(go.Pie(
        labels=levels,
        values=values,
        hole=0.5,
        marker=dict(colors=colors),
        textinfo="label+percent+value",
    ))
    fig.update_layout(
        title="Distribución Histórica de Riesgo",
        height=350, template="plotly_dark",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_fantasma_demo():
    st.markdown("**Demo: Composición del Fantasma**")
    rng = np.random.default_rng(int(time.time()) % 1000)
    bz = rng.normal(-3, 5)
    viento = max(0, rng.normal(400, 100))
    sch_wpc = max(0, rng.normal(0.5, 0.3))
    pressure = rng.normal(1010, 8)
    kp = max(0, rng.normal(3, 2))
    lod = rng.normal(0.2, 0.3)

    bz_c = abs(bz) ** 2
    wind_c = viento * 0.02
    sch_c = sch_wpc * 1.5
    fantasma = bz_c + wind_c + sch_c

    pressure_mod = 0.0
    if pressure < 1008:
        pressure_mod = min(3.0, (1008 - pressure) / 5.0)
        fantasma += pressure_mod

    kp_mod = 1.0
    if kp >= 5:
        kp_mod = 1.0 + (kp - 5.0) * 0.1
        fantasma *= kp_mod

    risk = classify_risk(fantasma)
    risk_color = RISK_COLORS.get(risk, "#757575")

    col1, col2 = st.columns([2, 1])
    with col1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=fantasma,
            title={"text": "Fantasma (Demo)"},
            gauge={
                "axis": {"range": [0, 50]},
                "bar": {"color": risk_color},
                "steps": [
                    {"range": [0, 5], "color": "#e8f5e9"},
                    {"range": [5, 15], "color": "#fff9c4"},
                    {"range": [15, 30], "color": "#ffe0b2"},
                    {"range": [30, 50], "color": "#ffcdd2"},
                ],
            },
        ))
        fig.update_layout(height=300, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.metric("Risk Level", risk)
        st.markdown(f"Bz² = `{bz_c:.2f}` (Bz={bz:.1f} nT)")
        st.markdown(f"Wind = `{wind_c:.2f}` ({viento:.0f} km/s)")
        st.markdown(f"Schumann = `{sch_c:.2f}` (WPC={sch_wpc:.2f})")
        st.markdown(f"Pressure mod = `+{pressure_mod:.2f}` ({pressure:.0f} hPa)")
        st.markdown(f"Kp mod = `×{kp_mod:.2f}` (Kp={kp:.1f})")


# ══════════════════════════════════════════════════════════════════════
# TAB 2: Muro de los 5 Eventos
# ══════════════════════════════════════════════════════════════════════

    st.divider()
    st.markdown("**Timeline Fantasma + Alertas (v2.5.3)**")
    try:
        _render_fantasma_timeline_plotly(get_repo())
    except Exception as _e:
        st.caption(f"Timeline no disponible: {_e}")
    if st.button("Vista previa alerta Telegram (ejemplo)", key="preview_alert"):
        try:
            from sentinel_omega.infrastructure.messaging.alert_service import AlertTemplates
            m = AlertTemplates.centinela_advertencia(18.5, -2.1, 520.0)
            st.markdown(m.html, unsafe_allow_html=True)
            st.code(m.plain)
            from sentinel_omega.infrastructure.messaging.charts import fantasma_timeline
            ch = fantasma_timeline([5,8,12,18.5], titulo="Fantasma - preview")
            if ch and ch.exists():
                st.image(str(ch), caption="PNG como se enviaria a Telegram")
        except Exception as _e:
            st.error(str(_e))

def render_muro():
    st.subheader("Muro de los 5 Eventos — Cross-Correlation Engine")

    repo = get_repo()
    breaches = repo.get_muro_breaches(limit=20)
    cycles = repo.get_ciclos(limit=1)

    wall_names = [WALL_GEOFISICO, WALL_ATMOSFERICO, WALL_OCEANICO, WALL_SOLAR, WALL_FINANCIERO]
    wall_fields = ["wall_geofisico", "wall_atmosferico", "wall_oceanico", "wall_solar", "wall_financiero"]

    if cycles:
        latest = cycles[0]
        walls_active = latest["muro_walls_active"]
        is_breach = latest["muro_breach"]
    else:
        walls_active = 0
        is_breach = False

    # Determinar fuente más reciente para sincronizar KPI y visual
    latest_muro = breaches[0] if breaches else None
    use_muro = False
    if latest_muro and cycles:
        use_muro = latest_muro.get("timestamp", 0) > cycles[0].get("timestamp", 0)
    elif latest_muro:
        use_muro = True

    c1, c2, c3 = st.columns(3)
    _kpi_walls = int(latest_muro.get("walls_active", walls_active)) if (use_muro and latest_muro) else walls_active
    c1.metric("Walls Active", f"{_kpi_walls}/5", help="Sincronizado muro↔ciclo")
    c2.metric("Breach", "YES" if is_breach else "NO")
    c3.metric("Historical Breaches", len(breaches))

    st.markdown("---")
    cols = st.columns(5)

    for i, (wall_name, wall_field) in enumerate(zip(wall_names, wall_fields)):
        with cols[i]:
            icon = WALL_ICONS.get(wall_name, "⬜")
            members = WALL_MEMBERS.get(wall_name, set())
            member_names = [PRECURSOR_DISPLAY_NAMES.get(m, m.value) for m in members]

            if use_muro and wall_field in latest_muro:
                active = bool(latest_muro.get(wall_field, 0))
            elif cycles and wall_field in cycles[0]:
                active = bool(cycles[0].get(wall_field, 0))
            elif not use_muro and latest_muro and wall_field in latest_muro:
                active = bool(latest_muro.get(wall_field, 0))
            else:
                active = False

            color = "#00c853" if active else "#616161"
            border = f"3px solid {color}"

            st.markdown(
                f"<div style='padding:16px;border-radius:12px;border:{border};"
                f"text-align:center;background:rgba(0,0,0,0.03)'>"
                f"<h2 style='margin:0'>{icon}</h2>"
                f"<b style='color:{color}'>{wall_name}</b><br>"
                f"<small>{'ACTIVO' if active else 'INACTIVO'}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
            for mn in member_names:
                st.caption(f"• {mn}")

    if breaches:
        st.markdown("---")
        st.markdown("**Historial de Breaches**")
        df = pd.DataFrame(breaches)
        df["time"] = pd.to_datetime(df["timestamp"], unit="s")
        display_cols = ["time", "walls_active", "correlation_score", "risk_label"]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available].head(20), use_container_width=True, hide_index=True)
    else:
        st.info("No se han registrado breaches del Muro. El Muro se activa cuando ≥3 muros están activos simultáneamente.")

    st.markdown("---")
    st.markdown("**Esquema de Correlación**")
    fig = go.Figure()
    categories = [w.split("/")[0] for w in wall_names]
    categories.append(categories[0])

    demo_values = [0.6, 0.3, 0.1, 0.8, 0.4]
    demo_values.append(demo_values[0])

    fig.add_trace(go.Scatterpolar(
        r=demo_values,
        theta=categories,
        fill="toself",
        name="Correlation Score",
        fillcolor="rgba(213,0,249,0.2)",
        line=dict(color="#d500f9"),
    ))
    fig.add_trace(go.Scatterpolar(
        r=[0.6] * 6,
        theta=categories,
        name="Breach Threshold",
        line=dict(color="#ff1744", dash="dash"),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        height=400, template="plotly_dark",
        title="Radar de Correlación Multi-Dominio",
    )
    st.plotly_chart(fig, use_container_width=True)

    _render_wall_activation_timeline(repo)


def _render_wall_activation_timeline(repo: SentinelRepository):
    history = repo.wall_activation_history(limit=100)
    if not history:
        return

    st.markdown("---")
    st.markdown("**Timeline de Activación por Muro**")

    df = pd.DataFrame(history)
    df["time"] = pd.to_datetime(df["timestamp"], unit="s")

    wall_cols = {
        "wall_geofisico": ("GEOFÍSICO", "#ff1744"),
        "wall_atmosferico": ("ATMOSFÉRICO", "#2979ff"),
        "wall_oceanico": ("OCEÁNICO", "#00c853"),
        "wall_solar": ("SOLAR", "#ffc107"),
        "wall_financiero": ("FINANCIERO", "#d500f9"),
    }

    fig = go.Figure()
    for col, (name, color) in wall_cols.items():
        fig.add_trace(go.Scatter(
            x=df["time"], y=df[col],
            mode="lines", name=name,
            line=dict(color=color, width=2),
            stackgroup="walls",
            fillcolor=color.replace(")", ",0.15)").replace("rgb", "rgba") if "rgb" in color else None,
        ))

    fig.add_trace(go.Scatter(
        x=df["time"], y=df["walls_active"],
        mode="lines+markers", name="Total Activos",
        line=dict(color="white", width=2, dash="dot"),
        yaxis="y2",
    ))

    fig.update_layout(
        yaxis=dict(title="Muros Activos (apilados)", range=[0, 5.5]),
        yaxis2=dict(title="Total", overlaying="y", side="right", range=[0, 5.5]),
        height=400, template="plotly_dark",
        title="Evolución Temporal de los 5 Muros",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# TAB 3: Precursor Scanner
# ══════════════════════════════════════════════════════════════════════

def render_scanner():
    st.subheader("Precursor Scanner — Detecciones Activas")

    repo = get_repo()
    detections = repo.get_detecciones(limit=100)

    if not detections:
        st.info("No hay detecciones registradas. Ejecuta un ciclo del orquestador para escanear precursores.")
        _render_precursor_types_reference()
        return

    col1, col2, col3 = st.columns(3)
    high_conf = [d for d in detections if d["confidence"] >= 0.7]
    col1.metric("Total Detecciones", len(detections))
    col2.metric("Alta Confianza (≥70%)", len(high_conf))
    unique_types = set(d["tipo"] for d in detections)
    col3.metric("Tipos Activos", len(unique_types))

    st.markdown("---")

    df = pd.DataFrame(detections)
    df["time"] = pd.to_datetime(df["timestamp"], unit="s")
    df["confidence_pct"] = (df["confidence"] * 100).round(1)

    display_df = df[["time", "tipo", "display_name", "station", "confidence_pct"]].copy()
    display_df.columns = ["Timestamp", "Tipo", "Nombre", "Estación", "Confianza (%)"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        type_counts = df["tipo"].value_counts()
        fig = go.Figure(go.Bar(
            x=type_counts.index,
            y=type_counts.values,
            marker_color="#d500f9",
        ))
        fig.update_layout(
            title="Detecciones por Tipo",
            yaxis_title="Count",
            height=350, template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = go.Figure(go.Histogram(
            x=df["confidence"],
            nbinsx=20,
            marker_color="#2979ff",
        ))
        fig.update_layout(
            title="Distribución de Confianza",
            xaxis_title="Confidence",
            yaxis_title="Count",
            height=350, template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    _render_precursor_confidence_stats(repo)


def _render_precursor_confidence_stats(repo: SentinelRepository):
    stats = repo.precursor_confidence_stats()
    if not stats:
        return

    st.markdown("---")
    st.markdown("**Estadísticas de Confianza por Tipo de Precursor**")

    types = list(stats.keys())
    display_names = []
    for t in types:
        try:
            pt = PrecursorType(t)
            display_names.append(PRECURSOR_DISPLAY_NAMES.get(pt, t))
        except ValueError:
            display_names.append(t)

    avgs = [stats[t]["avg"] for t in types]
    mins = [stats[t]["min"] for t in types]
    maxs = [stats[t]["max"] for t in types]
    counts = [stats[t]["count"] for t in types]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=display_names, y=avgs,
        name="Promedio",
        marker_color="#2979ff",
        error_y=dict(
            type="data",
            symmetric=False,
            array=[m - a for m, a in zip(maxs, avgs)],
            arrayminus=[a - mn for a, mn in zip(avgs, mins)],
            color="#aaa",
        ),
        text=[f"n={c}" for c in counts],
        textposition="outside",
    ))
    fig.update_layout(
        title="Confianza por Tipo (avg con rango min-max)",
        yaxis_title="Confidence",
        yaxis_range=[0, 1.1],
        height=400, template="plotly_dark",
    )
    st.plotly_chart(fig, use_container_width=True)

    freq = repo.precursor_type_frequency()
    if freq:
        st.markdown("**Frecuencia Acumulada de Detecciones**")
        freq_names = []
        for t in freq:
            try:
                pt = PrecursorType(t)
                freq_names.append(PRECURSOR_DISPLAY_NAMES.get(pt, t))
            except ValueError:
                freq_names.append(t)
        fig2 = go.Figure(go.Bar(
            x=list(freq.values()),
            y=freq_names,
            orientation="h",
            marker_color="#d500f9",
        ))
        fig2.update_layout(
            xaxis_title="Detecciones",
            height=max(250, len(freq) * 30),
            template="plotly_dark",
        )
        st.plotly_chart(fig2, use_container_width=True)


def _render_precursor_types_reference():
    st.markdown("**Referencia: 15 Tipos de Precursor**")
    data = []
    for pt in PrecursorType:
        dn = PRECURSOR_DISPLAY_NAMES.get(pt, pt.value)
        wall = "—"
        for wname, members in WALL_MEMBERS.items():
            if pt in members:
                wall = wname
                break
        data.append({"Tipo": pt.value, "Nombre": dn, "Muro": wall})
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════
# TAB 4: Topología 125 Nodos
# ══════════════════════════════════════════════════════════════════════


def render_cimatica():
    st.subheader("Cimatica - Patrones destilados por eventos")
    repo = get_repo()
    stats = repo.cimatica_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total patrones", stats.get("total", 0))
    col2.metric("Consistentes (x3+)", stats.get("consistentes", 0))
    col3.metric("Clases distintas", len(stats.get("por_clase", [])))
    patrones = repo.cimatica_top_patrones(limit=20)
    if not patrones:
        st.info("Sin patrones aun. Correr ciclos y entrenar_cimatica() para poblar.")
        st.markdown("- Cada ciclo toma snapshot en tbl_cimatica_patrones")
        return
    df = pd.DataFrame(patrones)
    df["label"] = df["patron_id"].astype(str) + " (" + df["event_class"].fillna("sin clase") + ")"
    fig = px.bar(df.head(10), x="label", y="frecuencia", color="event_class", title="Top 10 patrones por frecuencia", template="plotly_dark", color_discrete_sequence=px.colors.qualitative.Dark24)
    fig.update_layout(height=350, xaxis_title="Patron", yaxis_title="Frecuencia")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Tabla (20 mas frecuentes)**")
    show = df[["patron_id", "clave", "frecuencia", "event_class", "ambito", "id_nodo", "ultima_vez"]].copy()
    show["clave"] = show["clave"].str.slice(0, 48)
    st.dataframe(show, use_container_width=True, height=320)
    if stats.get("por_clase"):
        dfc = pd.DataFrame(stats["por_clase"])
        dfc["event_class"] = dfc["event_class"].fillna("(sin clase)")
        fig2 = px.pie(dfc, names="event_class", values="n", title="Distribucion por clase", template="plotly_dark")
        fig2.update_layout(height=300)
        st.plotly_chart(fig2, use_container_width=True)
    if st.button("Generar PNG cimatica (como Telegram)"):
        try:
            from sentinel_omega.infrastructure.messaging.charts import cimatica_bars
            ch = cimatica_bars(patrones[:10], titulo="Cimatica - Top 10")
            if ch and ch.exists():
                st.image(str(ch), caption=f"PNG {ch.stat().st_size} bytes")
                st.success(f"PNG: {ch}")
            else:
                st.warning("No PNG")
        except Exception as e:
            st.error(str(e))
def _render_fantasma_timeline_plotly(repo):
    hist = repo.fantasma_timeline(limit=50)
    if not hist:
        st.info("Sin historial fantasma")
        return
    df = pd.DataFrame(hist).sort_values("ts")
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=15, fillcolor="rgba(0,200,0,0.08)", line_width=0)
    fig.add_hrect(y0=15, y1=30, fillcolor="rgba(255,200,0,0.12)", line_width=0)
    fig.add_hrect(y0=30, y1=100, fillcolor="rgba(255,0,0,0.10)", line_width=0)
    fig.add_trace(go.Scatter(x=df["ts"], y=df["fantasma"], mode="lines+markers", line=dict(color="#00d4ff", width=2), marker=dict(size=4), name="Fantasma"))
    fig.add_hline(y=15, line_dash="dash", line_color="orange", annotation_text="AMARILLO 15")
    fig.add_hline(y=30, line_dash="dash", line_color="red", annotation_text="ROJO 30")
    fig.update_layout(height=320, template="plotly_dark", title="Timeline Fantasma (50 ciclos)")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df.tail(10).sort_values("ts", ascending=False), use_container_width=True, height=220)

def render_topology():
    st.subheader("Topología N-Body — 125 Nodos")

    repo = get_repo()
    nodes = repo.get_nodos()

    if not nodes:
        st.info("Nodos no cargados en la DB. Usando datos seed.")
        nodes = SEED_NODOS

    region_filter = st.selectbox(
        "Filtrar por región",
        ["All"] + sorted(set(n.get("region", "—") for n in nodes)),
    )
    filtered_nodes = nodes if region_filter == "All" else [
        n for n in nodes if n.get("region", "—") == region_filter
    ]

    c1, c2, c3 = st.columns(3)
    real = [n for n in filtered_nodes if n.get("tipo") == "real"]
    ghost = [n for n in filtered_nodes if n.get("tipo") == "ghost"]
    geobat = [n for n in filtered_nodes if n.get("tipo") == "geobattery"]
    c1.metric("Real Nodes", len(real))
    c2.metric("Ghost Nodes", len(ghost))
    c3.metric("Geobattery Nodes", len(geobat))

    tipo_colors = {"real": "#00c853", "ghost": "#ff9100", "geobattery": "#2979ff"}
    tipo_sizes = {"real": 10, "ghost": 7, "geobattery": 12}

    fig = go.Figure()

    for tipo in ["real", "ghost", "geobattery"]:
        subset = [n for n in filtered_nodes if n.get("tipo") == tipo]
        if not subset:
            continue
        lats = [n["lat"] for n in subset]
        lons = [n["lon"] for n in subset]
        names = [n.get("nombre", f"Node {n.get('node_id', '?')}") for n in subset]
        cond = [n.get("conductividad", n.get("conductividad_telurica", 0)) for n in subset]

        hover = [
            f"{name}<br>Lat: {lat:.2f}, Lon: {lon:.2f}<br>"
            f"Conductividad: {c:.2f}<br>Region: {n.get('region', '—')}"
            for name, lat, lon, c, n in zip(names, lats, lons, cond, subset)
        ]

        fig.add_trace(go.Scattergeo(
            lat=lats, lon=lons,
            text=hover,
            hoverinfo="text",
            name=tipo.capitalize(),
            marker=dict(
                size=tipo_sizes[tipo],
                color=tipo_colors[tipo],
                opacity=0.8,
                line=dict(width=1, color="white"),
            ),
        ))

    fig.update_geos(
        showland=True, landcolor="#1a1a2e",
        showocean=True, oceancolor="#0d1b2a",
        showcountries=True, countrycolor="#444",
        showcoastlines=True, coastlinecolor="#555",
        projection_type="natural earth",
        center=dict(lat=19, lon=-99),
    )
    fig.update_layout(
        title=(
            "Mapa de Nodos — Ring of Fire + Mexico Focus"
            if region_filter == "All"
            else f"Mapa de Nodos — {region_filter}"
        ),
        height=550,
        template="plotly_dark",
        geo=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("**Detalle de Nodos por Región**")

    table_data = []
    for n in filtered_nodes:
        table_data.append({
            "ID": n.get("node_id", "—"),
            "Nombre": n.get("nombre", "—"),
            "Tipo": n.get("tipo", "—"),
            "Lat": n.get("lat", 0),
            "Lon": n.get("lon", 0),
            "Conductividad": n.get("conductividad", n.get("conductividad_telurica", 0)),
            "Energía": n.get("energia", n.get("energia_acumulada", 0)),
            "Saturación": n.get("saturacion", 0),
            "Región": n.get("region", "—"),
        })
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

    _render_node_saturation(repo, region_filter)


def _render_node_saturation(repo: SentinelRepository, region_filter: str = "All"):
    ranking = repo.node_saturation_ranking(
        limit=25,
        region=None if region_filter == "All" else region_filter,
    )
    if not ranking:
        return

    st.markdown("---")
    st.markdown("**Ranking de Saturación de Nodos**")

    tipo_colors = {"real": "#00c853", "ghost": "#ff9100", "geobattery": "#2979ff"}

    df = pd.DataFrame(ranking)
    colors = [tipo_colors.get(r["tipo"], "#757575") for r in ranking]

    fig = go.Figure(go.Bar(
        x=df["saturacion"],
        y=[f"{r['nombre']} ({r['tipo']})" for r in ranking],
        orientation="h",
        marker_color=colors,
        text=[f"{s:.0%}" for s in df["saturacion"]],
        textposition="outside",
    ))
    fig.add_vline(x=1.0, line_dash="dash", line_color="#ff1744", annotation_text="Saturación Máxima")
    fig.update_layout(
        xaxis_title="Saturación",
        xaxis_range=[0, 1.15],
        height=max(350, len(ranking) * 28),
        template="plotly_dark",
        title=(
            "Top 25 Nodos por Saturación"
            if region_filter == "All"
            else f"Top Nodos por Saturación — {region_filter}"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fig2 = go.Figure(go.Scatter(
            x=df["conductividad"],
            y=df["energia"],
            mode="markers",
            marker=dict(
                size=df["saturacion"] * 30 + 5,
                color=colors,
                opacity=0.8,
                line=dict(width=1, color="white"),
            ),
            text=[f"{r['nombre']}<br>Sat: {r['saturacion']:.0%}" for r in ranking],
            hoverinfo="text",
        ))
        fig2.update_layout(
            title="Conductividad vs Energía",
            xaxis_title="Conductividad Telúrica",
            yaxis_title="Energía Acumulada",
            height=350, template="plotly_dark",
        )
        st.plotly_chart(fig2, use_container_width=True)

    with c2:
        tipo_sat = df.groupby("tipo")["saturacion"].mean()
        fig3 = go.Figure(go.Bar(
            x=tipo_sat.index,
            y=tipo_sat.values,
            marker_color=[tipo_colors.get(t, "#757575") for t in tipo_sat.index],
            text=[f"{v:.1%}" for v in tipo_sat.values],
            textposition="outside",
        ))
        fig3.update_layout(
            title="Saturación Promedio por Tipo de Nodo",
            yaxis_title="Saturación Promedio",
            yaxis_range=[0, 1.15],
            height=350, template="plotly_dark",
        )
        st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# TAB 5: Histórico Sísmico
# ══════════════════════════════════════════════════════════════════════

def render_sismico():
    st.subheader("Histórico Sísmico — Catálogo USGS")

    repo = get_repo()
    total = repo.count_sismos()

    if total == 0:
        st.info("No hay datos sísmicos en la DB. Se poblarán cuando el pipeline USGS se ejecute.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Eventos", f"{total:,}")
    col2.metric("M5.0+", f"{repo.count_sismos(min_magnitude=5.0):,}")
    col3.metric("M7.0+", f"{repo.count_sismos(min_magnitude=7.0):,}")

    min_mag = st.slider("Magnitud mínima", 0.0, 9.0, 4.0, 0.5)
    sismos = repo.get_sismos(min_magnitude=min_mag, limit=500)

    if sismos:
        df = pd.DataFrame(sismos)
        df["time"] = pd.to_datetime(df["timestamp"], unit="s")

        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure(go.Scattergeo(
                lat=df["lat"], lon=df["lon"],
                text=[
                    f"M{row['magnitude']:.1f} — {row['region']}<br>{row.get('source', 'USGS')}"
                    for _, row in df.iterrows()
                ],
                hoverinfo="text",
                marker=dict(
                    size=df["magnitude"] * 2,
                    color=df["magnitude"],
                    colorscale="Hot",
                    showscale=True,
                    colorbar=dict(title="Mag"),
                ),
            ))
            fig.update_geos(
                showland=True, landcolor="#1a1a2e",
                showocean=True, oceancolor="#0d1b2a",
                projection_type="natural earth",
            )
            fig.update_layout(
                title=f"Eventos ≥ M{min_mag:.1f} (últimos {len(df)})",
                height=450, template="plotly_dark",
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            fig = go.Figure(go.Histogram(
                x=df["magnitude"],
                nbinsx=30,
                marker_color="#ff9100",
            ))
            fig.update_layout(
                title="Distribución de Magnitudes",
                xaxis_title="Magnitud",
                yaxis_title="Frecuencia",
                height=450, template="plotly_dark",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            df[["time", "magnitude", "depth_km", "region", "lat", "lon", "source"]].head(50),
            use_container_width=True, hide_index=True,
        )

    _render_seismic_analytics(repo, min_mag)


def _render_seismic_analytics(repo: SentinelRepository, min_magnitude: float):
    depth_mag = repo.seismic_depth_vs_magnitude(min_magnitude=min_magnitude, limit=500)
    by_region = repo.seismic_by_region(min_magnitude=min_magnitude, limit=20)

    if depth_mag:
        st.markdown("---")
        st.markdown("**Profundidad vs Magnitud**")
        df = pd.DataFrame(depth_mag)

        fig = go.Figure(go.Scatter(
            x=df["magnitude"],
            y=df["depth_km"],
            mode="markers",
            marker=dict(
                size=df["magnitude"] * 2.5,
                color=df["depth_km"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Prof (km)"),
                opacity=0.7,
                line=dict(width=0.5, color="white"),
            ),
            text=[f"M{r['magnitude']:.1f} @ {r['depth_km']:.0f}km<br>{r['region']}" for r in depth_mag],
            hoverinfo="text",
        ))
        fig.update_layout(
            title=f"Scatter: Profundidad vs Magnitud (M{min_magnitude:.1f}+)",
            xaxis_title="Magnitud",
            yaxis_title="Profundidad (km)",
            yaxis_autorange="reversed",
            height=450, template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    if by_region:
        st.markdown("---")
        st.markdown(f"**Actividad Sísmica por Región (M{min_magnitude:.1f}+)**")

        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure(go.Bar(
                x=[r["count"] for r in by_region],
                y=[r["region"][:40] for r in by_region],
                orientation="h",
                marker_color="#ff9100",
                text=[f"n={r['count']}" for r in by_region],
                textposition="outside",
            ))
            fig.update_layout(
                title="Eventos por Región",
                xaxis_title="Eventos",
                height=max(350, len(by_region) * 28),
                template="plotly_dark",
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=[r["region"][:20] for r in by_region[:10]],
                y=[r["avg_magnitude"] for r in by_region[:10]],
                name="Promedio",
                marker_color="#2979ff",
            ))
            fig2.add_trace(go.Bar(
                x=[r["region"][:20] for r in by_region[:10]],
                y=[r["max_magnitude"] for r in by_region[:10]],
                name="Máxima",
                marker_color="#ff1744",
            ))
            fig2.update_layout(
                title="Magnitud Promedio y Máxima (Top 10)",
                yaxis_title="Magnitud",
                barmode="group",
                height=400, template="plotly_dark",
            )
            st.plotly_chart(fig2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# TAB 6: Layer Signals (existing, cleaned up)
# ══════════════════════════════════════════════════════════════════════

def fetch_real_layer_signals(repo) -> Optional[dict]:
    """Señales reales del último ciclo, por bot, desde viva_real
    (TBL_JUEZ_AUDITORIA fase='viva', alimentada por
    register_cycle_predictions() en cada ciclo del launcher).
    Devuelve None si todavía no hay ninguna predicción registrada
    (ej. sistema recién instalado, cero ciclos corridos) — en ese
    caso el caller debe mostrar el demo, etiquetado como demo.
    """
    filas = repo.get_ultima_prediccion_por_bot()
    if not filas:
        return None

    DISPLAY_NAMES = {
        "alfa1": "Alfa-1 (Bz/OMNI)",
        "alfa2": "Alfa-2 (Satellite)",
        "beta1": "Beta-1 (Kp/FFT+Schumann)",
        "beta2": "Beta-2 (Atmospheric)",
        "delta": "Delta (Financial)",
        "omega": "Omega (Dual-Ask)",
    }

    agents = {}
    padre = {"consensus": False, "signal": "NO_SIGNAL", "confidence": 0.0}
    for fila in filas:
        bot = (fila.get("bot_name") or "").lower()
        signal = fila.get("prediccion") or "NO_SIGNAL"
        conf = float(fila.get("confianza") or 0.0)
        if bot == "padre":
            padre = {
                "consensus": signal not in (None, "", "NO_SIGNAL"),
                "signal": signal,
                "confidence": conf,
            }
        elif bot in DISPLAY_NAMES:
            agents[DISPLAY_NAMES[bot]] = {"signal": signal, "confidence": conf}

    # Si algún bot conocido aun no registro nada (ej. Omega recien
    # agregado, o un bot deshabilitado), se muestra explicitamente
    # como sin datos en vez de omitirlo silenciosamente.
    for bot, label in DISPLAY_NAMES.items():
        if label not in agents:
            agents[label] = {"signal": "SIN_DATOS", "confidence": 0.0}

    return {"geodynamic": {"agents": agents, "padre": padre}}


def generate_demo_signals():
    """DEMO — valores de ejemplo, no telemetria real. Usar solo cuando
    fetch_real_layer_signals() devuelve None (cero ciclos corridos aun)."""
    rng = np.random.default_rng(int(time.time()) % 1000)
    layers = {
        "geodynamic": {
            "agents": {
                "Alfa-1 (Bz/OMNI)": {"signal": "NEUTRAL", "confidence": 0.3, "bz_mean": round(rng.normal(-2, 3), 1)},
                "Alfa-2 (Satellite)": {"signal": "NEUTRAL", "confidence": 0.3},
                "Beta-1 (Kp/FFT+Schumann)": {"signal": "NEUTRAL", "confidence": 0.3, "dominant_period_h": round(rng.uniform(6, 48), 1), "schumann_activity_pct": round(rng.uniform(0, 40), 1)},
                "Beta-2 (Atmospheric)": {"signal": "NEUTRAL", "confidence": 0.3},
                "Delta (Financial)": {"signal": "NEUTRAL", "confidence": 0.3, "fear_greed": round(rng.uniform(20, 80), 0)},
                "Omega (Dual-Ask)": {"signal": "NEUTRAL", "confidence": 0.3},
            },
            "padre": {"consensus": False, "signal": "NO_SIGNAL", "confidence": 0.0},
        },
    }
    return layers


def render_layer_signals(signals: dict):
    st.subheader("Layer Consensus Status")
    cols = st.columns(len(signals))
    emojis = {"geodynamic": "🌍"}

    for i, (layer_name, layer_data) in enumerate(signals.items()):
        with cols[i]:
            padre = layer_data["padre"]
            signal = padre["signal"]
            color = SIGNAL_COLORS.get(signal, "#757575")

            st.markdown(f"### {emojis.get(layer_name, '⚡')} {layer_name.upper()}")
            st.markdown(
                f"<div style='padding:12px;border-radius:8px;border-left:4px solid {color};"
                f"background:rgba(0,0,0,0.05)'>"
                f"<b>Padre:</b> <span style='color:{color}'>{signal}</span><br>"
                f"<b>Confidence:</b> {padre['confidence']:.0%}<br>"
                f"<b>Consensus:</b> {'Yes' if padre['consensus'] else 'No'}"
                f"</div>",
                unsafe_allow_html=True,
            )

            st.markdown("**Agent Signals:**")
            for agent_name, agent_data in layer_data["agents"].items():
                sig = agent_data["signal"]
                conf = agent_data["confidence"]
                sig_color = SIGNAL_COLORS.get(sig, "#757575")
                extras = {k: v for k, v in agent_data.items() if k not in ("signal", "confidence")}
                extra_str = " · ".join(f"{k}={v}" for k, v in extras.items())
                st.markdown(
                    f"<span style='color:{sig_color}'>●</span> **{agent_name}** — "
                    f"{sig} ({conf:.0%}) {extra_str}",
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════
# TAB 7: SNT Analysis (existing)
# ══════════════════════════════════════════════════════════════════════

def generate_demo_satellization():
    rng = np.random.default_rng(int(time.time()) % 1000)
    t = np.arange(1, 101, dtype=float)
    scenarios = {
        "BTC/ETH Dominance": (2.0, 0.35 + rng.normal(0, 0.05)),
        "BTC/SOL Dominance": (1.5, 0.65 + rng.normal(0, 0.08)),
        "SPY/QQQ Ratio": (1.1, -0.15 + rng.normal(0, 0.03)),
        "Kp Intensity": (3.0, 0.02 + rng.normal(0, 0.01)),
    }
    results = {}
    snt = st.session_state.snt
    for name, (a_true, b_true) in scenarios.items():
        noise = rng.normal(0, 0.02 * a_true, len(t))
        ratio = a_true * np.power(t, b_true) + np.abs(noise)
        ratio = np.maximum(ratio, 1e-6)
        try:
            result = snt.fit_ratio(t, ratio)
            results[name] = {"result": result, "t": t, "ratio": ratio}
        except ValueError:
            pass
    return results


def render_satellization_analysis(results: dict):
    st.subheader("SNT Satellization — R(t) = a·t^b")
    if not results:
        st.warning("No satellization results to display.")
        return

    names = list(results.keys())
    b_values = [results[n]["result"].b for n in names]
    regimes = [results[n]["result"].regime for n in names]
    colors = [REGIME_COLORS.get(r, "#757575") for r in regimes]

    cols = st.columns(2)
    with cols[0]:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=names, y=b_values,
            marker_color=colors,
            text=[f"b={b:.3f}" for b in b_values],
            textposition="outside",
        ))
        fig.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Roche Radius")
        fig.add_hline(y=0.3, line_dash="dot", line_color="orange", annotation_text="Active")
        fig.add_hrect(y0=-0.1, y1=0.05, fillcolor="yellow", opacity=0.1, annotation_text="Equilibrium")
        fig.update_layout(
            title="Satellization Exponent (b)", yaxis_title="b",
            height=400, template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    with cols[1]:
        fig = go.Figure()
        for name, data in results.items():
            regime = data["result"].regime
            color = REGIME_COLORS.get(regime, "#757575")
            fig.add_trace(go.Scatter(
                x=data["t"], y=data["ratio"],
                mode="lines", name=f"{name} (b={data['result'].b:.3f})",
                line=dict(color=color),
            ))
            a, b = data["result"].a, data["result"].b
            fig.add_trace(go.Scatter(
                x=data["t"], y=a * np.power(data["t"], b),
                mode="lines", name=f"{name} fit",
                line=dict(color=color, dash="dash"), showlegend=False,
            ))
        fig.update_layout(
            title="Power Law Fits", xaxis_title="t", yaxis_title="R(t)",
            height=400, template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    r2_values = [results[n]["result"].r_squared for n in names]
    regime_df = pd.DataFrame({
        "Domain": names,
        "b": [f"{b:.4f}" for b in b_values],
        "R²": [f"{r:.4f}" for r in r2_values],
        "Regime": [r.value for r in regimes],
    })
    st.dataframe(regime_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════
# TAB 8: Cycle History
# ══════════════════════════════════════════════════════════════════════

def render_cycle_history():
    st.subheader("Historial de Ciclos del Orquestador")

    repo = get_repo()
    cycles = repo.get_ciclos(limit=50)

    if not cycles:
        st.info("No hay ciclos registrados. El orquestador los registrará al ejecutarse.")
        return

    df = pd.DataFrame(cycles)
    df["time"] = pd.to_datetime(df["timestamp"], unit="s")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Ciclos", len(cycles))
    alerts = [c for c in cycles if c["geo_signal"] == "alert"]
    col2.metric("Geo Alerts", len(alerts))
    total_precursors = sum(c["precursors_count"] for c in cycles)
    col3.metric("Total Precursors", total_precursors)
    total_breaches = sum(1 for c in cycles if c["muro_breach"])
    col4.metric("Muro Breaches", total_breaches)

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=["Fantasma Index por Ciclo", "Precursores + Muro Walls"],
        shared_xaxes=True,
    )
    fig.add_trace(go.Scatter(
        x=df["time"], y=df["fantasma"],
        mode="lines+markers", name="Fantasma",
        line=dict(color="#d500f9"),
    ), row=1, col=1)
    fig.add_hline(y=15, line_dash="dot", line_color="#ff9100", row=1, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#ff1744", row=1, col=1)

    fig.add_trace(go.Bar(
        x=df["time"], y=df["precursors_count"],
        name="Precursors", marker_color="#2979ff",
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df["time"], y=df["muro_walls_active"],
        mode="lines+markers", name="Muro Walls",
        line=dict(color="#ff9100"),
    ), row=2, col=1)

    fig.update_layout(height=500, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    display_cols = [
        "time", "geo_signal", "geo_confidence", "fantasma",
        "nivel_riesgo", "precursors_count", "muro_walls_active", "muro_breach",
    ]
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available].head(50), use_container_width=True, hide_index=True)

    _render_cycle_alert_rate(repo)


def _render_cycle_alert_rate(repo: SentinelRepository):
    stats = repo.cycle_alert_rate()
    if stats["total_cycles"] == 0:
        return

    st.markdown("---")
    st.markdown("**Estadísticas de Alertas**")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Ciclos", stats["total_cycles"])
    c2.metric("Alert Rate", f"{stats['alert_rate']:.1%}")
    c3.metric("Breach Rate", f"{stats['breach_rate']:.1%}")
    c4.metric("Fantasma Promedio", f"{stats['avg_fantasma']:.2f}")

    c1b, c2b = st.columns(2)
    with c1b:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=stats["alert_rate"] * 100,
            title={"text": "Alert Rate (%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#ff9100"},
                "steps": [
                    {"range": [0, 10], "color": "#e8f5e9"},
                    {"range": [10, 30], "color": "#fff9c4"},
                    {"range": [30, 60], "color": "#ffe0b2"},
                    {"range": [60, 100], "color": "#ffcdd2"},
                ],
            },
        ))
        fig.update_layout(height=250, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    with c2b:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=stats["breach_rate"] * 100,
            title={"text": "Muro Breach Rate (%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#ff1744"},
                "steps": [
                    {"range": [0, 5], "color": "#e8f5e9"},
                    {"range": [5, 15], "color": "#fff9c4"},
                    {"range": [15, 30], "color": "#ffe0b2"},
                    {"range": [30, 100], "color": "#ffcdd2"},
                ],
            },
        ))
        fig.update_layout(height=250, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# TAB 9: Schumann Monitor
# ══════════════════════════════════════════════════════════════════════

def render_schumann_monitor():
    st.subheader("Monitor Schumann — Frecuencia y Coherencia")

    repo = get_repo()
    trend = repo.schumann_trend(limit=100)

    if not trend:
        st.info("No hay datos de Schumann registrados. Se poblarán al ejecutar ciclos del orquestador.")
        _render_schumann_reference()
        return

    df = pd.DataFrame(trend)
    df["time"] = pd.to_datetime(df["timestamp"], unit="s")

    latest = trend[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Frecuencia Schumann", f"{latest['schumann_hz']:.2f} Hz")
    col2.metric("Actividad WPC", f"{latest['schumann_activity']:.0f}%")
    deviation = latest["schumann_hz"] - 7.83
    col3.metric("Desviación de 7.83 Hz", f"{deviation:+.3f} Hz")

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=["Frecuencia Schumann (Hz)", "Actividad WPC (%)"],
        shared_xaxes=True,
    )

    fig.add_trace(go.Scatter(
        x=df["time"], y=df["schumann_hz"],
        mode="lines+markers", name="Schumann Hz",
        line=dict(color="#d500f9", width=2),
    ), row=1, col=1)
    fig.add_hline(y=7.83, line_dash="dash", line_color="#ffc107",
                  annotation_text="Fundamental (7.83 Hz)", row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df["time"], y=df["schumann_activity"],
        mode="lines", name="Actividad %",
        line=dict(color="#2979ff", width=2),
        fill="tozeroy",
        fillcolor="rgba(41,121,255,0.15)",
    ), row=2, col=1)

    fig.update_layout(height=500, template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("**Distribución de Frecuencia Schumann**")
    c1, c2 = st.columns(2)

    with c1:
        fig2 = go.Figure(go.Histogram(
            x=df["schumann_hz"],
            nbinsx=30,
            marker_color="#d500f9",
        ))
        fig2.add_vline(x=7.83, line_dash="dash", line_color="#ffc107", annotation_text="7.83 Hz")
        fig2.update_layout(
            title="Histograma de Frecuencia",
            xaxis_title="Hz",
            yaxis_title="Observaciones",
            height=300, template="plotly_dark",
        )
        st.plotly_chart(fig2, use_container_width=True)

    with c2:
        fig3 = go.Figure(go.Scatter(
            x=df["schumann_hz"],
            y=df["schumann_activity"],
            mode="markers",
            marker=dict(
                size=8,
                color=df["schumann_activity"],
                colorscale="Magma",
                showscale=True,
                colorbar=dict(title="WPC %"),
            ),
            text=[f"{row['schumann_hz']:.2f} Hz / {row['schumann_activity']:.0f}%" for _, row in df.iterrows()],
            hoverinfo="text",
        ))
        fig3.update_layout(
            title="Frecuencia vs Actividad",
            xaxis_title="Schumann Hz",
            yaxis_title="Actividad WPC (%)",
            height=300, template="plotly_dark",
        )
        st.plotly_chart(fig3, use_container_width=True)

    _render_schumann_reference()


def _render_schumann_reference():
    st.markdown("---")
    st.markdown("**Referencia: Armónicos de Schumann**")
    harmonics = [
        {"Armónico": "Fundamental", "Frecuencia (Hz)": 7.83, "Descripción": "Resonancia base Tierra-Ionosfera"},
        {"Armónico": "2do", "Frecuencia (Hz)": 14.3, "Descripción": "Primer sobretono"},
        {"Armónico": "3ro", "Frecuencia (Hz)": 20.8, "Descripción": "Segundo sobretono"},
        {"Armónico": "4to", "Frecuencia (Hz)": 27.3, "Descripción": "Tercer sobretono"},
        {"Armónico": "5to", "Frecuencia (Hz)": 33.8, "Descripción": "Cuarto sobretono"},
    ]
    st.dataframe(pd.DataFrame(harmonics), use_container_width=True, hide_index=True)
    st.caption(
        "Beta-1 aplica un filtro armónico: bins FFT sub-armónicos se retienen, "
        "el resto se atenúa al 10%. Coherencia armónica > 0.3 con excitación activa "
        "produce señal WATCH."
    )


# ══════════════════════════════════════════════════════════════════════
# Main App
# ══════════════════════════════════════════════════════════════════════

def main():
    active_layers = render_sidebar()

    st.title("⚡ Sentinel Omega — Command Dashboard")
    st.caption("Precursor Detection Platform · TITAN V32 Lineage · R(t) = a·t^b")

    col1, col2, col3, col4, col5 = st.columns(5)
    cfg = st.session_state.config
    active = sum(1 for v in cfg.layers.values() if v.enabled)
    col1.metric("Active Layers", f"{active}/3")
    col2.metric("Precursor Types", "15")
    col3.metric("Topology Nodes", "125")
    col4.metric("Muro Walls", "5")
    col5.metric("Architecture", "SNT + TITAN")

    st.divider()

    tabs = st.tabs([
        "🔴 Precursor Risk",
        "🧱 Muro 5 Eventos",
        "🔍 Scanner",
        "🗺️ Topología",
        "📊 Sísmico",
        "🌐 Schumann",
        "📡 Layer Signals",
        "📐 SNT Analysis",
        "📋 Ciclos",
        "🌀 Cimatica",
        "🤖 Agente",
    ])

    with tabs[0]:
        render_precursor_risk()

    with tabs[1]:
        render_muro()

    with tabs[2]:
        render_scanner()

    with tabs[3]:
        render_topology()

    with tabs[4]:
        render_sismico()

    with tabs[5]:
        render_schumann_monitor()

    with tabs[6]:
        _repo = get_repo()
        signals = fetch_real_layer_signals(_repo)
        if signals is None:
            st.info(
                "Aún no hay predicciones registradas (0 ciclos corridos). "
                "Mostrando valores de ejemplo — no es telemetría real."
            )
            signals = generate_demo_signals()
        render_layer_signals(signals)

    with tabs[7]:
        st.info("SNT Analysis — valores de ejemplo (DEMO). No es teletria satelital real.")
        snt_results = generate_demo_satellization()
        render_satellization_analysis(snt_results)

    with tabs[8]:
        render_cycle_history()

    with tabs[9]:
        render_cimatica()

    with tabs[10]:
        if HAS_AGENT_TAB:
            render_agent_tab()
        else:
            st.error("Pestaña Agente no disponible")


if __name__ == "__main__":
    main()
