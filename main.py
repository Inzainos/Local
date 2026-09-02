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
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Ruta al archivo de configuración YAML"
    )
    parser.add_argument(
        "--task",
        "-t",
        type=str,
        default=None,
        help="Ejecutar una tarea directamente desde la línea de comandos"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Ejecutar auditoría completa del proyecto Sentinel Omega (usa modo AUDIT_PROJECT)"
    )
    parser.add_argument(
        "--focus",
        type=str,
        default="",
        help="Foco adicional para la auditoría (ej: 'tests', 'migraciones', 'secretos')"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Iniciar el servidor de interfaz web gráfica"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Puerto para el servidor web (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host para web (default: 127.0.0.1; usa 0.0.0.0 para exponer en red)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verificar estado de Ollama y disponibilidad de modelos"
    )

    args = parser.parse_args()

    if args.check:
        print("[*] Verificando modelos en Ollama...")
        orch = ConsensusOrchestrator(config_path=args.config)
        print(f"  • {orch.researcher.name} ({orch.researcher.model}): {'✅ Disponible' if orch.researcher.check_availability() else '⚠️ No encontrado'}")
        print(f"  • {orch.coder.name} ({orch.coder.model}): {'✅ Disponible' if orch.coder.check_availability() else '⚠️ No encontrado'}")
        print(f"  • {orch.optimizer.name} ({orch.optimizer.model}): {'✅ Disponible' if orch.optimizer.check_availability() else '⚠️ No encontrado'}")
        sys.exit(0)

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

    # Modo interactivo por defecto
    interactive_loop(config_path=args.config)

if __name__ == "__main__":
    main()
