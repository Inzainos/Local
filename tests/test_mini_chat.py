"""Chat del Concilio en la Mini App: /api/mini/chat y la clave del túnel.

El chat rápido usa fast_ask (un modelo, segundos) y se BLOQUEA mientras corre
una tarea: fast_ask haría ensure_exclusive y desalojaría el modelo que la
tarea está usando (ping-pong en Ollama).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

import web_ui                                        # noqa: E402


@pytest.fixture()
def client():
    # Se llama DENTRO de la prueba para que los monkeypatch de setup lleguen
    # antes de la primera peticion.
    with TestClient(web_ui.app) as c:
        yield c


def _sin_tareas(web_ui_mod):
    """Deja task_jobs vacio (otra prueba pudo dejar uno en curso)."""
    web_ui_mod.task_jobs.clear()


def test_chat_responde_con_fast_ask(client, monkeypatch):
    llamado = []
    monkeypatch.setattr(web_ui, "MINI_APP_KEY", "")
    monkeypatch.setattr(web_ui.orchestrator, "fast_ask",
                        lambda p, **k: llamado.append(p) or "respuesta de prueba")
    _sin_tareas(web_ui)
    r = client.post("/api/mini/chat", json={"prompt": "hola"})
    assert r.status_code == 200
    assert r.json()["reply"] == "respuesta de prueba"
    assert r.json()["mode"] == "rapida"
    assert llamado == ["hola"]


def test_chat_vacio_da_400(client, monkeypatch):
    monkeypatch.setattr(web_ui, "MINI_APP_KEY", "")
    _sin_tareas(web_ui)
    r = client.post("/api/mini/chat", json={"prompt": "   "})
    assert r.status_code == 400


def test_chat_bloqueado_mientras_corre_una_tarea(client, monkeypatch):
    monkeypatch.setattr(web_ui, "MINI_APP_KEY", "")
    _sin_tareas(web_ui)
    web_ui.task_jobs["job-x"] = {"status": "RUNNING", "prompt": "t",
                                 "created_at": 0, "updated_at": 0}
    try:
        r = client.post("/api/mini/chat", json={"prompt": "hola"})
        assert r.status_code == 409, "no debe desalojar el modelo de la tarea en curso"
        assert "tarea" in r.json()["error"].lower()
    finally:
        web_ui.task_jobs.clear()


def test_chat_con_clave_sin_header_da_401(client, monkeypatch):
    monkeypatch.setattr(web_ui, "MINI_APP_KEY", "secreto")
    monkeypatch.setattr(web_ui.orchestrator, "fast_ask",
                        lambda p, **k: "no debería llegar aquí")
    _sin_tareas(web_ui)
    r = client.post("/api/mini/chat", json={"prompt": "hola"})
    assert r.status_code == 401
    r2 = client.post("/api/mini/chat", json={"prompt": "hola"},
                     headers={"X-Mini-Key": "secreto"})
    assert r2.status_code == 200
    r3 = client.post("/api/mini/chat", json={"prompt": "hola"},
                     headers={"X-Mini-Key": "otra"})
    assert r3.status_code == 401


def test_task_con_clave_mal_da_401(client, monkeypatch):
    """La clave también cierra /api/task: era el endpoint abierto del túnel.

    _run_task va a no-op: el 202 dispara el executor de verdad y pytest se
    quedaría esperando un run_consensus de minutos (medido: hang de la suite).
    """
    monkeypatch.setattr(web_ui, "MINI_APP_KEY", "secreto")
    monkeypatch.setattr(web_ui, "_run_task", lambda job_id, prompt: None)
    _sin_tareas(web_ui)
    r = client.post("/api/task", json={"prompt": "tarea"})
    assert r.status_code == 401, "/api/task expuesto por el túnel debe pedir clave"
    r2 = client.post("/api/task", json={"prompt": "tarea"},
                     headers={"X-Mini-Key": "secreto"})
    assert r2.status_code in (200, 202)


def test_sin_clave_configurada_todo_queda_como_antes(client, monkeypatch):
    monkeypatch.setattr(web_ui, "MINI_APP_KEY", "")
    _sin_tareas(web_ui)
    r = client.post("/api/task", json={"prompt": ""})
    assert r.status_code == 400, "sin clave no exige header; valida el prompt igual"
