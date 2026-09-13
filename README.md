# Local

Monorepo índice de sistemas locales en WSL Kali (**deamon** / X-Deamon).

`main` solo contiene este índice + LICENSE. El código de cada sistema vive en su propia rama huérfana (raíz limpia por sistema).

## Ramas

| Rama | Sistema | Origen local |
|------|---------|--------------|
| `local/home-bridge` | Home bridge / DeamonX móvil | `/home/deamon` (README, AGENTS, CHANGELOG, `bridge/`, docs DeamonX) |
| `local/concilio` | Consensus / Concilio expert agent | `/home/deamon/consensus-expert-agent` |
| `local/padron` | Padrón de afiliados (Streamlit) | `/home/deamon/padron_afiliados_app` |
| `local/sentinel-omega` | Sentinel Ω (workspaces) | `/home/deamon/workspaces` (sin ONNX/DB/.env/venv) |

## Uso rápido

```bash
git clone -b local/home-bridge https://github.com/Inzainos/Local.git Local-home-bridge
git clone -b local/concilio https://github.com/Inzainos/Local.git Local-concilio
git clone -b local/padron https://github.com/Inzainos/Local.git Local-padron
git clone -b local/sentinel-omega https://github.com/Inzainos/Local.git Local-sentinel-omega
```

Cada rama incluye su propio `README.md` y `AGENTS.md` (sin secretos).
