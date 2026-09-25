"""Ollama sequential model lifecycle for Concilio.

Rule: NEVER keep the heavy arbiter (gemma3:4b / concilio-arbitro /
sentinel-concilio-arbitro) loaded together with another chat model. Pattern: load → run role → write .concilio → stop/unload → next.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class ModelLifecycle:
    def __init__(self, ollama_host: str = "http://127.0.0.1:11434", timeout: float = 30.0):
        self.ollama_host = ollama_host.rstrip("/")
        self.timeout = timeout

    def list_running(self) -> List[str]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.ollama_host}/api/ps")
                if res.status_code != 200:
                    return []
                models = res.json().get("models") or []
                names = []
                for m in models:
                    name = m.get("name") or m.get("model") or ""
                    if name:
                        names.append(name)
                return names
        except Exception as e:
            logger.warning("list_running failed: %s", e)
            return []

    def stop_model(self, model: str) -> bool:
        """Unload a model from VRAM/RAM via `ollama stop` (CLI) with API fallback."""
        if not model:
            return False
        # Prefer CLI — most reliable unload on current Ollama.
        try:
            proc = subprocess.run(
                ["ollama", "stop", model],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode == 0:
                logger.info("ollama stop %s OK", model)
                return True
            logger.warning("ollama stop %s rc=%s stderr=%s", model, proc.returncode, proc.stderr[:200])
        except FileNotFoundError:
            logger.warning("ollama CLI not found; trying API unload")
        except Exception as e:
            logger.warning("ollama stop CLI failed: %s", e)

        # API fallback: generate with keep_alive=0 to unload after (or immediately).
        try:
            with httpx.Client(timeout=self.timeout) as client:
                client.post(
                    f"{self.ollama_host}/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": 0, "stream": False},
                )
            logger.info("API keep_alive=0 unload requested for %s", model)
            return True
        except Exception as e:
            logger.warning("API unload failed for %s: %s", model, e)
            return False

    def stop_all_except(self, keep: Optional[str] = None) -> None:
        running = self.list_running()
        for name in running:
            base = name.split(":")[0]
            keep_base = (keep or "").split(":")[0]
            if keep and (name == keep or name.startswith(keep) or base == keep_base):
                continue
            self.stop_model(name)

    def ensure_exclusive(self, model: str, settle_seconds: float = 1.0,
                         num_ctx: Optional[int] = None) -> None:
        """Stop every other loaded model, then optionally warm `model`."""
        self.stop_all_except(keep=None)  # unload everything first (incl. previous role)
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        # Warm load with keep_alive so the next generate is faster; caller still owns stop.
        try:
            with httpx.Client(timeout=max(self.timeout, 120.0)) as client:
                cuerpo = {
                    "model": model,
                    "prompt": "",
                    "keep_alive": "5m",
                    "stream": False,
                }
                # La PRECARGA es la que fija la ventana. Sin num_ctx aqui,
                # Ollama reserva la del modelo (131.072 en deepseek/llama3.2) y
                # el generate posterior ya no puede reducirla sin recargar:
                # medido, el modelo quedaba con 18-25 GB reservados y solo un
                # 8-10% en GPU. Pasarlo solo en generate() no bastaba.
                if num_ctx:
                    cuerpo["options"] = {"num_ctx": int(num_ctx)}
                client.post(f"{self.ollama_host}/api/generate", json=cuerpo)
            # Registrar lo PEDIDO y lo CONCEDIDO. Sin esto, diagnosticar por
            # que un modelo quedo con la ventana completa obliga a muestrear
            # /api/ps a ciegas y a inventar hipotesis --- que es exactamente lo
            # que paso el 2026-09-24: cargas inconsistentes del mismo modelo,
            # unas con 16.384 y otras con 131.072, sin forma de saber quien las
            # hizo.
            concedido = None
            try:
                with httpx.Client(timeout=20.0) as c2:
                    for m in c2.get(f"{self.ollama_host}/api/ps").json().get("models", []):
                        if m.get("name", "").split(":")[0] == model.split(":")[0]:
                            concedido = m.get("context_length")
                            break
            except Exception:
                pass
            # TRES resultados, no dos. La version anterior tenia un `else`
            # que se comia el caso "no se pudo verificar" y lo registraba a
            # nivel INFO como si fuera un exito: el log de las 19:01 del
            # 2026-09-24 decia cuatro veces "warm-loaded ... concedido=None",
            # que leido de corrido parece confirmacion y en realidad es que
            # /api/ps no encontro el modelo. Mismo patron que el resto de los
            # fallos de esta semana: el silencio tratado como afirmacion, y
            # aqui dentro de la propia herramienta de medir.
            if num_ctx and concedido is None:
                logger.warning(
                    "warm-load %s: se pidio num_ctx=%s y NO SE PUDO VERIFICAR "
                    "lo concedido (el modelo no aparecio en /api/ps; puede que "
                    "aun estuviera cargando). La ventana real es DESCONOCIDA, "
                    "no la pedida", model, num_ctx)
            elif num_ctx and int(concedido) != int(num_ctx):
                logger.warning(
                    "warm-load %s: se pidio num_ctx=%s y Ollama concedio %s "
                    "--- la cache reservada no es la esperada",
                    model, num_ctx, concedido)
            else:
                logger.info("warm-loaded exclusive model %s (num_ctx pedido=%s, "
                            "concedido=%s)", model, num_ctx, concedido)
        except Exception as e:
            # Soft-fail: generate() in the agent will still try to load.
            logger.warning("warm-load %s failed (will lazy-load): %s", model, e)

    def unload_after_role(self, model: str) -> None:
        self.stop_model(model)
        # Also clear any stragglers (e.g. tag variants).
        for name in self.list_running():
            if model.split(":")[0] in name:
                self.stop_model(name)
