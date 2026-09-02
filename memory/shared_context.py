import uuid
from typing import Optional, Dict, Any, List
from .blackboard import Blackboard
from .persistent_store import PersistentMemoryStore

class SharedMemory:
    """
    Fachada unificada de Memoria Compartida que integra:
    1. Memoria de Trabajo activa (Blackboard / Pizarra de Consenso).
    2. Memoria Episódica persistente (Historial de turnos y tareas).
    3. Memoria de Hechos y Conocimiento (Base de datos de patrones aprendidos).
    AUDITORÍA 2026-08-22: añadido atributo research_context para inyectar el
    contexto del repositorio Sentinel Omega al Researcher (antes no existía,
    el Researcher trabajaba "a ciegas" sin conocer reglas/arquitectura/estado).
    """
    def __init__(self, session_id: Optional[str] = None, db_path: str = "data/shared_memory.db"):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.store = PersistentMemoryStore(db_path=db_path)
        self.active_blackboard: Optional[Blackboard] = None
        # Contexto del proyecto Sentinel Omega (inyectado por Orchestrator).
        # Contiene: resumen canónico + AGENTS.md + CLAUDE.md + CHANGELOG +
        # INFORME_CORRECCIONES + HANDOFF + RESTORE_SCHEMA + logs recientes.
        # Usado por ResearcherAgent.run_research() como ancla real.
        self.research_context: Optional[str] = None

    def create_task_blackboard(self, user_prompt: str, task_type: str = "FULL_CONSENSUS_CODING") -> Blackboard:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        self.active_blackboard = Blackboard(
            task_id=task_id,
            session_id=self.session_id,
            user_prompt=user_prompt,
            task_type=task_type
        )
        return self.active_blackboard

    @property
    def blackboard(self) -> Blackboard:
        if self.active_blackboard is None:
            raise RuntimeError("No hay una pizarra (blackboard) activa creada.")
        return self.active_blackboard

    def persist_current_state(self):
        """Guarda la pizarra activa y el resultado en la base de datos persistente."""
        if self.active_blackboard:
            self.store.save_blackboard(self.active_blackboard.model_dump())
            if self.active_blackboard.final_synthesis:
                self.store.save_message(
                    self.session_id,
                    "consensus_system",
                    self.active_blackboard.final_synthesis
                )

    def record_user_message(self, message: str):
        self.store.save_message(self.session_id, "user", message)

    def get_conversation_history(self, limit: int = 6) -> List[Dict[str, Any]]:
        return self.store.get_recent_messages(self.session_id, limit=limit)
