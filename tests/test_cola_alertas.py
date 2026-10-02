"""Pruebas de la entrega de la cola de alertas.

Lo que se prueba es lo que se perdia: un aviso sacado de la cola y no enviado
(el proceso muere en medio), un aviso que Telegram rechaza siempre y tapa la
cola, y una entrega a medias que se daba por entregada.

Todo sin red: el bot de Telegram se sustituye por un doble.
"""
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alert_queue import MAX_INTENTOS, Alert, AlertQueue  # noqa: E402


def cola(tmp_path) -> AlertQueue:
    return AlertQueue(queue_path=str(tmp_path / "alert_queue.json"))


def aviso(ident: str = "a1", **kw) -> Alert:
    base = dict(
        id=ident,
        timestamp=1.0,
        priority="medium",
        title=f"Aviso {ident}",
        message="cuerpo",
    )
    base.update(kw)
    return Alert(**base)


# --- el hueco entre sacar y enviar ---------------------------------------


def test_pop_batch_deja_el_aviso_marcado_en_vuelo(tmp_path):
    q = cola(tmp_path)
    q.push(aviso())

    sacados = q.pop_batch()

    assert [a.id for a in sacados] == ["a1"]
    assert q.size() == 0, "sale de la cola, como antes"
    assert q.get_stats()["en_vuelo"] == 1, "pero queda constancia de que esta en vuelo"


def test_lo_que_quedo_en_vuelo_vuelve_a_la_cabeza_de_la_cola(tmp_path):
    """El caso del reinicio: se saca, muere el proceso, arranca otro."""
    q = cola(tmp_path)
    q.push(aviso("viejo"))
    q.pop_batch()  # y aqui muere el proceso, sin mark_sent ni requeue

    otro_proceso = AlertQueue(queue_path=str(q.queue_path))
    otro_proceso.push(aviso("nuevo"))

    recuperados = otro_proceso.recover_inflight()

    assert [a.id for a in recuperados] == ["viejo"]
    assert [a.id for a in otro_proceso.peek()] == ["viejo", "nuevo"], (
        "el recuperado va primero: llego antes a la cola"
    )
    assert otro_proceso.get_stats()["en_vuelo"] == 0


def test_recover_inflight_sin_nada_en_vuelo_no_toca_la_cola(tmp_path):
    q = cola(tmp_path)
    q.push(aviso())

    assert q.recover_inflight() == []
    assert [a.id for a in q.peek()] == ["a1"]


def test_mark_sent_cierra_el_aviso(tmp_path):
    q = cola(tmp_path)
    q.push(aviso())
    sacado = q.pop_batch()[0]

    q.mark_sent(sacado)

    assert q.get_stats()["en_vuelo"] == 0
    assert AlertQueue(queue_path=str(q.queue_path)).recover_inflight() == [], (
        "un aviso entregado no resucita en el siguiente arranque"
    )


# --- el aviso que tapa la cola -------------------------------------------


def test_requeue_cuenta_intentos_y_al_tope_descarta(tmp_path):
    q = cola(tmp_path)
    q.push(aviso())
    a = q.pop_batch()[0]

    for intento in range(1, MAX_INTENTOS):
        assert q.requeue(a) is True, f"intento {intento} todavia vuelve a la cola"
        a = q.pop_batch()[0]
        assert a.attempts == intento

    assert q.requeue(a) is False, "al tope deja de volver a la cola"
    assert q.size() == 0, "ya no tapa lo que viene detras"
    assert q.get_stats()["descartados"] == 1
    assert q.get_stats()["total_dead"] == 1
    muertos = json.loads(Path(q.dead_path).read_text(encoding="utf-8"))
    assert muertos[0]["id"] == "a1", "se guarda, no se borra"


def test_el_aviso_descartado_no_bloquea_a_los_de_detras(tmp_path):
    q = cola(tmp_path)
    q.push(aviso("malo"))
    q.push(aviso("bueno"))
    malo = q.pop_batch(max_count=1)[0]
    for _ in range(MAX_INTENTOS - 1):
        q.requeue(malo)
        malo = q.pop_batch(max_count=1)[0]

    q.requeue(malo)

    assert [a.id for a in q.peek()] == ["bueno"]


def test_sin_chats_configurados_no_se_gastan_intentos(tmp_path):
    """Una configuracion a medias no debe descartar la cola entera."""
    q = cola(tmp_path)
    q.push(aviso())
    a = q.pop_batch()[0]

    for _ in range(MAX_INTENTOS * 2):
        assert q.requeue(a, contar_intento=False) is True
        a = q.pop_batch()[0]

    assert a.attempts == 0
    assert q.get_stats()["descartados"] == 0


# --- migracion hacia delante ---------------------------------------------


@dataclass
class AlertViejo:
    """El Alert tal como lo lee un proceso que cargo el modulo antes."""
    id: str
    timestamp: float
    priority: str
    title: str
    message: str
    parse_mode: str = "HTML"
    source: str = "sentinel"
    metadata: dict = None


def test_un_aviso_nuevo_se_escribe_con_el_esquema_de_siempre(tmp_path):
    """El bot vivo tiene el modulo viejo en memoria hasta que se reinicie.

    Si el aviso llevara claves que ese bot no conoce, su `Alert(**data)` falla
    DESPUES de haberlo sacado de la cola: aviso perdido.
    """
    q = cola(tmp_path)
    q.push(aviso())

    crudo = json.loads(Path(q.queue_path).read_text(encoding="utf-8"))[0]

    assert "attempts" not in crudo
    assert "pending_chats" not in crudo
    AlertViejo(**crudo)  # el consumidor viejo lo hidrata sin TypeError


def test_un_reintento_si_conserva_su_cuenta_de_intentos(tmp_path):
    q = cola(tmp_path)
    q.push(aviso())
    q.requeue(q.pop_batch()[0])

    crudo = json.loads(Path(q.queue_path).read_text(encoding="utf-8"))[0]

    assert crudo["attempts"] == 1


def test_un_aviso_del_esquema_viejo_se_lee_igual(tmp_path):
    """Lo ya escrito en la cola no tiene los campos nuevos."""
    q = cola(tmp_path)
    q._write_all([
        {
            "id": "viejo",
            "timestamp": 1.0,
            "priority": "critical",
            "title": "Del esquema 1",
            "message": "cuerpo",
            "parse_mode": "HTML",
            "source": "sentinel",
            "metadata": None,
            "campo_que_no_existe": 7,
        }
    ])

    a = q.pop_batch()[0]

    assert a.id == "viejo"
    assert a.attempts == 0
    assert a.pending_chats is None
    assert a.metadata == {}


# --- contadores entre procesos -------------------------------------------


def test_dos_procesos_no_se_pisan_los_contadores(tmp_path):
    """El bot y el Sentinel tienen cada uno su copia de stats en memoria.

    Antes `_save_stats()` escribia el dict completo, asi que cada escritura de
    uno revertia lo que habia sumado el otro: el archivo de produccion marcaba
    2163 enviados contra 92 encolados.
    """
    sentinel = cola(tmp_path)
    bot = AlertQueue(queue_path=str(sentinel.queue_path))

    sentinel.push(aviso("a1"))
    bot.mark_sent(aviso("a1"))
    sentinel.push(aviso("a2"))
    bot.mark_sent(aviso("a2"))
    bot.mark_failed(aviso("a2"))

    stats = AlertQueue(queue_path=str(sentinel.queue_path)).get_stats()
    assert stats["total_enqueued"] == 2
    assert stats["total_sent"] == 2
    assert stats["total_failed"] == 1


# --- la entrega a medias, en el poller del bot ---------------------------


class BotFalso:
    def __init__(self, rechazan=()):
        self.rechazan = {str(c) for c in rechazan}
        self.enviados = []

    async def send_message(self, chat_id, text, parse_mode=None):
        if str(chat_id) in self.rechazan:
            raise RuntimeError("chat_id rechazado")
        self.enviados.append(str(chat_id))


class AppFalsa:
    def __init__(self, bot):
        self.bot = bot


async def _una_vuelta(tb, bot, hasta, limite=4.0):
    """Corre el poller hasta que `hasta()` sea cierto, y lo corta."""
    tarea = asyncio.ensure_future(tb.poll_alert_queue(AppFalsa(bot)))
    try:
        esperado = 0.0
        while esperado < limite:
            if hasta():
                return
            await asyncio.sleep(0.02)
            esperado += 0.02
        pytest.fail("el poller no llego al estado esperado")
    finally:
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass


@pytest.fixture
def bot_module(tmp_path, monkeypatch):
    tb = pytest.importorskip("telegram_bot")
    monkeypatch.setattr(tb, "alert_queue", cola(tmp_path))
    monkeypatch.setattr(tb, "TELEGRAM_CHAT_ID", "111,222")
    return tb


def test_entrega_a_medias_vuelve_a_la_cola_solo_con_quien_falta(bot_module):
    tb = bot_module
    tb.alert_queue.push(aviso())
    bot = BotFalso(rechazan=["222"])

    # attempts == 1 solo despues de que el poller lo devuelva a la cola; la
    # cola ya valia 1 antes de empezar.
    def devuelto():
        pendientes = tb.alert_queue.peek()
        return bool(pendientes) and pendientes[0].attempts == 1

    asyncio.run(_una_vuelta(tb, bot, hasta=devuelto))

    assert bot.enviados == ["111"]
    pendiente = tb.alert_queue.peek()[0]
    assert pendiente.pending_chats == ["222"], (
        "antes bastaba un chat para darlo por entregado y destruirlo"
    )
    assert pendiente.attempts == 1


def test_el_reintento_no_repite_el_aviso_a_quien_ya_lo_recibio(bot_module):
    tb = bot_module
    tb.alert_queue.push(aviso(pending_chats=["222"]))
    bot = BotFalso()

    asyncio.run(_una_vuelta(tb, bot, hasta=lambda: bot.enviados == ["222"]))

    assert tb.alert_queue.size() == 0
    assert tb.alert_queue.get_stats()["en_vuelo"] == 0


def test_el_poller_recupera_lo_que_quedo_en_vuelo_al_arrancar(bot_module):
    tb = bot_module
    tb.alert_queue.push(aviso())
    tb.alert_queue.pop_batch()  # muere el proceso aqui
    bot = BotFalso()

    asyncio.run(_una_vuelta(tb, bot, hasta=lambda: bot.enviados == ["111", "222"]))

    assert tb.alert_queue.size() == 0
    assert tb.alert_queue.get_stats()["en_vuelo"] == 0
