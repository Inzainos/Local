"""Pruebas de la URL de la Mini App cuando el tunel la cambia.

El tunel rapido de Cloudflare estrena URL en cada arranque. Lo que se prueba es
que el bot se entera leyendo el log del tunel y re-registra el boton, sin que
nadie lo reinicie: el reinicio mataba la tarea del concilio en curso.

Sin red: la comprobacion de que la URL responde se sustituye.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

tb = pytest.importorskip("telegram_bot")  # noqa: E402

LOG_UNA = """2026-10-02T04:07:05Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-10-02T04:07:09Z INF |  https://metals-june-kiss-mate.trycloudflare.com    |
2026-10-02T04:07:10Z INF Registered tunnel connection connIndex=0
"""

LOG_DOS = LOG_UNA + """2026-10-02T06:11:00Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-10-02T06:11:04Z INF |  https://quiet-forest-plum-dusk.trycloudflare.com   |
"""


def escribir_log(tmp_path, contenido) -> Path:
    ruta = tmp_path / "cloudflared-mini.log"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# --- leer la URL del log -------------------------------------------------


def test_toma_la_ultima_url_del_log_y_le_pone_la_ruta_mini(tmp_path):
    assert tb.url_tunel_en_log(escribir_log(tmp_path, LOG_DOS)) == (
        "https://quiet-forest-plum-dusk.trycloudflare.com/mini"
    )


def test_con_una_sola_url_devuelve_esa(tmp_path):
    assert tb.url_tunel_en_log(escribir_log(tmp_path, LOG_UNA)) == (
        "https://metals-june-kiss-mate.trycloudflare.com/mini"
    )


def test_sin_log_o_sin_url_no_inventa_nada(tmp_path):
    assert tb.url_tunel_en_log(tmp_path / "no-existe.log") is None
    assert tb.url_tunel_en_log(escribir_log(tmp_path, "INF nada que ver\n")) is None


def test_webapp_url_ok_devuelve_el_valor_vivo_no_el_del_entorno(monkeypatch):
    monkeypatch.setattr(tb, "_webapp_url_actual", "https://viva.example/mini")
    assert tb.webapp_url_ok() == "https://viva.example/mini"

    monkeypatch.setattr(tb, "_webapp_url_actual", "http://sin-tls.example/mini")
    assert tb.webapp_url_ok() is None, "Telegram exige HTTPS"

    monkeypatch.setattr(tb, "_webapp_url_actual", None)
    assert tb.webapp_url_ok() is None


# --- la vigilancia -------------------------------------------------------


@pytest.fixture
def vigilancia(tmp_path, monkeypatch):
    """Deja el bot con un log de tunel propio y el registro del boton contado."""
    estado = {"registros": 0, "comprobadas": []}

    async def registro_falso(application):
        estado["registros"] += 1

    monkeypatch.setattr(tb, "MINI_APP_TUNEL_LOG", escribir_log(tmp_path, LOG_UNA))
    monkeypatch.setattr(tb, "registrar_boton_mini_app", registro_falso)
    monkeypatch.setattr(
        tb, "_webapp_url_actual", "https://metals-june-kiss-mate.trycloudflare.com/mini"
    )
    estado["log"] = tb.MINI_APP_TUNEL_LOG
    return estado


def correr_vigilancia(hasta=None, limite=2.0):
    """Corre la vigilancia hasta que `hasta()` sea cierto, y la corta.

    Sin `hasta`, la deja dar vueltas `limite` segundos: sirve para comprobar lo
    que NO debe pasar.
    """

    async def _ir():
        tarea = asyncio.ensure_future(tb.vigilar_url_mini_app(None, intervalo=0.01))
        try:
            esperado = 0.0
            while esperado < limite:
                if hasta is not None and hasta():
                    return
                await asyncio.sleep(0.01)
                esperado += 0.01
            if hasta is not None:
                pytest.fail("la vigilancia no llego al estado esperado")
        finally:
            tarea.cancel()
            try:
                await tarea
            except asyncio.CancelledError:
                pass

    asyncio.run(_ir())


def test_url_nueva_que_responde_se_adopta_y_re_registra_el_boton(vigilancia, monkeypatch):
    async def responde(url, timeout=6.0):
        vigilancia["comprobadas"].append(url)
        return True

    monkeypatch.setattr(tb, "url_responde", responde)
    vigilancia["log"].write_text(LOG_DOS, encoding="utf-8")

    correr_vigilancia(hasta=lambda: vigilancia["registros"] > 0)

    assert tb._webapp_url_actual == (
        "https://quiet-forest-plum-dusk.trycloudflare.com/mini"
    )
    assert vigilancia["comprobadas"][0] == tb._webapp_url_actual


def test_url_nueva_que_no_responde_no_se_adopta(vigilancia, monkeypatch):
    anterior = tb._webapp_url_actual

    async def no_responde(url, timeout=6.0):
        vigilancia["comprobadas"].append(url)
        return False

    monkeypatch.setattr(tb, "url_responde", no_responde)
    vigilancia["log"].write_text(LOG_DOS, encoding="utf-8")

    correr_vigilancia(hasta=lambda: len(vigilancia["comprobadas"]) >= 2)

    assert tb._webapp_url_actual == anterior, "el log miente, el boton se queda"
    assert vigilancia["registros"] == 0


def test_la_misma_url_no_gasta_una_comprobacion_de_red(vigilancia, monkeypatch):
    async def responde(url, timeout=6.0):
        vigilancia["comprobadas"].append(url)
        return True

    monkeypatch.setattr(tb, "url_responde", responde)

    # El log no cambia: nada que adoptar. Se deja dar varias vueltas.
    correr_vigilancia(limite=0.1)

    assert vigilancia["comprobadas"] == []
    assert vigilancia["registros"] == 0


def test_un_fallo_leyendo_el_log_no_mata_la_vigilancia(vigilancia, monkeypatch):
    vueltas = {"n": 0}

    def explota(log_path=None):
        vueltas["n"] += 1
        raise OSError("disco ocupado")

    monkeypatch.setattr(tb, "url_tunel_en_log", explota)

    correr_vigilancia(limite=0.1)

    assert vueltas["n"] > 1, "sigue vigilando despues del fallo"
