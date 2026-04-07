#!/usr/bin/env python3
"""UFW OkBoy - Dynamic Firewall Allowlist Manager.

Server application providing:
1. HTTPS API for clients to register their IP in the firewall allowlist
2. CLI tools for user management and stale-rule cleanup

Authentication: HMAC-SHA256 with timestamp (secret never transmitted).
"""

import argparse
import hashlib
import hmac
import logging
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

import os

import yaml
from flask import Flask, request, jsonify, send_from_directory

from ufw_ops import UFWManager

logger = logging.getLogger("ufw-okboy")

# ====================================================================== #
#  Configuration
# ====================================================================== #

def load_config(path: str) -> dict:
    """Load and validate YAML configuration file."""
    p = Path(path)
    if not p.exists():
        sys.exit(f"Config file not found: {path}")
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Validate required fields
    if not cfg.get("protected_ports"):
        sys.exit("Config error: 'protected_ports' must be a non-empty list")
    if not cfg.get("users"):
        sys.exit("Config error: 'users' must contain at least one user")
    for name, info in cfg["users"].items():
        if not info.get("secret"):
            sys.exit(f"Config error: user '{name}' is missing 'secret'")

    return cfg

# ====================================================================== #
#  HMAC-SHA256 Authentication
# ====================================================================== #

def verify_auth(auth_header: str | None, users: dict, ttl: int = 300) -> tuple[str | None, str | None]:
    """Verify the HMAC-SHA256 Authorization header.

    Header format: ``HMAC-SHA256 <username>:<timestamp>:<hex_signature>``
    Where signature = HMAC-SHA256(secret, "<username>:<timestamp>")

    Returns:
        (username, None) on success, or (None, error_message) on failure.
    """
    if not auth_header or not auth_header.startswith("HMAC-SHA256 "):
        return None, "Missing or invalid Authorization header"

    payload = auth_header[len("HMAC-SHA256 "):]

    # Parse payload
    parts = payload.split(":", 2)
    if len(parts) != 3:
        return None, "Malformed auth payload (expected username:timestamp:signature)"
    username, ts_str, signature = parts

    # Validate timestamp
    try:
        ts = int(ts_str)
    except ValueError:
        return None, "Invalid timestamp"
    if abs(int(time.time()) - ts) > ttl:
        return None, "Signature expired"

    # Validate user
    if username not in users:
        return None, "Unknown user"

    # Verify HMAC
    secret = users[username]["secret"]
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{username}:{ts_str}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        return None, "Invalid signature"

    return username, None

# ====================================================================== #
#  Flask Application Factory
# ====================================================================== #

def create_app(config_path: str = "config.yaml") -> Flask:
    """Create and configure the Flask application."""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    app = Flask(__name__, static_folder=static_dir, static_url_path="/static")
    cfg = load_config(config_path)

    ufw = UFWManager(
        rule_prefix=cfg.get("rule_prefix", "ufw-okboy"),
        state_file=cfg.get("state_file", "/var/lib/ufw-okboy/state.json"),
    )

    users = cfg["users"]
    ttl = cfg.get("signature_ttl", 300)
    ports = cfg["protected_ports"]
    proto = cfg.get("proto", "tcp")

    def _auth():
        return verify_auth(request.headers.get("Authorization"), users, ttl)

    def _client_ip() -> str:
        """Extract real client IP, respecting reverse-proxy headers."""
        return (
            request.headers.get("X-Real-IP")
            or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
        )

    # ---- API Routes ---- #

    @app.route("/api/knock", methods=["POST"])
    def knock():
        """Register or update the caller's IP in the firewall allowlist."""
        username, err = _auth()
        if err:
            logger.warning("Auth failed from %s: %s", _client_ip(), err)
            return jsonify({"ok": False, "error": err}), 401

        client_ip = _client_ip()
        if not client_ip or client_ip == "127.0.0.1":
            return jsonify({
                "ok": False,
                "error": "Cannot determine real client IP. Check Nginx X-Real-IP header.",
            }), 400

        old_ip = ufw.get_user_ip(username)

        # IP unchanged - just refresh the timestamp
        if old_ip == client_ip:
            ufw.update_knock_time(username, client_ip)
            logger.info("Knock: %s@%s (unchanged)", username, client_ip)
            return jsonify({
                "ok": True,
                "ip": client_ip,
                "changed": False,
                "message": "IP unchanged, heartbeat recorded",
            })

        # IP changed - swap firewall rules
        if old_ip:
            for port in ports:
                ufw.remove_rule(old_ip, port, username, proto)
            logger.info("Removed old rules for %s (was %s)", username, old_ip)

        for port in ports:
            ufw.add_rule(client_ip, port, username, proto)

        ufw.update_state(username, client_ip)
        logger.info("Knock: %s@%s (was %s)", username, client_ip, old_ip or "new")

        return jsonify({
            "ok": True,
            "ip": client_ip,
            "changed": True,
            "old_ip": old_ip,
            "message": "Firewall rules updated",
        })

    @app.route("/api/status", methods=["GET"])
    def status():
        """Return the caller's current registration state."""
        username, err = _auth()
        if err:
            return jsonify({"ok": False, "error": err}), 401

        state = ufw.get_user_state(username)
        return jsonify({"ok": True, "username": username, **state})

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint (no auth required)."""
        return jsonify({"ok": True, "service": "ufw-okboy"})

    # ---- Web Client ---- #

    @app.route("/")
    def client_page():
        """Serve the web-based client UI."""
        return send_from_directory(static_dir, "index.html")

    return app

# ====================================================================== #
#  CLI Commands
# ====================================================================== #

def cmd_serve(args):
    """Start the Flask development server."""
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = create_app(args.config)
    cfg = load_config(args.config)
    host = cfg.get("listen_host", "127.0.0.1")
    port = cfg.get("listen_port", 5000)
    logger.info("Starting server on %s:%s", host, port)
    app.run(host=host, port=port, debug=args.debug)


def cmd_gen_secret(args):
    """Generate a random secret for a user."""
    secret = secrets.token_hex(32)
    username = args.username or "<username>"
    print(f"Generated secret for '{username}':\n")
    print(f"  {secret}\n")
    print(f"Add to config.yaml:\n")
    print(f"  users:")
    print(f"    {username}:")
    print(f'      secret: "{secret}"')
    print(f"\nClient config.yaml:\n")
    print(f"  username: \"{username}\"")
    print(f'  secret: "{secret}"')


def cmd_list(args):
    """List all managed users and their current firewall rules."""
    cfg = load_config(args.config)
    ufw = UFWManager(
        rule_prefix=cfg.get("rule_prefix", "ufw-okboy"),
        state_file=cfg.get("state_file", "/var/lib/ufw-okboy/state.json"),
    )

    # Configured users
    print("=== Configured Users ===")
    for name in cfg["users"]:
        state = ufw.get_user_state(name)
        ip = state.get("ip") or "not registered"
        last = state.get("last_knock")
        last_str = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "never"
        print(f"  {name:20s}  IP: {ip:20s}  Last knock: {last_str}")

    # State entries not in config (orphaned)
    orphaned = set(ufw.state.keys()) - set(cfg["users"].keys())
    if orphaned:
        print("\n=== Orphaned State Entries (user removed from config) ===")
        for name in orphaned:
            state = ufw.state[name]
            print(f"  {name:20s}  IP: {state.get('ip', 'N/A')}")

    # Actual UFW rules
    print("\n=== UFW Rules (managed) ===")
    rules = ufw.list_managed_rules()
    if rules:
        for rule in rules:
            print(f"  {rule}")
    else:
        print("  (none)")


def cmd_cleanup(args):
    """Remove firewall rules for users who haven't knocked recently."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = load_config(args.config)
    ufw = UFWManager(
        rule_prefix=cfg.get("rule_prefix", "ufw-okboy"),
        state_file=cfg.get("state_file", "/var/lib/ufw-okboy/state.json"),
    )
    max_age = args.max_age * 86400  # days -> seconds
    removed = ufw.cleanup_stale(max_age, cfg["protected_ports"], cfg.get("proto", "tcp"))
    if removed:
        print(f"Cleaned up {len(removed)} stale user(s): {', '.join(removed)}")
    else:
        print("No stale rules found.")


def cmd_sync(args):
    """Rebuild state.json from current UFW rules (disaster recovery)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = load_config(args.config)
    ufw = UFWManager(
        rule_prefix=cfg.get("rule_prefix", "ufw-okboy"),
        state_file=cfg.get("state_file", "/var/lib/ufw-okboy/state.json"),
    )
    recovered = ufw.sync_state_from_ufw(cfg["protected_ports"])
    if recovered:
        print(f"Recovered {len(recovered)} user(s) from UFW rules:")
        for name, data in recovered.items():
            print(f"  {name}: {data['ip']}")
    else:
        print("No managed rules found in UFW.")


# ====================================================================== #
#  Entry point
# ====================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description="UFW OkBoy - Dynamic Firewall Allowlist Manager",
    )
    parser.add_argument(
        "-c", "--config", default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # serve
    p_serve = sub.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--debug", action="store_true", help="Enable debug mode")

    # gen-secret
    p_gen = sub.add_parser("gen-secret", help="Generate a user secret")
    p_gen.add_argument("username", nargs="?", help="Username (optional)")

    # list
    sub.add_parser("list", help="List managed users and rules")

    # cleanup
    p_clean = sub.add_parser("cleanup", help="Remove stale firewall rules")
    p_clean.add_argument(
        "--max-age", type=int, default=7,
        help="Max age in days before a rule is considered stale (default: 7)",
    )

    # sync
    sub.add_parser("sync", help="Rebuild state from UFW rules (disaster recovery)")

    args = parser.parse_args()

    commands = {
        "serve": cmd_serve,
        "gen-secret": cmd_gen_secret,
        "list": cmd_list,
        "cleanup": cmd_cleanup,
        "sync": cmd_sync,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
