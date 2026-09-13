# Puente seguro DeamonX ↔ Ollama (X-Deamon / Kali)

Puente cifrado Termux (Honor / DeamonX) → Ollama en el PC **sin** abrir Ollama a la LAN.

## Estado (2026-09-13)

- sshd Kali: enabled/active, escucha `:22` en `192.168.1.144`
- Auth: solo pubkey Termux (`PasswordAuthentication no`, `AllowUsers deamon`)
- Pubkey Termux fingerprint: `SHA256:Euih1LjCoXOZEBpu+byhf8lWgPY46haK8bj2Bs9cso4` (`u0_a254@localhost`)
- Host key ED25519: `SHA256:HWCSXJ0CxelYdW7lg4QbGDlPuIm+LUbQpqVejxz1jk4`
- Ollama: solo `127.0.0.1:11434` (HTTP 200 desde Kali; no bind LAN)
- Firewall Windows: regla `WSL SSH 22` Allow Inbound TCP 22, perfiles **Private,Public**; Wi‑Fi `INFINITUM039E_2.4` en **Private**
- WSL: `networkingMode=Mirrored` (`.wslconfig`)
- Verificado: sesión ESTAB desde Termux `192.168.1.137` + `curl http://127.0.0.1:11434/api/tags` OK por túnel
- Modelo móvil: `concilio-lightest:latest` (no hay `deepseek-r1:8b` en el host)

## Archivos en este directorio

| Archivo | Uso |
|---------|-----|
| `TERMUX.md` | Pasos en el teléfono (túnel, config.env, autossh) |
| `check_bridge.sh` | Health check sshd / sesiones / Ollama / keys |
| `install_sshd.sh` | `bootstrap` o `harden` (requiere sudo) |
| `sshd_bootstrap.conf` | Password+pubkey temporal |
| `sshd_deamonx.conf` | Solo pubkey (producción) |

## Roles

- **Agente-C**: sshd, authorized_keys, checks, docs de puente
- **Agente-G**: sudo (install/harden sshd), coord
- **Agente-A**: Termux config/scripts/tests (`tunnel_ollama.sh`, `REMOTE_*`)
- **Agente-T**: Concilio/Telegram (no depende de este túnel)

## Comandos Kali

```bash
~/bridge/check_bridge.sh
# sudo bash ~/bridge/install_sshd.sh bootstrap   # solo bootstrap inicial
# sudo bash ~/bridge/install_sshd.sh harden      # password off (ya aplicado)
```

## Reglas

1. No poner `OLLAMA_HOST=0.0.0.0` sin OK explícito de Elán.
2. Remoto móvil = túnel SSH → `REMOTE_OLLAMA_URL=http://127.0.0.1:11434`.
3. Ahorro tokens: Ollama ligero en móvil; Concilio heavy solo si Elán lo pide.