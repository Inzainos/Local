# DeamonX ↔ X-Deamon — Puente SSH (2026-09-13)

Resumen de sesión / ops. Sin métricas inventadas. Complementa `bridge/TERMUX.md` y la entrada de CHANGELOG del mismo día.

Doc del nodo móvil (Agente-A): [DEAMONX_MOBILE.md](DEAMONX_MOBILE.md).

## Objetivo

Conectar **DeamonX-Mobile** (Honor X7d / Termux) a **X-Deamon** (Kali WSL) para usar Ollama **solo** por túnel SSH local-forward. El teléfono no habla HTTP abierto a la LAN.

## Topología

| Nodo | Rol |
|------|-----|
| Windows host | Corre `ollama.exe`; firewall permite SSH/WSL puerto 22; Wi-Fi Private; tarea `WSL-Kali-Autostart` al login |
| Kali WSL (`deamon`) | Host SSH (`sshd` pubkey-only); `ollama.service` **disabled**; scripts en `~/bridge/` |
| Termux (Honor X7d) | Cliente SSH; `-L 11434:127.0.0.1:11434`; `REMOTE_OLLAMA_URL=http://127.0.0.1:11434` |

## Reglas duras

1. **Nunca** `OLLAMA_HOST=0.0.0.0` (ni bind LAN) sin OK explícito del operador.
2. Ollama queda en `127.0.0.1:11434` (lado Windows / reachable desde Kali vía localhost WSL).
3. Acceso móvil solo vía `ssh -L 11434:127.0.0.1:11434` (cifrado).
4. En Termux: `REMOTE_OLLAMA_URL=http://127.0.0.1:11434`, `REMOTE_MODEL=concilio-lightest:latest` (modelos light en móvil).
5. `sshd`: pubkey-only (`PasswordAuthentication no`, `AllowUsers deamon`, etc. — ver `bridge/sshd_deamonx.conf`).

## Artefactos en host

- `/home/deamon/bridge/TERMUX.md` — guía Termux
- `/home/deamon/bridge/check_bridge.sh` — chequeo sshd / :22 / Ollama tags / keys
- `/home/deamon/bridge/install_sshd.sh`, `sshd_bootstrap.conf`, `sshd_deamonx.conf`
- `jq` instalado (para listar modelos en el check)
- Docs Sentinel ya existentes: `workspaces/sentinel_omega/docs/SESSION_2026-09-13.md`, `SYSTEM_HEALTH_2026-09-13.md`

## Roles (sesión / ecosistema)

| Código | Rol |
|--------|-----|
| **G** | Coordinación / sudo |
| **C** | Host / sshd / puente |
| **T** | Concilio / Telegram |
| **A** | DeamonX mobile |

## Concilio (contexto mismo día)

- `/task` → light + pack
- `/concilio` → heavy
- Mini App vía `cloudflared` (túnel; no abrir Ollama a LAN)

## Sentinel (contexto mismo día)

- Scheduler disabled; 1 launcher (omega)
- Runtime Ollama = Windows `ollama.exe`; unit Kali disabled

## Verificación sugerida (sin afirmar resultados aquí)

```bash
~/bridge/check_bridge.sh
# En Termux, con túnel arriba:
curl -s http://127.0.0.1:11434/api/tags | head
```

Ver también: `/home/deamon/CHANGELOG.md` (entrada 2026-09-13 DeamonX), `/home/deamon/AGENTS.md` (sección DeamonX-Mobile).
