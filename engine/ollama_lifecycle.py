"""Ollama sequential lifecycle: ONE model resident at a time."""
from __future__ import annotations
import logging, subprocess
from typing import List, Optional
import httpx

logger = logging.getLogger("concilio.ollama")


class OllamaLifecycle:
    def __init__(self, host: str = "http://127.0.0.1:11434", timeout: float = 120.0):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._loaded: Optional[str] = None

    def list_running(self) -> List[str]:
        try:
            with httpx.Client(timeout=min(self.timeout, 30)) as client:
                res = client.get(f"{self.host}/api/ps")
                if res.status_code != 200:
                    return []
                out = []
                for m in res.json().get("models") or []:
                    name = m.get("name") or m.get("model") or ""
                    if name:
                        out.append(name)
                return out
        except Exception as e:
            logger.warning("list_running: %s", e)
            return []

    def stop(self, model: str) -> bool:
        if not model:
            return False
        ok = False
        try:
            proc = subprocess.run(["ollama", "stop", model], capture_output=True, text=True, timeout=60)
            ok = proc.returncode == 0
        except Exception as e:
            logger.warning("ollama stop CLI: %s", e)
        try:
            with httpx.Client(timeout=min(self.timeout, 30)) as client:
                client.post(
                    f"{self.host}/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": 0, "stream": False},
                )
            ok = True
        except Exception as e:
            logger.warning("API unload: %s", e)
        if self._loaded == model:
            self._loaded = None
        return ok

    def stop_all_known(self, models: List[str]) -> None:
        running = self.list_running()
        for m in list(dict.fromkeys([*(models or []), *running])):
            if m:
                self.stop(m)

    def unload_all(self) -> None:
        self.stop_all_known([])

    def warm(self, model: str) -> None:
        if self._loaded and self._loaded != model:
            self.stop(self._loaded)
        for name in self.list_running():
            if model.split(":")[0] not in name:
                self.stop(name)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                client.post(
                    f"{self.host}/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": "5m", "stream": False},
                )
            self._loaded = model
        except Exception as e:
            logger.warning("warm %s failed: %s", model, e)
            self._loaded = model
