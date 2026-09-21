"""Herramientas de solo lectura para los perfiles independientes del Concilio
(profiles/investigacion.yaml, profiles/general.yaml).

Alcance explícito (2026-09-16): SOLO estos perfiles nuevos las usan. El
config.yaml de producción / engine/orchestrator.py (bot de Telegram en vivo)
no las importa ni las expone — decisión del operador para no abrir superficie
de ataque en un servicio expuesto a mensajes externos.

Sin shell, sin escritura, sin ejecución. Todo path se resuelve contra
ALLOWED_ROOTS; cualquier intento de salir de esas raíces se rechaza.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

ALLOWED_ROOTS = [
    Path("/home/deamon/consensus-expert-agent").resolve(),
    Path("/home/deamon/workspaces").resolve(),
]
MAX_READ_BYTES = 50_000
MAX_GREP_RESULTS = 50


class ToolError(Exception):
    pass


def _resolve_safe(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not any(p == root or root in p.parents for root in ALLOWED_ROOTS):
        raise ToolError(
            f"path fuera de las raíces permitidas ({p}); "
            f"permitidas: {[str(r) for r in ALLOWED_ROOTS]}"
        )
    return p


def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Lee un archivo de texto (solo lectura), opcionalmente por rango de líneas."""
    try:
        p = _resolve_safe(path)
    except ToolError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: no existe: {p}"
    if not p.is_file():
        return f"ERROR: no es un archivo: {p}"
    text = p.read_text(errors="replace")
    lines = text.splitlines()
    end = end_line or len(lines)
    snippet = "\n".join(lines[max(0, start_line - 1):end])
    encoded = snippet.encode()
    if len(encoded) > MAX_READ_BYTES:
        snippet = encoded[:MAX_READ_BYTES].decode(errors="replace") + "\n...[truncado]"
    return snippet


def list_directory(path: str) -> List[str]:
    """Lista el contenido de un directorio (solo lectura)."""
    try:
        p = _resolve_safe(path)
    except ToolError as e:
        return [f"ERROR: {e}"]
    if not p.is_dir():
        return [f"ERROR: no es un directorio: {p}"]
    return sorted(
        str(e.relative_to(p)) + ("/" if e.is_dir() else "") for e in p.iterdir()
    )


def grep_search(pattern: str, path: str = ".", max_results: int = MAX_GREP_RESULTS) -> List[str]:
    """Busca un patrón de texto recursivamente (solo lectura, sin shell=True)."""
    try:
        p = _resolve_safe(path)
    except ToolError as e:
        return [f"ERROR: {e}"]
    try:
        res = subprocess.run(
            [
                "grep", "-rn",
                "--include=*.py", "--include=*.yaml", "--include=*.yml", "--include=*.md",
                "-e", pattern, str(p),
            ],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:
        return [f"ERROR: {e}"]
    lines = res.stdout.splitlines()
    return lines[:max_results] if lines else ["(sin resultados)"]


TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Lee un archivo de texto (solo lectura) dentro de las rutas permitidas. "
                "Úsala SIEMPRE que ya conozcas o te den la ruta exacta del archivo — "
                "es más directa y confiable que grep_search para eso."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa del archivo"},
                    "start_line": {"type": "integer", "description": "Línea inicial (1-indexada), opcional"},
                    "end_line": {"type": "integer", "description": "Línea final inclusive, opcional"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lista el contenido de un directorio (solo lectura).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Directorio a listar"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": (
                "Busca un patrón de TEXTO DENTRO del contenido de .py/.yaml/.yml/.md "
                "recursivamente (solo lectura). NO sirve para encontrar archivos por "
                "nombre — si ya sabes la ruta de un archivo, usa read_file directo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Patrón de búsqueda (regex de grep)"},
                    "path": {"type": "string", "description": "Directorio raíz de búsqueda"},
                },
                "required": ["pattern"],
            },
        },
    },
]

TOOL_IMPLS = {
    "read_file": read_file,
    "list_directory": list_directory,
    "grep_search": grep_search,
}
