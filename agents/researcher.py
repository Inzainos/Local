from typing import Optional, Callable
from .base_agent import BaseExpertAgent
from memory.shared_context import SharedMemory
from memory.blackboard import ResearchArtifact


class ResearcherAgent(BaseExpertAgent):
    """
    Experto 1: Investigador y Buscador de Información (Nemotron).
    Analiza los requisitos, explora mejores prácticas, casos borde y arquitectura técnica.
    AUDITORÍA 2026-08-22: ahora usa shared_memory.research_context (inyectado por el
    Orchestrator al crear el blackboard) para que la investigación sea **anclada al
    proyecto real** (reglas duras, arquitectura Sentinel Omega, estado actual).
    """
    def run_research(
        self,
        shared_memory: SharedMemory,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> ResearchArtifact:
        blackboard = shared_memory.blackboard
        user_query = blackboard.user_prompt

        # AUDITORÍA 2026-08-22: inyectar el contexto del repo aguas abajo
        # (canonical summary + AGENTS.md + CHANGELOG + INFORME + HANDOFF + ...).
        # Si el orchestrator no lo cargó (caso raro), caemos a cargar bajo demanda.
        repo_context = getattr(shared_memory, "research_context", None)
        if not repo_context:
            from memory.repository_context import load_repository_context
            repo_context = load_repository_context()

        # Construcción del prompt especializado ANCLADO AL PROYECTO
        prompt = f"""CONTEXTO DEL PROYECTO (Sentinel Omega — reglas duras, arquitectura, estado actual):
{repo_context}

---

TAREA A INVESTIGAR:
{user_query}

Por favor realiza un análisis técnico exhaustivo **sobre la base del proyecto real** y genera un reporte estructurado con las siguientes secciones:
1. DESGLOSE DE REQUERIMIENTOS: ¿Qué se necesita exactamente? (Referencia reglas del proyecto si aplica)
2. ENFOQUE TÉCNICO Y ARQUITECTURA: Algoritmo óptimo, patrones recomendados y librerías clave **compatibles con el stack del proyecto**.
3. CASOS BORDE Y CONSIDERACIONES DE SEGURIDAD: Errores comunes, validaciones críticas y limitaciones **según las reglas duras del proyecto** (cero sintéticos, secretos solo por entorno, migración forward-only, etc.).
4. GUÍA PARA EL PROGRAMADOR: Pautas clave para que el desarrollador construya una solución perfecta **que pase los tests y cumpla la Regla Cero**.

Escribe tu reporte de forma clara, técnica y estructurada.
"""
        response_text = self.generate(prompt=prompt, stream_callback=stream_callback)
        artifact = blackboard.update_research(response_text)
        return artifact
