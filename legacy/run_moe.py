#!/usr/bin/env python3
"""CLI para el perfil MoE + Capitán del Concilio (profiles/moe_captain.yaml).
No toca config.yaml ni el bot de Telegram en producción.

Uso:
    python run_moe.py "tarea a resolver"
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

from engine.moe_captain import run_moe  # noqa: E402

PROFILE_PATH = "profiles/moe_captain.yaml"


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python run_moe.py <tarea>")
        sys.exit(1)
    task = " ".join(sys.argv[1:])
    outcome = run_moe(PROFILE_PATH, task)

    print("\n" + "=" * 70)
    print(
        f"Tipo: {outcome['task_type']}  Worker: {outcome['worker']} "
        f"({outcome['worker_model']})  Auditor: {outcome['auditor']} "
        f"({outcome['auditor_model']})"
    )
    print(
        f"Worker score: {outcome['worker_score']}  Audit score: {outcome['audit_score']}  "
        f"Rondas: {outcome['rounds']}  Tiempo: {outcome['elapsed_s']}s"
    )
    print("=" * 70)
    print("\n--- RESULTADO ---\n")
    print(outcome["result"])


if __name__ == "__main__":
    main()
