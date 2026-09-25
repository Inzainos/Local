"""Una tarea que muere a medias tiene que dejar rastro y avisarse.

Origen (2026-09-25): un reinicio de Windows corto una tarea del concilio a los
10 minutos, con el codigo ya correcto en la pizarra. No se entrego nada y el
operador se quedo esperando. Sin red y sin modelos: todo esto es de archivo.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory.concilio_store import ConcilioStore, CONCILIO_SCHEMA_VERSION  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return ConcilioStore(str(tmp_path / "sesiones"))


def test_una_sesion_recien_creada_esta_abierta(store):
    store.create("s1", "una tarea")
    assert [s["session_id"] for s in store.sesiones_interrumpidas()] == ["s1"]


def test_al_cerrarla_deja_de_estar_pendiente(store):
    doc = store.create("s1", "una tarea")
    store.cerrar(doc)
    assert store.sesiones_interrumpidas() == []
    assert store.load("s1")["cerrado"]["motivo"] == "terminada"


def test_cerrar_dos_veces_no_pisa_el_motivo(store):
    doc = store.create("s1", "una tarea")
    store.cerrar(doc, motivo="entregada")
    store.cerrar(doc, motivo="otra cosa")
    assert store.load("s1")["cerrado"]["motivo"] == "entregada"


def test_las_sesiones_viejas_no_se_juzgan(store, tmp_path):
    # Escritas sin el campo: no se sabe si terminaron. Avisar seria inventar.
    doc = store.create("vieja", "tarea de ayer")
    doc["schema_version"] = 1
    del doc["cerrado"]
    store.save(doc)
    assert store.sesiones_interrumpidas() == []


def test_un_archivo_ilegible_no_se_reporta(store, tmp_path):
    store.create("buena", "tarea")
    (Path(store.sessions_dir) / "rota.concilio").write_text("{esto no es json")
    assert [s["session_id"] for s in store.sesiones_interrumpidas()] == ["buena"]


def test_se_ordenan_de_mas_antigua_a_mas_reciente(store):
    for sid in ("a", "b", "c"):
        doc = store.create(sid, sid)
        doc["updated_at"] = {"a": 300.0, "b": 100.0, "c": 200.0}[sid]
        with open(store.path_for(sid), "w", encoding="utf-8") as f:
            json.dump(doc, f)
    assert [s["session_id"] for s in store.sesiones_interrumpidas()] == ["b", "c", "a"]


def test_el_aviso_dice_la_tarea_y_que_no_se_entrego():
    from telegram_bot import _texto_interrumpidas
    texto = _texto_interrumpidas([
        {"session_id": "s1", "task": "Escribe una funcion es_ipv4", "round": 2,
         "updated_at": 1790363760.0, "tiene_codigo": True},
    ])
    assert "Escribe una funcion es_ipv4" in texto
    assert "ronda 2" in texto and "No se entrego nada" in texto


def test_el_aviso_resume_cuando_son_muchas():
    from telegram_bot import _texto_interrumpidas
    texto = _texto_interrumpidas([
        {"session_id": f"s{i}", "task": f"tarea {i}", "round": 1,
         "updated_at": 1790363760.0 + i, "tiene_codigo": False} for i in range(8)
    ])
    assert "8 tareas" in texto and "3 mas" in texto
    assert "tarea 7" not in texto


def test_el_enunciado_no_se_interpreta_como_formato():
    # Si se enviara con Markdown, un enunciado con * o ` romperia el mensaje.
    from telegram_bot import _texto_interrumpidas
    texto = _texto_interrumpidas([
        {"session_id": "s1", "task": "usa `re` y *asteriscos_", "round": 0,
         "updated_at": 1790363760.0, "tiene_codigo": False},
    ])
    assert "usa `re` y *asteriscos_" in texto


# ─── El cierre pase lo que pase ──────────────────────────────────────────────

class _OrquestadorFalso:
    """Solo la envoltura de run_consensus, con el cuerpo sustituido."""

    def __init__(self, store, cuerpo):
        self.concilio_store = store
        self._cuerpo = cuerpo

    run_consensus = None  # se rellena abajo

    def _run_consensus(self, tarea, *resto, _sesiones_abiertas=None):
        doc = self.concilio_store.create("s1", tarea)
        if _sesiones_abiertas is not None:
            _sesiones_abiertas.append(doc)
        return self._cuerpo(doc)


def _con_envoltura(store, cuerpo):
    from engine.orchestrator import ConsensusOrchestrator
    o = _OrquestadorFalso(store, cuerpo)
    o.run_consensus = ConsensusOrchestrator.run_consensus.__get__(o)
    return o


def test_la_salida_normal_cierra_la_sesion(store):
    o = _con_envoltura(store, lambda doc: "listo")
    assert o.run_consensus("tarea") == "listo"
    assert store.sesiones_interrumpidas() == []


def test_una_excepcion_tambien_cierra_la_sesion(store):
    def revienta(doc):
        raise RuntimeError("se cayo Ollama")
    o = _con_envoltura(store, revienta)
    with pytest.raises(RuntimeError):
        o.run_consensus("tarea")
    assert store.sesiones_interrumpidas() == []


def test_si_el_proceso_muere_la_sesion_queda_abierta(store):
    # Sin `finally` que corra: es exactamente lo que pasa con un apagon.
    store.create("s1", "tarea")
    assert [s["session_id"] for s in store.sesiones_interrumpidas()] == ["s1"]


def test_el_aviso_no_cierra_nada_si_no_se_pudo_enviar(store, monkeypatch):
    import telegram_bot as tb
    store.create("s1", "tarea")
    monkeypatch.setattr(tb, "orchestrator", type("O", (), {"concilio_store": store})())
    monkeypatch.setattr(tb, "TELEGRAM_CHAT_ID", "")
    asyncio.run(tb.avisar_sesiones_interrumpidas(object()))
    assert [s["session_id"] for s in store.sesiones_interrumpidas()] == ["s1"]


def test_si_el_envio_falla_la_sesion_sigue_pendiente(store, monkeypatch):
    # Hay a quien avisar, pero Telegram no responde. Cerrarla aqui seria
    # perder el aviso para siempre: se queda para el proximo arranque.
    import telegram_bot as tb
    store.create("s1", "tarea")

    class _Bot:
        async def send_message(self, chat_id, text):
            raise ConnectionError("Telegram no responde")

    class _App:
        bot = _Bot()

    monkeypatch.setattr(tb, "orchestrator", type("O", (), {"concilio_store": store})())
    monkeypatch.setattr(tb, "TELEGRAM_CHAT_ID", "12345")
    asyncio.run(tb.avisar_sesiones_interrumpidas(_App()))
    assert [s["session_id"] for s in store.sesiones_interrumpidas()] == ["s1"]


def test_el_aviso_cierra_lo_avisado(store, monkeypatch):
    import telegram_bot as tb
    store.create("s1", "tarea")
    enviados = []

    class _Bot:
        async def send_message(self, chat_id, text):
            enviados.append((chat_id, text))

    class _App:
        bot = _Bot()

    monkeypatch.setattr(tb, "orchestrator", type("O", (), {"concilio_store": store})())
    monkeypatch.setattr(tb, "TELEGRAM_CHAT_ID", "12345")
    asyncio.run(tb.avisar_sesiones_interrumpidas(_App()))
    assert enviados and enviados[0][0] == 12345
    assert store.sesiones_interrumpidas() == []
    assert "avisado al operador" in store.load("s1")["cerrado"]["motivo"]


def test_el_esquema_subio_de_version():
    assert CONCILIO_SCHEMA_VERSION >= 2
