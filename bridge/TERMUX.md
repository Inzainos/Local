# Termux → Ollama por túnel SSH

Ollama en el PC permanece en `127.0.0.1:11434`. El teléfono usa SSH local-forward a Kali `192.168.1.144`.

## Requisitos

- Misma Wi‑Fi que X-Deamon
- Wi‑Fi del PC en perfil **Private** (si está Public, la regla SSH puede no aplicar)
- Firewall Windows: regla `WSL SSH 22` Allow TCP 22 (Private,Public)
- Pubkey Termux en `/home/deamon/.ssh/authorized_keys` (ya instalada 2026-09-13)

## 1) Una vez: clave SSH

```bash
pkg update -y && pkg install openssh autossh -y
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Si regeneras la clave, mándala a Agente-C para `authorized_keys`.

## 2) Túnel (dejar corriendo)

Sesión A:

```bash
ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -L 11434:127.0.0.1:11434 deamon@192.168.1.144
```

Con `-N` la sesión se ve “quieta”: es normal. Host key esperada:
`SHA256:HWCSXJ0CxelYdW7lg4QbGDlPuIm+LUbQpqVejxz1jk4`

### autossh (opcional, reconecta)

Script documentado por Agente-A: `~/deamonx_mobile/bin/tunnel_ollama.sh`

```bash
autossh -M 0 -N \
  -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -L 11434:127.0.0.1:11434 deamon@192.168.1.144
```

Si `bind: Address already in use` en 11434, ya hay un túnel previo (`ssh -N`).

## 3) config.env (`~/deamonx_mobile/`)

```
REMOTE_OLLAMA_URL=http://127.0.0.1:11434
REMOTE_MODEL=concilio-lightest:latest
```

Alternativa ligera: `qwen2.5:1.5b`. Heavy/arbitro solo si Elán pide Concilio.

## 4) Probar (otra sesión Termux, túnel arriba)

```bash
curl -s http://127.0.0.1:11434/api/tags | head
```

## Troubleshooting

| Síntoma | Qué revisar |
|---------|-------------|
| Cuelga en `Connecting to … port 22` | Wi‑Fi PC Public vs regla Private; misma red; firewall `WSL SSH 22` |
| `Permission denied (publickey)` | pubkey en `authorized_keys`; usuario `deamon` |
| `Address already in use` 11434 | túnel anterior aún vivo |
| curl falla con túnel up | Ollama en PC (`check_bridge.sh` en Kali) |