"""Cliente minimo de AlienVault OTX (Open Threat Exchange)."""
import requests

BASE = "https://otx.alienvault.com/api/v1"


def _headers(api_key: str) -> dict:
    return {"X-OTX-API-KEY": api_key}


def lookup_hash(api_key: str, sha256: str, timeout: int = 15) -> dict | None:
    if not api_key:
        return None
    try:
        r = requests.get(
            f"{BASE}/indicators/file/{sha256}/general",
            headers=_headers(api_key), timeout=timeout,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    pulse_count = data.get("pulse_info", {}).get("count", 0)
    return {"hit": pulse_count > 0, "pulse_count": pulse_count}


def lookup_ip(api_key: str, ip: str, timeout: int = 15) -> dict | None:
    if not api_key:
        return None
    try:
        r = requests.get(
            f"{BASE}/indicators/IPv4/{ip}/general",
            headers=_headers(api_key), timeout=timeout,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    pulse_count = data.get("pulse_info", {}).get("count", 0)
    return {"hit": pulse_count > 0, "pulse_count": pulse_count}
