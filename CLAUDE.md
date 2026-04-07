# UFW OkBoy - Dynamic Firewall Allowlist Manager

## Project Overview

A lightweight system that allows authorized clients to automatically register their IP addresses
in the server's UFW firewall allowlist. Designed for scenarios where client IPs change frequently
and manual allowlist management is impractical.

## Architecture

```
Client (knock.py / knock.sh)
    |
    | HTTPS (port 443)
    v
Nginx (reverse proxy, TLS termination, passes X-Real-IP)
    |
    | HTTP (127.0.0.1:5000)
    v
Flask API (app.py)
    |
    | subprocess
    v
UFW Firewall (ufw_ops.py)
    |
    v
State Store (/var/lib/ufw-okboy/state.json)
```

## Authentication Protocol

HMAC-SHA256 with timestamp, sent via `Authorization` header:

```
Authorization: HMAC-SHA256 <username>:<timestamp>:<signature>
signature = HMAC-SHA256(secret, "<username>:<timestamp>")
```

- Secret never transmitted over the wire
- Timestamp window: 300 seconds (configurable)
- HTTPS provides transport-layer encryption

## Key Design Decisions

- **One UFW rule per user per port**: old IP removed before adding new IP
- **UFW comment format**: `ufw-okboy:<username>` for traceability
- **State file**: JSON file tracks current IP + last knock time per user
- **Server runs as root**: required for UFW management
- **Gunicorn for production**: Flask dev server only for testing

## Directory Structure

```
server/
  app.py              - Flask API + CLI management commands
  ufw_ops.py          - UFW firewall operations + state management
  config.example.yaml - Server configuration template
  requirements.txt    - Python dependencies (Flask, PyYAML, Gunicorn)
client/
  knock.py            - Python client (requires: pyyaml)
  knock.sh            - Shell client (zero dependencies, uses curl + openssl)
  config.example.yaml - Client configuration template
nginx/
  ufw-okboy.conf      - Nginx reverse proxy configuration example
deploy/
  ufw-okboy.service   - Systemd service for server
  ufw-okboy-cleanup.service - Systemd service for stale rule cleanup
  ufw-okboy-cleanup.timer   - Systemd timer for daily cleanup
  knock.service       - Systemd service for client auto-knock
  knock.timer         - Systemd timer for client periodic knock
```

## CLI Commands (Server)

```bash
python app.py serve                    # Start API server
python app.py serve --debug            # Start in debug mode
python app.py gen-secret [username]    # Generate a user secret
python app.py list                     # List managed users and rules
python app.py cleanup --max-age 7     # Remove rules older than 7 days
```

## Development

- Python 3.8+
- Server dependencies: `pip install -r server/requirements.txt`
- Client dependencies: `pip install pyyaml` (or use knock.sh for zero deps)
- Server requires root privileges for UFW management
- Test locally with `python app.py serve --debug`
