from typing import Optional, Callable
from .base_agent import BaseExpertAgent
from memory.shared_context import SharedMemory
from memory.blackboard import CodeArtifact


class CoderAgent(BaseExpertAgent):
    """
    Experto 2: Ingeniero de Software y Desarrollador (DeepSeek).
    Lee la Memoria Compartida (Blackboard) y escribe el código fuente limpio y tipado.
    AUDITORÍA 2026-08-22: ahora recibe el contexto del proyecto (shared_memory.research_context)
    para que el código cumpla el stack real, reglas duras y arquitectura Sentinel Omega.
    """
    def build_code(
        self,
        shared_memory: SharedMemory,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> CodeArtifact:
        blackboard = shared_memory.blackboard
        context = blackboard.get_context_for_coder()

        # AUDITORÍA 2026-08-22: pasar el contexto del proyecto al Coder
        # (reglas duras: cero sintéticos, secretos solo por entorno, migración forward-only,
        # tests antes de commit, Regla Cero: nunca asumas, siempre revisa).
        project_context = getattr(shared_memory, "research_context", None)
        project_section = f"\n\n=== CONTEXTO DEL PROYECTO (REGLAS DURAS + STACK) ===\n{project_context}\n" if project_context else ""

        prompt = f"""{context}{project_section}

INSTRUCCIÓN PARA EL PROGRAMADOR:
Con base en la investigación y especificaciones anteriores en la Memoria Compartida:
1. Diseña e implementa la solución completa, lista para producción.
2. Asegúrate de incluir tipos (type hints), control de excepciones y comentarios explicativos.
3. Envuelve el código completo en bloques de código markdown legibles (```lenguaje ... ```).
4. Explica brevemente la estructura y cómo ejecutar la solución.
5. **El código debe cumplir las reglas duras del proyecto Sentinel Omega** (ver sección contexto):
   - Secretos SOLO por entorno (os.environ), NUNCA hardcodeados
   - Cero datos sintéticos; faltante = NULL; LOCF solo desde reales
   - Migración forward-only (EXPECTED_COLUMNS + _migrate_add_missing_columns)
   - sentinel_omega/data/ en .gitignore — crear con mkdir(parents=True, exist_ok=True)
   - Tests deben pasar antes de commitear

"""
        response_text = self.generate(prompt=prompt, stream_callback=stream_callback)
        artifact = blackboard.update_code(response_text, is_refinement=False)
        return artifact

    def refine_code(
        self,
        shared_memory: SharedMemory,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> CodeArtifact:
        blackboard = shared_memory.blackboard
        context = blackboard.get_context_for_refinement()

        project_context = getattr(shared_memory, "research_context", None)
        project_section = f"\n\n=== CONTEXTO DEL PROYECTO (REGLAS DURAS + STACK) ===\n{project_context}\n" if project_context else ""

        prompt = f"""{context}{project_section}

INSTRUCCIÓN DE REFINAMIENTO:
1. Aplica estrictamente todas las correcciones, refactorizaciones y optimizaciones solicitadas por el Optimizador.
2. Presenta el código corregido y optimizado completo en un bloque markdown (```lenguaje ... ```).
3. Explica puntualmente qué cambios realizaste para resolver cada punto de la auditoría.
4. **El código refinado debe seguir cumpliendo las reglas duras del proyecto Sentinel Omega**.

"""
        response_text = self.generate(prompt=prompt, stream_callback=stream_callback)
        artifact = blackboard.update_code(response_text, is_refinement=True)
        return artifact