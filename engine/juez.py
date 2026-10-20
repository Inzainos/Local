"""Juez Interno — aprende de los resultados VERIFICADOS (estilo Juez Sentinel).

Solo se alimenta con resultados donde consensus_reached=True y via in
("especificacion", "relaciones", "concilio_verificado").
NUNCA con SIN VERIFICAR ni SIN CONSENSO.
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

JUEZ_DB = "data/juez.db"


def _init_db():
    Path("data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(JUEZ_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()

    # 1. Regresión permanente: casos que fallaron en tareas VERIFICADAS
    c.execute("""
        CREATE TABLE IF NOT EXISTS juez_regresion (
            tarea TEXT NOT NULL,
            tipo_tarea TEXT NOT NULL,           -- 'formato', 'duracion', 'validador', 'ipv4', etc.
            modelo TEXT NOT NULL,
            caso_entrada TEXT NOT NULL,
            caso_esperado TEXT NOT NULL,
            caso_obtenido TEXT NOT NULL,
            verificado_en REAL NOT NULL,        -- timestamp
            PRIMARY KEY (tarea, caso_entrada, modelo)
        )
    """)

    # 2. Aciertos por modelo × tipo_tarea (para elegir mejor modelo en intento 2)
    c.execute("""
        CREATE TABLE IF NOT EXISTS juez_aciertos (
            modelo TEXT NOT NULL,
            tipo_tarea TEXT NOT NULL,
            aciertos INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            actualizado_en REAL NOT NULL,
            PRIMARY KEY (modelo, tipo_tarea)
        )
    """)

    # 3. Few-shot bank: mejores soluciones VERIFICADAS por tarea
    c.execute("""
        CREATE TABLE IF NOT EXISTS juez_fewshot (
            tarea TEXT NOT NULL PRIMARY KEY,
            tipo_tarea TEXT NOT NULL,
            codigo_verificado TEXT NOT NULL,
            verificado_en REAL NOT NULL,
            via TEXT NOT NULL,                   -- 'especificacion' | 'relaciones' | 'concilio_verificado'
            aciertos INTEGER NOT NULL,
            total INTEGER NOT NULL
        )
    """)

    # 4. Feedback operador para tareas SIN VERIFICAR
    c.execute("""
        CREATE TABLE IF NOT EXISTS juez_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarea TEXT NOT NULL,
            tipo_tarea TEXT NOT NULL,
            enunciado TEXT NOT NULL,
            codigo_candidato TEXT NOT NULL,
            veredicto_humano TEXT NOT NULL,      -- 'aprueba' | 'rechaza' | 'parcial'
            notas TEXT DEFAULT '',
            creado_en REAL NOT NULL
        )
    """)

    # Índices útiles
    c.execute("CREATE INDEX IF NOT EXISTS idx_regresion_tarea ON juez_regresion(tarea)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_aciertos_modelo ON juez_aciertos(modelo)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fewshot_tipo ON juez_fewshot(tipo_tarea)")

    conn.commit()
    conn.close()


def _conectar() -> sqlite3.Connection:
    _init_db()
    conn = sqlite3.connect(JUEZ_DB)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass
class RegresionEntry:
    tarea: str
    tipo_tarea: str
    modelo: str
    caso_entrada: str
    caso_esperado: str
    caso_obtenido: str
    verificado_en: float


def registrar_regresion(entry: RegresionEntry) -> None:
    """Guarda un caso fallido de una tarea VERIFICADA."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO juez_regresion
        (tarea, tipo_tarea, modelo, caso_entrada, caso_esperado, caso_obtenido, verificado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (entry.tarea, entry.tipo_tarea, entry.modelo, entry.caso_entrada,
          entry.caso_esperado, entry.caso_obtenido, entry.verificado_en))
    conn.commit()
    conn.close()


def actualizar_aciertos(modelo: str, tipo_tarea: str, delta_aciertos: int, delta_total: int) -> None:
    """Incrementa contadores de aciertos por modelo×tipo."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("""
        INSERT INTO juez_aciertos (modelo, tipo_tarea, aciertos, total, actualizado_en)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(modelo, tipo_tarea) DO UPDATE SET
            aciertos = aciertos + excluded.aciertos,
            total = total + excluded.total,
            actualizado_en = excluded.actualizado_en
    """, (modelo, tipo_tarea, delta_aciertos, delta_total, time.time()))
    conn.commit()
    conn.close()


def get_accuracy(modelo: str, tipo_tarea: str) -> Optional[float]:
    """Devuelve accuracy histórico (aciertos/total) o None si no hay datos."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("SELECT aciertos, total FROM juez_aciertos WHERE modelo=? AND tipo_tarea=?",
              (modelo, tipo_tarea))
    row = c.fetchone()
    conn.close()
    if row and row["total"] > 0:
        return row["aciertos"] / row["total"]
    return None


def mejor_modelo_para_tipo(tipo_tarea: str, candidatos: List[str]) -> Optional[str]:
    """Elige el modelo con mejor accuracy histórico para un tipo de tarea."""
    mejor = None
    mejor_acc = -1.0
    for m in candidatos:
        acc = get_accuracy(m, tipo_tarea)
        if acc is not None and acc > mejor_acc:
            mejor_acc = acc
            mejor = m
    return mejor


def guardar_fewshot(tarea: str, tipo_tarea: str, codigo: str,
                    via: str, aciertos: int, total: int) -> None:
    """Guarda la mejor solución VERIFICADA como few-shot."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("""
        INSERT INTO juez_fewshot (tarea, tipo_tarea, codigo_verificado, verificado_en, via, aciertos, total)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tarea) DO UPDATE SET
            codigo_verificado = excluded.codigo_verificado,
            verificado_en = excluded.verificado_en,
            via = excluded.via,
            aciertos = excluded.aciertos,
            total = excluded.total
    """, (tarea, tipo_tarea, codigo, time.time(), via, aciertos, total))
    conn.commit()
    conn.close()


def get_fewshot(tarea: str) -> Optional[str]:
    """Recupera la solución few-shot para inyectar como contexto."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("SELECT codigo_verificado FROM juez_fewshot WHERE tarea=?", (tarea,))
    row = c.fetchone()
    conn.close()
    return row["codigo_verificado"] if row else None


def get_fewshots_by_tipo(tipo_tarea: str, limite: int = 3) -> List[str]:
    """Recupera N mejores few-shots del mismo tipo para inyección de contexto."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("""
        SELECT codigo_verificado FROM juez_fewshot
        WHERE tipo_tarea=?
        ORDER BY verificado_en DESC
        LIMIT ?
    """, (tipo_tarea, limite))
    rows = c.fetchall()
    conn.close()
    return [r["codigo_verificado"] for r in rows]


def registrar_feedback(tarea: str, tipo_tarea: str, enunciado: str,
                       codigo: str, veredicto: str, notas: str = "") -> None:
    """Guarda feedback del operador para tareas SIN VERIFICAR."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("""
        INSERT INTO juez_feedback (tarea, tipo_tarea, enunciado, codigo_candidato,
                                   veredicto_humano, notas, creado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (tarea, tipo_tarea, enunciado, codigo, veredicto, notas, time.time()))
    conn.commit()
    conn.close()


def stats() -> Dict[str, Any]:
    """Estadísticas generales del Juez."""
    conn = _conectar()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM juez_regresion")
    n_reg = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM juez_aciertos")
    n_acc = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM juez_fewshot")
    n_few = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM juez_feedback")
    n_fb = c.fetchone()[0]
    conn.close()
    return {
        "regresiones": n_reg,
        "modelos_tipos": n_acc,
        "fewshots": n_few,
        "feedback": n_fb,
    }


# ─── Hook para orchestrator ──────────────────────────────────────────────────
def on_tarea_verificada(
    tarea: str,
    tipo_tarea: str,
    modelo: str,
    via: str,
    aciertos: int,
    total: int,
    casos_detalle: List[Dict],
    codigo: str,
) -> None:
    """Llamar desde orchestrator cuando consensus_reached=True y via fiable.
    
    Actualiza: regresión (fallos), aciertos (modelo×tipo), fewshot (mejor código).
    """
    # 1. Regresión: cada caso fallado
    for d in casos_detalle:
        if not d.get("correcto"):
            registrar_regresion(RegresionEntry(
                tarea=tarea, tipo_tarea=tipo_tarea, modelo=modelo,
                caso_entrada=d["entrada"], caso_esperado=d["esperado"],
                caso_obtenido=d.get("obtenido", ""), verificado_en=time.time()
            ))
    # 2. Aciertos
    actualizar_aciertos(modelo, tipo_tarea, aciertos, total)
    # 3. Few-shot: si es el mejor código visto para esta tarea
    conn = _conectar()
    c = conn.cursor()
    c.execute("SELECT aciertos FROM juez_fewshot WHERE tarea=?", (tarea,))
    row = c.fetchone()
    conn.close()
    if not row or aciertos > row["aciertos"]:
        guardar_fewshot(tarea, tipo_tarea, codigo, via, aciertos, total)


def infer_tipo_tarea(enunciado: str) -> str:
    """Clasificación simple del tipo de tarea por palabras clave."""
    low = enunciado.lower()
    if "token" in low and "telegram" in low:
        return "formato_token"
    if "duracion" in low or "segundos" in low or "convierte" in low:
        return "duracion"
    if "ipv4" in low or "direccion" in low:
        return "ipv4"
    if "palindromo" in low:
        return "palindromo"
    if "matricula" in low:
        return "formato_matricula"
    if "bisiesto" in low:
        return "bisiesto"
    if "romano" in low:
        return "romano"
    return "general"
