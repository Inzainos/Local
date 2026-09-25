"""Pruebas de ModelLifecycle, centradas en la instrumentacion de num_ctx.

POR QUE EXISTEN
---------------
El 2026-09-24 el log de una corrida decia cuatro veces:

    warm-loaded exclusive model concilio-investigador (num_ctx pedido=16384,
    concedido=None)

Leido de corrido parece una confirmacion. No lo era: `concedido=None`
significa que la comprobacion contra /api/ps no encontro el modelo, asi que
la ventana real quedaba SIN VERIFICAR. El `else` de la version anterior
metia ese caso en el mismo cajon que el exito --- silencio tratado como
afirmacion, dentro de la propia herramienta de medir.

Estas pruebas fijan los TRES desenlaces por separado.
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.model_lifecycle import ModelLifecycle  # noqa: E402


class _RespuestaPs:
    """Remeda la respuesta de GET /api/ps."""

    def __init__(self, modelos):
        self._modelos = modelos
        self.status_code = 200

    def json(self):
        return {"models": self._modelos}


class _ClienteFalso:
    """Cliente httpx de mentira: no sale a la red y anota lo que se le pide."""

    def __init__(self, ps_modelos, posts):
        self._ps_modelos = ps_modelos
        self._posts = posts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, *a, **k):
        return _RespuestaPs(self._ps_modelos)

    def post(self, url, json=None, **k):
        self._posts.append(json)
        return _RespuestaPs([])


@pytest.fixture
def espiar(monkeypatch):
    """Sustituye httpx.Client y el `ollama stop` por dobles."""

    def _montar(ps_modelos):
        posts = []
        import engine.model_lifecycle as ml

        monkeypatch.setattr(ml.httpx, "Client",
                            lambda *a, **k: _ClienteFalso(ps_modelos, posts))
        # stop_all_except no debe intentar nada real
        monkeypatch.setattr(ModelLifecycle, "stop_all_except",
                            lambda self, keep=None: None)
        return posts

    return _montar


def _registros(caplog, nivel):
    return [r.getMessage() for r in caplog.records if r.levelno == nivel]


# ─── los tres desenlaces ─────────────────────────────────────────────────────

def test_ventana_confirmada_es_info(espiar, caplog):
    """Cuando /api/ps confirma la ventana pedida, basta con INFO."""
    espiar([{"name": "concilio-medium:latest", "context_length": 16384}])
    lc = ModelLifecycle()
    with caplog.at_level(logging.INFO, logger="engine.model_lifecycle"):
        lc.ensure_exclusive("concilio-medium", settle_seconds=0, num_ctx=16384)
    assert not _registros(caplog, logging.WARNING)
    assert any("concedido=16384" in m for m in _registros(caplog, logging.INFO))


def test_ventana_distinta_avisa(espiar, caplog):
    """Si Ollama concede otra ventana, es un AVISO: la cache no es la esperada."""
    espiar([{"name": "concilio-medium:latest", "context_length": 131072}])
    lc = ModelLifecycle()
    with caplog.at_level(logging.INFO, logger="engine.model_lifecycle"):
        lc.ensure_exclusive("concilio-medium", settle_seconds=0, num_ctx=16384)
    avisos = _registros(caplog, logging.WARNING)
    assert avisos, "conceder 131072 tras pedir 16384 tiene que avisar"
    assert "131072" in avisos[0]


def test_sin_verificar_no_se_reporta_como_exito(espiar, caplog):
    """EL FALLO DE HOY: /api/ps no devuelve el modelo.

    No se puede afirmar nada sobre la ventana. Antes esto caia en el `else`
    y salia por INFO como si todo hubiera ido bien.
    """
    espiar([])  # /api/ps vacio: el modelo no aparece
    lc = ModelLifecycle()
    with caplog.at_level(logging.INFO, logger="engine.model_lifecycle"):
        lc.ensure_exclusive("concilio-medium", settle_seconds=0, num_ctx=16384)

    avisos = _registros(caplog, logging.WARNING)
    assert avisos, ("no verificar la ventana NO es un exito: tiene que salir "
                    "por WARNING, no por INFO")
    assert "NO SE PUDO VERIFICAR" in avisos[0]
    # Y jamas debe decir "warm-loaded ... concedido=None" con cara de exito.
    assert not any("concedido=None" in m for m in _registros(caplog, logging.INFO))


def test_sin_num_ctx_no_inventa_avisos(espiar, caplog):
    """Quien no pide ventana no puede quejarse de la que le den."""
    espiar([])
    lc = ModelLifecycle()
    with caplog.at_level(logging.INFO, logger="engine.model_lifecycle"):
        lc.ensure_exclusive("concilio-medium", settle_seconds=0, num_ctx=None)
    assert not _registros(caplog, logging.WARNING)


def test_la_precarga_lleva_num_ctx(espiar):
    """La PRECARGA es la que fija la ventana; si no va aqui, no sirve.

    Pasarlo solo en generate() no bastaba: medido el 2026-09-24, el modelo
    quedaba con la ventana completa reservada.
    """
    posts = espiar([{"name": "concilio-medium:latest", "context_length": 16384}])
    ModelLifecycle().ensure_exclusive("concilio-medium", settle_seconds=0,
                                      num_ctx=16384)
    assert posts, "la precarga no llego a hacer POST"
    assert posts[0].get("options", {}).get("num_ctx") == 16384
