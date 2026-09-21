#!/usr/bin/env python3
"""CLI para correr el pipeline de un perfil independiente del Concilio
(profiles/investigacion.yaml, profiles/general.yaml). No toca config.yaml
ni el bot de Telegram en producción.

Uso:
    # Pipeline completo (researcher -> coder -> optimizer, con refinamiento)
    python run_profile.py profiles/investigacion.yaml "tarea a resolver"

    # Solo la etapa de investigación (rol ligero), sin coder ni optimizer —
    # más rápido y barato cuando solo se necesita un archivo de investigación.
    python run_profile.py profiles/investigacion.yaml "tarea" --research-only --out archivo.md
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

from engine.profile_pipeline import load_profile, run_pipeline, run_researcher_stage  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runner de perfiles independientes del Concilio")
    parser.add_argument("profile", help="Ruta al YAML del perfil (profiles/investigacion.yaml o profiles/general.yaml)")
    parser.add_argument("task", nargs="+", help="Descripción de la tarea")
    parser.add_argument(
        "--research-only", action="store_true",
        help="Corre solo el rol de investigación (ligero) y sale — sin coder ni optimizer",
    )
    parser.add_argument(
        "--out", metavar="PATH",
        help="Guarda el resultado en este archivo además de imprimirlo",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    task = " ".join(args.task)

    if args.research_only:
        profile = load_profile(args.profile)
        host = profile["ollama"]["host"]
        research = run_researcher_stage(profile["roles"]["researcher"], host, task)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(research)
            print(f"Guardado en: {args.out}\n")
        print(research)
        return

    result = run_pipeline(args.profile, task)

    print("\n" + "=" * 70)
    print(f"Score: {result['score']}  Rondas: {result['rounds']}  Tiempo: {result['elapsed_s']}s")
    print("=" * 70)
    print("\n--- INVESTIGACIÓN ---\n")
    print(result["research"])
    print("\n--- CÓDIGO/PROPUESTA FINAL ---\n")
    print(result["code"])
    print("\n--- AUDITORÍA FINAL ---\n")
    print(result["audit"])

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(f"# Investigación\n\n{result['research']}\n\n")
            f.write(f"# Propuesta\n\n{result['code']}\n\n")
            f.write(f"# Auditoría (score={result['score']})\n\n{result['audit']}\n")
        print(f"\nGuardado en: {args.out}")


if __name__ == "__main__":
    main()
