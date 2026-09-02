import httpx
import json
from typing import Optional, Callable, Dict, Any, List

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
        num_predict: int = 800  # Reducido para evitar loops con modelos pequeños
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

    def check_availability(self) -> bool:
        """Verifica si el modelo está disponible en Ollama."""
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{self.ollama_host}/api/tags")
                if res.status_code == 200:
                    models = [m["name"] for m in res.json().get("models", [])]
                    # Comprobar si coincide con o sin tag :latest
                    return any(self.model in m or m.startswith(self.model) for m in models)
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
        active_model = self.model
        sys_prompt = system_override if system_override is not None else self.system_prompt
        
        payload = {
            "model": active_model,
            "prompt": prompt,
            "system": sys_prompt,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            }
        }

        full_response = []
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", f"{self.ollama_host}/api/generate", json=payload) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"Ollama API Error ({response.status_code}): {response.read().decode('utf-8')}")
                    
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
        except Exception as e:
            # Intentar fallback si está configurado
            if self.fallback_model and self.fallback_model != self.model:
                if stream_callback:
                    stream_callback(f"\n[Aviso: Conmutando a modelo alternativo {self.fallback_model}]\n")
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
            else:
                raise e

        result = "".join(full_response).strip()
        if result:
            return result

        # An empty answer is a failed inference, not a valid artifact.
        if self.fallback_model and self.fallback_model != active_model:
            fallback_payload = dict(payload)
            fallback_payload["model"] = self.fallback_model
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

        if not result:
            raise RuntimeError(f"El modelo {active_model} devolvió una respuesta vacía")
        return result
