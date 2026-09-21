"""Bucle genérico de tool-calling (Ollama /api/chat) para los perfiles
independientes del Concilio (profiles/investigacion.yaml, profiles/general.yaml).

NO se usa desde engine/orchestrator.py (producción / bot de Telegram en vivo)
— alcance limitado a los perfiles nuevos por decisión explícita del operador
(2026-09-16), para no exponer ejecución de herramientas a mensajes externos.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def run_with_tools(
    model: str,
    system_prompt: str,
    user_prompt: str,
    ollama_host: str = "http://127.0.0.1:11434",
    tools_schema: Optional[List[Dict[str, Any]]] = None,
    tool_impls: Optional[Dict[str, Callable]] = None,
    max_iterations: int = 5,
    timeout_seconds: float = 180.0,
    num_ctx: Optional[int] = None,
    format_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """Corre una conversación con tool-calling hasta que el modelo responda
    sin pedir más herramientas, o se agoten las iteraciones.

    `num_ctx`: Ollama usa 2048 tokens de contexto por default sin importar
    el máximo que soporte el modelo — si no se pasa explícito aquí, un
    system_prompt largo (p.ej. un pack de memoria inyectado) se trunca en
    silencio. Pasar num_ctx explícito cuando el prompt pueda ser grande.

    `format_schema`: JSON schema para decodificación restringida (Ollama
    `format`). Usar cuando la respuesta DEBE tener una forma exacta (p.ej.
    clasificación de una etiqueta fija) — confirmado en vivo 2026-09-16 que
    instruir por texto "responde SOLO con X" no es confiable: nemotron-mini
    ignoró la instrucción y contestó la pregunta del usuario directamente
    (alucinando), en vez de clasificar. Con `format_schema` la salida queda
    forzada a cumplir el schema sin depender de que el modelo obedezca.
    No combinar con tools_schema en la misma llamada (Ollama no soporta
    tool-calling + format estructurado a la vez de forma confiable).
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tool_impls = tool_impls or {}

    with httpx.Client(timeout=timeout_seconds) as client:
        for iteration in range(max_iterations):
            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
            }
            if tools_schema:
                payload["tools"] = tools_schema
            if format_schema is not None:
                payload["format"] = format_schema
            if num_ctx is not None:
                payload["options"] = {"num_ctx": num_ctx}

            resp = client.post(f"{ollama_host.rstrip('/')}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return msg.get("content", "")

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                impl = tool_impls.get(name)
                if impl is None:
                    result: Any = f"ERROR: herramienta desconocida: {name}"
                else:
                    try:
                        result = impl(**args)
                    except Exception as e:
                        result = f"ERROR ejecutando {name}({args}): {e}"
                logger.info(f"[tool_call {model} it={iteration}] {name}({args}) -> {str(result)[:200]}")
                messages.append({
                    "role": "tool",
                    "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
                })

    logger.warning(f"run_with_tools: máximo de {max_iterations} iteraciones alcanzado sin respuesta final")
    return "(máximo de iteraciones de herramientas alcanzado sin respuesta final)"
