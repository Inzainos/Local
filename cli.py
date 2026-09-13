import sys
import os
import time
from typing import Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner
from rich.rule import Rule

from engine.orchestrator import ConsensusOrchestrator
from memory.shared_context import SharedMemory

console = Console()


def render_banner():
    banner_text = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║       CONCILIO — cadena secuencial (standalone)                  ║
    ║   • Worker-Research (qwen2.5:1.5b / concilio-worker)             ║
    ║   • Worker-Coder    (qwen2.5:1.5b / concilio-worker)             ║
    ║   • Árbitro         (gemma4:26b / concilio-arbitro)              ║
    ║   Umbral 85 · unload entre roles · sessions/*.concilio           ║
    ╚══════════════════════════════════════════════════════════════════╝
    """
    console.print(Panel(banner_text, style="bold cyan", expand=False))


def execute_task(orchestrator: ConsensusOrchestrator, shared_memory: SharedMemory, prompt: str):
    console.print(Rule("[bold green]Iniciando Tarea (pipeline secuencial)[/bold green]"))
    console.print(f"[bold yellow]Petición:[/bold yellow] {prompt}\n")

    current_stage = ""
    current_agent = ""

    def on_stage_start(stage: str, agent: str, msg: str):
        nonlocal current_stage, current_agent
        current_stage = stage
        current_agent = agent
        icon = {"RESEARCH": "🔍", "CODING": "💻", "REVIEW": "⚖️", "REFINING": "🛠️", "SYNTHESIS": "✨"}.get(stage, "🤖")
        console.print(f"\n{icon} [bold magenta]{agent}[/bold magenta] - [cyan]{msg}[/cyan]")

    def on_token(stage: str, token: str):
        pass

    def on_stage_end(stage: str, artifact: Any):
        if stage == "REVIEW":
            score = artifact.score
            color = "green" if artifact.passed else "yellow"
            console.print(f"   📊 [bold {color}]Puntaje de Consenso: {score}/100[/bold {color}] - {'[Aprobado ✅]' if artifact.passed else '[Requiere Refinamiento ⚠️]'}")
        elif stage == "RESEARCH":
            console.print("   ✅ [dim]Investigación registrada + session .concilio[/dim]")
        elif stage in ["CODING", "REFINING"]:
            console.print("   ✅ [dim]Código actualizado + session .concilio[/dim]")

    with console.status("[bold blue]Concilio coordinando (1 modelo a la vez)...[/bold blue]", spinner="dots"):
        blackboard = orchestrator.run_consensus(
            user_prompt=prompt,
            shared_memory=shared_memory,
            on_stage_start=on_stage_start,
            on_token=on_token,
            on_stage_end=on_stage_end
        )

    console.print("\n" + "="*70)
    console.print(Rule("[bold green]RESPUESTA FINAL CONSENSUADA[/bold green]"))
    console.print(Markdown(blackboard.final_synthesis))
    console.print("="*70 + "\n")

    table = Table(title="Métricas del Consenso", show_header=True, header_style="bold cyan")
    table.add_column("Métrica", style="dim")
    table.add_column("Valor", justify="right")
    table.add_row("ID de Tarea", blackboard.task_id)
    table.add_row("Session ID", blackboard.session_id)
    table.add_row("Puntaje Final", f"{blackboard.consensus_score}/100")
    table.add_row("Consenso Alcanzado", "Sí ✅" if blackboard.consensus_reached else "Límite Rondas ⚠️")
    table.add_row("Rondas de Refinamiento", str(blackboard.refinement_rounds))
    table.add_row("Session file", f"data/sessions/{blackboard.session_id}.concilio")
    console.print(table)


def run_audit(orchestrator: ConsensusOrchestrator, shared_memory: SharedMemory, focus: str = ""):
    """Auditoría opcional (sin forzar corpus Sentinel si injector está off)."""
    console.print(Rule("[bold yellow]MODO AUDITORÍA[/bold yellow]"))
    if focus:
        console.print(f"[bold]Foco:[/bold] {focus}\n")

    def on_stage_start(stage: str, agent: str, msg: str):
        icon = {"RESEARCH": "🔍", "CODING": "💻", "REVIEW": "⚖️", "REFINING": "🛠️", "SYNTHESIS": "✨"}.get(stage, "🤖")
        console.print(f"\n{icon} [bold magenta]{agent}[/bold magenta] - [cyan]{msg}[/cyan]")

    def on_token(stage: str, token: str):
        pass

    def on_stage_end(stage: str, artifact: Any):
        if stage == "REVIEW":
            score = artifact.score
            color = "green" if artifact.passed else "yellow"
            console.print(f"   📊 [bold {color}]Puntaje: {score}/100[/bold {color}]")

    with console.status("[bold blue]Auditoría en curso...[/bold blue]", spinner="dots"):
        blackboard = orchestrator.audit_project(focus=focus)

    console.print("\n" + "="*70)
    console.print(Rule("[bold yellow]INFORME[/bold yellow]"))
    console.print(Markdown(blackboard.final_synthesis))
    console.print("="*70 + "\n")


def interactive_loop(config_path: str = "config.yaml"):
    render_banner()
    orchestrator = ConsensusOrchestrator(config_path=config_path)
    shared_memory = SharedMemory(db_path=orchestrator.db_path)

    console.print("[dim]Escribe tu consulta. 'salir' para terminar. Ver CONCILIO.md[/dim]\n")

    while True:
        try:
            prompt = console.input("[bold cyan]Concilio >> [/bold cyan]").strip()
            if not prompt:
                continue
            if prompt.lower() in ["salir", "exit", "quit", "q"]:
                console.print("[green]¡Hasta pronto![/green]")
                break
            if prompt.lower() == "/blackboard":
                if shared_memory.active_blackboard:
                    console.print(Markdown(shared_memory.active_blackboard.to_markdown_summary()))
                else:
                    console.print("[yellow]Aún no hay una pizarra activa.[/yellow]")
                continue

            execute_task(orchestrator, shared_memory, prompt)
        except KeyboardInterrupt:
            console.print("\n[yellow]Operación cancelada por el usuario.[/yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]Error en ejecución:[/bold red] {e}")
