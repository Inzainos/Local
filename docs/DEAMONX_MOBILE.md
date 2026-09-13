# DeamonX Mobile (Honor X7d / Termux)

Nodo móvil del Capitán. Dueño operativo: **Agente-A** (config/scripts/tests en Termux).
Puente/seguridad host: **Agente-C**. Sudo/coord: **Agente-G**. Concilio/Telegram: **Agente-T** (no duplicar alertas).

**Estado:** GO confirmado **2026-09-13** (`curl http://127.0.0.1:11434/api/tags` OK vía túnel SSH desde Termux `192.168.1.137`).

Ops detallado del túnel: [`~/bridge/TERMUX.md`](../bridge/TERMUX.md).
Resumen puente/sesión del día: [DEAMONX_BRIDGE_2026-09-13.md](DEAMONX_BRIDGE_2026-09-13.md).

---

## Arquitectura (hechos)

```
Honor X7d (Termux / DeamonX)
  ├── Gateway móvil :8090
  ├── Llama local Qwen (nodo ligero)
  └── REMOTE Ollama → http://127.0.0.1:11434  (local-forward SSH)
         │
         │  ssh -N -L 11434:127.0.0.1:11434 deamon@192.168.1.144
         ▼
X-Deamon / Kali (WSL)
  └── Ollama solo 127.0.0.1:11434  (NO bind LAN / 0.0.0.0 sin OK explícito)
```

| Pieza | Valor |
|-------|--------|
| `REMOTE_OLLAMA_URL` | `http://127.0.0.1:11434` |
| `REMOTE_MODEL` | `concilio-lightest:latest` |
| Host SSH | `deamon@192.168.1.144:22` |
| Pubkey Termux | fingerprint `SHA256:Euih1LjCoXOZEBpu+byhf8lWgPY46haK8bj2Bs9cso4` (`u0_a254@localhost`) |
| Gateway | `:8090` en el móvil |

**No usar** `http://192.168.1.144:11434` como REMOTE (Ollama no se abre a la LAN).

---

## Modelos (vía túnel, 2026-09-13)

Ligeros (default / ahorro tokens): `concilio-lightest:latest`, `concilio-worker:latest`, `concilio-medium:latest`, `qwen2.5:1.5b`.

Heavy / árbitro (`concilio-heavy`, `concilio-arbitro`, `gemma4:26b`, sentinel-*): **solo si Elán pide Concilio explícito**.

`deepseek-r1:8b`: **no** estaba en el host al momento del GO.

---

## Termux — arranque

`config.env` (`~/deamonx_mobile/`):

```
REMOTE_OLLAMA_URL=http://127.0.0.1:11434
REMOTE_MODEL=concilio-lightest:latest
NODE_NAME=DeamonX
GATEWAY_PORT=8090
```

Túnel (sesión A; o script `~/deamonx_mobile/bin/tunnel_ollama.sh` con autossh):

```bash
ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -L 11434:127.0.0.1:11434 deamon@192.168.1.144
```

Prueba (sesión B):

```bash
curl -s http://127.0.0.1:11434/api/tags
# opcional: ./test_ollama_connection.sh
# opcional: ./start_deamonx_mobile.sh fast
```

Si `bind: Address already in use` en 11434 → ya hay un `ssh -N` previo; no hace falta otro túnel.

---

## Reglas (Capitán)

1. Preferir Ollama/agentes ligeros; Concilio heavy solo con pedido explícito.
2. Ollama en X-Deamon: solo `127.0.0.1:11434`.
3. Remoto móvil = túnel SSH (`-L 11434`), no bind LAN.
4. Roles A/C/G/T como arriba; T no duplica cola de alertas Telegram.

---

## Checklist GO (2026-09-13)

- [x] `sshd` Kali :22 + harden (password off, pubkey only)
- [x] Firewall Windows `WSL SSH 22` Allow (Private/Public) + Wi‑Fi Private
- [x] `authorized_keys` con pubkey Termux
- [x] Túnel ESTAB + `/api/tags` 200
- [x] `REMOTE_MODEL=concilio-lightest:latest`
- [x] `autossh` / `tunnel_ollama.sh` documentados (opcional si el `ssh -N` sigue vivo)
- [x] `jq` + `~/bridge/check_bridge.sh` en Kali (Agente-C)
