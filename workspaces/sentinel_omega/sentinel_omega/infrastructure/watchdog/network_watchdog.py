
"""
Sentinel Omega — Network & Agent Watchdog
Levanta el sistema si ve desconexiones o fallos de red/servicio.

- Chequea conectividad cada 60s (ping 8.8.8.8 + 1.1.1.1 + http google)
- Chequea health del agente (ollama + DB) via agent_bridge si existe
- Si falla N veces seguidas => intenta systemctl restart sentinel-omega + dashboard + watchdog alert
- Notifica via AlertService (Telegram/Correo/Log) cuando vuelve
- Corre como servicio systemd sentinel-omega-watchdog.service (Restart=always)

No requiere credenciales para chequear; si hay Telegram, notifica.
"""
from __future__ import annotations
import time, subprocess, logging, socket, os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s [WATCHDOG] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = int(os.environ.get('WATCHDOG_INTERVAL_S', '60'))
FAIL_THRESHOLD = int(os.environ.get('WATCHDOG_FAIL_THRESHOLD', '3'))
PING_HOSTS = ['8.8.8.8','1.1.1.1']
HTTP_HOSTS = ['https://www.google.com','https://api.nasa.gov']

def has_network() -> bool:
    # 1) DNS + TCP check (sin depender de ping binario)
    for host in PING_HOSTS:
        try:
            socket.create_connection((host, 53), timeout=5)
            return True
        except Exception:
            continue
    # 2) fallback http
    try:
        import httpx
        for url in HTTP_HOSTS:
            try:
                with httpx.Client(timeout=5.0, follow_redirects=True) as c:
                    r = c.get(url)
                    if r.status_code < 500:
                        return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def service_active(name: str) -> bool:
    try:
        r = subprocess.run(['systemctl','is-active',name], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() == 'active'
    except Exception:
        return False

def try_restart(services):
    for svc in services:
        try:
            logger.warning(f'Restart {svc}')
            subprocess.run(['sudo','systemctl','restart',svc], timeout=30)
        except Exception as e:
            logger.error(f'restart {svc} fail: {e}')
            # fallback sin sudo (si corre como root)
            try:
                subprocess.run(['systemctl','restart',svc], timeout=30)
            except Exception as e2:
                logger.error(f'fallback restart fail: {e2}')

def agent_ok() -> bool:
    try:
        from sentinel_omega.infrastructure.messaging.agent_bridge import agent_health
        h = agent_health()
        # ok si ollama responde o al menos DB existe
        return bool(h.get('db_exists') or h.get('ollama_ok'))
    except Exception:
        return True  # no bloquear por agente si no esta

def notify(subject: str, html: str):
    try:
        from sentinel_omega.infrastructure.messaging.alert_service import AlertService, AlertTemplates, Severity, FormattedMessage
        svc = AlertService()
        msg = FormattedMessage(html=html, markdown=html, plain=html, subject=subject, severity=Severity.AMARILLO, alert_type='WATCHDOG')
        svc.dispatch(msg, channels=['telegram','log'])
        logger.info(f'notify {subject}')
    except Exception as e:
        logger.warning(f'notify fail: {e}')
        logger.info(html)

def main():
    logger.info(f'Watchdog start interval={CHECK_INTERVAL_S}s threshold={FAIL_THRESHOLD}')
    fails = 0
    was_down = False
    while True:
        net = has_network()
        ag = agent_ok()
        if net and ag:
            if was_down:
                notify('[SENTINEL] Red restaurada', f'Red OK tras {fails} fallos. {datetime.now(timezone.utc).isoformat()}')
                # asegurar servicios arriba
                for svc in ['sentinel-omega','sentinel-omega-dashboard','sentinel-omega-scheduler']:
                    if not service_active(svc):
                        try_restart([svc])
            fails = 0
            was_down = False
            logger.info('OK net+agent')
        else:
            fails += 1
            logger.warning(f'FAIL net={net} agent={ag} fails={fails}/{FAIL_THRESHOLD}')
            if fails >= FAIL_THRESHOLD:
                was_down = True
                # si no hay red, no intentar restart inmediato (esperar red), pero si hay red y agente mal, restart
                if net and not ag:
                    try_restart(['sentinel-omega'])  # scheduler disabled: duplicate launcher fought omega
                    notify('[SENTINEL] Watchdog reinicio agente', f'Agente no OK, reiniciado. fails={fails}')
                elif not net:
                    logger.warning('Sin red, esperando restauracion...')
                    # no restart hasta que vuelva red, pero avisar una vez
                    if fails == FAIL_THRESHOLD:
                        logger.warning('Red caida, watchdog en espera')
                # si la red sigue caida, no resetear a 0 (evitar esperar 3 ciclos mas); dejar en threshold-1 para re-evaluar rapido
                fails = 0 if net else FAIL_THRESHOLD - 1
        time.sleep(CHECK_INTERVAL_S)

if __name__ == '__main__':
    main()
