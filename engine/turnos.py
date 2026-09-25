"""
=============================================================================
MODULE : turnos
=============================================================================

Motor de deliberación POR TURNOS del Concilio MoE.

MODELO OPERATIVO
----------------
Un modelo a la vez. Cada uno entra, lee lo que dejaron los anteriores, decide
si PASA o REFINA, y puntúa su confianza en el resultado conjunto. El nivel sube
al Juez cuando la media de puntuaciones alcanza el umbral; si tras recorrer a
todos no llega, se escala al siguiente nivel con el trabajo acumulado.

POR QUÉ TURNOS Y NO PARALELO
----------------------------
El ensemble anterior corría concurrente (`ThreadPoolExecutor`) y fusionaba al
final. Eso tiene dos problemas medidos en este proyecto:

  1. RAM: tres modelos a la vez pedían 5,7 GB. En turnos el techo es el modelo
     más grande, no la suma, y eso permite usar modelos que antes no cabían.
  2. El 2026-09-16, dos de tres modelos inventaron la MISMA ruta genérica y la
     fusión no lo detectó. En paralelo nadie ve el trabajo del otro hasta que
     ya es tarde; por turnos, el segundo lee lo que escribió el primero y puede
     contradecirlo.

LO QUE ESTE MOTOR **NO** RESUELVE
---------------------------------
El anclaje. En deliberación secuencial el primer turno fija el marco y los
siguientes tienden a refinar dentro de él en vez de cuestionarlo. Se mitiga con
el orden de los perfiles (débil→fuerte) pero no desaparece. Para saber si los
turnos deliberan o solo asienten, comparar `veredicto` del primer turno con el
final: si casi nunca cambia, están asintiendo.
=============================================================================
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from memory.anti_injection import fence_untrusted

logger = logging.getLogger("Concilio.Turnos")
logger.addHandler(logging.NullHandler())


PASO = "PASO"
REFINO = "REFINO"


# ─── ESTRUCTURAS ─────────────────────────────────────────────────────────────

@dataclass
class Turno:
    """Lo que deja un modelo al terminar su turno.

    `borrador` es lo que hace posible el refinamiento: la memoria anterior solo
    guardaba el marcador (quién corrió, qué nota sacó) y con eso el siguiente
    modelo no tiene nada que refinar.
    """
    n: int
    modelo: str
    rol: str
    veredicto: str                      # PASO | REFINO
    puntuacion: int                     # 0-100
    borrador: str
    objeciones: List[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)
    duracion_s: float = 0.0

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ResultadoNivel:
    """Cierre de un nivel completo."""
    area: str                           # investigacion | codigo
    nivel: str                          # ligero | intermedio | avanzado
    turnos: List[Turno]
    media: float
    alcanzo_umbral: bool
    borrador_final: str

    @property
    def cambio_de_opinion(self) -> bool:
        """¿Deliberaron o solo asintieron?

        Si el primer turno dijo PASO y el último también, sin que nadie
        objetara en medio, el nivel no deliberó: se ancló al primero.
        """
        if len(self.turnos) < 2:
            return False
        return any(t.veredicto == REFINO for t in self.turnos[1:])


# ─── MEMORIA DE TURNOS ───────────────────────────────────────────────────────

class MemoriaTurnos:
    """Registro append-only de turnos, uno por línea JSON.

    A diferencia de `data/moe_shared_memory.jsonl`, que guardaba solo el
    resultado de la tarea, aquí va el BORRADOR de cada turno. Sin eso el
    siguiente modelo no puede refinar nada --- solo repetir.
    """

    def __init__(self, ruta: str, turnos_visibles: int = 6) -> None:
        self.ruta = Path(ruta)
        self.turnos_visibles = turnos_visibles
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

    def anotar(self, tarea_id: str, turno: Turno) -> None:
        linea = json.dumps({"tarea_id": tarea_id, **turno.as_dict()},
                           ensure_ascii=False)
        try:
            with self.ruta.open("a", encoding="utf-8") as f:
                f.write(linea + "\n")
        except OSError as e:
            # Perder el registro no debe tumbar la deliberación en curso.
            logger.error("No se pudo anotar el turno: %s", e)

    def leer(self, tarea_id: str) -> List[Dict]:
        if not self.ruta.exists():
            return []
        salida: List[Dict] = []
        try:
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                try:
                    d = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if d.get("tarea_id") == tarea_id:
                    salida.append(d)
        except OSError as e:
            logger.error("No se pudo leer la memoria de turnos: %s", e)
            return []
        return salida[-self.turnos_visibles:]


# ─── CONTEXTO ────────────────────────────────────────────────────────────────

def presupuesto_material(escalado: Dict, ventana: int, n_turno: int) -> int:
    """Tokens de material NUEVO que recibe este turno.

    Baja con el número de turno a propósito: el turno hereda lo ya destilado
    por los anteriores, así que necesita menos material bruto. Si material y
    acumulado crecieran a la vez, el último turno se ahogaría.
    """
    por_ventana = escalado.get("por_ventana", {}) or {}
    base = por_ventana.get(ventana)
    if base is None:
        # Ventana no listada: escalar desde la más cercana por debajo.
        menores = [v for v in por_ventana if v <= ventana]
        base = por_ventana[max(menores)] if menores else 1200
    mult = (escalado.get("por_turno", {}) or {}).get(n_turno, 0.35)
    return int(base * mult)


VEREDICTO_ETIQUETAS = (PASO, REFINO)

CONTRATO_RESPUESTA = """
=== CÓMO RESPONDER (formato obligatorio, en este orden) ===
VEREDICTO: PASO | REFINO
CONFIANZA: un entero de 0 a 100
BORRADOR:
<tu versión completa del entregable; si das PASO, repite la anterior tal cual>
OBJECIONES:
- una por línea, o "ninguna"

No escribas nada fuera de esos cuatro campos.
"""


def parsear_respuesta(texto: str) -> Tuple[str, int, str, List[str]]:
    """Saca (veredicto, confianza, borrador, objeciones) de la respuesta.

    ANTE LA DUDA, REFINO --- igual que el portero del perfil. Equivocarse
    hacia otra vuelta cuesta tiempo; equivocarse hacia PASO entrega trabajo sin
    revisar. Y una confianza que no se puede leer vale 0, no 100: un campo
    ilegible no es un aval.
    """
    t = texto or ""

    m = re.search(r"^\s*VEREDICTO\s*:\s*(PASO|REFINO)\b", t, re.I | re.M)
    veredicto = m.group(1).upper() if m else REFINO

    m = re.search(r"^\s*CONFIANZA\s*:\s*(\d{1,3})", t, re.I | re.M)
    confianza = max(0, min(100, int(m.group(1)))) if m else 0

    m = re.search(r"^\s*BORRADOR\s*:\s*\n?(.*?)(?=^\s*OBJECIONES\s*:|\Z)",
                  t, re.I | re.M | re.S)
    if m:
        borrador = m.group(1).strip()
    elif re.search(r"^\s*(VEREDICTO|CONFIANZA|OBJECIONES)\s*:", t, re.I | re.M):
        # Trae los marcadores del contrato pero NO el borrador: el entregable
        # falta de verdad. Usar el texto entero aquí metería las líneas
        # "VEREDICTO:" y "CONFIANZA:" dentro del borrador, y de paso salvaría un
        # PASO que no tiene nada que aprobar.
        borrador = ""
    else:
        # No siguió el contrato en absoluto. Se es indulgente: lo que escribió
        # ES su borrador, y el veredicto cae a REFINO por no ser legible.
        borrador = t.strip()

    objeciones: List[str] = []
    m = re.search(r"^\s*OBJECIONES\s*:\s*\n?(.*)\Z", t, re.I | re.M | re.S)
    if m:
        for linea in m.group(1).splitlines():
            linea = linea.strip().lstrip("-*• ").strip()
            if linea and linea.lower() not in ("ninguna", "ninguno", "none", "n/a"):
                objeciones.append(linea)

    # Un PASO sin borrador no es un PASO: no hay nada que aprobar.
    if veredicto == PASO and not borrador:
        veredicto = REFINO
        objeciones.append("dio PASO sin entregar borrador")

    return veredicto, confianza, borrador, objeciones


def componer_contexto(
    enunciado: str,
    previos: List[Turno],
    material: str,
    max_material_chars: int,
) -> str:
    """Arma lo que ve un modelo en su turno.

    El acumulado va ENTERO y primero: es lo que distingue un turno de una
    ejecución aislada. El material nuevo se recorta si no cabe --- nunca al
    revés. Perder lo que dijeron los compañeros convierte la deliberación en
    N intentos independientes, que es justo lo que veníamos a evitar.
    """
    partes = [f"TAREA:\n{enunciado}\n"]

    if previos:
        partes.append("\n=== LO QUE DEJARON LOS TURNOS ANTERIORES ===")
        for t in previos:
            partes.append(
                f"\n--- Turno {t.n} · {t.rol} ({t.modelo}) · "
                f"{t.veredicto} · confianza {t.puntuacion}/100 ---\n"
                f"{t.borrador}"
            )
            if t.objeciones:
                partes.append("Objetó:\n- " + "\n- ".join(t.objeciones))
        partes.append(
            "\nSi lo anterior ya resuelve la tarea responde PASO. Si no, REFINA "
            "y di explícitamente QUÉ objetas y POR QUÉ."
        )

    if material:
        recortado = material[:max_material_chars]
        if len(material) > max_material_chars:
            recortado += "\n…(material recortado al presupuesto de este turno)"
        partes.append("\n=== MATERIAL DE CONSULTA ===")
        partes.append(fence_untrusted(recortado, role="material"))

    # El CONTRATO va siempre, también en el primer turno. Antes sólo se añadía
    # `if previos`, así que el turno 1 no recibía ninguna instrucción de formato
    # y _invocar prometía devolver cuatro campos que nadie había pedido.
    partes.append(CONTRATO_RESPUESTA)
    return "\n".join(partes)


# ─── MOTOR ───────────────────────────────────────────────────────────────────

class MotorTurnos:
    """Recorre los turnos de un nivel y decide si alcanza el umbral.

    `invocar` y `cargar_exclusivo` se inyectan para poder probar el bucle sin
    levantar Ollama. En producción los aporta el orquestador.
    """

    def __init__(
        self,
        perfil: Dict,
        invocar: Callable[[str, str, int], Tuple[str, int, str, List[str]]],
        cargar_exclusivo: Optional[Callable[[str, Optional[int]], None]] = None,
        memoria: Optional[MemoriaTurnos] = None,
    ) -> None:
        self.perfil = perfil
        self._invocar = invocar
        self._cargar = cargar_exclusivo or (lambda _m, _ventana=None: None)
        cfg_mem = perfil.get("memoria", {}) or {}
        self.memoria = memoria or MemoriaTurnos(
            cfg_mem.get("store", "data/moe_turnos.jsonl"),
            int(cfg_mem.get("turnos_visibles", 6)),
        )
        self.escalado = perfil.get("escalado_contexto", {}) or {}
        cons = perfil.get("consenso", {}) or {}
        self.umbral = int(cons.get("umbral_nivel", 85))

    # ── un nivel ─────────────────────────────────────────────────────────────

    def correr_nivel(
        self,
        tarea_id: str,
        enunciado: str,
        area: str,
        nivel: str,
        material: str = "",
    ) -> ResultadoNivel:
        cfg = (self.perfil.get(area, {}) or {}).get(nivel)
        if not cfg:
            raise ValueError(f"nivel inexistente: {area}/{nivel}")

        turnos: List[Turno] = []
        for i, t_cfg in enumerate(cfg["turnos"], start=1):
            modelo = t_cfg["model"]
            rol = t_cfg.get("rol", modelo)
            ventana = int(t_cfg.get("ctx", 4096))

            tokens = presupuesto_material(self.escalado, ventana, i)
            ctx = componer_contexto(enunciado, turnos, material, tokens * 4)

            logger.info("turno %d · %s (%s) · ventana %d · material ~%d tokens",
                        i, rol, modelo, ventana, tokens)
            # LA VENTANA VA EN LA PRECARGA, no solo en la invocación. Medido el
            # 2026-09-24: sin num_ctx en la carga, Ollama reserva caché para la
            # ventana COMPLETA del modelo y el generate posterior ya no puede
            # reducirla sin recargar. deepseek-r1:8b quedaba en 23,93 GiB
            # medidos, de los que sólo 2,2 entraban en la GPU.
            #
            # La firma anterior era Callable[[str], None] y se llamaba con el
            # modelo a secas, así que el motor de turnos habría reproducido ese
            # desastre entero en cuanto se cableara. Ningún test inyectaba
            # cargar_exclusivo, así que nada lo delataba.
            self._cargar(modelo, ventana)

            t0 = time.time()
            try:
                veredicto, punt, borrador, objeciones = self._invocar(
                    modelo, ctx, ventana
                )
            except Exception as e:  # noqa: BLE001
                # Un modelo caído no debe abortar el nivel: se registra como
                # REFINO con confianza 0 y el siguiente sigue desde lo que haya.
                logger.error("turno %d (%s) falló: %s: %s",
                             i, modelo, type(e).__name__, e)
                veredicto, punt = REFINO, 0
                borrador = turnos[-1].borrador if turnos else ""
                objeciones = [f"el modelo {modelo} no respondió: {e}"]

            turno = Turno(
                n=i, modelo=modelo, rol=rol,
                veredicto=veredicto if veredicto in (PASO, REFINO) else REFINO,
                puntuacion=max(0, min(100, int(punt or 0))),
                borrador=borrador or "",
                objeciones=list(objeciones or []),
                duracion_s=round(time.time() - t0, 1),
            )
            turnos.append(turno)
            self.memoria.anotar(tarea_id, turno)

        media = sum(t.puntuacion for t in turnos) / len(turnos) if turnos else 0.0
        return ResultadoNivel(
            area=area, nivel=nivel, turnos=turnos,
            media=round(media, 1),
            alcanzo_umbral=media >= self.umbral,
            borrador_final=turnos[-1].borrador if turnos else "",
        )

    # ── escalado entre niveles ───────────────────────────────────────────────

    def deliberar(
        self,
        tarea_id: str,
        enunciado: str,
        area: str,
        nivel_inicial: str = "ligero",
        material: str = "",
    ) -> ResultadoNivel:
        """Corre niveles en orden y escala mientras no se alcance el umbral."""
        orden = ["ligero", "intermedio", "avanzado"]
        try:
            desde = orden.index(nivel_inicial)
        except ValueError:
            desde = 0

        ultimo: Optional[ResultadoNivel] = None
        for nivel in orden[desde:]:
            if nivel not in (self.perfil.get(area, {}) or {}):
                continue
            logger.info("=== nivel %s/%s ===", area, nivel)
            ultimo = self.correr_nivel(tarea_id, enunciado, area, nivel, material)
            logger.info("nivel %s: media %.1f (umbral %d) -> %s",
                        nivel, ultimo.media, self.umbral,
                        "PASA" if ultimo.alcanzo_umbral else "ESCALA")
            if ultimo.alcanzo_umbral:
                return ultimo
            # El siguiente nivel arranca con lo ya trabajado como material.
            material = ultimo.borrador_final or material

        if ultimo is None:
            raise ValueError(f"no hay niveles corribles para el área {area}")
        return ultimo
