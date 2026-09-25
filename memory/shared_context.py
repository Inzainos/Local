import math
import re
import uuid
from typing import Optional, Dict, Any, List
from .blackboard import Blackboard
from .persistent_store import PersistentMemoryStore

# ─── RELEVANCIA ENTRE ENUNCIADOS ─────────────────────────────────────────────
# El 2026-09-24, en una tarea de validación de tokens, el Concilio entregó
# `validar_token_telegram` Y ADEMÁS `es_palindromo`. La causa: la memoria
# histórica inyectaba las 5 tareas MÁS RECIENTES, por fecha y sin filtro
# ninguno, y dos de ellas eran de otras baterías:
#
#   [CONSENSO 88] ... validar_token_telegram ...
#   [CONSENSO 88] ... es_palindromo ...          <- nada que ver
#   [SIN CONSENSO 78] ... a_segundos ...         <- nada que ver
#
# El modelo leyó ese enunciado en su contexto y lo resolvió también. Ruido
# inyectado en una tarea cuyo problema es la precisión.
#
# POR QUÉ NO SIRVE CONTAR PALABRAS EN COMÚN
# Todos estos enunciados empiezan igual: «Escribe una funcion Python llamada
# ... que devuelva ...». Un parecido por palabras crudas los declara a todos
# semejantes, porque la mayoría de lo que comparten es plantilla.
#
# Se pesa cada palabra por lo INFORMATIVA que es: las que aparecen en casi
# todos los antecedentes no distinguen nada y valen ~0; las que aparecen en
# pocos («telegram», «palindromo», «segundos») son las que cargan el tema.
# Es el idf de toda la vida, calculado sobre los propios antecedentes y sin
# dependencias.
#
# Esto es un SUELO, no el destino: `vectorial` en profiles/niveles.yaml
# prevé hacerlo con nomic-embed-text, que captura parecido semántico y no
# solo léxico. Mientras eso no exista, esto ya impide la fuga.

_CORTE_PALABRA = 4          # palabras más cortas no discriminan

# EL CORTE, MEDIDO sobre los 20 antecedentes reales del 2026-09-24. Hay un
# hueco amplio entre «misma plantilla, otro tema» y «mismo tema»:
#
#   mismo tema (validar_token)      1,000
#   misma plantilla, otro tema      0,267   <- es_palindromo, la fuga
#                                   0,216   <- a_segundos
#   auditorías frente a código      0,034
#   saludos («hola», «status»)      0,000
#
# 0,50 cae en medio de ese hueco, lejos de ambos lados. Mi primer intento fue
# 0,12 y habría dejado pasar el palíndromo: sólo se salvó porque había cinco
# antecedentes con 1,0 que ordenaban delante. Calibrado con ESTOS datos; si
# aparecen familias de tareas más parecidas entre sí, hay que volver a mirarlo.
RELEVANCIA_MINIMA = 0.50


def palabras_informativas(texto: str) -> set:
    """Palabras en minúscula, sin signos, de más de `_CORTE_PALABRA` letras."""
    limpio = re.sub(r"[^\w\s]", " ", (texto or "").lower(), flags=re.UNICODE)
    return {p for p in limpio.split() if len(p) > _CORTE_PALABRA}


def pesos_idf(corpus: List[str]) -> Dict[str, float]:
    """Cuánto distingue cada palabra, sobre el corpus de antecedentes.

    Una palabra en TODOS los documentos pesa 0: no separa nada. Una en uno
    solo pesa el máximo.
    """
    docs = [palabras_informativas(t) for t in corpus]
    n = len(docs)
    if not n:
        return {}
    frec: Dict[str, int] = {}
    for d in docs:
        for w in d:
            frec[w] = frec.get(w, 0) + 1
    # idf SUAVIZADO: log((1+n)/(1+f)) + 1. El «+1» final importa --- mi primera
    # version usaba log(n/f) y daba 0 a las palabras presentes en todos los
    # documentos. Consecuencia: con un corpus homogeneo (solo tareas de token)
    # TODAS las palabras pesaban 0, la relevancia salia 0 y se descartaban los
    # antecedentes BUENOS. Lo cazaron sus propios tests.
    #
    # Suavizado, una palabra comun pesa 1 y una distintiva mas, asi que se
    # conserva el orden relativo sin anular nada.
    return {w: math.log((1 + n) / (1 + f)) + 1.0 for w, f in frec.items()}


def relevancia(consulta: str, candidato: str, idf: Dict[str, float]) -> float:
    """0..1. Peso compartido sobre el peso de la consulta.

    Se normaliza por la CONSULTA y no por la unión: lo que importa es cuánto
    del tema de la tarea en curso cubre el antecedente, no que se parezcan
    en longitud.
    """
    a, b = palabras_informativas(consulta), palabras_informativas(candidato)
    if not a or not b:
        return 0.0
    # Palabras nuevas, que no están en el corpus, cuentan como distintivas.
    por_defecto = max(idf.values(), default=1.0) or 1.0
    peso = lambda w: idf.get(w, por_defecto)  # noqa: E731
    total = sum(peso(w) for w in a)
    if total <= 0:
        return 0.0
    return sum(peso(w) for w in a & b) / total


def filtrar_por_relevancia(
    consulta: str,
    tareas: List[Dict[str, Any]],
    limite: int,
    minimo: float = RELEVANCIA_MINIMA,
) -> List[Dict[str, Any]]:
    """Antecedentes que de verdad se parecen, de mayor a menor.

    Si ninguno pasa el mínimo devuelve LISTA VACÍA. «No hay antecedente
    relevante» no es lo mismo que «aquí van los cinco últimos»: inyectar los
    más recientes por no tener mejores es precisamente el fallo que esto
    corrige.
    """
    if not consulta or not tareas:
        return []
    idf = pesos_idf([t.get("user_prompt") or "" for t in tareas])
    puntuadas = [
        (relevancia(consulta, t.get("user_prompt") or "", idf), t) for t in tareas
    ]
    puntuadas = [(r, t) for r, t in puntuadas if r >= minimo]
    puntuadas.sort(key=lambda par: par[0], reverse=True)
    for r, t in puntuadas:
        t["relevancia"] = round(r, 3)
    return [t for _, t in puntuadas[:limite]]


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
