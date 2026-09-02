import yaml
import os
import time
from typing import Optional, Callable, Dict, Any

from memory.shared_context import SharedMemory
from memory.blackboard import Blackboard, TaskStatus
from memory.repository_context import load_repository_context, project_metadata
from agents.researcher import ResearcherAgent
from agents.coder import CoderAgent
from agents.optimizer import OptimizerAgent
from .router import TaskRouter, PipelineType


# Auditoría 2026-08-22: el orquestador guardaba el contexto del repo en
# blackboard.shared_notes["repository_context"], pero NUNCA lo propagaba al
# prompt del Researcher (researcher.py construye su prompt sin esa memoria).
# Ahora se inyecta vía shared_memory.research_context (atributo nuevo en
# SharedMemory) y se reusa también en optimize/síntesis si el orquestador lo
# solicita (modo AUDIT_PROJECT).

class ConsensusOrchestrator:
    """
    Motor central que orquesta el concilio de agentes y el consenso con memoria compartida.
    """
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.ollama_host = self.config["ollama"]["host"]
        self.timeout = self.config["ollama"].get("timeout_seconds", 180)
        self.threshold = self.config["consensus"].get("threshold_score", 80)
        self.max_rounds = self.config["consensus"].get("max_refinement_rounds", 3)
        self.db_path = self.config["memory"].get("sqlite_db", "data/shared_memory.db")

        # Inicialización de agentes expertos con sus modelos asignados
        r_cfg = self.config["roles"]["researcher"]
        c_cfg = self.config["roles"]["coder"]
        o_cfg = self.config["roles"]["optimizer"]

        self.researcher = ResearcherAgent(
            name=r_cfg["name"],
            role="Investigador",
            model=r_cfg["model"],
            fallback_model=r_cfg.get("fallback_model"),
            temperature=r_cfg.get("temperature", 0.3),
            system_prompt=r_cfg["system_prompt"],
            ollama_host=self.ollama_host,
            timeout_seconds=self.timeout,
            num_predict=r_cfg.get("max_tokens", 1500)
        )

        self.coder = CoderAgent(
            name=c_cfg["name"],
            role="Programador",
            model=c_cfg["model"],
            fallback_model=c_cfg.get("fallback_model"),
            temperature=c_cfg.get("temperature", 0.2),
            system_prompt=c_cfg["system_prompt"],
            ollama_host=self.ollama_host,
            timeout_seconds=self.timeout,
            num_predict=c_cfg.get("max_tokens", 1500)
        )

        self.optimizer = OptimizerAgent(
            name=o_cfg["name"],
            role="Optimizador y Árbitro",
            model=o_cfg["model"],
            fallback_model=o_cfg.get("fallback_model"),
            temperature=o_cfg.get("temperature", 0.2),
            system_prompt=o_cfg["system_prompt"],
            ollama_host=self.ollama_host,
            timeout_seconds=self.timeout,
            num_predict=o_cfg.get("max_tokens", 1500)
        )

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run_consensus(
        self,
        user_prompt: str,
        shared_memory: Optional[SharedMemory] = None,
        on_stage_start: Optional[Callable[[str, str, str], None]] = None,
        on_token: Optional[Callable[[str, str], None]] = None,
        on_stage_end: Optional[Callable[[str, Any], None]] = None
    ) -> Blackboard:
        """
        Ejecuta el pipeline completo de consenso con memoria compartida (Blackboard).
        """
        if shared_memory is None:
            shared_memory = SharedMemory(db_path=self.db_path)

        shared_memory.record_user_message(user_prompt)
        pipeline_type = TaskRouter.route_task(user_prompt)
        blackboard = shared_memory.create_task_blackboard(user_prompt, task_type=pipeline_type.value)

        # AUDITORÍA 2026-08-22 — fix #1:
        # cargar el contexto del proyecto UNA sola vez y dejarlo disponible
        # para todos los agentes. Antes esto se guardaba en shared_notes pero
        # nadie lo leía: el Researcher construía su prompt solo con la pregunta.
        repo_ctx = load_repository_context()
        shared_memory.research_context = repo_ctx
        blackboard.shared_notes["repository_context"] = repo_ctx
        blackboard.shared_notes["repository_metadata"] = project_metadata()
        blackboard.log_event("CONTEXT", "Orchestrator", f"Contexto del proyecto inyectado ({len(repo_ctx)} chars)")

        # -------------------------------------------------------------
        # FASE 1: BÚSQUEDA E INVESTIGACIÓN (Nemotron)
        # -------------------------------------------------------------
        if on_stage_start:
            on_stage_start("RESEARCH", self.researcher.name, "Analizando requerimientos e investigando soluciones óptimas...")

        def researcher_stream(tok: str):
            if on_token:
                on_token("RESEARCH", tok)

        research_artifact = self.researcher.run_research(shared_memory, stream_callback=researcher_stream)
        if on_stage_end:
            on_stage_end("RESEARCH", research_artifact)

        # -------------------------------------------------------------
        # FASE 2: IMPLEMENTACIÓN DE CÓDIGO INICIAL (DeepSeek)
        # -------------------------------------------------------------
        if on_stage_start:
            on_stage_start("CODING", self.coder.name, "Escribiendo código limpio y modular según la memoria compartida...")

        def coder_stream(tok: str):
            if on_token:
                on_token("CODING", tok)

        code_artifact = self.coder.build_code(shared_memory, stream_callback=coder_stream)
        if on_stage_end:
            on_stage_end("CODING", code_artifact)

        # -------------------------------------------------------------
        # FASE 3: BUCLE DE REVISIÓN, OPTIMIZACIÓN Y CONSENSO (Gemma)
        # -------------------------------------------------------------
        round_count = 0
        consensus_achieved = False

        # max_refinement_rounds = 0 significa SIN LÍMITE (loop infinito hasta umbral)
        # Esto garantiza veracidad sobre velocidad — el concilio itera hasta ≥ threshold.
        infinite_loop = (self.max_rounds == 0)

        while infinite_loop or round_count < self.max_rounds:
            round_count += 1
            if on_stage_start:
                on_stage_start(
                    "REVIEW",
                    self.optimizer.name,
                    f"Auditoría técnica y cálculo de consenso (Ronda {round_count}) [umbral={self.threshold}]..."
                )

            def optimizer_stream(tok: str):
                if on_token:
                    on_token("REVIEW", tok)

            critique = self.optimizer.evaluate_solution(
                shared_memory,
                threshold=self.threshold,
                stream_callback=optimizer_stream
            )
            if on_stage_end:
                on_stage_end("REVIEW", critique)

            if critique.passed:
                consensus_achieved = True
                if on_stage_start:
                    on_stage_start("REVIEW", self.optimizer.name, f"✅ CONSENSO ALCANZADO en ronda {round_count} (score={critique.score}/100 ≥ {self.threshold})")
                break

            # Si no pasa el umbral, el Programador refina (siempre en loop infinito;
            # en modo limitado solo si quedan rondas)
            if infinite_loop or round_count < self.max_rounds:
                if on_stage_start:
                    on_stage_start(
                        "REFINING",
                        self.coder.name,
                        f"Refinando código según auditoría del Optimizador (Puntaje actual: {critique.score}/100, ronda {round_count})..."
                    )

                def refiner_stream(tok: str):
                    if on_token:
                        on_token("REFINING", tok)

                refined_code = self.coder.refine_code(shared_memory, stream_callback=refiner_stream)
                if on_stage_end:
                    on_stage_end("REFINING", refined_code)
            else:
                # Rondas agotadas sin consenso
                if on_stage_start:
                    on_stage_start("REVIEW", self.optimizer.name, f"⚠️ Rondas máximas ({self.max_rounds}) alcanzadas sin consenso (último score={critique.score}/100)")
                break

        # -------------------------------------------------------------
        # FASE 4: SÍNTESIS FINAL CONVERGENTE
        # -------------------------------------------------------------
        if on_stage_start:
            on_stage_start("SYNTHESIS", self.optimizer.name, "Generando síntesis final consensuada...")

        def synth_stream(tok: str):
            if on_token:
                on_token("SYNTHESIS", tok)

        final_answer = self.optimizer.synthesize_consensus(shared_memory, stream_callback=synth_stream)
        blackboard.final_synthesis = final_answer  # AUDITORÍA 2026-08-22: antes faltaba esta asignación.
        if on_stage_end:
            on_stage_end("SYNTHESIS", final_answer)

        # Persistir todo en SQLite
        shared_memory.persist_current_state()
        return blackboard

    def audit_project(self, focus: str = "") -> Blackboard:
        """
        Modo AUDIT_PROJECT — corre el concilio específicamente contra el
        repositorio de Sentinel Omega. El Researcher usa como ancla el resumen
        canónico + los archivos prioritarios del repo aguas abajo; el Optimizer
        evalúa cumplimiento de las reglas duras (cero sintéticos, secretos
        solo por entorno, etc.) y emite veredictos accionables.
        """
        prompt = (
            "AUDITORÍA DEL PROYECTO SENTINEL OMEGA. "
            "Revisa los archivos prioritarios (AGENTS.md, CLAUDE.md, README.md, "
            "CHANGELOG, INFORME_CORRECCIONES, HANDOFF, RESTORE_SCHEMA) que ya "
            "tienes inyectados como contexto. "
            "Produce una lista priorizada de hallazgos: (a) brechas entre el "
            "código y la documentación, (b) riesgo de regresión de las reglas "
            "duras, (c) cosas que el Concilio cree que faltan (tests, mocks, "
            "doc, hooks), (d) oportunidades de automatización. "
            "Cada hallazgo lleva severidad (rojo/amarillo/verde), archivo y "
            "línea aproximada, y acción sugerida concreta. "
        )
        if focus:
            prompt += f"\nFoco adicional de la auditoría: {focus}"
        shared = SharedMemory(db_path=self.db_path)
        return self.run_consensus(user_prompt=prompt, shared_memory=shared)

    def health(self) -> Dict[str, Any]:
        """Estado rápido del concilio para /api/health y debugging."""
        info: Dict[str, Any] = {
            "ollama_host": self.ollama_host,
            "timeout": self.timeout,
            "consensus_threshold": self.threshold,
            "max_refinement_rounds": self.max_rounds,
            "db_path": self.db_path,
            "agents": {
                "researcher": {
                    "name": self.researcher.name,
                    "model": self.researcher.model,
                    "available": self.researcher.check_availability(),
                },
                "coder": {
                    "name": self.coder.name,
                    "model": self.coder.model,
                    "available": self.coder.check_availability(),
                },
                "optimizer": {
                    "name": self.optimizer.name,
                    "model": self.optimizer.model,
                    "available": self.optimizer.check_availability(),
                },
            },
            "context_injector": project_metadata(),
        }
        return info
