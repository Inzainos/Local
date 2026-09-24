import httpx
import json
from typing import Optional, Callable, Dict, Any, List



def _model_matches(want: str, have: str) -> bool:
    """Exact Ollama tag match (avoid substring false positives)."""
    if not want or not have:
        return False
    if have == want:
        return True
    if ":" not in want and (have == want or have.startswith(want + ":")):
        return True
    return False


class BaseExpertAgent:
    def __init__(
        self,
        name: str,
        role: str,
        model: str,
        fallback_model: Optional[str] = None,
        temperature: float = 0.3,
        system_prompt: str = "",
        ollama_host: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 180.0,
        num_predict: int = 800,
        num_ctx: Optional[int] = None,
        timeout_retries: int = 2,
        keep_alive: Optional[str] = "0",
        lifecycle=None,
    ):
        self.name = name
        self.role = role
        self.model = model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.system_prompt = system_prompt.strip()
        self.ollama_host = ollama_host.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self.timeout_retries = max(0, int(timeout_retries))
        # Default keep_alive=0 so weights drop after each call unless lifecycle manages exclusivity.
        self.keep_alive = keep_alive
        self.lifecycle = lifecycle

    def check_availability(self) -> bool:
        """Verifica si el modelo está disponible en Ollama."""
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{self.ollama_host}/api/tags")
                if res.status_code == 200:
                    models = [m["name"] for m in res.json().get("models", [])]
                    return any(_model_matches(self.model, m) for m in models)
        except Exception:
            return False
        return False

    def generate(
        self,
        prompt: str,
        system_override: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Envía un prompt a Ollama y retorna la respuesta (con soporte de streaming)."""
        if self.lifecycle is not None:
            self.lifecycle.ensure_exclusive(self.model)

        active_model = self.model
        sys_prompt = system_override if system_override is not None else self.system_prompt

        payload: Dict[str, Any] = {
            "model": active_model,
            "prompt": prompt,
            "system": sys_prompt,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }
        # num_ctx ACOTADO. Sin fijarlo, Ollama reserva cache para la ventana
        # COMPLETA del modelo. Medido el 2026-09-24 con concilio-medium
        # (deepseek-r1:8b, ventana 131.072):
        #
        #   size          25,7 GB   <- modelo 5,2 + cache de contexto
        #   size_vram      2,1 GB   <- lo unico que entra en la RTX 3050 (4 GB)
        #   context_length 131.072  <- para un prompt real de ~5.000 tokens
        #
        # El resto se va a RAM del host y de ahi a disco: por eso la etapa del
        # coder tardaba 20-30 min por vuelta. La cache escala lineal con la
        # ventana, asi que acotarla a lo que la tarea necesita la reduce ~16x.
        if self.num_ctx:
            payload["options"]["num_ctx"] = int(self.num_ctx)

        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive

        full_response = []
        last_error: Optional[Exception] = None
        attempts = 1 + self.timeout_retries
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    with client.stream("POST", f"{self.ollama_host}/api/generate", json=payload) as response:
                        if response.status_code != 200:
                            raise RuntimeError(
                                f"Ollama API Error ({response.status_code}): {response.read().decode('utf-8')}"
                            )

                        for line in response.iter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("response", "")
                                if token:
                                    full_response.append(token)
                                    if stream_callback:
                                        stream_callback(token)
                                if chunk.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
                last_error = None
                if self.lifecycle is not None:
                    self.lifecycle.mark_loaded(active_model)
                break
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                full_response = []
                if attempt < attempts:
                    if stream_callback:
                        stream_callback(f"\n[Aviso: timeout/transporte, reintento {attempt}/{attempts}]\n")
                    continue
            except Exception as e:
                last_error = e
                break

        if last_error is not None and not full_response:
            e = last_error
            if self.fallback_model and self.fallback_model != self.model:
                if stream_callback:
                    stream_callback(f"\n[Aviso: Conmutando a modelo alternativo {self.fallback_model}]\n")
                if self.lifecycle is not None:
                    self.lifecycle.ensure_exclusive(self.fallback_model)
                payload["model"] = self.fallback_model
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    with client.stream("POST", f"{self.ollama_host}/api/generate", json=payload) as response:
                        for line in response.iter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("response", "")
                                if token:
                                    full_response.append(token)
                                    if stream_callback:
                                        stream_callback(token)
                            except Exception:
                                continue
                if self.lifecycle is not None:
                    self.lifecycle.mark_loaded(self.fallback_model)
            else:
                raise e

        result = "".join(full_response).strip()
        if result:
            return result

        if self.fallback_model and self.fallback_model != active_model:
            fallback_payload = dict(payload)
            fallback_payload["model"] = self.fallback_model
            if self.lifecycle is not None:
                self.lifecycle.ensure_exclusive(self.fallback_model)
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", f"{self.ollama_host}/api/generate", json=fallback_payload) as response:
                    response.raise_for_status()
                    fallback_response = []
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("response", "")
                        if token:
                            fallback_response.append(token)
                            if stream_callback:
                                stream_callback(token)
                        if chunk.get("done", False):
                            break
            result = "".join(fallback_response).strip()
            if self.lifecycle is not None:
                self.lifecycle.mark_loaded(self.fallback_model)

        if not result:
            raise RuntimeError(f"El modelo {active_model} devolvió una respuesta vacía")
        return result
