"""Cliente minimo de AbuseIPDB."""
import requests

BASE = "https://api.abuseipdb.com/api/v2/check"


def check_ip(api_key: str, ip: str, timeout: int = 15) -> dict | None:
    if not api_key:
        return None
    try:
        r = requests.get(
            BASE,
            headers={"Key": api_key, "Accept": "application/json"},
            params={"ipAddress": ip, "maxAgeInDays": 90},
            timeout=timeout,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    data = r.json().get("data", {})
    return {
        "abuse_score": data.get("abuseConfidenceScore", 0),
        "total_reports": data.get("totalReports", 0),
        "country": data.get("countryCode"),
    }
