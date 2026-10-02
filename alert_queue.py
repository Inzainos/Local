"""
Alert Queue System — Centralized Telegram via Consensus Bot.

Sentinel Omega writes alerts to a shared JSON queue file.
Consensus Bot polls the queue and sends via its Telegram connection.

Architecture:
- Sentinel Omega (launcher/orchestrator) → writes to alert_queue.json
- Consensus Bot (telegram_bot.py) → reads queue, sends to Telegram
- Single bot token, single chat_id, centralized messaging
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict, field, fields
from enum import Enum
import threading


# Tope de reintentos por aviso. Un aviso que Telegram rechaza siempre (HTML
# invalido, mensaje demasiado largo, un chat que bloqueo al bot) se reinsertaba
# al frente de la cola cada 5 s para siempre, y la cola es FIFO: tapaba todo lo
# que venia detras hasta que alguien reiniciaba el proceso.
MAX_INTENTOS = 5


class AlertPriority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    HEARTBEAT = "heartbeat"
    SYSTEM = "system"


@dataclass
class Alert:
    id: str
    timestamp: float
    priority: str
    title: str
    message: str
    parse_mode: str = "HTML"
    source: str = "sentinel"
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Campos nuevos con default: los avisos ya escritos en la cola se leen
    # igual (migracion hacia delante, nada que convertir).
    attempts: int = 0
    # Chats que faltan por entregar. None = todos los configurados. Se llena
    # cuando una entrega sale a medias, para no repetirle el aviso a quien ya
    # lo recibio.
    pending_chats: Optional[List[str]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def _a_dict(alert: Alert) -> Dict[str, Any]:
    """asdict() omitiendo los campos nuevos cuando no dicen nada.

    El bot y el Sentinel comparten este archivo pero son procesos distintos y
    cargan el modulo AL ARRANCAR. Mientras un bot viejo siga en memoria, un
    aviso encolado por un Sentinel recien arrancado con claves que ese bot no
    conoce reventaba su `Alert(**data)` --- y revienta DESPUES de haberlo
    sacado de la cola, o sea que el aviso se pierde. Un aviso recien encolado
    se escribe con el esquema de siempre; las claves nuevas solo aparecen en
    los reintentos, que unicamente escribe el codigo nuevo.
    """
    data = asdict(alert)
    if not data.get("attempts"):
        data.pop("attempts", None)
    if data.get("pending_chats") is None:
        data.pop("pending_chats", None)
    return data


class AlertQueue:
    """Thread-safe alert queue using JSON file as backing store.

    Cross-process safety is best-effort: writes use temp+replace.
    Concurrent writers from another process can still race; prefer a
    single producer or external locking if that becomes hot.
    """

    def __init__(self, queue_path: Optional[str] = None):
        if queue_path is None:
            base = Path(__file__).resolve().parent
            queue_path = str(base / "data" / "alert_queue.json")
        self.queue_path = Path(queue_path)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.stats_path = self.queue_path.with_name("alert_queue_stats.json")
        # Lo sacado de la cola y todavia sin confirmar vive aqui, no solo en
        # memoria del proceso que lo envia. Ver pop_batch().
        self.inflight_path = self.queue_path.with_name("alert_queue_inflight.json")
        # Lo que agoto MAX_INTENTOS: se guarda en vez de borrarse.
        self.dead_path = self.queue_path.with_name("alert_queue_dead.json")
        self._lock = threading.RLock()
        self._ensure_queue_exists()
        self._stats = self._load_stats()

    def _ensure_queue_exists(self):
        if not self.queue_path.exists():
            self._atomic_write(self.queue_path, "[]")

    def _default_stats(self) -> Dict[str, Any]:
        return {
            "total_enqueued": 0,
            "total_sent": 0,
            "total_failed": 0,
            "total_dead": 0,
            "last_alert": None,
        }

    def _load_stats(self) -> Dict[str, Any]:
        with self._lock:
            if not self.stats_path.exists():
                return self._default_stats()
            try:
                data = json.loads(self.stats_path.read_text(encoding="utf-8") or "{}")
                stats = self._default_stats()
                stats.update({k: data.get(k, stats[k]) for k in stats})
                return stats
            except Exception:
                return self._default_stats()

    def _save_stats(self):
        with self._lock:
            self._atomic_write(
                self.stats_path,
                json.dumps(self._stats, ensure_ascii=False, indent=2),
            )

    @staticmethod
    def _atomic_write(path: Path, content: str):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)

    def _read_json(self, path: Path) -> List[Dict]:
        with self._lock:
            try:
                content = path.read_text(encoding="utf-8")
                return json.loads(content) if content.strip() else []
            except Exception:
                return []

    def _write_json(self, path: Path, alerts: List[Dict]):
        with self._lock:
            self._atomic_write(path, json.dumps(alerts, ensure_ascii=False, indent=2))

    def _read_all(self) -> List[Dict]:
        return self._read_json(self.queue_path)

    def _write_all(self, alerts: List[Dict]):
        self._write_json(self.queue_path, alerts)

    @staticmethod
    def _hidratar(data: Dict) -> Alert:
        """Dict -> Alert ignorando claves que Alert no conoce.

        Un campo de mas en el archivo tiraba `Alert(**data)` con TypeError, y
        con el la vuelta entera del poller.
        """
        conocidos = {f.name for f in fields(Alert)}
        limpio = {k: v for k, v in data.items() if k in conocidos}
        if limpio.get("metadata") is None:
            limpio["metadata"] = {}
        return Alert(**limpio)

    def _quitar_de_vuelo(self, alert_id: str) -> None:
        with self._lock:
            en_vuelo = self._read_json(self.inflight_path)
            quedan = [a for a in en_vuelo if a.get("id") != alert_id]
            if len(quedan) != len(en_vuelo):
                self._write_json(self.inflight_path, quedan)

    def push(self, alert: Alert) -> str:
        """Add alert to queue. Returns alert ID."""
        with self._lock:
            alerts = self._read_all()
            alerts.append(_a_dict(alert))
            self._write_all(alerts)
            self._stats["total_enqueued"] = int(self._stats.get("total_enqueued", 0)) + 1
            self._stats["last_alert"] = {
                "type": alert.source,
                "priority": alert.priority,
                "timestamp": alert.timestamp,
                "title": alert.title,
                "id": alert.id,
            }
            self._save_stats()
        return alert.id

    def pop_batch(self, max_count: int = 10) -> List[Alert]:
        """Saca hasta max_count avisos (FIFO) y los deja marcados EN VUELO.

        El aviso sale del archivo de la cola antes de que el envio ocurra. Sin
        la marca de en vuelo, entre ese borrado y el envio el aviso no existia
        en ningun archivo: si el proceso moria ahi --- y aqui los reinicios de
        Windows cortan procesos a mitad, paso el 25-sep 13:16 con una tarea del
        concilio --- se perdia sin dejar rastro.

        Quien reciba los avisos debe cerrar cada uno con mark_sent() o
        devolverlo con requeue(). Lo que quede en vuelo lo recupera
        recover_inflight() en el siguiente arranque.
        """
        with self._lock:
            alerts = self._read_all()
            if not alerts:
                return []
            to_send = alerts[:max_count]
            self._write_all(alerts[max_count:])
            en_vuelo = self._read_json(self.inflight_path)
            en_vuelo.extend(to_send)
            self._write_json(self.inflight_path, en_vuelo)
            return [self._hidratar(a) for a in to_send]

    def recover_inflight(self) -> List[Alert]:
        """Devuelve a la cabeza de la cola lo que quedo en vuelo sin confirmar.

        Se llama al arrancar: un aviso en vuelo que siga ahi murio con el
        proceso anterior, porque una entrega confirmada lo habria borrado.
        Asume un solo proceso consumidor (lo que garantiza systemd con estas
        units); con dos a la vez, uno le quitaria al otro lo que esta enviando.
        """
        with self._lock:
            en_vuelo = self._read_json(self.inflight_path)
            if not en_vuelo:
                return []
            self._write_all(en_vuelo + self._read_all())
            self._write_json(self.inflight_path, [])
            return [self._hidratar(a) for a in en_vuelo]

    def requeue(self, alert: Alert, contar_intento: bool = True) -> bool:
        """Devuelve el aviso al frente de la cola. False si ya agoto sus intentos.

        Al agotarlos el aviso pasa a `alert_queue_dead.json` en vez de volver a
        la cola: de otro modo tapa indefinidamente todo lo que viene detras.

        `contar_intento=False` para fallos que no son del aviso (p. ej. no hay
        TELEGRAM_CHAT_ID configurado): si contaran, una configuracion a medias
        descartaria la cola entera en cinco vueltas.
        """
        with self._lock:
            self._quitar_de_vuelo(alert.id)
            if contar_intento:
                alert.attempts = int(alert.attempts or 0) + 1
                if alert.attempts >= MAX_INTENTOS:
                    muertos = self._read_json(self.dead_path)
                    muertos.append(_a_dict(alert))
                    self._write_json(self.dead_path, muertos)
                    self._stats["total_dead"] = int(self._stats.get("total_dead", 0)) + 1
                    self._save_stats()
                    return False
            alerts = self._read_all()
            alerts.insert(0, _a_dict(alert))
            self._write_all(alerts)
            return True

    def mark_sent(self, alert: Optional[Alert] = None) -> None:
        with self._lock:
            self._stats["total_sent"] = int(self._stats.get("total_sent", 0)) + 1
            if alert is not None:
                self._quitar_de_vuelo(alert.id)
                self._stats["last_alert"] = {
                    "type": alert.source,
                    "priority": alert.priority,
                    "timestamp": alert.timestamp,
                    "title": alert.title,
                    "id": alert.id,
                }
            self._save_stats()

    def mark_failed(self, alert: Optional[Alert] = None) -> None:
        with self._lock:
            self._stats["total_failed"] = int(self._stats.get("total_failed", 0)) + 1
            self._save_stats()

    def peek(self, max_count: int = 10) -> List[Alert]:
        """View alerts without removing."""
        return [self._hidratar(a) for a in self._read_all()[:max_count]]

    def clear(self):
        """Vacia la cola y lo que hubiera en vuelo (si no, volveria al arrancar)."""
        with self._lock:
            self._write_all([])
            self._write_json(self.inflight_path, [])

    def size(self) -> int:
        return len(self._read_all())

    def get_stats(self) -> Dict[str, Any]:
        """Stats expected by telegram_bot /queue command."""
        with self._lock:
            self._stats = self._load_stats()
            return {
                "size": len(self._read_all()),
                "en_vuelo": len(self._read_json(self.inflight_path)),
                "descartados": len(self._read_json(self.dead_path)),
                "total_enqueued": int(self._stats.get("total_enqueued", 0)),
                "total_sent": int(self._stats.get("total_sent", 0)),
                "total_failed": int(self._stats.get("total_failed", 0)),
                "total_dead": int(self._stats.get("total_dead", 0)),
                "file_path": str(self.queue_path),
                "last_alert": self._stats.get("last_alert"),
            }


# Global instance for easy import
alert_queue = AlertQueue()


def queue_alert(
    title: str,
    message: str,
    priority: AlertPriority = AlertPriority.MEDIUM,
    parse_mode: str = "HTML",
    metadata: Dict = None,
) -> str:
    """Queue an alert for the Consensus Bot to send."""
    alert = Alert(
        id=f"{int(time.time()*1000)}-{os.urandom(4).hex()}",
        timestamp=time.time(),
        priority=priority.value,
        title=title,
        message=message,
        parse_mode=parse_mode,
        source="sentinel",
        metadata=metadata or {},
    )
    return alert_queue.push(alert)


def queue_critical(title: str, message: str, metadata: Dict = None) -> str:
    return queue_alert(title, message, AlertPriority.CRITICAL, metadata=metadata)


def queue_warning(title: str, message: str, metadata: Dict = None) -> str:
    return queue_alert(title, message, AlertPriority.HIGH, metadata=metadata)


def queue_info(title: str, message: str, metadata: Dict = None) -> str:
    return queue_alert(title, message, AlertPriority.MEDIUM, metadata=metadata)


def queue_heartbeat(message: str, metadata: Dict = None) -> str:
    return queue_alert("Heartbeat", message, AlertPriority.HEARTBEAT, metadata=metadata)


def queue_system(title: str, message: str, metadata: Dict = None) -> str:
    return queue_alert(title, message, AlertPriority.SYSTEM, metadata=metadata)


def format_precursor_alert(
    precursor_type: str,
    display_name: str,
    value: float,
    details: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    lugar: Optional[str] = None,
    lag_horas: Optional[float] = None,
) -> str:
    from datetime import datetime, timedelta, timezone
    ahora = datetime.now(timezone.utc)
    location = ""
    if lugar:
        location = f"\n<b>Zona:</b> {lugar}"
    if lat is not None and lon is not None:
        location += f"\n<b>Coords:</b> {lat:.2f}, {lon:.2f}"

    if lag_horas and lag_horas > 0:
        h = int(lag_horas)
        ventanas = (
            f"\n<b>Ventana tipica firma:</b> ~{h}h "
            f"-> {(ahora + timedelta(hours=h)).strftime('%d/%m %H:%M')} UTC\n"
        )
    else:
        ventanas = (
            f"\n<b>Ventanas:</b>\n"
            f"  72h -> {(ahora + timedelta(hours=72)).strftime('%d/%m %H:%M')} UTC\n"
            f"  48h -> {(ahora + timedelta(hours=48)).strftime('%d/%m %H:%M')} UTC\n"
            f"  24h -> {(ahora + timedelta(hours=24)).strftime('%d/%m %H:%M')} UTC\n"
        )

    return (
        f"<b>SENTINEL OMEGA — PRECURSOR</b>\n\n"
        f"<b>Tipo:</b> {display_name}\n"
        f"<b>Conf:</b> <code>{value:.0%}</code>"
        f"{location}{ventanas}\n"
        f"{details}\n\n"
        f"<i>{ahora.strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
    )


def format_centinela_threat(
    risk: float,
    bz: float,
    wind: float,
    schumann: Optional[float] = None,
) -> Optional[tuple]:
    r = float(risk)
    if r > 1.5:
        r = r / 10.0
    bz = float(bz)
    wind = float(wind)

    TH_RISK_CRIT = 0.75
    TH_RISK_WARN = 0.60
    TH_BZ_CRACK = -5.0
    TH_WIND_STORM = 600

    if r >= TH_RISK_CRIT:
        return (
            "CRITICO",
            f"ALERTA CRITICA\n\n"
            f"Fantasma: <b>{r:.2f}</b>\n"
            f"Bz: {bz:.1f} nT\n"
            f"Viento: {wind:.0f} km/s"
            + (f"\nSchumann: {schumann:.2f} Hz" if schumann else ""),
        )
    if bz <= TH_BZ_CRACK:
        return (
            "GRIETA",
            f"FALLO DE ESCUDO (GRIETA)\n\n"
            f"Bz colapsado: <b>{bz:.1f} nT</b>\n"
            f"Posible entrada de energia solar.",
        )
    if wind >= TH_WIND_STORM:
        return (
            "TORMENTA",
            f"TORMENTA SOLAR\n\n"
            f"Viento: <b>{wind:.0f} km/s</b>\n"
            f"Presion sobre magnetosfera.",
        )
    if r >= TH_RISK_WARN:
        return (
            "ADVERTENCIA",
            f"ACTIVIDAD ELEVADA\n\n"
            f"Fantasma: {r:.2f}\n"
            f"Bz: {bz:.1f} | Viento: {wind:.0f}",
        )
    return None


if __name__ == "__main__":
    q = AlertQueue()
    q.clear()
    queue_critical("Test", "Alerta critica de prueba")
    queue_warning("Test", "Advertencia de prueba")
    queue_heartbeat("Sistema funcionando")
    print(f"Queue size: {q.size()}")
    print("Stats:", q.get_stats())
    for a in q.peek():
        print(f"  [{a.priority}] {a.title}: {a.message[:50]}...")
