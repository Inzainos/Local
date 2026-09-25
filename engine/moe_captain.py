"""Capitán + MoE (Mixture of Experts) para el Concilio — perfil independiente
(profiles/moe_captain.yaml). Standalone, no toca config.yaml ni el bot de
Telegram en producción.

Flujo (acordado 2026-09-16):
  1. El CAPITÁN (chico) clasifica la tarea y elige un experto del WORK_POOL.
  2. El capitán se descarga; solo el experto elegido queda cargado.
  3. El experto entrega resultado + su propio [SCORE: XX] (0-100).
  4. SIEMPRE se pasa a un auditor del AUDIT_POOL — un modelo DISTINTO al que
     hizo el trabajo, para una segunda opinión real (no autoevaluación).
  5. Si el score del auditor >= threshold_score: se entrega y se guarda en
     memoria compartida. Si no, se devuelve al mismo worker con la crítica,
     hasta max_refinement_rounds.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from engine.profile_pipeline import _resolve_model, _tools_for_resolved_model
from engine.tool_agent import run_with_tools

logger = logging.getLogger(__name__)

SCORE_RE = re.compile(r"\[SCORE:\s*(\d+)\]")


def load_profile(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_task_types(pool: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for member in pool:
        for t in member.get("task_types", []):
            if t not in seen:
                seen.append(t)
    return seen


def _pick_from_pool(pool: List[Dict[str, Any]], task_type: str) -> Dict[str, Any]:
    for member in pool:
        if task_type in member.get("task_types", []):
            return member
    logger.warning(f"ningún miembro del pool declara task_type='{task_type}' — usando el primero")
    return pool[0]


def _read_recent_memory(store_path: str, n: int) -> List[Dict[str, Any]]:
    p = Path(store_path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _append_memory(store_path: str, entry: Dict[str, Any]) -> None:
    p = Path(store_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def classify_task(
    captain_cfg: Dict[str, Any],
    host: str,
    task_prompt: str,
    task_types: List[str],
    scope_note: str = "",
) -> str:
    """El capitán elige UNA etiqueta de task_type para rutear la tarea.

    Deliberadamente NO recibe el pack de memoria persistente completo: el
    capitán solo clasifica, no necesita el contexto profundo, y modelos
    chicos como nemotron-mini tienen una ventana de contexto nativa de solo
    4096 tokens — un pack de ~4000 tokens ya la saturaría casi entera. Basta
    con un `scope_note` corto que le diga a qué proyecto está limitado este
    MoE (ver profiles/moe_sentinel.yaml).
    """
    system_prompt = (
        "Eres el Capitán del Concilio (MoE). Clasifica la tarea del usuario "
        "según a qué tipo pertenece."
        + (f"\n\n{scope_note}" if scope_note else "")
    )
    # Decodificación restringida (Ollama `format`) en vez de confiar en que
    # el modelo obedezca "responde SOLO con la etiqueta" — confirmado en
    # vivo 2026-09-16 que nemotron-mini ignoraba esa instrucción y
    # contestaba la pregunta del usuario directamente (alucinando nombres
    # de agentes que no existen), rompiendo el ruteo. Con format_schema la
    # salida SIEMPRE es una de las etiquetas válidas.
    schema = {
        "type": "object",
        "properties": {"task_type": {"type": "string", "enum": task_types}},
        "required": ["task_type"],
    }
    resp = run_with_tools(
        model=captain_cfg["model"],
        system_prompt=system_prompt,
        user_prompt=task_prompt,
        ollama_host=host,
        tools_schema=None,
        tool_impls=None,
        max_iterations=1,
        num_ctx=2048,
        format_schema=schema,
        # Clasificar es decidir, no crear: determinista.
        temperature=0.0,
    )
    try:
        parsed = json.loads(resp)
        task_type = parsed.get("task_type")
        if task_type in task_types:
            return task_type
    except (json.JSONDecodeError, AttributeError):
        pass
    logger.warning(f"capitán respondió '{resp!r}' fuera de schema — usando '{task_types[0]}'")
    return task_types[0]


def _parse_score(text: str) -> Optional[int]:
    m = SCORE_RE.search(text)
    return int(m.group(1)) if m else None


def _run_pool_member(
    member_cfg: Dict[str, Any],
    host: str,
    user_prompt: str,
    persistent_context: str = "",
    num_ctx: Optional[int] = None,
    timeout_seconds: float = 180.0,
) -> str:
    model = _resolve_model(host, member_cfg)
    tools_schema, tool_impls = _tools_for_resolved_model(member_cfg, host, model)
    system_prompt = member_cfg["system_prompt"]
    if persistent_context:
        system_prompt = (
            f"{persistent_context}\n\n---\n\n"
            "El bloque anterior es tu memoria persistente de referencia "
            "(datos verificados del proyecto). Lo que sigue es tu rol "
            "específico dentro del Concilio:\n\n" + system_prompt
        )
    return run_with_tools(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        ollama_host=host,
        tools_schema=tools_schema,
        tool_impls=tool_impls,
        max_iterations=4,
        num_ctx=num_ctx,
        timeout_seconds=timeout_seconds,
    )


def run_moe(profile_path: str, task_prompt: str) -> Dict[str, Any]:
    profile = load_profile(profile_path)
    host = profile["ollama"]["host"]
    captain_cfg = profile["captain"]
    threshold = profile["consensus"]["threshold_score"]
    max_rounds = profile["consensus"]["max_refinement_rounds"]
    mem_cfg = profile.get("memory", {})
    store_path = mem_cfg.get("shared_store")
    context_n = mem_cfg.get("context_last_n", 0)

    work_pool = profile["work_pool"]
    audit_pool = profile["audit_pool"]
    task_types = _all_task_types(work_pool)

    persistent_context = ""
    pmf = profile.get("persistent_memory_file")
    if pmf:
        p = Path(pmf)
        if p.exists():
            persistent_context = p.read_text(encoding="utf-8")
            logger.info(f"memoria persistente cargada: {pmf} ({len(persistent_context)} chars)")
        else:
            logger.warning(f"persistent_memory_file declarado pero no existe: {pmf}")
    worker_num_ctx = profile.get("worker_num_ctx", 8192) if persistent_context else None
    # Contexto grande = más tokens que procesar antes de responder — el
    # timeout default (180s) no alcanzaba con el pack de Sentinel inyectado
    # (visto en vivo 2026-09-16: httpx.ReadTimeout). Escala con num_ctx.
    worker_timeout_s = profile.get("worker_timeout_seconds", 420.0 if persistent_context else 180.0)

    t0 = time.time()
    logger.info(f"=== MoE Capitán | tarea: {task_prompt[:80]} ===")

    if store_path and context_n:
        recent = _read_recent_memory(store_path, context_n)
        if recent:
            logger.info(f"memoria compartida: {len(recent)} entradas recientes disponibles (no inyectadas automáticamente en v1)")

    scope_note = profile.get("captain_scope_note", "")
    task_type = classify_task(captain_cfg, host, task_prompt, task_types, scope_note=scope_note)
    logger.info(f"capitán clasificó la tarea como: {task_type}")

    worker_cfg = _pick_from_pool(work_pool, task_type)
    auditor_cfg = _pick_from_pool(audit_pool, task_type)
    logger.info(f"worker={worker_cfg['name']}({worker_cfg['model']}) auditor={auditor_cfg['name']}({auditor_cfg['model']})")

    if worker_cfg["model"] == auditor_cfg["model"]:
        logger.warning(
            f"worker y auditor son el MISMO modelo ({worker_cfg['model']}) para "
            f"task_type='{task_type}' — la auditoría pierde independencia real"
        )

    result = _run_pool_member(worker_cfg, host, task_prompt, persistent_context, worker_num_ctx, worker_timeout_s)
    worker_score = _parse_score(result)
    logger.info(f"worker score autoreportado: {worker_score}")

    round_n = 0
    audit_text = ""
    audit_score: Optional[int] = None
    while round_n <= max_rounds:
        audit_prompt = (
            f"Tarea original (DATA):\n{task_prompt}\n\n"
            f"Propuesta del experto {worker_cfg['name']} (DATA):\n{result}"
        )
        audit_text = _run_pool_member(auditor_cfg, host, audit_prompt, persistent_context, worker_num_ctx, worker_timeout_s)
        audit_score = _parse_score(audit_text)
        logger.info(f"ronda {round_n}: audit_score={audit_score}")

        if audit_score is not None and audit_score >= threshold:
            break
        if round_n == max_rounds:
            logger.warning(f"máximo de {max_rounds} rondas alcanzado sin llegar a {threshold}")
            break

        refine_prompt = (
            f"Tarea original (DATA):\n{task_prompt}\n\n"
            f"Tu propuesta anterior (DATA):\n{result}\n\n"
            f"Crítica del auditor (DATA):\n{audit_text}\n\n"
            "Corrige tu propuesta con base en la crítica."
        )
        result = _run_pool_member(worker_cfg, host, refine_prompt, persistent_context, worker_num_ctx, worker_timeout_s)
        worker_score = _parse_score(result)
        round_n += 1

    elapsed = time.time() - t0
    outcome = {
        "task": task_prompt,
        "task_type": task_type,
        "worker": worker_cfg["name"],
        "worker_model": worker_cfg["model"],
        "auditor": auditor_cfg["name"],
        "auditor_model": auditor_cfg["model"],
        "result": result,
        "worker_score": worker_score,
        "audit_score": audit_score,
        "rounds": round_n,
        "elapsed_s": round(elapsed, 1),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if store_path:
        _append_memory(store_path, {
            "timestamp": outcome["timestamp"],
            "task": task_prompt[:200],
            "task_type": task_type,
            "worker": worker_cfg["name"],
            "auditor": auditor_cfg["name"],
            "audit_score": audit_score,
            "rounds": round_n,
        })

    return outcome
