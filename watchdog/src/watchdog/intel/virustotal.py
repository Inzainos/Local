"""Cliente minimo de VirusTotal API v3. Sin key configurada, todo devuelve
None (no bloquea el pipeline, solo se pierde ese enriquecimiento)."""
import requests

BASE = "https://www.virustotal.com/api/v3"


def _headers(api_key: str) -> dict:
    return {"x-apikey": api_key}


def lookup_hash(api_key: str, sha256: str, timeout: int = 15) -> dict | None:
    if not api_key:
        return None
    try:
        r = requests.get(f"{BASE}/files/{sha256}", headers=_headers(api_key), timeout=timeout)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    stats = r.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
    positives = stats.get("malicious", 0) + stats.get("suspicious", 0)
    total = sum(stats.values()) if stats else 0
    return {"positives": positives, "total": total, "raw_stats": stats}


def lookup_ip(api_key: str, ip: str, timeout: int = 15) -> dict | None:
    if not api_key:
        return None
    try:
        r = requests.get(f"{BASE}/ip_addresses/{ip}", headers=_headers(api_key), timeout=timeout)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    stats = r.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
    positives = stats.get("malicious", 0) + stats.get("suspicious", 0)
    total = sum(stats.values()) if stats else 0
    return {"positives": positives, "total": total, "raw_stats": stats}
