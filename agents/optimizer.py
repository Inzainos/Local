import re
from typing import Optional, Callable, Tuple
from .base_agent import BaseExpertAgent
from memory.shared_context import SharedMemory
from memory.blackboard import CritiqueArtifact


class OptimizerAgent(BaseExpertAgent):
    """
    Experto 3: Crítico Técnico, Optimizador y Árbitro de Consenso (Gemma).
    Audita el código, evalúa complejidad, seguridad, asigna puntaje y sintetiza la solución final.
    AUDITORÍA 2026-08-22: ahora evalúa también cumplimiento de las reglas duras del proyecto
    Sentinel Omega (cero sintéticos, secretos solo entorno, migración forward-only, tests, Regla Cero).
    """
    def evaluate_solution(
        self,
        shared_memory: SharedMemory,
        threshold: int = 80,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> CritiqueArtifact:
        blackboard = shared_memory.blackboard
        context = blackboard.get_context_for_optimizer()

        # AUDITORÍA 2026-08-22: contexto del proyecto para auditar cumplimiento
        project_context = getattr(shared_memory, "research_context", None)
        project_section = f"\n\n=== REGLAS DURAS DEL PROYECTO (OBLIGATORIO CUMPLIR) ===\n{project_context}\n" if project_context else ""

        prompt = f"""{context}{project_section}

INSTRUCCIÓN PARA EL CRÍTICO Y OPTIMIZADOR:
Audita rigurosamente la solución de código propuesta:
1. RENDIMIENTO Y COMPLEJIDAD: ¿Es óptima la complejidad temporal O(...) y espacial O(...)? ¿Hay cuellos de botella?
2. SEGURIDAD Y CASOS BORDE: ¿Maneja entradas inválidas, nulos o fallos de red/memoria?
3. CALIDAD Y MEJORES PRÁCTICAS: ¿El código es limpio, idiomático y mantenible?
4. CUMPLIMIENTO REGLAS DURAS SENTINEL OMEGA (CRÍTICO):
   - Secretos SOLO por entorno (os.environ), NUNCA hardcodeados
   - Cero datos sintéticos; faltante = NULL; LOCF solo desde reales
   - Migración forward-only (EXPECTED_COLUMNS + _migrate_add_missing_columns)
   - sentinel_omega/data/ en .gitignore — mkdir(parents=True, exist_ok=True)
   - Tests deben pasar antes de commitear
   - Regla Cero: nunca asumas, siempre revisa (flujo punta a punta)
5. OPTIMIZACIONES SUGERIDAS: Detalla mejoras concretas con fragmentos de código si aplica.
6. PUNTUACIÓN DE CONSENSO: Califica la solución de 0 a 100 y colócala OBLIGATORIAMENTE en este formato:
   [PUNTUACION_CONSENSO: XX]

Si la puntuación es >= {threshold}, declara el consenso APROBADO. Si es menor, indica qué corregir para el siguiente pase.
"""
        response_text = self.generate(prompt=prompt, stream_callback=stream_callback)
        
        # Extraer puntaje con Regex
        score = self._extract_score(response_text)
        artifact = blackboard.add_critique(response_text, score=score, threshold=threshold)
        return artifact

    def synthesize_consensus(
        self,
        shared_memory: SharedMemory,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Genera la respuesta final pulida combinando la investigación, código y optimizaciones."""
        blackboard = shared_memory.blackboard
        
        prompt = f"""=== CONCILIO DE EXPERTOS: SÍNTESIS FINAL ===
TAREA ORIGINAL:
{blackboard.user_prompt}

INVESTIGACIÓN (NEMOTRON):
{blackboard.research.raw_content if blackboard.research else "N/A"}

CÓDIGO APROBADO (DEEPSEEK):
{blackboard.code_proposal.raw_content if blackboard.code_proposal else "N/A"}

AUDITORÍA DE CONSENSO (GEMMA):
Puntaje alcanzado: {blackboard.consensus_score}/100

INSTRUCCIÓN:
Genera la presentación final definitiva para el usuario. Debe contener:
1. 💡 Resumen y enfoque estratégico.
2. 🚀 Código final consolidado y listo para producción con sus dependencias y tipado.
3. ⚡ Optimizaciones y notas de rendimiento clave.
4. 📋 Guía rápida de uso/ejecución.
"""
        synthesis = self.generate(prompt=prompt, stream_callback=stream_callback)
        blackboard.final_synthesis = synthesis
        return synthesis

    def _extract_score(self, text: str) -> int:
        match = re.search(r"\[PUNTUACION_CONSENSO:\s*(\d{1,3})\]", text, re.IGNORECASE)
        if match:
            try:
                val = int(match.group(1))
                return max(0, min(100, val))
            except ValueError:
                pass
        
        # Fallback de búsqueda de números asociados a score / puntuacion
        alt_match = re.search(r"(?:puntuaci[oó]n|score|calificaci[oó]n)[:=\s]+(\d{1,3})\s*/\s*100", text, re.IGNORECASE)
        if alt_match:
            try:
                return max(0, min(100, int(alt_match.group(1))))
            except ValueError:
                pass

        # Si el modelo aprobó explícitamente pero no puso tag
        if "consenso alcanzado" in text.lower() or "aprobado" in text.lower():
            return 85
        return 75