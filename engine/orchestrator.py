import yaml
import httpx
import os
import time
import re
from typing import Optional, Callable, Dict, Any

from memory.shared_context import SharedMemory
from memory.blackboard import Blackboard, TaskStatus
from memory.repository_context import load_repository_context, project_metadata
from memory.concilio_store import ConcilioStore
from memory.anti_injection import fence_untrusted, build_data_preamble
from memory.memory_pack import build_memory_pack, memory_pack_metadata
from agents.researcher import ResearcherAgent
from agents.coder import CoderAgent
from agents.optimizer import OptimizerAgent
from .router import TaskRouter, PipelineType
from .model_lifecycle import ModelLifecycle


class ConsensusOrchestrator:
    """
    Motor central del Concilio: cadena secuencial un modelo a la vez.
    Patrón: load → rol → write .concilio → unload → siguiente.
    Nunca gemma4:26b junto a otro modelo.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = os.path.abspath(config_path)
        self._project_root = os.path.dirname(self.config_path)
        self.config = self._load_config(self.config_path)
        self.ollama_host = self.config["ollama"]["host"]
        self.timeout = self.config["ollama"].get("timeout_seconds", 180)
        self.threshold = self.config["consensus"].get("threshold_score", 85)
        self.max_rounds = self.config["consensus"].get("max_refinement_rounds", 3)
        self.timeout_retries = self.config["consensus"].get("timeout_retries", 2)
        self.auto_refine = bool(self.config["consensus"].get("auto_refine", True))
        raw_db = self.config["memory"].get("sqlite_db", "data/shared_memory.db")
        if os.path.isabs(raw_db):
            self.db_path = raw_db
        else:
            self.db_path = os.path.normpath(os.path.join(self._project_root, raw_db))

        conc = self.config.get("concilio") or {}
        self.sequential = bool(conc.get("sequential", True))
        self.verify_with_light = bool(conc.get("verify_with_light", True))
        self.settle_seconds = float(conc.get("settle_seconds", 1.0))
        sessions_rel = conc.get("sessions_dir", "data/sessions")
        if os.path.isabs(sessions_rel):
            self.sessions_dir = sessions_rel
        else:
            self.sessions_dir = os.path.normpath(os.path.join(self._project_root, sessions_rel))
        self.concilio_store = ConcilioStore(self.sessions_dir)
        self.inject_sentinel = bool(conc.get('inject_sentinel_architecture', False))
        self.lifecycle = ModelLifecycle(ollama_host=self.ollama_host)

        r_cfg = self.config["roles"]["researcher"]
        c_cfg = self.config["roles"]["coder"]
        o_cfg = self.config["roles"]["optimizer"]

        preferred_worker = conc.get("worker_model") or r_cfg["model"]
        preferred_arbiter = conc.get("arbiter_model") or o_cfg["model"]
        base_worker = r_cfg.get("fallback_model") or r_cfg["model"] or "qwen2.5:1.5b"
        base_arbiter = "gemma4:26b" if self._model_installed("gemma4:26b") else (o_cfg.get("fallback_model") or o_cfg.get("model") or "qwen2.5:1.5b")
        # Prefer custom Modelfile tags when present in Ollama.
        worker_model = self._resolve_model(preferred_worker, base_worker)
        arbiter_model = self._resolve_model(preferred_arbiter, base_arbiter)
        # gemma4:26b ONLY as final arbiter — never as worker.
        if "gemma4" in worker_model.lower() or worker_model == arbiter_model:
            worker_model = base_worker if "gemma4" not in base_worker.lower() else "qwen2.5:1.5b"

        self.researcher = ResearcherAgent(
            name=r_cfg["name"],
            role="Investigador",
            model=worker_model,
            fallback_model=r_cfg.get("fallback_model") or base_worker,
            temperature=r_cfg.get("temperature", 0.3),
            system_prompt=self._augment_system(r_cfg["system_prompt"]),
            ollama_host=self.ollama_host,
            timeout_seconds=self.timeout,
            num_predict=r_cfg.get("max_tokens", 1500),
            timeout_retries=self.timeout_retries,
        )
        self.coder = CoderAgent(
            name=c_cfg["name"],
            role="Programador",
            model=worker_model,
            fallback_model=c_cfg.get("fallback_model") or base_worker,
            temperature=c_cfg.get("temperature", 0.2),
            system_prompt=self._augment_system(c_cfg["system_prompt"]),
            ollama_host=self.ollama_host,
            timeout_seconds=self.timeout,
            num_predict=c_cfg.get("max_tokens", 1500),
            timeout_retries=self.timeout_retries,
        )
        self.optimizer = OptimizerAgent(
            name=o_cfg["name"],
            role="Optimizador y Árbitro",
            model=arbiter_model,
            fallback_model=o_cfg.get("fallback_model") or base_worker,
            temperature=o_cfg.get("temperature", 0.2),
            system_prompt=self._augment_system(o_cfg["system_prompt"]),
            ollama_host=self.ollama_host,
            timeout_seconds=self.timeout,
            num_predict=o_cfg.get("max_tokens", 1500),
            timeout_retries=self.timeout_retries,
        )

        # Optional: swap to thin custom Modelfiles if present and prefer_custom_models
        if bool(conc.get("prefer_custom_models", True)):
            self._maybe_prefer_custom_models()


    def _model_exists(self, name: str) -> bool:
        if not name:
            return False
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{self.ollama_host}/api/tags")
                if res.status_code != 200:
                    return False
                models = [m.get("name", "") for m in res.json().get("models", [])]
                return any(name == m or m.startswith(name + ":") or name in m for m in models)
        except Exception:
            return False

    def _maybe_prefer_custom_models(self) -> None:
        """Prefer thin concilio-* aliases when inject_sentinel=false; sentinel-* first only if inject on."""
        exists = self._model_exists if hasattr(self, "_model_exists") else self._model_installed
        if getattr(self, "inject_sentinel", False):
            worker_candidates = [
                "sentinel-concilio-worker",
                "concilio-worker",
                "concilio-lightest",
                "concilio-medium",
                getattr(self.researcher, "model", "") or "qwen2.5:1.5b",
            ]
            arbiter_candidates = [
                "sentinel-concilio-arbitro",
                "concilio-arbitro",
                "concilio-heavy",
                "gemma4:26b",
                getattr(self.optimizer, "model", "") or "gemma4:26b",
            ]
        else:
            # Thin Concilio: prefer worker/arbitro / lightest|medium|heavy over sentinel-* tags
            worker_candidates = [
                "concilio-worker",
                "concilio-lightest",
                "concilio-medium",
                "sentinel-concilio-worker",
                getattr(self.researcher, "model", "") or "qwen2.5:1.5b",
                "qwen2.5:1.5b",
            ]
            arbiter_candidates = [
                "concilio-arbitro",
                "concilio-heavy",
                "sentinel-concilio-arbitro",
                "gemma4:26b",
                getattr(self.optimizer, "model", "") or "gemma4:26b",
            ]
        worker = next((m for m in worker_candidates if m and exists(m)), "qwen2.5:1.5b")
        arbitro = next((m for m in arbiter_candidates if m and exists(m)), "gemma4:26b")
        if "gemma4" in worker.lower() or worker == arbitro:
            worker = next((m for m in worker_candidates if m and "gemma" not in m.lower() and exists(m)), "qwen2.5:1.5b")
        self.researcher.model = worker
        self.coder.model = worker
        self.optimizer.model = arbitro
        self.researcher.fallback_model = "qwen2.5:1.5b"
        self.coder.fallback_model = "qwen2.5:1.5b"
        self.optimizer.fallback_model = "gemma4:26b" if exists("gemma4:26b") else "qwen2.5:1.5b"

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def _augment_system(base: str) -> str:
        return f"{build_data_preamble()}\n{(base or '').strip()}"

    def _model_installed(self, name: str) -> bool:
        return self._model_exists(name) if hasattr(self, "_model_exists") else False

    def _resolve_model(self, preferred: str, fallback: str) -> str:
        if preferred and self._model_installed(preferred):
            return preferred
        if fallback and self._model_installed(fallback):
            return fallback
        return preferred or fallback

    def _run_exclusive(self, model: str, fn, stage: str, on_stage_start, on_stage_end, agent_name: str, msg: str):
        if on_stage_start:
            on_stage_start(stage, agent_name, msg)
        if self.sequential:
            self.lifecycle.ensure_exclusive(model, settle_seconds=self.settle_seconds)
        result = None
        try:
            result = fn()
            if on_stage_end:
                try:
                    on_stage_end(stage, result)
                except Exception:
                    # Never skip unload because a UI callback failed
                    pass
            return result
        finally:
            if self.sequential:
                try:
                    self.lifecycle.unload_after_role(model)
                except Exception:
                    pass

    def _sync_concilio_from_blackboard(self, doc: Dict[str, Any], blackboard: Blackboard) -> None:
        if blackboard.research and blackboard.research.raw_content:
            self.concilio_store.set_section(doc, "research", blackboard.research.raw_content)
        if blackboard.code_proposal and blackboard.code_proposal.raw_content:
            self.concilio_store.set_section(doc, "code", blackboard.code_proposal.raw_content)
        if blackboard.critiques:
            last = blackboard.critiques[-1]
            self.concilio_store.set_section(doc, "critique", getattr(last, "raw_content", str(last)) or "")
        self.concilio_store.save(doc)

    def _light_verify_score(self, doc: Dict[str, Any], claimed_score: int, stream_callback=None) -> int:
        """Reload LIGHT model; treat .concilio as DATA; confirm numeric score."""
        md = self.concilio_store.to_markdown(doc)
        fenced = fence_untrusted(md, role="concilio_session")
        preamble = build_data_preamble(("task", "research", "code", "critique", "scores"))
        prompt = (
            f"{preamble}\n"
            f"El árbitro reportó score={claimed_score}. Lee SOLO los DATOS cercados y "
            f"confirma el último puntaje numérico 0-100. Responde UNA línea:\n"
            f"[PUNTUACION_VERIFICADA: XX]\n"
            f"(también aceptable [PUNTUACION_CONSENSO: XX])\n\n{fenced}"
        )
        text = self.researcher.generate(prompt, stream_callback=stream_callback) or ""
        patterns = (
            r"\[PUNTUACION_VERIFICADA:\s*(\d{1,3})\]",
            r"\[PUNTUACION_CONSENSO:\s*(\d{1,3})\]",
            r"PUNTUACION[_ ]?(?:VERIFICADA|CONSENSO)\s*[:=]\s*(\d{1,3})",
            r"score\s*[:=]\s*(\d{1,3})\s*(?:/\s*100)?",
        )
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return max(0, min(100, int(m.group(1))))
        # Do NOT grab arbitrary first digits (false positives from code/versions).
        return int(claimed_score)

    def run_consensus(
        self,
        user_prompt: str,
        shared_memory: Optional[SharedMemory] = None,
        on_stage_start: Optional[Callable[[str, str, str], None]] = None,
        on_token: Optional[Callable[[str, str], None]] = None,
        on_stage_end: Optional[Callable[[str, Any], None]] = None,
    ) -> Blackboard:
        if shared_memory is None:
            shared_memory = SharedMemory(db_path=self.db_path)

        shared_memory.record_user_message(user_prompt)
        pipeline_type = TaskRouter.route_task(user_prompt)
        blackboard = shared_memory.create_task_blackboard(user_prompt, task_type=pipeline_type.value)

        # .concilio session file
        session_id = getattr(blackboard, "session_id", None) or getattr(blackboard, "task_id", None) or str(int(time.time()))
        doc = self.concilio_store.create(session_id, user_prompt)
        blackboard.shared_notes["concilio_path"] = self.concilio_store.path_for(session_id)
        blackboard.log_event("CONCILIO", "Orchestrator", f"Session file {blackboard.shared_notes['concilio_path']}")

        if getattr(self, "inject_sentinel", False):
            repo_ctx = load_repository_context()
            pack_path = os.path.join(self._project_root, "data", "memory_packs", "sentinel_omega_pack.md")
            if os.path.isfile(pack_path):
                with open(pack_path, "r", encoding="utf-8") as fh:
                    pack = fh.read()
            else:
                try:
                    pack = build_memory_pack()
                except Exception:
                    pack = ""
            shared_memory.research_context = (
                build_data_preamble(("repository_context", "memory_pack"))
                + "\n=== MEMORY PACK (DEV docs, no secrets) ===\n"
                + fence_untrusted(pack, role="memory_pack")
                + "\n=== REPOSITORY CONTEXT ===\n"
                + fence_untrusted(repo_ctx, role="repository_context")
            )
            blackboard.shared_notes["repository_context"] = repo_ctx
            blackboard.shared_notes["repository_metadata"] = project_metadata()
            try:
                blackboard.shared_notes["memory_pack_meta"] = memory_pack_metadata()
            except Exception:
                blackboard.shared_notes["memory_pack_meta"] = {"pack_file": pack_path}
            blackboard.log_event(
                "CONTEXT",
                "Orchestrator",
                f"Memory pack ({len(pack)} chars) + repo context ({len(repo_ctx)} chars) inyectados",
            )
        else:
            # Empty string (not None) so ResearcherAgent does not legacy-autoload repo corpus.
            # Optional thin stub path is recorded for operators; contents are NOT forced here.
            shared_memory.research_context = ""
            stub_rel = (self.config.get("concilio") or {}).get(
                "hard_rules_stub", "data/memory_packs/home_hard_rules_stub.md"
            )
            stub_path = (
                stub_rel
                if os.path.isabs(stub_rel)
                else os.path.normpath(os.path.join(self._project_root, stub_rel))
            )
            blackboard.shared_notes["hard_rules_stub"] = stub_path if os.path.isfile(stub_path) else stub_rel
            blackboard.log_event(
                "CONTEXT",
                "Orchestrator",
                "Standalone: inject_sentinel_architecture=false (no Sentinel corpus; thin stub optional)",
            )

        skip_coding = pipeline_type in (
            PipelineType.RESEARCH_AND_ANALYSIS,
            PipelineType.GENERAL_QA,
        )

        round_count = 0
        consensus_achieved = False
        infinite_loop = self.max_rounds == 0
        last_critique = None
        verified_score = 0

        # FULL Concilio re-entry: lightest -> medium -> heavy -> lightest verify
        while infinite_loop or round_count < self.max_rounds:
            round_count += 1
            doc["round"] = round_count
            blackboard.log_event(
                "CONCILIO",
                "Orchestrator",
                f"Ronda completa {round_count}: light->medium->heavy->verify",
            )

            # ---- LIGHTEST: research ----
            def researcher_stream(tok: str):
                if on_token:
                    on_token("RESEARCH", tok)

            self._run_exclusive(
                self.researcher.model,
                lambda: self.researcher.run_research(shared_memory, stream_callback=researcher_stream),
                "RESEARCH",
                on_stage_start,
                on_stage_end,
                self.researcher.name,
                f"LIGHT: investigando ronda {round_count} (un modelo a la vez)...",
            )
            self._sync_concilio_from_blackboard(doc, blackboard)

            # ---- MEDIUM: code / refine ----
            if not skip_coding:
                def coder_stream(tok: str):
                    if on_token:
                        on_token("CODING" if round_count == 1 or not blackboard.code_proposal else "REFINING", tok)

                if round_count == 1 or not blackboard.code_proposal:
                    self._run_exclusive(
                        self.coder.model,
                        lambda: self.coder.build_code(shared_memory, stream_callback=coder_stream),
                        "CODING",
                        on_stage_start,
                        on_stage_end,
                        self.coder.name,
                        f"MEDIUM: escribiendo código (ronda {round_count})...",
                    )
                else:
                    self._run_exclusive(
                        self.coder.model,
                        lambda: self.coder.refine_code(shared_memory, stream_callback=coder_stream),
                        "REFINING",
                        on_stage_start,
                        on_stage_end,
                        self.coder.name,
                        f"MEDIUM: refine con reentrada FULL (ronda {round_count})...",
                    )
                self._sync_concilio_from_blackboard(doc, blackboard)
            else:
                blackboard.log_event(
                    "CODING",
                    "Orchestrator",
                    f"Pipeline {pipeline_type.value}: se omite fase de código",
                )

            # ---- HEAVY: review ----
            def optimizer_stream(tok: str):
                if on_token:
                    on_token("REVIEW", tok)

            critique = self._run_exclusive(
                self.optimizer.model,
                lambda: self.optimizer.evaluate_solution(
                    shared_memory,
                    threshold=self.threshold,
                    stream_callback=optimizer_stream,
                ),
                "REVIEW",
                on_stage_start,
                on_stage_end,
                self.optimizer.name,
                f"HEAVY: auditoría ronda {round_count} [umbral={self.threshold}]...",
            )
            last_critique = critique
            self.concilio_store.add_score(
                doc,
                score=critique.score,
                passed=bool(critique.passed),
                model=self.optimizer.model,
                role="optimizer",
                round_num=round_count,
            )
            self._sync_concilio_from_blackboard(doc, blackboard)

            # ---- LIGHTEST: verify ----
            verified_score = critique.score
            if self.verify_with_light:
                def verify_stream(tok: str):
                    if on_token:
                        on_token("VERIFY", tok)

                verified_score = self._run_exclusive(
                    self.researcher.model,
                    lambda: self._light_verify_score(doc, critique.score, stream_callback=verify_stream),
                    "VERIFY",
                    on_stage_start,
                    on_stage_end,
                    self.researcher.name,
                    f"LIGHT verify: confirmando score={critique.score} desde .concilio...",
                )
                self.concilio_store.append_timeline(
                    doc, "verify", "light_confirm", f"claimed={critique.score} verified={verified_score}"
                )
                self.concilio_store.save(doc)

            final_round_score = min(int(critique.score), int(verified_score))
            if abs(int(verified_score) - int(critique.score)) <= 2 and critique.score >= self.threshold:
                final_round_score = int(critique.score)

            blackboard.consensus_score = final_round_score
            passed = final_round_score >= self.threshold
            if passed:
                consensus_achieved = True
                blackboard.consensus_reached = True
                try:
                    blackboard.status = TaskStatus.CONSENSUS_REACHED
                except Exception:
                    pass
                if on_stage_start:
                    on_stage_start(
                        "REVIEW",
                        self.optimizer.name,
                        f"CONSENSO ALCANZADO ronda {round_count} (score={final_round_score}/100 >= {self.threshold})",
                    )
                break

            if skip_coding:
                if on_stage_start:
                    on_stage_start(
                        "REVIEW",
                        self.optimizer.name,
                        f"Pipeline sin código: score={final_round_score}/100 (sin reentrada)",
                    )
                break

            if not getattr(self, "auto_refine", True):
                break

            if not infinite_loop and round_count >= self.max_rounds:
                if on_stage_start:
                    on_stage_start(
                        "REVIEW",
                        self.optimizer.name,
                        f"Rondas máximas ({self.max_rounds}) sin consenso (último score={final_round_score}/100)",
                    )
                break

            if on_stage_start:
                on_stage_start(
                    "REFINING",
                    "Concilio",
                    f"Score {final_round_score} < {self.threshold}: reentrada FULL light->medium->heavy->verify",
                )

        # ---- synthesis (heavy again, exclusive) ----
        def synth_stream(tok: str):
            if on_token:
                on_token("SYNTHESIS", tok)

        final_answer = self._run_exclusive(
            self.optimizer.model,
            lambda: self.optimizer.synthesize_consensus(shared_memory, stream_callback=synth_stream),
            "SYNTHESIS",
            on_stage_start,
            on_stage_end,
            self.optimizer.name,
            "HEAVY: síntesis final consensuada...",
        )
        blackboard.final_synthesis = final_answer
        self.concilio_store.append_timeline(doc, "synthesis", "final", f"{len(final_answer or '')} chars")
        self.concilio_store.save(doc)

        if consensus_achieved:
            try:
                blackboard.status = TaskStatus.COMPLETED
            except Exception:
                pass

        shared_memory.persist_current_state()
        return blackboard


    def fast_ask(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
        preload_sentinel: bool = False,
    ) -> str:
        """Fast path outside Concilio. preload_sentinel injects thin Sentinel pack (Telegram)."""
        fenced = fence_untrusted(prompt, role="fast_ask")
        sys_prompt = (
            build_data_preamble(("fast_ask",))
            + "\nResponde breve y en español. No inventes datos de sensores ni secretos.\n"
        )
        if preload_sentinel or bool((self.config.get("concilio") or {}).get("telegram_preload_sentinel_pack", True)):
            pack_path = os.path.join(self._project_root, "data", "memory_packs", "sentinel_omega_pack.md")
            if os.path.isfile(pack_path):
                try:
                    with open(pack_path, "r", encoding="utf-8") as fh:
                        pack = fh.read(8000)
                    sys_prompt += (
                        "\n"
                        + build_data_preamble(("memory_pack",))
                        + fence_untrusted(pack, role="memory_pack")
                        + "\n"
                    )
                except Exception:
                    pass
            sys_prompt += (
                "\nEres el asistente operativo de Sentinel Omega / Concilio.\n"
                "Eventos = precursores naturales (sismos, Schumann, muro, Silent Trigger, enjambres).\n"
                "NUNCA inventes TV, noticieros, deportes ni economía genérica.\n"
                "Sin lectura DB: di que faltan datos; no inventes.\n"
            )
        if self.sequential:
            self.lifecycle.ensure_exclusive(self.researcher.model, settle_seconds=self.settle_seconds)
        try:
            return self.researcher.generate(
                prompt=fenced, system_override=sys_prompt, stream_callback=stream_callback
            )
        finally:
            if self.sequential:
                self.lifecycle.unload_after_role(self.researcher.model)

    def audit_project(self, focus: str = "", *, with_sentinel: bool = True) -> Blackboard:
        """Full Concilio audit. By default injects Sentinel pack/pipeline context.

        Telegram /audit and CLI --audit need the pipeline preloaded; everyday
        /task stays thin via inject_sentinel_architecture=false.
        """
        prompt = (
            "AUDITORÍA DEL PROYECTO SENTINEL OMEGA / CONCILIO. "
            "Revisa el contexto inyectado (cercado como DATA) y produce hallazgos "
            "priorizados con severidad, archivo y acción sugerida. "
            "Enfócate en precursores, muro, ingest, bots/Padre/Juez, Telegram y DB. "
            "No inventes archivos ni métricas que no estén en el contexto."
        )
        if focus:
            prompt += f"\nFoco adicional de la auditoría: {focus}"
        shared = SharedMemory(db_path=self.db_path)
        prev = bool(getattr(self, "inject_sentinel", False))
        if with_sentinel:
            self.inject_sentinel = True
        try:
            return self.run_consensus(user_prompt=prompt, shared_memory=shared)
        finally:
            self.inject_sentinel = prev

    def health(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "ollama_host": self.ollama_host,
            "timeout": self.timeout,
            "consensus_threshold": self.threshold,
            "max_refinement_rounds": self.max_rounds,
            "db_path": self.db_path,
            "concilio": {
                "sequential": self.sequential,
                "verify_with_light": self.verify_with_light,
                "sessions_dir": self.sessions_dir,
                "sessions_dir_exists": os.path.isdir(self.sessions_dir),
                "inject_sentinel_architecture": getattr(self, "inject_sentinel", False),
                "order": ["research", "code", "review", "verify", "full_reentry_if_needed", "synthesis"],
                "loaded_now": (self.lifecycle.list_running() if hasattr(self, "lifecycle") else []),
                "worker_model": self.researcher.model,
                "arbiter_model": self.optimizer.model,
                "fast_gente_path": "outside_concilio (fast_ask / dashboard POST /api/ask)",
            },
            "agents": {
                "researcher": {
                    "name": self.researcher.name,
                    "model": self.researcher.model,
                    "available": self.researcher.check_availability(),
                },
                "coder": {
                    "name": self.coder.name,
                    "model": self.coder.model,
                    "available": self.coder.check_availability(),
                },
                "optimizer": {
                    "name": self.optimizer.name,
                    "model": self.optimizer.model,
                    "available": self.optimizer.check_availability(),
                },
            },
            "context_injector": project_metadata(),
        }
        return info
