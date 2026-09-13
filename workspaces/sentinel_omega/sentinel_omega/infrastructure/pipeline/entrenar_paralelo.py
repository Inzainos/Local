"""
Entrenamiento paralelo por BOT — mismo resultado que el secuencial, en fracción
del tiempo.

Idea (de Elán, con el eje correcto): partir el trabajo y unir al final. El eje
que NO fragmenta la memoria es el **bot**, no el mes: `FirmaMemoria.registrar`
agrupa por `(bot_name, event_class)`, así que las firmas de un bot JAMÁS se
cruzan con las de otro. Por eso cada bot puede entrenarse en su propio proceso,
sobre su propia copia de la base, y al final solo se PEGAN las filas (UNION) —
disjuntas por construcción, sin merge que reconciliar, sin riesgo de sesgo.

Por qué no por mes/cuatrimestre: la recurrencia NO es local en el tiempo (la
misma firma precede sismos de 1997, 2004, 2011…). Partir por tiempo obligaría a
un merge que reconcilie la misma firma partida entre bloques — frágil. Partir
por bot lo evita entero.

Se reutiliza `entrenar_reconocimiento(..., bots=[bot])` sin tocar su lógica, así
el resultado por-bot es byte-idéntico al secuencial. La equivalencia está
probada en tests/test_entrenar_paralelo.py.

Nota operativa: cada worker trabaja sobre una COPIA de la base (para leer el
backcast y escribir sus firmas sin pelear el lock de SQLite). En un servidor con
disco esto es trivial; en contenedores con disco acotado, correr N copias de una
base grande puede agotar el espacio — por eso `entrenar_reconocimiento_paralelo`
recibe `n_workers` para acotar cuántas copias viven a la vez.
"""

import logging
import multiprocessing as mp
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _worker_un_bot(args) -> Dict:
    """Entrena UN bot sobre una copia dedicada de la base. Corre en su propio
    proceso. Devuelve el path de la copia para que el padre extraiga las firmas.
    """
    db_origen, dir_trabajo, bot, max_eventos = args
    from sentinel_omega.infrastructure.pipeline.entrenamiento import (
        entrenar_reconocimiento,
    )
    copia = str(Path(dir_trabajo) / f"train_{bot}.db")
    # Checkpoint del WAL del origen para que la copia binaria quede consistente.
    src = sqlite3.connect(db_origen)
    src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    src.close()
    shutil.copy2(db_origen, copia)
    stats = entrenar_reconocimiento(copia, max_eventos=max_eventos, bots=[bot])
    return {"bot": bot, "copia": copia, "stats": stats}


def entrenar_reconocimiento_paralelo(
    db_path: str,
    bots: Optional[List[str]] = None,
    n_workers: Optional[int] = None,
    max_eventos: Optional[int] = None,
    dir_trabajo: Optional[str] = None,
) -> Dict:
    """Fase 1 en paralelo por bot. Resultado idéntico al secuencial.

    Cada bot se entrena en un proceso sobre su copia; al final las firmas
    (y las filas de auditoría fase='reconocimiento') se PEGAN de vuelta en
    db_path. Como las filas son disjuntas por bot, la unión es una simple
    inserción — sin reconciliación.
    """
    from sentinel_omega.infrastructure.pipeline.entrenamiento import BOT_FEATURES

    bots = bots or [b for b in BOT_FEATURES if b != "alfa2"]  # alfa2 es live-only
    n_workers = n_workers or min(len(bots), mp.cpu_count())
    tmp_owner = dir_trabajo is None
    dir_trabajo = dir_trabajo or tempfile.mkdtemp(prefix="entrena_par_")

    logger.info(
        f"=== FASE 1 PARALELA: {len(bots)} bots en {n_workers} procesos "
        f"({', '.join(bots)}) ==="
    )
    tareas = [(db_path, dir_trabajo, bot, max_eventos) for bot in bots]

    resultados: List[Dict] = []
    try:
        with mp.get_context("spawn").Pool(n_workers) as pool:
            for res in pool.imap_unordered(_worker_un_bot, tareas):
                logger.info(f"  bot {res['bot']} listo: {res['stats'].get('memoria')}")
                resultados.append(res)

        # Unión: pegar las firmas y la auditoría de cada copia en la base madre.
        destino = sqlite3.connect(db_path)
        total_firmas = 0
        for res in resultados:
            # Idempotente: la copia partió del estado de db_path y lo re-generó
            # entero para su bot, así que reemplazamos las filas de ese bot.
            destino.execute("DELETE FROM TBL_FIRMAS WHERE bot_name = ?",
                            (res["bot"],))
            destino.execute("DELETE FROM TBL_JUEZ_AUDITORIA "
                            "WHERE bot_name = ? AND fase = 'reconocimiento'",
                            (res["bot"],))
            origen = sqlite3.connect(res["copia"])
            # Insertamos firma por firma para remapear firma_id (AUTOINCREMENT
            # difiere entre la copia y el destino) y arrastrar sus eventos
            # (tabla hija normalizada) con el id nuevo.
            filas = origen.execute(
                "SELECT firma_id, bot_name, event_class, id_nodo, features_json, "
                "ventana_horas, recurrencia, estado, primera_vista, ultima_vista "
                "FROM TBL_FIRMAS WHERE bot_name = ?",
                (res["bot"],),
            ).fetchall()
            for fila in filas:
                old_fid = fila[0]
                cur = destino.execute(
                    "INSERT INTO TBL_FIRMAS "
                    "(bot_name, event_class, id_nodo, features_json, "
                    " ventana_horas, recurrencia, estado, primera_vista, "
                    " ultima_vista) VALUES (?,?,?,?,?,?,?,?,?)", fila[1:],
                )
                new_fid = cur.lastrowid
                try:
                    eventos = origen.execute(
                        "SELECT evento_ref, ts_evento, orden FROM tbl_firma_eventos "
                        "WHERE firma_id = ?", (old_fid,),
                    ).fetchall()
                    destino.executemany(
                        "INSERT OR IGNORE INTO tbl_firma_eventos "
                        "(firma_id, evento_ref, ts_evento, orden) VALUES (?,?,?,?)",
                        [(new_fid, ev[0], ev[1], ev[2]) for ev in eventos],
                    )
                except sqlite3.OperationalError:
                    pass
            total_firmas += len(filas)
            # Auditoría fase='reconocimiento' del Juez (disjunta por bot)
            try:
                audit = origen.execute(
                    "SELECT timestamp, bot_name, prediccion, confianza, ventana_h, "
                    "verdad, resultado, severidad, reincidencia, detalles_json, "
                    "resuelto_at, fase FROM TBL_JUEZ_AUDITORIA "
                    "WHERE bot_name = ? AND fase = 'reconocimiento'",
                    (res["bot"],),
                ).fetchall()
                destino.executemany(
                    "INSERT INTO TBL_JUEZ_AUDITORIA "
                    "(timestamp, bot_name, prediccion, confianza, ventana_h, "
                    " verdad, resultado, severidad, reincidencia, detalles_json, "
                    " resuelto_at, fase) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", audit,
                )
            except sqlite3.OperationalError:
                pass
            origen.close()
        destino.commit()
        destino.close()
    finally:
        if tmp_owner:
            shutil.rmtree(dir_trabajo, ignore_errors=True)

    return {"bots": bots, "n_workers": n_workers,
            "firmas_unidas": total_firmas,
            "por_bot": {r["bot"]: r["stats"].get("memoria") for r in resultados}}
