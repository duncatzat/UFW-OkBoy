"""UFW firewall operations and state management.

Responsibilities:
- Add/remove UFW allow rules with user-identifying comments
- Track per-user state (current IP, last knock time) in a JSON file
- Cleanup stale rules that exceed a configurable max age
"""

import json
import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("ufw-okboy.ufw")


class UFWManager:
    """Manages UFW firewall rules and persists user-IP mapping state."""

    def __init__(self, rule_prefix: str = "ufw-okboy",
                 state_file: str = "/var/lib/ufw-okboy/state.json"):
        self.rule_prefix = rule_prefix
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state: dict = self._load_state()

    # ------------------------------------------------------------------ #
    #  State persistence
    # ------------------------------------------------------------------ #

    def _load_state(self) -> dict:
        """Load user state from JSON file. Return empty dict if missing or corrupt."""
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("State file corrupt or unreadable, starting fresh: %s", exc)
            return {}

    def _save_state(self) -> None:
        """Atomically write state to disk (write-then-rename)."""
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
        tmp.replace(self.state_file)

    # ------------------------------------------------------------------ #
    #  UFW commands
    # ------------------------------------------------------------------ #

    @staticmethod
    def _run_ufw(*args: str) -> str:
        """Execute a UFW command, return stdout.

        Note: ``--force`` is NOT added globally — callers must include it
        explicitly when needed (e.g. ``delete``).  Some UFW versions reject
        ``--force`` before ``allow``/``deny``, causing *Invalid syntax*.
        """
        cmd = ["ufw", *args]
        logger.info("Exec: %s", " ".join(cmd))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            logger.error(
                "UFW failed (rc=%d): cmd=%s | stderr=%s",
                result.returncode, " ".join(cmd), result.stderr.strip(),
            )
            raise RuntimeError(f"UFW command failed: {result.stderr.strip()}")
        return result.stdout

    def add_rule(self, ip: str, port: int, username: str, proto: str = "tcp") -> None:
        """Add a UFW allow rule: allow <ip> to access <port> with identifying comment."""
        comment = f"{self.rule_prefix}:{username}"
        self._run_ufw(
            "allow", "from", ip,
            "to", "any", "port", str(port), "proto", proto,
            "comment", comment,
        )
        logger.info("Added rule: %s -> port %s/%s (%s)", ip, port, proto, username)

    def remove_rule(self, ip: str, port: int, username: str, proto: str = "tcp") -> None:
        """Remove a specific UFW rule. Logs warning if rule doesn't exist.

        Uses ``--force`` to suppress the interactive confirmation prompt
        that ``ufw delete`` would otherwise display.
        """
        try:
            self._run_ufw(
                "--force", "delete", "allow", "from", ip,
                "to", "any", "port", str(port), "proto", proto,
            )
            logger.info("Removed rule: %s -> port %s/%s (%s)", ip, port, proto, username)
        except RuntimeError:
            logger.warning("Rule removal failed (may not exist): %s -> %s/%s", ip, port, proto)

    # ------------------------------------------------------------------ #
    #  User state queries
    # ------------------------------------------------------------------ #

    def get_user_ip(self, username: str) -> str | None:
        """Return the currently registered IP for a user, or None."""
        return self.state.get(username, {}).get("ip")

    def get_user_state(self, username: str) -> dict:
        """Return full state dict for a user (safe copy without ip_history)."""
        data = self.state.get(username, {"ip": None, "last_knock": None})
        # Return a clean view for the API (omit internal tracking fields)
        return {
            "ip": data.get("ip"),
            "last_knock": data.get("last_knock"),
            "ip_changes_recent": len(data.get("ip_history", [])),
        }

    def update_state(self, username: str, ip: str) -> None:
        """Record a new IP and knock timestamp, maintaining IP change history."""
        now = int(time.time())
        existing = self.state.get(username, {})
        old_ip = existing.get("ip")

        # Maintain a rolling window of recent IP changes for anomaly detection.
        # Each entry: {"ip": ..., "ts": ...}
        ip_history = existing.get("ip_history", [])
        if old_ip and old_ip != ip:
            ip_history.append({"ip": old_ip, "ts": now})
        # Keep only last 24 hours of history
        cutoff = now - 86400
        ip_history = [e for e in ip_history if e["ts"] > cutoff]

        self.state[username] = {
            "ip": ip,
            "last_knock": now,
            "ip_history": ip_history,
        }
        self._save_state()

    def update_knock_time(self, username: str, ip: str) -> None:
        """Update only the last-knock timestamp (IP unchanged)."""
        if username in self.state:
            self.state[username]["last_knock"] = int(time.time())
        else:
            self.state[username] = {
                "ip": ip,
                "last_knock": int(time.time()),
                "ip_history": [],
            }
        self._save_state()

    def check_ip_anomaly(self, username: str, window_seconds: int = 3600,
                         max_changes: int = 5) -> dict | None:
        """Detect suspicious IP change patterns that suggest credential sharing.

        Checks if IP has changed more than *max_changes* times within the
        rolling *window_seconds*. Normal users rarely change IP more than
        once or twice per day.

        Returns:
            None if normal, or dict with anomaly details if suspicious.
        """
        data = self.state.get(username, {})
        ip_history = data.get("ip_history", [])
        if not ip_history:
            return None

        now = int(time.time())
        cutoff = now - window_seconds
        recent_changes = [e for e in ip_history if e["ts"] > cutoff]

        if len(recent_changes) >= max_changes:
            unique_ips = {e["ip"] for e in recent_changes}
            unique_ips.add(data.get("ip", ""))
            return {
                "changes": len(recent_changes),
                "window": window_seconds,
                "unique_ips": len(unique_ips),
                "ips": list(unique_ips),
            }
        return None

    # ------------------------------------------------------------------ #
    #  Maintenance
    # ------------------------------------------------------------------ #

    def cleanup_stale(self, max_age_seconds: int, ports: list[int],
                      proto: str = "tcp") -> list[str]:
        """Remove firewall rules for users who haven't knocked within *max_age_seconds*.

        Returns list of removed usernames.
        """
        now = int(time.time())
        removed: list[str] = []

        for username in list(self.state):
            data = self.state[username]
            last_knock = data.get("last_knock", 0)
            if now - last_knock > max_age_seconds:
                ip = data.get("ip")
                if ip:
                    for port in ports:
                        self.remove_rule(ip, port, username, proto)
                del self.state[username]
                removed.append(username)
                logger.info("Cleaned up stale user: %s (last knock %ds ago)", username, now - last_knock)

        if removed:
            self._save_state()
        return removed

    def list_managed_rules(self) -> list[str]:
        """Parse ``ufw status`` output and return lines containing our rule prefix."""
        try:
            output = subprocess.run(
                ["ufw", "status"], capture_output=True, text=True, timeout=15, check=False,
            ).stdout
        except Exception:
            return []

        return [
            line.strip()
            for line in output.splitlines()
            if self.rule_prefix in line
        ]

    def sync_state_from_ufw(self, ports: list[int]) -> dict:
        """Rebuild state by parsing current UFW rules (recovery tool).

        Useful if state.json is lost but UFW rules still exist.
        """
        pattern = re.compile(
            rf"ALLOW\s+IN?\s+(\S+)\s+.*#\s*{re.escape(self.rule_prefix)}:(\S+)"
        )
        try:
            output = subprocess.run(
                ["ufw", "status"], capture_output=True, text=True, timeout=15, check=False,
            ).stdout
        except Exception:
            return {}

        recovered = {}
        for line in output.splitlines():
            m = pattern.search(line)
            if m:
                ip, username = m.group(1), m.group(2)
                recovered[username] = {"ip": ip, "last_knock": int(time.time())}

        if recovered:
            self.state.update(recovered)
            self._save_state()
            logger.info("Recovered %d users from UFW rules", len(recovered))
        return recovered
