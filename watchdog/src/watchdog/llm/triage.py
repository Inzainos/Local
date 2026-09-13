"""Triage asistido por LLM (via OpenRouter): NO 'entrena' nada ni 'aprende'
ciberseguridad, solo lee el hallazgo + intel ya recolectada y devuelve una
explicacion en lenguaje natural para el humano que va a revisar la
cuarentena. Es opcional (llm.enabled en config.yaml) y nunca bloquea el
pipeline si falla."""
import requests

PROMPT_TEMPLATE = """Sos un analista SOC junior. Te paso un hallazgo de un \
watchdog de seguridad local en Kali Linux (WSL2) y el enriquecimiento de \
threat intel ya obtenido. Da un veredicto breve (2-4 lineas, en espanol) \
sobre que tan preocupante es, y una sugerencia de proximo paso.

Hallazgo: {finding}
Threat intel: {intel}
Accion ya tomada por la politica automatica: {action}
"""


def triage(cfg, finding: dict, intel: dict, action: str) -> str | None:
    if not cfg.get("llm", "enabled", default=False):
        return None
    api_key = cfg.api_keys["openrouter"]
    if not api_key:
        return None

    prompt = PROMPT_TEMPLATE.format(finding=finding, intel=intel, action=action)
    try:
        r = requests.post(
            f"{cfg.get('llm', 'api_base')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": cfg.get("llm", "model"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
            },
            timeout=30,
        )
        if r.status_code != 200:
            return None
        return r.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError):
        return None
