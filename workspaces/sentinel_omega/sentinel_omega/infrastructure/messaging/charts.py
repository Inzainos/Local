from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Dict, Optional
import os
logger = logging.getLogger(__name__)

def _ensure_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt

CHARTS_DIR = Path(os.environ.get("SENTINEL_CHARTS_DIR", "/tmp/sentinel_charts"))
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

def fantasma_timeline(valores: List[float], labels=None, titulo="Fantasma - ultimos ciclos"):
    try:
        plt = _ensure_mpl()
        fig, ax = plt.subplots(figsize=(8, 3), dpi=150)
        xs = list(range(len(valores)))
        ax.plot(xs, valores, marker="o", linewidth=2, markersize=4, color="#e74c3c")
        ax.axhline(15, color="#f39c12", linestyle="--", alpha=0.6, label="Umbral AMARILLO")
        ax.axhline(30, color="#c0392b", linestyle="--", alpha=0.6, label="Umbral ROJO")
        ax.set_title(titulo, fontsize=10)
        ax.set_ylabel("Fantasma")
        ax.set_xlabel("Ciclo")
        if labels:
            ax.set_xticks(xs)
            ax.set_xticklabels(labels, rotation=20, fontsize=7)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="best")
        fig.tight_layout()
        out = CHARTS_DIR / "fantasma.png"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        return out
    except Exception as e:
        logger.warning(f"chart fantasma fail: {e}")
        return None

def cimatica_bars(patrones: List[Dict], titulo="Cimatica - patrones consistentes"):
    try:
        plt = _ensure_mpl()
        if not patrones:
            return None
        labels = [str(p.get("patron_id", p.get("clave","")[:8])) for p in patrones]
        freqs = [int(p.get("frecuencia",1)) for p in patrones]
        colors = ["#2ecc71" if p.get("event_class") else "#95a5a6" for p in patrones]
        fig, ax = plt.subplots(figsize=(8, 3), dpi=150)
        bars = ax.bar(labels, freqs, color=colors)
        for b, f in zip(bars, freqs):
            ax.text(b.get_x() + b.get_width()/2, b.get_height()+0.05, str(f), ha="center", fontsize=8)
        ax.set_title(titulo, fontsize=10)
        ax.set_ylabel("Frecuencia")
        ax.set_xlabel("Patron ID")
        fig.tight_layout()
        out = CHARTS_DIR / "cimatica.png"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        return out
    except Exception as e:
        logger.warning(f"cimatica_bars fail: {e}")
        return None

def precursores_tabla_png(filas: List[Dict]):
    try:
        plt = _ensure_mpl()
        if not filas:
            return None
        fig, ax = plt.subplots(figsize=(8, max(2, 0.6*len(filas)+1)), dpi=150)
        ax.axis("off")
        cols = ["Tipo","Conf","Zona","Lag"]
        table_data = []
        for r in filas:
            conf = r.get("conf", r.get("value", ""))
            if isinstance(conf, float):
                conf = f"{conf:.0%}"
            table_data.append([r.get("tipo",""), str(conf), r.get("zona",""), r.get("lag","")])
        table = ax.table(cellText=table_data, colLabels=cols, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        table.scale(1, 1.4)
        ax.set_title("Precursores detectados", fontsize=10, pad=12)
        out = CHARTS_DIR / "precursores.png"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        return out
    except Exception as e:
        logger.warning(f"precursores_tabla fail: {e}")
        return None
