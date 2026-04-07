#!/usr/bin/env bash
# UFW OkBoy - Shell Client (zero dependencies beyond curl + openssl)
#
# Usage:
#   ./knock.sh                        # Knock once
#   ./knock.sh status                 # Check registration status
#   KNOCK_CONFIG=/path/cfg ./knock.sh # Custom config path
#
# Config file format (default: ~/.config/ufw-okboy/config):
#   SERVER_URL=https://your-server.com
#   USERNAME=alice
#   SECRET=your-secret-here

set -euo pipefail

# ---- Configuration ---- #

CONFIG_FILE="${KNOCK_CONFIG:-$HOME/.config/ufw-okboy/config}"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    echo ""
    echo "Create it with:"
    echo "  mkdir -p ~/.config/ufw-okboy"
    echo "  cat > ~/.config/ufw-okboy/config << 'EOF'"
    echo "  SERVER_URL=https://your-server.com"
    echo "  USERNAME=alice"
    echo "  SECRET=your-secret-here"
    echo "  EOF"
    echo "  chmod 600 ~/.config/ufw-okboy/config"
    exit 1
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"

: "${SERVER_URL:?SERVER_URL is required in config}"
: "${USERNAME:?USERNAME is required in config}"
: "${SECRET:?SECRET is required in config}"

# ---- HMAC-SHA256 Auth ---- #

build_auth() {
    local timestamp
    timestamp=$(date +%s)
    local message="${USERNAME}:${timestamp}"
    local signature
    signature=$(printf '%s' "$message" | openssl dgst -sha256 -hmac "$SECRET" -hex 2>/dev/null | awk '{print $NF}')
    echo "HMAC-SHA256 ${USERNAME}:${timestamp}:${signature}"
}

# ---- Actions ---- #

do_knock() {
    local auth
    auth=$(build_auth)
    curl -s -X POST \
        "${SERVER_URL}/api/knock" \
        -H "Authorization: ${auth}" \
        -H "Content-Type: application/json" \
        --connect-timeout 10 \
        --max-time 30
    echo ""
}

do_status() {
    local auth
    auth=$(build_auth)
    curl -s -X GET \
        "${SERVER_URL}/api/status" \
        -H "Authorization: ${auth}" \
        --connect-timeout 10 \
        --max-time 30
    echo ""
}

# ---- Main ---- #

ACTION="${1:-knock}"

case "$ACTION" in
    knock)
        do_knock
        ;;
    status)
        do_status
        ;;
    *)
        echo "Usage: $0 [knock|status]"
        exit 1
        ;;
esac
