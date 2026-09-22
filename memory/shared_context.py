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

    def recuperar_tareas_previas(
        self, limit: int = 5, excluir_task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Deliberaciones anteriores, de otras sesiones incluidas.

        `blackboard_snapshots` se venia escribiendo desde siempre pero su
        unico lector (`get_recent_tasks`) no tenia llamadores: el Concilio
        acumulaba tareas resueltas en disco sin poder consultarlas, y cada
        sesion arrancaba en frio. Esta es la via de lectura.

        Se pide un margen extra porque la tarea en curso ya puede estar
        persistida y hay que descartarla para no darle al Concilio su
        propio enunciado como antecedente.
        """
        try:
            filas = self.store.get_recent_tasks(limit=limit + 1)
        except Exception:
            # Memoria historica degradada no debe tumbar la deliberacion.
            return []
        if excluir_task_id:
            filas = [f for f in filas if f.get("task_id") != excluir_task_id]
        return filas[:limit]

    def recordar_consenso(self, blackboard) -> bool:
        """Archiva como hecho una deliberacion que supero el umbral.

        Criterio fijado por el operador: solo se recuerda lo que el Concilio
        aprobo. Una sintesis por debajo del umbral es un borrador, y
        archivarla contaminaria la memoria con material que el propio
        sistema rechazo.

        Se compara contra el umbral REGISTRADO en la pizarra, no contra un
        85 escrito aqui: si config.yaml cambia, las tareas viejas siguen
        juzgadas por la barra de su momento. Sin umbral registrado no se
        archiva nada --- ausencia de dato no es permiso.
        """
        score = int(getattr(blackboard, "consensus_score", 0) or 0)
        umbral = int(getattr(blackboard, "consensus_threshold", 0) or 0)
        if not umbral or score < umbral:
            return False
        sintesis = (getattr(blackboard, "final_synthesis", "") or "").strip()
        enunciado = (getattr(blackboard, "user_prompt", "") or "").strip()
        if not sintesis or not enunciado:
            return False
        try:
            self.store.save_fact(
                category=getattr(blackboard, "task_type", "") or "CONSENSO",
                key=enunciado[:200],
                value=sintesis[:8000],
                source_agent=f"Concilio score={score}/{umbral}",
            )
            return True
        except Exception:
            return False

    def buscar_hechos(self, consulta: str, limite: int = 3) -> List[Dict[str, Any]]:
        """Hechos archivados que se parezcan a la consulta.

        `search_facts` hace LIKE sobre key y value, asi que pasarle el
        enunciado entero casi nunca casa. Se buscan en cambio sus palabras
        mas largas, que son las que cargan el tema, y se unen resultados
        deduplicando por key.
        """
        palabras = sorted(
            {p.strip(".,;:()[]\"'").lower() for p in (consulta or "").split()},
            key=len,
            reverse=True,
        )
        terminos = [p for p in palabras if len(p) >= 5][:3]
        if not terminos:
            return []
        vistos, salida = set(), []
        for t in terminos:
            try:
                for h in self.store.search_facts(t, limit=limite):
                    k = h.get("key")
                    if k not in vistos:
                        vistos.add(k)
                        salida.append(h)
            except Exception:
                continue
        return salida[:limite]
