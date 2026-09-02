import time
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RESEARCHING = "RESEARCHING"
    CODING = "CODING"
    REVIEWING = "REVIEWING"
    REFINING = "REFINING"
    CONSENSUS_REACHED = "CONSENSUS_REACHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ResearchArtifact(BaseModel):
    task_summary: str = ""
    key_findings: List[str] = Field(default_factory=list)
    recommended_approach: str = ""
    edge_cases_and_risks: List[str] = Field(default_factory=list)
    suggested_libraries: List[str] = Field(default_factory=list)
    raw_content: str = ""
    created_at: float = Field(default_factory=time.time)

class CodeArtifact(BaseModel):
    language: str = "python"
    code: str = ""
    explanation: str = ""
    complexity: str = ""
    raw_content: str = ""
    created_at: float = Field(default_factory=time.time)

class CritiqueArtifact(BaseModel):
    round_num: int = 1
    score: int = 0  # 0 to 100
    passed: bool = False
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    optimizations_suggested: List[str] = Field(default_factory=list)
    raw_content: str = ""
    created_at: float = Field(default_factory=time.time)

class Blackboard(BaseModel):
    task_id: str
    session_id: str
    user_prompt: str
    task_type: str = "FULL_CONSENSUS_CODING"
    status: TaskStatus = TaskStatus.PENDING
    
    # Artefactos producidos por los agentes
    research: Optional[ResearchArtifact] = None
    code_proposal: Optional[CodeArtifact] = None
    critiques: List[CritiqueArtifact] = Field(default_factory=list)
    refinement_history: List[CodeArtifact] = Field(default_factory=list)
    
    # Consenso final
    refinement_rounds: int = 0
    consensus_score: int = 0
    consensus_reached: bool = False
    final_synthesis: str = ""
    
    # Espacio libre compartido (pizarra para notas entre agentes)
    shared_notes: Dict[str, Any] = Field(default_factory=dict)
    execution_timeline: List[Dict[str, Any]] = Field(default_factory=list)

    def log_event(self, stage: str, agent: str, message: str):
        self.execution_timeline.append({
            "timestamp": time.time(),
            "stage": stage,
            "agent": agent,
            "message": message
        })

    def update_research(self, raw_content: str) -> ResearchArtifact:
        self.research = ResearchArtifact(
            raw_content=raw_content,
            task_summary=self.user_prompt[:200]
        )
        self.status = TaskStatus.CODING
        self.log_event("RESEARCH", "Researcher", "Investigación completada y registrada en pizarra")
        return self.research

    def update_code(self, raw_content: str, is_refinement: bool = False) -> CodeArtifact:
        # Extraer código markdown si está disponible
        code_block = ""
        lines = raw_content.splitlines()
        inside_code = False
        lang = "python"
        extracted = []
        for line in lines:
            if line.startswith("```"):
                if inside_code:
                    inside_code = False
                else:
                    inside_code = True
                    tag = line.strip("`").strip()
                    if tag:
                        lang = tag
                continue
            if inside_code:
                extracted.append(line)
        
        if extracted:
            code_block = "\n".join(extracted)
        else:
            code_block = raw_content

        artifact = CodeArtifact(
            language=lang,
            code=code_block,
            raw_content=raw_content
        )

        if is_refinement and self.code_proposal:
            self.refinement_history.append(self.code_proposal)
            self.refinement_rounds += 1
            self.log_event("REFINEMENT", "Coder", f"Refinamiento ronda {self.refinement_rounds} completado")
        else:
            self.log_event("CODE", "Coder", "Propuesta de código inicial registrada en pizarra")

        self.code_proposal = artifact
        self.status = TaskStatus.REVIEWING
        return artifact

    def add_critique(self, raw_content: str, score: int, threshold: int = 80) -> CritiqueArtifact:
        passed = score >= threshold
        critique = CritiqueArtifact(
            round_num=len(self.critiques) + 1,
            score=score,
            passed=passed,
            raw_content=raw_content
        )
        self.critiques.append(critique)
        self.consensus_score = score
        self.consensus_reached = passed
        
        if passed:
            self.status = TaskStatus.CONSENSUS_REACHED
            self.log_event("REVIEW", "Optimizer", f"Consenso ALCANZADO (Puntaje: {score}/100)")
        else:
            self.status = TaskStatus.REFINING
            self.log_event("REVIEW", "Optimizer", f"Revisión completada (Puntaje: {score}/100). Requiere refinamiento.")
            
        return critique

    def get_context_for_coder(self) -> str:
        """Contexto que se le inyecta al Programador con la investigación."""
        ctx = [
            f"=== MEMORIA COMPARTIDA (PIZARRA) ===",
            f"TAREA DEL USUARIO:\n{self.user_prompt}\n",
        ]
        if self.research:
            ctx.append(f"=== REPORTE DEL INVESTIGADOR (NEMOTRON) ===\n{self.research.raw_content}\n")
        if self.shared_notes:
            ctx.append(f"=== NOTAS ADICIONALES COMPARTIDAS ===\n{self.shared_notes}\n")
        return "\n".join(ctx)

    def get_context_for_optimizer(self) -> str:
        """Contexto que se le inyecta al Optimizador con la investigación y el código."""
        ctx = [
            f"=== MEMORIA COMPARTIDA (PIZARRA) ===",
            f"TAREA DEL USUARIO:\n{self.user_prompt}\n",
        ]
        if self.research:
            ctx.append(f"=== REPORTE DEL INVESTIGADOR (NEMOTRON) ===\n{self.research.raw_content}\n")
        if self.code_proposal:
            ctx.append(f"=== CÓDIGO PROPUESTO POR EL PROGRAMADOR (DEEPSEEK) ===\n{self.code_proposal.raw_content}\n")
        if self.critiques:
            ctx.append(f"=== CRÍTICAS PREVIAS ===\n")
            for c in self.critiques:
                ctx.append(f"Ronda {c.round_num} (Puntaje: {c.score}/100):\n{c.raw_content}\n")
        return "\n".join(ctx)

    def get_context_for_refinement(self) -> str:
        """Contexto para que el Programador corrija su código según las críticas."""
        latest_critique = self.critiques[-1] if self.critiques else None
        critique_text = latest_critique.raw_content if latest_critique else "Por favor optimiza el código."
        ctx = [
            f"=== MEMORIA COMPARTIDA: SOLICITUD DE REFINAMIENTO (RONDA {self.refinement_rounds + 1}) ===",
            f"TAREA ORIGINAL:\n{self.user_prompt}\n",
        ]
        if self.code_proposal:
            ctx.append(f"=== TU CÓDIGO EN LA RONDA ANTERIOR ===\n{self.code_proposal.raw_content}\n")
        ctx.append(f"=== AUDITORÍA Y OBSERVACIONES DEL OPTIMIZADOR (GEMMA) ===\n{critique_text}\n")
        ctx.append("INSTRUCCIÓN: Modifica y optimiza el código resolviendo todos los puntos señalados por el Optimizador.")
        return "\n".join(ctx)

    def to_markdown_summary(self) -> str:
        """Genera un resumen completo en Markdown de toda la sesión de consenso."""
        md = [
            f"# Consenso de Expertos: Reporte de Ejecución",
            f"- **ID de Tarea**: `{self.task_id}`",
            f"- **Puntaje de Consenso**: **{self.consensus_score}/100** ({'Consenso Aprobado' if self.consensus_reached else 'Límite de rondas alcanzado'})",
            f"- **Rondas de Refinamiento**: {self.refinement_rounds}",
            f"- **Estado**: `{self.status.value}`\n",
            f"## 1. Petición del Usuario\n{self.user_prompt}\n",
        ]
        if self.research:
            md.append(f"## 2. Investigación y Hallazgos (Nemotron)\n{self.research.raw_content}\n")
        if self.code_proposal:
            md.append(f"## 3. Código Desarrollado (DeepSeek)\n{self.code_proposal.raw_content}\n")
        if self.critiques:
            md.append(f"## 4. Auditoría y Consenso (Gemma)\n")
            for c in self.critiques:
                md.append(f"### Ronda {c.round_num} - Puntaje: {c.score}/100\n{c.raw_content}\n")
        if self.final_synthesis:
            md.append(f"## 5. Solución Final Consensuada\n{self.final_synthesis}\n")
        return "\n".join(md)
