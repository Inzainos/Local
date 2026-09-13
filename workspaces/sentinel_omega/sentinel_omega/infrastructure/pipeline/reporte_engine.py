"""
Sentinel Omega — ReportEngine unificado (refactor)
Capa DRY sobre reporte_sentinel.py — mantiene compatibilidad total.

Uso nuevo (recomendado):
    from sentinel_omega.infrastructure.pipeline.reporte_engine import ReportEngine
    eng = ReportEngine(db_path)
    result = eng.render("general")          # ReportResult con .text, .dict, .path
    eng.render_to_file("padre", filtros={})

Uso legacy (sigue funcionando):
    from sentinel_omega.infrastructure.pipeline.reporte_sentinel import reporte_general
    reporte_general(db_path)  # imprime como antes

Versionado: guarda en estado/historial/AAAA/MM/ y actualiza estado/REPORTE.md
"""
from __future__ import annotations
import sqlite3, json, hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal
import logging
logger = logging.getLogger(__name__)

ReportTipo = Literal["general", "padre", "omega"]

@dataclass
class ReportFiltros:
    desde: Optional[str] = None
    hasta: Optional[str] = None
    bot: Optional[str] = None
    limit: int = 200

@dataclass
class ReportResult:
    tipo: str
    text: str
    data: Dict[str, Any] = field(default_factory=dict)
    filtros: ReportFiltros = field(default_factory=ReportFiltros)
    hash: str = ""
    created_at: str = ""
    path_txt: Optional[Path] = None

def _hash_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:12]

class ReportEngine:
    def __init__(self, db_path: str | Path, workspace_root: Optional[Path] = None):
        self.db_path = str(db_path)
        # workspace_root para resolver estado/historial
        if workspace_root is None:
            # inferir desde db_path -> .../sentinel_omega/data/ -> workspace_root
            p = Path(db_path).resolve()
            # subir hasta workspaces
            for parent in p.parents:
                if (parent / "sentinel_omega").exists():
                    workspace_root = parent
                    break
            if workspace_root is None:
                workspace_root = Path(db_path).parent.parent
        self.workspace_root = Path(workspace_root)
        self.estado_dir = self.workspace_root / "sentinel_omega" / "estado" if (self.workspace_root / "sentinel_omega").exists() else self.workspace_root / "estado"
        # fallback: si estamos en /home/deamon/workspaces
        if not self.estado_dir.exists():
            # intentar /home/deamon/workspaces/estado
            alt = Path("/home/deamon/workspaces/estado")
            if alt.exists():
                self.estado_dir = alt

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def render(self, tipo: ReportTipo, filtros: Optional[ReportFiltros] = None) -> ReportResult:
        filtros = filtros or ReportFiltros()
        # delega a reporte_sentinel existente para no duplicar 871 líneas
        # captura el texto impreso y también datos estructurados
        import io, contextlib
        from sentinel_omega.infrastructure.pipeline import reporte_sentinel as rs
        buf = io.StringIO()
        data: Dict[str, Any] = {"tipo": tipo, "filtros": filtros.__dict__}
        with contextlib.redirect_stdout(buf):
            if tipo == "general":
                # reporte_general imprime y retorna dict
                ret = rs.reporte_general(self.db_path)
                if isinstance(ret, dict):
                    data.update(ret)
            elif tipo == "padre":
                ret = rs.reporte_padre(self.db_path)
                if isinstance(ret, dict):
                    data.update(ret)
            elif tipo == "omega":
                ret = rs.reporte_omega(self.db_path)
                if isinstance(ret, dict):
                    data.update(ret)
            else:
                raise ValueError(f"tipo desconocido: {tipo}")
        text = buf.getvalue()
        h = _hash_text(text)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return ReportResult(tipo=tipo, text=text, data=data, filtros=filtros, hash=h, created_at=created)

    def render_to_file(self, tipo: ReportTipo, filtros: Optional[ReportFiltros] = None, also_update_latest: bool = True) -> ReportResult:
        res = self.render(tipo, filtros)
        # guardar versionado en estado/historial/AAAA/MM/
        try:
            now = datetime.now(timezone.utc)
            # hora local MX (UTC-6) para nombre archivo
            from datetime import timedelta
            mx = now - timedelta(hours=6)
            hist_dir = self.estado_dir / "historial" / mx.strftime("%Y") / mx.strftime("%m")
            hist_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{mx.strftime('%Y-%m-%d_%H-%M')}_{tipo.upper()}_MX.md"
            # si ya existe, agregar sufijo hash
            path = hist_dir / fname
            if path.exists():
                path = hist_dir / f"{mx.strftime('%Y-%m-%d_%H-%M')}_{tipo.upper()}_{res.hash}_MX.md"
            path.write_text(res.text, encoding="utf-8")
            res.path_txt = path
            logger.info(f"Reporte {tipo} versionado → {path}")
            # actualizar REPORTE.md (último) y copia por tipo
            if also_update_latest:
                latest = self.estado_dir / "REPORTE.md"
                latest.write_text(res.text, encoding="utf-8")
                # además guardar REPORTE_<TIPO>.md para trazabilidad
                (self.estado_dir / f"REPORTE_{tipo.upper()}.md").write_text(res.text, encoding="utf-8")
        except Exception as e:
            logger.warning(f"No se pudo versionar reporte {tipo}: {e}")
        return res

    def list_historial(self, tipo: Optional[str] = None, limit: int = 20) -> List[Path]:
        if not self.estado_dir.exists():
            return []
        hist = self.estado_dir / "historial"
        if not hist.exists():
            return []
        files = sorted(hist.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if tipo:
            files = [p for p in files if tipo.upper() in p.name.upper()]
        return files[:limit]
