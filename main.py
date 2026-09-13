#!/usr/bin/env python3
import sys
import argparse
from cli import interactive_loop, execute_task, run_audit
from engine.orchestrator import ConsensusOrchestrator
from memory.shared_context import SharedMemory

def main():
    parser = argparse.ArgumentParser(
        description="Sistema Multi-Agente de Consenso de Expertos con Memoria Compartida (Ollama)"
    )
    parser.add_argument("--config", type=str, default="config.yaml", help="Ruta al YAML de configuracion")
    parser.add_argument("--task", "-t", type=str, default=None, help="Ejecutar una tarea directa")
    parser.add_argument("--audit", action="store_true", help="Ejecutar auditoria del proyecto")
    parser.add_argument("--focus", type=str, default="", help="Foco adicional para auditoria")
    parser.add_argument("--web", action="store_true", help="Iniciar interfaz web")
    parser.add_argument("--port", type=int, default=8000, help="Puerto web")
    parser.add_argument("--host", type=str, default=None, help="Host web")
    parser.add_argument("--check", action="store_true", help="Verificar Ollama y modelos Concilio")

    args = parser.parse_args()

    if args.check:
        print("[*] Verificando Concilio / Ollama...")
        orch = ConsensusOrchestrator(config_path=args.config)
        health = orch.health()
        conc = health.get("concilio") or {}
        print(f"  Host: {health.get('ollama_host')}")
        print(f"  Umbral: {health.get('consensus_threshold')}")
        print(f"  max_refinement_rounds: {health.get('max_refinement_rounds')}")
        print(f"  Sesiones: {conc.get('sessions_dir')} (exists={conc.get('sessions_dir_exists')})")
        print(f"  Sentinel injection: {conc.get('inject_sentinel_architecture', getattr(orch, 'inject_sentinel', False))}")
        order = conc.get("order") or ["research", "code", "review", "refine?", "synthesis"]
        print(f"  Orden: {' -> '.join(order)}")
        for key in ("researcher", "coder", "optimizer"):
            a = health["agents"][key]
            flag = "OK" if a["available"] else "MISSING"
            print(f"  - [{a.get('tier', key)}] {a['name']} ({a['model']}): {flag}")
        loaded = conc.get("loaded_now") or []
        print(f"  Modelos cargados ahora: {loaded if loaded else '(ninguno)'}")
        try:
            orch.lifecycle.unload_all()
        except Exception:
            pass
        missing = [k for k, a in health["agents"].items() if not a["available"]]
        sys.exit(1 if missing else 0)


    if args.web:
        from web_ui import start_server
        start_server(host=args.host, port=args.port)
        return

    if args.audit:
        orch = ConsensusOrchestrator(config_path=args.config)
        mem = SharedMemory(db_path=orch.db_path)
        run_audit(orch, mem, args.focus)
        return

    if args.task:
        orch = ConsensusOrchestrator(config_path=args.config)
        mem = SharedMemory(db_path=orch.db_path)
        execute_task(orch, mem, args.task)
        return

    interactive_loop(config_path=args.config)

if __name__ == "__main__":
    main()
