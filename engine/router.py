from enum import Enum

class PipelineType(str, Enum):
    FULL_CONSENSUS_CODING = "FULL_CONSENSUS_CODING"  # Researcher -> Coder -> Optimizer -> Consensus Loop
    RESEARCH_AND_ANALYSIS = "RESEARCH_AND_ANALYSIS"  # Researcher -> Optimizer / Synthesis
    CODE_OPTIMIZATION = "CODE_OPTIMIZATION"          # Coder -> Optimizer -> Refinement
    GENERAL_QA = "GENERAL_QA"                        # Researcher -> Optimizer

class TaskRouter:
    """Analiza la consulta del usuario y selecciona el flujo de trabajo multi-agente idóneo."""
    @staticmethod
    def route_task(prompt: str) -> PipelineType:
        p = prompt.lower()
        code_keywords = [
            "código", "codigo", "script", "programa", "funcion", "función", "clase",
            "python", "javascript", "bash", "sql", "api", "desarrolla", "crea un", "implementa",
            "algoritmo", "debug", "corrige", "refactoriza", "app", "aplicacion"
        ]
        research_keywords = [
            "investiga", "busca", "explica", "compara", "qué es", "que es", "diferencias",
            "analiza", "cuáles son", "cuales son", "historia de", "definicion"
        ]
        optimize_keywords = [
            "optimiza", "mejora este", "haz más rápido", "haz mas rapido", "reduce memoria", "audita"
        ]

        # Auditar un PROYECTO es analizar, no programar. "audita" vivia solo en
        # optimize_keywords, condicionado a que el prompt trajera codigo (```,
        # def, class): auditar un repositorio entero nunca cumple eso, asi que
        # caia al default --- que es FULL_CONSENSUS_CODING. Medido el
        # 2026-09-24: la auditoria gasto 70 de 105 minutos en el coder y
        # entrego un ConfigurationManager inventado en vez de hallazgos.
        auditoria_sin_codigo = (
            any(k in p for k in ("auditoría", "auditoria", "audita", "hallazgos"))
            and not ("```" in prompt or "def " in prompt or "class " in prompt)
        )
        if auditoria_sin_codigo:
            return PipelineType.RESEARCH_AND_ANALYSIS

        if any(k in p for k in optimize_keywords) and ("```" in prompt or "def " in prompt or "class " in prompt):
            return PipelineType.CODE_OPTIMIZATION

        if any(k in p for k in code_keywords):
            return PipelineType.FULL_CONSENSUS_CODING

        if any(k in p for k in research_keywords):
            return PipelineType.RESEARCH_AND_ANALYSIS

        return PipelineType.FULL_CONSENSUS_CODING
