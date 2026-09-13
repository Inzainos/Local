"""Pestaña Agente — render para dashboard Streamlit."""
from __future__ import annotations
import streamlit as st
import pandas as pd

def render_agent_tab():
    st.subheader("🤖 Agente Consenso — Consensus Expert Agent")
    st.caption("Concilio de 3 expertos (Investigador / Coder / Optimizador) con memoria compartida y umbral 85/100")

    try:
        from sentinel_omega.infrastructure.messaging.agent_bridge import agent_health
        health = agent_health()
    except Exception as e:
        st.error(f"No se pudo cargar agent_bridge: {e}")
        return

    # Métricas superiores
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Agent Root", "OK" if health.get("exists") else "NO")
    c2.metric("DB", "OK" if health.get("db_exists") else "—")
    c3.metric("Ollama", "OK" if health.get("ollama_ok") else "OFF")
    thr = health.get("threshold","threshold_score: 85")
    c4.metric("Umbral", thr.split(":")[-1].strip() if ":" in thr else "85")

    # Modelos
    with st.expander("Modelos y Config", expanded=False):
        models = health.get("models", [])
        if models:
            st.code("\n".join(models))
        else:
            st.write("Sin modelos detectados en config.yaml")
        if health.get("ollama_models"):
            st.write("Ollama disponibles:", ", ".join(health["ollama_models"]))
        if health.get("ollama_error"):
            st.warning(health["ollama_error"])

    # Historial reciente (blackboards)
    st.divider()
    st.markdown("#### 📋 Historial de Consensos Recientes")
    boards = health.get("recent_blackboards", [])
    if boards:
        df = pd.DataFrame(boards)
        # truncar síntesis para tabla
        if "final_synthesis" in df.columns:
            df["final_synthesis"] = df["final_synthesis"].astype(str).str.slice(0, 120) + "…"
        st.dataframe(df, use_container_width=True, hide_index=True)
        # Detalle del último
        sel = st.selectbox("Ver síntesis completa de:", [b["task_id"] for b in boards], index=0)
        full = next((b for b in boards if b["task_id"]==sel), None)
        if full and full.get("final_synthesis"):
            st.markdown("**Síntesis:**")
            st.markdown(full["final_synthesis"][:4000])
    else:
        st.info("Aún no hay blackboards persistidos. Ejecuta un --audit o --task.")

    # Conversación reciente
    hist = health.get("recent_history", [])
    if hist:
        with st.expander("💬 Historial de Conversación (últimos 6)"):
            for h in reversed(hist):
                role = h.get("role","?")
                content = str(h.get("content",""))[:600]
                st.markdown(f"**{role}:** {content}")

    # Acciones
    st.divider()
    st.markdown("#### ⚡ Acciones")
    col_a, col_b = st.columns(2)
    with col_a:
        focus = st.text_input("Focus para auditoría (opcional)", placeholder="ej: reglas duras, migraciones, secretos")
        if st.button("🔍 Lanzar Auditoría (--audit)", use_container_width=True):
            with st.spinner("Ejecutando audit (puede tardar 2-4 min)…"):
                try:
                    from sentinel_omega.infrastructure.messaging.agent_bridge import agent_run_audit
                    res = agent_run_audit(focus=focus, timeout_s=600)
                    if res.get("ok"):
                        st.success("Auditoría completada")
                        st.code(res.get("stdout","")[-6000:])
                    else:
                        st.error(f"Fallo (rc={res.get('returncode')})")
                        st.code((res.get("stdout","") + "\n" + res.get("stderr",""))[-6000:])
                except Exception as e:
                    st.error(str(e))
    with col_b:
        prompt = st.text_area("Prompt para tarea directa (--task)", placeholder="ej: Refactoriza reporte_sentinel con ReportEngine", height=100)
        if st.button("▶️ Ejecutar Tarea", use_container_width=True, disabled=not prompt.strip()):
            with st.spinner("Ejecutando tarea…"):
                try:
                    from sentinel_omega.infrastructure.messaging.agent_bridge import agent_run_task
                    res = agent_run_task(prompt, timeout_s=400)
                    if res.get("ok"):
                        st.success("Tarea completada")
                        st.code(res.get("stdout","")[-6000:])
                    else:
                        st.error(f"Fallo rc={res.get('returncode')}")
                        st.code((res.get("stdout","") + "\n" + res.get("stderr",""))[-6000:])
                except Exception as e:
                    st.error(str(e))

    st.caption("Bridge: sentinel_omega/infrastructure/messaging/agent_bridge.py → consensus-expert-agent/main.py")
