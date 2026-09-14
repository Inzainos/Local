#!/usr/bin/env python3
"""
Sentinel Omega — Launcher
Starts the orchestrator in continuous cycle mode with graceful signal handling.

Usage:
    python -m sentinel_omega.launcher
    python sentinel_omega/launcher.py
    python sentinel_omega/launcher.py --once          # Single cycle, then exit
    python sentinel_omega/launcher.py --dashboard     # Launch dashboard alongside
    python sentinel_omega/launcher.py --dry-run       # No Telegram alerts
    python sentinel_omega/launcher.py --entrenar --reporte  # Train then report
    python sentinel_omega/launcher.py --reporte       # Report only (no training)
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime as _dt
from pathlib import Path

# Ensure the workspace root is importable when run as a script
# (python sentinel_omega/launcher.py), not just as a module.
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

PIDFILE = Path(__file__).parent / "data" / "sentinel_omega.pid"
LOGFILE = Path(__file__).parent / "data" / "sentinel_omega.log"
# data/ está en .gitignore: en un checkout limpio (GitHub Actions) no existe
LOGFILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LAUNCHER] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGFILE, mode="a"),
    ],
)
logger = logging.getLogger(__name__)

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} — initiating graceful shutdown...")
    _shutdown_requested = True


def _write_pid():
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(os.getpid()))
    logger.info(f"PID {os.getpid()} written to {PIDFILE}")


def _clear_pid():
    try:
        if PIDFILE.exists():
            PIDFILE.unlink()
    except OSError:
        pass


def _check_already_running() -> bool:
    if not PIDFILE.exists():
        return False
    try:
        pid = int(PIDFILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except PermissionError:
        # Proceso existe pero pertenece a otro usuario (root) -> sí está corriendo
        return True
    except (ProcessLookupError, ValueError, OSError):
        try:
            _clear_pid()
        except OSError:
            pass
        return False


def _launch_dashboard() -> subprocess.Popen:
    dashboard_path = Path(__file__).parent / "infrastructure" / "dashboard" / "app.py"
    logger.info(f"Launching dashboard: {dashboard_path}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(dashboard_path),
         "--server.headless", "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"Dashboard PID: {proc.pid}")
    return proc


def _print_banner(config):
    print()
    print("=" * 60)
    print(f"  SENTINEL OMEGA v{config.version}")
    print(f"  Precursor Detection Platform")
    print(f"  Author: {config.author}")
    print("=" * 60)
    print(f"  PID:        {os.getpid()}")
    print(f"  Location:   {config.coordinates.get('location', '—')}")
    active = [k for k, v in config.layers.items() if v.enabled]
    print(f"  Layers:     {', '.join(active)}")
    print(f"  Telegram:   {'ON' if config.telegram.enabled else 'OFF (dry run)'}")
    print(f"  Log:        {LOGFILE}")
    print("=" * 60)
    print()


def _run_reportes(db_path: str) -> None:
    """
    Genera el reporte general y el reporte del Padre en stdout.
    Guarda también ambos reportes en data/reporte_<timestamp>.txt
    para revisión posterior.

    Se invoca automáticamente después de --entrenar si se pasa --reporte,
    o de forma independiente con solo --reporte.
    """
    from sentinel_omega.infrastructure.pipeline.reporte_sentinel import (
        reporte_general,
        reporte_padre,
    )

    ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(db_path).parent
    general_path = out_dir / f"reporte_general_{ts}.txt"
    padre_path = out_dir / f"reporte_padre_{ts}.txt"

    # ── Reporte General ──────────────────────────────────────────────────────
    logger.info("Generando reporte general...")
    try:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            reporte_general(db_path)
        texto_general = buf.getvalue()
        print(texto_general)
        general_path.write_text(texto_general, encoding="utf-8")
        logger.info(f"Reporte general guardado en: {general_path}")
    except Exception as e:
        logger.error(f"reporte_general() falló: {e}", exc_info=True)

    # ── Reporte del Padre ────────────────────────────────────────────────────
    logger.info("Generando reporte del Padre...")
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            reporte_padre(db_path)
        texto_padre = buf.getvalue()
        print(texto_padre)
        padre_path.write_text(texto_padre, encoding="utf-8")
        logger.info(f"Reporte del Padre guardado en: {padre_path}")
    except Exception as e:
        logger.error(f"reporte_padre() falló: {e}", exc_info=True)


def run(args):
    global _shutdown_requested

    if _check_already_running():
        logger.error("Sentinel Omega is already running. Use shutdown.py first.")
        sys.exit(1)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    from sentinel_omega.config.sentinel_config import SentinelOmegaConfig
    from sentinel_omega.orchestrator import SentinelOrchestrator
    from sentinel_omega.infrastructure.database.schema import init_database, get_connection
    from sentinel_omega.infrastructure.database.repository import SentinelRepository
    from sentinel_omega.infrastructure.database.seed_nodos import seed_topology

    config = SentinelOmegaConfig()

    if args.dry_run:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        config = SentinelOmegaConfig()

    _print_banner(config)
    _write_pid()

    logger.info("Initializing database...")
    db_path = Path(__file__).parent / config.databases.geodynamic_db
    init_database(str(db_path))

    repo = SentinelRepository(str(db_path))
    existing_nodes = repo.get_nodos()
    if not existing_nodes:
        logger.info("Seeding 125 topology nodes...")
        seed_topology(repo)
        logger.info("Topology seeded.")

    if args.backcast:
        from sentinel_omega.infrastructure.pipeline.backcast import (
            run_backcast,
            run_backfill_secundario,
        )
        logger.info("Running historical backcast (one-time)...")
        run_backcast(str(db_path))
        logger.info("Running secondary backfill (volcanic SO2 + BTC)...")
        run_backfill_secundario(str(db_path))
        logger.info("Backcast complete.")

    if args.entrenar:
        from sentinel_omega.infrastructure.pipeline.entrenamiento import entrenar
        logger.info("Running signature training (Fase 1 + Fase 2)...")
        resultado = entrenar(str(db_path))
        logger.info(f"Training complete: {resultado}")

    if args.disciplina:
        from sentinel_omega.infrastructure.pipeline.entrenamiento import (
            disciplina_trasfondo,
        )
        logger.info("Running background discipline (castigo desde abajo)...")
        resultado = disciplina_trasfondo(str(db_path))
        logger.info(f"Background discipline complete: {resultado}")

    if args.barrido:
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            barrido_diario,
        )
        logger.info("Running daily maintenance sweep (barrido diario)...")
        resultado = barrido_diario(str(db_path))
        logger.info(f"Daily sweep complete: {resultado}")

    # ── Reportes (después de cualquier operación batch) ──────────────────────
    if args.reporte:
        _run_reportes(str(db_path))

    # ── Modo tarea: ejecutar y salir ─────────────────────────────────────────
    # Los flags batch (--backcast/--entrenar/--disciplina/--barrido/--reporte)
    # sin --once NO deben caer al loop continuo de vigilancia: el vigilante los
    # invoca como pasos one-shot y el loop dejaba el job colgado indefinidamente
    # (la disciplina corría 3s y luego ciclaba 2h+ hasta cancelarse a mano).
    # Con --once se conserva el comportamiento de bootstrap: tareas + UN ciclo.
    tarea_batch = (
        args.backcast or args.entrenar or args.disciplina
        or args.barrido or args.reporte
    )
    if tarea_batch and not args.once:
        logger.info("Batch task(s) complete — exiting (no --once/continuous).")
        _clear_pid()
        return

    # Los modos batch de mantenimiento/disciplina no entran al ciclo de
    # vigilancia continuo: ejecutan su trabajo y salen limpiamente. Sin esto,
    # `--disciplina` / `--barrido` caían en el loop de "Next cycle in Ns...".
    if args.disciplina or args.barrido:
        _clear_pid()
        logger.info("Batch operation complete — exiting without watch loop.")
        return

    dashboard_proc = None
    if args.dashboard:
        dashboard_proc = _launch_dashboard()

    logger.info("Creating orchestrator with live pipelines...")
    orch = SentinelOrchestrator.create_with_live_pipelines(config)

    try:
        from sentinel_omega.core.juez.pesos import cargar_pesos
        pesos = cargar_pesos(repo._conn)
        if pesos and orch._runner is not None:
            orch._runner.padre.set_pesos(pesos)
            logger.info(f"Pesos disciplinarios cargados: {pesos}")
    except Exception as e:
        logger.warning(f"Could not load bot weights: {e}")

    cycle_interval = config.layers.get("geodynamic", config.layers["geodynamic"]).refresh_interval_s
    logger.info(f"Cycle interval: {cycle_interval}s")
    logger.info("Sentinel Omega ONLINE.")

    try:
        while not _shutdown_requested:
            cycle_start = time.time()

            try:
                logger.info(f"--- Starting cycle #{orch.get_status().cycle_count + 1} ---")
                results = orch.run_cycle()
                status = orch.get_status()

                _log_cycle_summary(status, results, repo, config, runner=orch._runner)

            except Exception as e:
                logger.error(f"Cycle failed: {e}", exc_info=True)

            if args.once:
                logger.info("--once flag: exiting after single cycle.")
                break

            elapsed = time.time() - cycle_start
            sleep_time = max(0, cycle_interval - elapsed)
            if sleep_time > 0 and not _shutdown_requested:
                logger.info(f"Next cycle in {sleep_time:.0f}s...")
                _interruptible_sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")

    finally:
        logger.info("Shutting down...")
        if dashboard_proc:
            logger.info(f"Terminating dashboard (PID {dashboard_proc.pid})...")
            dashboard_proc.terminate()
            dashboard_proc.wait(timeout=10)
        _clear_pid()
        logger.info("Sentinel Omega OFFLINE.")


def _interruptible_sleep(seconds: float):
    end = time.time() + seconds
    while time.time() < end and not _shutdown_requested:
        time.sleep(min(1.0, end - time.time()))


def _log_cycle_summary(status, results, repo, config, runner=None):
    risk = status.last_precursor_risk
    if risk:
        logger.info(
            f"Fantasma: {risk.fantasma:.2f} ({risk.risk_level}) | "
            f"Precursors: {len(status.active_precursors)} | "
            f"Alerts dispatched: {status.alerts_dispatched} | "
            f"Uptime: {status.uptime_s:.0f}s"
        )

        try:
            _b1 = getattr(runner.pipeline, "_cache", {}).get("beta1") or {} if runner else {}
            _a1 = getattr(runner.pipeline, "_cache", {}).get("alfa1") or {} if runner else {}
            _sch_hz = _b1.get("schumann_frequency")
            try:
                from sentinel_omega.infrastructure.api.geophysical import compute_lunar_phase
                _lunar = compute_lunar_phase()
                import numpy as _np
                _lp = _b1.get("lunar_phase", 0.5)
                if isinstance(_lp, _np.ndarray):
                    _lp = float(_lp[-1]) if _lp.size > 0 else 0.5
                _fase = _lunar.get("phase_fraction", _lp or 0.5)
            except Exception:
                import numpy as _np
                _lp = _b1.get("lunar_phase", 0.0)
                if isinstance(_lp, _np.ndarray):
                    _lp = float(_lp[-1]) if _lp.size > 0 else 0.0
                _fase = _lp or _b1.get("fase_lunar", 0.0) or 0.5
            try:
                _prot = _a1.get("proton_flux") or _a1.get("proton_speed") or _b1.get("proton_speed") or 0.0
                # Handle numpy arrays and other iterables
                import numpy as _np
                if isinstance(_prot, _np.ndarray):
                    _prot = float(_prot[-1]) if _prot.size > 0 else 0.0
                elif isinstance(_prot, (list, tuple)):
                    _prot = float(_prot[-1]) if _prot else 0.0
                else:
                    _prot = float(_prot) if _prot else 0.0
            except Exception:
                _prot = 0.0
            # Defensive scalar conversion for numpy arrays
            import numpy as _np
            def _scalar(v, default=0.0):
                if isinstance(v, _np.ndarray):
                    return float(v[-1]) if v.size > 0 else default
                if isinstance(v, (list, tuple)):
                    return float(v[-1]) if v else default
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return default

            repo.insert_precursor_cosmico(
                bz=_scalar(risk.components.get("bz_nT", 0)),
                viento=_scalar(risk.components.get("wind_kms", 0)),
                protones=_prot,
                kp=_scalar(risk.components.get("kp", 0)),
                lod_ms=_scalar(risk.components.get("lod_ms", 0)),
                schumann_hz=_sch_hz if _sch_hz is not None else 7.83,
                schumann_activity=_scalar(risk.components.get("schumann_wpc", 0)) * 100,
                presion_hpa=_scalar(risk.components.get("pressure_hpa", 1013)),
                fantasma=_scalar(risk.fantasma),
                nivel_riesgo=risk.risk_level,
                fase_lunar=_fase,
            )
        except Exception as e:
            import traceback
            logger.warning(f"Failed to persist cycle data: {e}")
            logger.warning(f"Traceback: {traceback.format_exc()}")

        muro = status.last_muro
        walls_active = muro.walls_active if muro else 0
        muro_breach = muro.muro_breach if muro else False

        geo = results.get("geodynamic")
        if geo:
            try:
                cycle_id = repo.insert_ciclo(
                    geo_signal=geo.final_signal.value,
                    geo_confidence=geo.confidence,
                    geo_consensus=geo.consensus_reached,
                    fantasma=risk.fantasma,
                    nivel_riesgo=risk.risk_level,
                    precursors_count=len(status.active_precursors),
                    precursor_types=status.active_precursors,
                    muro_walls_active=walls_active,
                    muro_breach=muro_breach,
                    alerts_dispatched=status.alerts_dispatched,
                )
            except Exception as e:
                logger.warning(f"Failed to persist cycle record: {e}")
                cycle_id = None

            if muro:
                try:
                    wall_states = {ws.name: ws.active for ws in muro.wall_statuses}
                    repo.insert_muro_evento(
                        walls_active=muro.walls_active,
                        correlation_score=muro.correlation_score,
                        muro_breach=muro.muro_breach,
                        risk_label=muro.risk_label,
                        wall_states=wall_states,
                        active_types=muro.active_precursor_types,
                        cycle_id=cycle_id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist muro record: {e}")

            detections = getattr(geo, "precursor_detections", None) or []
            for det in detections:
                try:

                    repo.insert_deteccion(
                        tipo=det.tipo.value,
                        display_name=det.display_name,
                        confidence=det.confidence,
                        station=det.station,
                        lat=det.lat,
                        lon=det.lon,
                        values=det.values,
                        cycle_id=cycle_id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist detection: {e}")

            _auditar_ciclo(geo, repo, runner)

    # ── Persistir alfa2 (cobertura satelital) ──────────────────────
    if runner is not None:
        try:
            alfa2_data = getattr(runner, "_last_alfa2_data", None)
            if alfa2_data and alfa2_data.get("zone_coverages"):
                ts_blk = _dt.utcnow().strftime("%Y-%m-%d %H:00:00")
                for zona, cov in alfa2_data["zone_coverages"].items():
                    cloud_covers = cov.get("s2_cloud_covers", [])
                    clear_passes = sum(1 for cc in cloud_covers if cc < 20.0)
                    total = cov.get("total_passes", 0)
                    s2 = cov.get("s2_count", 0)
                    s1 = cov.get("s1_count", 0)
                    coverage_score = min(total / 8.0, 1.0)
                    clarity = clear_passes / max(len(cloud_covers), 1)
                    revisit = cov.get("mean_revisit_days", 0.0)
                    repo.insert_cobertura_satelital(
                        timestamp_blk=ts_blk,
                        zona=zona,
                        coverage_score=round(coverage_score * 0.4 + clarity * 0.3 +
                                             max(0, 1.0 - revisit / 12.0) * 0.3, 4),
                        thermal_anomalies=alfa2_data.get("thermal_anomaly_count", 0),
                        clear_passes=clear_passes,
                        total_passes=total,
                        revisit_days=revisit,
                    )
        except Exception as exc:
            logger.warning(f"Failed to persist alfa2 coverage (non-blocking): {exc}")

    # ── Persistir correlación cruzada delta_enriched ──────────────
    if runner is not None:
        try:
            delta_cache = getattr(runner.pipeline, "_cache", {}).get("delta") or {}
            if delta_cache.get("cross_coupling") is not None:
                ts_blk = _dt.utcnow().strftime("%Y-%m-%d %H:00:00")
                repo.insert_delta_cross(
                    timestamp_blk=ts_blk,
                    cross_coupling=delta_cache.get("cross_coupling", 0.0),
                    geomagnetic_coupling=delta_cache.get("geo_coupling", 0.0),
                    schumann_coupling=delta_cache.get("schumann_coupling", 0.0),
                    composite_score=delta_cache.get("delta_composite_score", 0.0),
                    regime_label=delta_cache.get("delta_regime_label", ""),
                    confidence=delta_cache.get("delta_confidence", 0.0),
                    data_completeness=delta_cache.get("delta_data_completeness", 0.0),
                    geo_kp_max_3d=delta_cache.get("geo_kp_max_3d"),
                    geo_storm_active=delta_cache.get("geo_storm_active", 0),
                    geo_schumann_deviation=delta_cache.get("geo_schumann_deviation"),
                )
        except Exception as exc:
            logger.warning(f"Failed to persist delta cross (non-blocking): {exc}")


def _build_live_features(runner) -> dict:
    """Build the firma feature vector from the live pipeline cache.

    Extrae features para los 5 bots entrenados:
      alfa1  — clima espacial (Bz, viento solar)
      beta1  — Kp, Schumann, sismicidad, fase lunar
      beta2  — desgasificación volcánica (proxy OWM → escala kt aproximada)
      delta  — volatilidad financiera BTC
      alfa2  — cobertura satelital ESA Sentinel (acumulación desde ciclos vivos)

    El proxy de beta2 usa el global_node_scan de OpenWeatherMap:
    - erupciones_win  ≈ # nodos volcánicos/tectónicos con SO2 > umbral
    - so2_kt_win      ≈ suma de exceso SO2 en nodos (μg/m³) × factor escala
    El factor de escala es muy conservador (1e-4) porque 1 kilotón de SO2
    dispersado a nivel global corresponde a ~10 μg/m³ en 1 nodo de referencia.
    Los valores se mueven en la misma escala relativa que el histórico entrenado
    (0 en calma, positivo en actividad), lo que es suficiente para que la
    función de similitud distinga estados activos de estados quietos.
    """
    import numpy as np

    features = {}
    if runner is None or not hasattr(runner, "pipeline"):
        return features
    cache = getattr(runner.pipeline, "_cache", {})

    # ── alfa1: clima espacial ──────────────────────────────────────
    alfa1 = cache.get("alfa1") or {}
    omni = alfa1.get("omni_dataframe")
    if omni is not None:
        if "bz_gsm" in omni.columns:
            bz = omni["bz_gsm"].dropna()
            if len(bz) > 0:
                features["bz_mean"] = float(bz.mean())
                features["bz_min"] = float(bz.min())
        if "plasma_speed" in omni.columns:
            wind = omni["plasma_speed"].dropna()
            if len(wind) > 0:
                features["viento_avg"] = float(wind.mean())
                features["viento_max"] = float(wind.max())

    # ── beta1: Kp / Schumann / sismicidad / lunar ─────────────────
    beta1 = cache.get("beta1") or {}
    kp = beta1.get("kp_series")
    if kp is not None and len(kp) > 0:
        features["kp_mean"] = float(np.nanmean(kp))
        features["kp_max"] = float(np.nanmax(kp))
    if "schumann_frequency" in beta1:
        features["schumann_mean"] = float(beta1["schumann_frequency"])
    mags = beta1.get("seismic_magnitudes")
    if mags is not None and len(mags) > 0:
        features["sismo_count_win"] = float(len(mags))
        features["sismo_max_mag_win"] = float(np.nanmax(mags))
    lunar = beta1.get("lunar_phase")
    if lunar is not None and len(lunar) > 0:
        features["fase_lunar"] = float(lunar[-1])

    # ── beta2: desgasificación volcánica (proxy OWM) ──────────────
    _SO2_SCALE = 1e-4
    beta2 = cache.get("beta2") or {}
    node_scan = beta2.get("global_node_scan", [])
    if node_scan:
        degassing_nodes = [
            n for n in node_scan
            if n.get("tipo", "") in ("VOLCAN", "TECTONICO")
        ]
        aq_baseline = beta2.get("degassing_baseline") or {}
        base_so2 = aq_baseline.get("so2", 0.0)
        erupciones_proxy = 0
        so2_sum = 0.0
        for node in degassing_nodes:
            excess = max(0.0, node.get("so2", 0.0) - base_so2)
            if excess > 50.0:  # NODE_SO2_EXCESS_ALERT
                erupciones_proxy += 1
                so2_sum += excess
        features["erupciones_win"] = float(erupciones_proxy)
        features["so2_kt_win"] = round(so2_sum * _SO2_SCALE, 6)
        features["erupciones_90d"] = float(erupciones_proxy)
        features["so2_kt_90d"] = round(so2_sum * _SO2_SCALE, 6)

    # ── delta: volatilidad financiera BTC ─────────────────────────
    delta = cache.get("delta") or {}
    for key in ("btc_volatilidad", "btc_vol_max", "btc_ret_win", "btc_vol_72h"):
        if key in delta:
            features[key] = float(delta[key])

    # ── alfa2: cobertura satelital ────────────────────────────────
    alfa2_data = getattr(runner, "_last_alfa2_data", None)
    if alfa2_data and alfa2_data.get("zone_coverages"):
        scores = []
        clear_total = 0
        total_passes = 0
        for zona, cov in alfa2_data["zone_coverages"].items():
            cloud_covers = cov.get("s2_cloud_covers", [])
            clear_p = sum(1 for cc in cloud_covers if cc < 20.0)
            total_p = cov.get("total_passes", 0)
            revisit = cov.get("mean_revisit_days", 0.0)
            score = min(total_p / 8.0, 1.0) * 0.4
            score += (clear_p / max(len(cloud_covers), 1)) * 0.3
            score += max(0, 1.0 - revisit / 12.0) * 0.3
            scores.append(score)
            clear_total += clear_p
            total_passes += total_p
        if scores:
            features["satellite_coverage_score"] = round(float(np.mean(scores)), 4)
            features["satellite_thermal_anomalies"] = float(
                alfa2_data.get("thermal_anomaly_count", 0)
            )
            features["satellite_clear_passes"] = float(clear_total)

    # ── delta_enriched: acoplamiento cruzado geofísico-financiero ──
    # Solo si la pasada delta_enriched corrió: un fetch fallido deja las
    # claves ausentes y la feature debe quedar NaN (excluida por similitud),
    # nunca un 0.0 falso.
    if delta.get("cross_coupling") is not None:
        features["delta_cross_coupling"] = float(delta["cross_coupling"])
    if delta.get("geo_coupling") is not None:
        features["delta_geo_coupling"] = float(delta["geo_coupling"])
    if delta.get("schumann_coupling") is not None:
        features["delta_schumann_coupling"] = float(delta["schumann_coupling"])

    return features


def _auditar_ciclo(geo, repo, runner) -> None:
    """Firma matching + Juez registration/resolution for this cycle."""
    try:
        from sentinel_omega.core.firmas.signature_engine import FirmaMemoria
        from sentinel_omega.core.juez.juez import Juez

        conn = repo._conn_safe
        memoria = FirmaMemoria(conn)
        juez = Juez(conn)

        # Serie viva de Schumann: la lectura en tiempo real de esta corrida
        # (WPC de Tomsk) se acumula con su bloque horario. Con el tiempo esta
        # serie alimenta el dominio SCHUMANN de los cruces (no hay backcast).
        try:
            import time as _t
            beta1_cache = getattr(runner.pipeline, "_cache", {}).get("beta1") or {}
            sch_hz = beta1_cache.get("schumann_frequency")
            sch_act = beta1_cache.get("schumann_activity")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS tbl_schumann_vivo ("
                "timestamp_blk TEXT PRIMARY KEY, schumann_hz REAL, "
                "schumann_activity REAL, creada_at TEXT DEFAULT (datetime('now')))")
            # LOCF (Last Observation Carried Forward): si la API de Tomsk se
            # cortó (activity == 0.0 exacto = descarga fallida, no calma real),
            # arrastramos el último valor conocido en vez de escribir un cero
            # falso. Tomsk solo sirve la imagen ACTUAL (no hay histórico que
            # rebobinar), así que el LOCF cubre el hueco; las APIs que sí sirven
            # historia (USGS days=7, NOAA) ya rellenan su ventana solas.
            señal_viva = sch_act is not None and sch_act != 0.0
            if not señal_viva:
                ult = conn.execute(
                    "SELECT schumann_hz, schumann_activity FROM tbl_schumann_vivo "
                    "ORDER BY timestamp_blk DESC LIMIT 1").fetchone()
                if ult:
                    sch_hz = sch_hz or ult[0]
                    sch_act = ult[1]   # arrastra el último medido
                    logger.info(
                        f"Schumann: API sin señal — LOCF del último valor "
                        f"({sch_act}%)")
            if sch_hz is not None or sch_act is not None:
                ts_blk = _t.strftime("%Y-%m-%d %H:00", _t.gmtime())
                conn.execute(
                    "INSERT OR REPLACE INTO tbl_schumann_vivo "
                    "(timestamp_blk, schumann_hz, schumann_activity) VALUES (?,?,?)",
                    (ts_blk, sch_hz, sch_act))
                conn.commit()
        except Exception as e:
            logger.warning(f"Persistencia Schumann viva falló (non-blocking): {e}")

        matches = []
        features = _build_live_features(runner)
        if features:
            matches = memoria.match_estado_actual(features)
            for m in matches[:5]:
                try:
                    nodo = conn.execute(
                        "SELECT nombre, lat, lon, region FROM "
                        "TBL_NODOS_TOPOLOGIA WHERE node_id = ?",
                        (m["id_nodo"],),
                    ).fetchone()
                    if nodo:
                        m["nodo_nombre"] = nodo[0]
                        m["nodo_lat"] = round(nodo[1], 1)
                        m["nodo_lon"] = round(nodo[2], 1)
                        m["nodo_region"] = nodo[3]
                except Exception:
                    pass
            for m in matches[:3]:
                ventana = ""
                try:
                    lag_firma = conn.execute(
                        "SELECT lag_promedio_h, lag_n FROM TBL_FIRMAS "
                        "WHERE firma_id = ? AND lag_promedio_h IS NOT NULL",
                        (m["firma_id"],),
                    ).fetchone()
                    if lag_firma:
                        m["ventana_tipica_dias"] = round(lag_firma[0] / 24, 1)
                        ventana = (
                            f" — ESTA firma suele presentarse en "
                            f"~{lag_firma[0]/24:.0f} días (n={lag_firma[1]})"
                        )
                    else:
                        lag = conn.execute(
                            "SELECT lag_promedio_h, lag_max_h FROM "
                            "tbl_lag_anticipacion WHERE event_class = ?",
                            (m["event_class"],),
                        ).fetchone()
                        if lag:
                            m["ventana_tipica_dias"] = round(lag[0] / 24, 1)
                            ventana = (
                                f" — ventana típica ~{lag[0]/24:.0f} días "
                                f"(hasta {lag[1]/24:.0f}d)"
                            )
                except Exception:
                    pass
                lugar = m.get("nodo_nombre") or f"nodo {m['id_nodo']}"
                logger.warning(
                    f"FIRMA MATCH: estado actual se parece {m['similitud']:.0%} "
                    f"a la firma que precedió {m['event_class']} "
                    f"({lugar}, nodo {m['id_nodo']}, "
                    f"vista {m['recurrencia']} veces){ventana}"
                )

        muro_lags = {}
        try:
            from sentinel_omega.core.precursor.muro_lags import (
                evaluar_muro_lags,
                format_muro_lags,
            )
            muro_lags = evaluar_muro_lags(matches)
            if muro_lags.get("activo"):
                logger.warning(format_muro_lags(muro_lags))
        except Exception as e:
            logger.warning(f"Muro de lags failed (non-blocking): {e}")

        # Nodos DE la predicción: un aviso solo vale si acierta DÓNDE avisó.
        # El Juez valida esta fila solo contra estos nodos (no toda la malla)
        # — sin esto, el modelo nulo de Molchan gana siempre.
        nodos_pred = [
            {"id": m["id_nodo"], "lat": m.get("nodo_lat"),
             "lon": m.get("nodo_lon")}
            for m in matches[:5]
            if m.get("nodo_lat") is not None
        ]
        from sentinel_omega.infrastructure.pipeline.juez_cycle_register import (
            register_cycle_predictions,
        )
        register_cycle_predictions(
            juez, geo, matches=matches, conn=conn,
            muro_lags=muro_lags, nodos_pred=nodos_pred,
        )

        # ── Cimática: snapshot del sistema → patrón nuevo o frecuencia+1 ──
        # Todo alta/incremento dispara la revisión del Padre; si el patrón
        # es nuevo con el Padre activo, o se volvió consistente y está
        # asociado a un tipo de evento, se encola la alerta por correo.
        try:
            from sentinel_omega.core.firmas.cimatica import (
                FRECUENCIA_CONSISTENTE, registrar_snapshot,
            )
            from sentinel_omega.infrastructure.api.correo import encolar_correo

            if features:
                ec_top = matches[0]["event_class"] if matches else None
                snapshots = [(None, ec_top)] + [
                    (m["id_nodo"], m["event_class"]) for m in matches[:3]
                ]
                padre_activo = geo.final_signal.value in ("alert", "watch")
                for id_nodo, ec in snapshots:
                    pid_c, es_nuevo, frec = registrar_snapshot(
                        conn, features, id_nodo=id_nodo, event_class=ec,
                    )
                    if not pid_c:
                        continue
                    # Trigger: el Padre revisa cada alta/incremento
                    logger.info(
                        f"PADRE REVISA cimática: patrón {pid_c} "
                        f"({'nuevo' if es_nuevo else f'frecuencia {frec}'}"
                        f"{f', nodo {id_nodo}' if id_nodo else ', general'})"
                    )
                    if es_nuevo and padre_activo:
                        encolar_correo(
                            conn,
                            asunto=(f"🌀 Sentinel Omega — patrón cimático "
                                    f"NUEVO con Padre en "
                                    f"{geo.final_signal.value.upper()}"),
                            cuerpo=(
                                f"Patrón de telemetría nunca visto "
                                f"(id {pid_c}, "
                                f"{'nodo ' + str(id_nodo) if id_nodo else 'general'}) "
                                f"mientras el Padre está en "
                                f"{geo.final_signal.value.upper()} "
                                f"({geo.confidence:.0%}).\n"
                                f"Telemetría completa guardada en "
                                f"tbl_cimatica_patrones."
                            ),
                            tipo="ALERTA",
                        )
                    elif frec == FRECUENCIA_CONSISTENTE and ec:
                        encolar_correo(
                            conn,
                            asunto=(f"🔁 Sentinel Omega — cimática "
                                    f"CONSISTENTE para {ec}"),
                            cuerpo=(
                                f"El patrón {pid_c} "
                                f"({'nodo ' + str(id_nodo) if id_nodo else 'general'}) "
                                f"alcanzó frecuencia {frec} asociado a {ec}: "
                                f"ya no es coincidencia, es cimática del "
                                f"sistema. El Padre lo tiene en revisión."
                            ),
                            tipo="ALERTA",
                        )
        except Exception as e:
            logger.warning(f"Cimática falló (non-blocking): {e}")

        # AssertivityTracker: los avisos se anclan a SUS nodos al momento
        # de emitirse (la validación + Molchan corre en la pasada del Juez).
        tracker = getattr(runner, "assertivity", None)
        if tracker is not None and geo.final_signal.value in ("alert", "watch"):
            for m in matches[:3]:
                if m.get("nodo_lat") is not None:
                    tracker.record_prediction(
                        m["nodo_lat"], m["nodo_lon"],
                        risk_level=geo.final_signal.value.upper(),
                        fantasma=float(geo.confidence),
                        source=f"nodo{m['id_nodo']}",
                    )

        # El Juez pasa a verificar real vs predicción CADA 4 HORAS (ritmo
        # auto-impuesto en verificacion.py): el ciclo del Padre solo
        # registra; la confrontación con USGS es tarea del Juez.
        from sentinel_omega.infrastructure.pipeline.verificacion import (
            verificar_juez,
        )
        resultado_juez = verificar_juez(conn, tracker=tracker)
        if resultado_juez.get("resueltas"):
            logger.info(
                f"Juez resolvió {resultado_juez['resueltas']} predicciones "
                f"pendientes"
            )
    except Exception as e:
        logger.warning(f"Audit step failed (non-blocking): {e}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sentinel Omega — Precursor Detection Platform Launcher",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single cycle and exit",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Also launch the Streamlit dashboard",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Disable Telegram alerts (dry run mode)",
    )
    parser.add_argument(
        "--backcast", action="store_true",
        help="Run historical backcast (1994-2025) before starting cycles",
    )
    parser.add_argument(
        "--entrenar", action="store_true",
        help="Run signature training over the backcast (Fase 1 + Fase 2)",
    )
    parser.add_argument(
        "--disciplina", action="store_true",
        help="Run background discipline on minor quakes (castigo desde abajo)",
    )
    parser.add_argument(
        "--barrido", action="store_true",
        help="Run daily maintenance sweep (compact history, keep significant)",
    )
    parser.add_argument(
        "--reporte", action="store_true",
        help=(
            "Generate post-training reports (reporte_general + reporte_padre). "
            "Can be combined with --entrenar (runs after training) or standalone."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
