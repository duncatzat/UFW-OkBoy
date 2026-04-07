# UFW OkBoy

Dynamic firewall allowlist manager — automatically registers authorized clients' IP addresses in UFW when they authenticate, and cleans up stale entries to keep the firewall tidy.

[English](README.en.md) | [中文](README.md)

---

## Problem

Your server's sensitive ports (admin panels, databases, APIs) are protected by UFW firewall rules that only allow access from specific IPs. But client IPs change — switching networks, traveling, restarting routers. Every change means contacting the admin to manually update the firewall.

## Solution

UFW OkBoy automates this. Clients authenticate through an HTTPS endpoint, and the server automatically updates UFW rules to allow their current IP. When their IP changes, the old rule is swapped out on the next heartbeat. Each rule is tagged with the username for full traceability.

```
Client (Browser / Python / Shell)
    |
    | HTTPS + HMAC-SHA256 auth
    v
Nginx (reverse proxy, TLS, passes X-Real-IP)
    |
    v
Flask API (verify identity, extract client IP)
    |
    v
UFW (remove old rule → add new rule → comment: ufw-okboy:<username>)
```

## Key Features

- **Web client** — open a page, login once, auto-knocks every 30s. Credentials saved for auto-reconnect on reopen. Works on mobile.
- **One IP per user per port** — old IP removed before new IP added, firewall stays clean
- **Traceable rules** — every UFW rule tagged `ufw-okboy:<username>`, visible in `ufw status`
- **Anti-sharing** — sharing credentials = mutual kicking (only one IP active per account). Anomaly detection alerts on suspicious IP switching patterns.
- **Auto-cleanup** — stale rules (users who haven't knocked in 7+ days) purged by daily timer
- **Simple auth** — HMAC-SHA256 with timestamp. Secret never transmitted. HTTPS encrypted.
- **Three client options** — Web UI (browser only), Python script, Shell script (curl + openssl)

## Quick Start

**Server (admin):**

```bash
git clone https://github.com/lvusyy/UFW-OkBoy.git /opt/ufw-okboy
cd /opt/ufw-okboy
python3 -m venv venv && venv/bin/pip install -r server/requirements.txt
cd server
../venv/bin/python app.py gen-secret alice        # generate user secret
cp config.example.yaml config.yaml                # edit: set ports and secrets
sudo ../venv/bin/python app.py serve --debug       # start (dev mode)
```

**Client (user):**

Open `https://your-server.com/` in a browser → enter username and secret → Connect.

## Documentation

See **[GUIDE.md](GUIDE.md)** for the complete guide (Chinese), including:

- Server deployment (UFW prerequisites, Nginx, Systemd)
- Key generation and secure distribution workflow
- Client usage (Web / Python / Shell)
- Daily management (user CRUD, rule cleanup, troubleshooting)
- Security mechanisms and best practices
- FAQ

## Project Structure

```
server/
  app.py              Flask API + CLI management (serve/gen-secret/list/cleanup/sync)
  ufw_ops.py          UFW operations + state management
  static/index.html   Web client (single-file SPA)
  config.example.yaml Configuration template
  requirements.txt    Python dependencies
client/
  knock.py            Python client (stdlib only, zero external deps)
  knock.sh            Shell client (curl + openssl)
  config.example.yaml Client config template
nginx/
  ufw-okboy.conf      Nginx reverse proxy configuration
deploy/
  ufw-okboy.service   Systemd service (Gunicorn)
  ufw-okboy-cleanup.* Daily stale rule cleanup timer
  knock.*             Client auto-knock timer
  install-server.sh   Server installation script
```

## License

MIT
