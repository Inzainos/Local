"""Ollama sequential model lifecycle for Concilio.

Rule: NEVER keep gemma4:26b (or sentinel-concilio-arbitro) loaded together
with another chat model. Pattern: load → run role → write .concilio → stop/unload → next.
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

    def ensure_exclusive(self, model: str, settle_seconds: float = 1.0) -> None:
        """Stop every other loaded model, then optionally warm `model`."""
        self.stop_all_except(keep=None)  # unload everything first (incl. previous role)
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        # Warm load with keep_alive so the next generate is faster; caller still owns stop.
        try:
            with httpx.Client(timeout=max(self.timeout, 120.0)) as client:
                client.post(
                    f"{self.ollama_host}/api/generate",
                    json={
                        "model": model,
                        "prompt": "",
                        "keep_alive": "5m",
                        "stream": False,
                    },
                )
            logger.info("warm-loaded exclusive model %s", model)
        except Exception as e:
            # Soft-fail: generate() in the agent will still try to load.
            logger.warning("warm-load %s failed (will lazy-load): %s", model, e)

    def unload_after_role(self, model: str) -> None:
        self.stop_model(model)
        # Also clear any stragglers (e.g. tag variants).
        for name in self.list_running():
            if model.split(":")[0] in name:
                self.stop_model(name)
