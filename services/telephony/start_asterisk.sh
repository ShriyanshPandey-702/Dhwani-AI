#!/usr/bin/env bash
# Start VoiceShield Asterisk 20 container
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve ARI credentials from environment or project .env files
ARI_USER="${ARI_USER:-voiceshield}"
ARI_PASSWORD="${ARI_PASSWORD:-${ARI_PASS:-}}"

if [ -z "${ARI_PASSWORD}" ]; then
  if [ -f "${SCRIPT_DIR}/../../.env" ]; then
    val=$(grep -E '^(ARI_PASSWORD|ARI_PASS)=' "${SCRIPT_DIR}/../../.env" | head -n 1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$val" ] && ARI_PASSWORD="$val"
  fi
fi

if [ -z "${ARI_PASSWORD}" ]; then
  if [ -f "${SCRIPT_DIR}/../api/.env" ]; then
    val=$(grep -E '^(ARI_PASSWORD|ARI_PASS)=' "${SCRIPT_DIR}/../api/.env" | head -n 1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$val" ] && ARI_PASSWORD="$val"
  fi
fi

if [ -z "${ARI_PASSWORD}" ]; then
  echo "ERROR: ARI_PASSWORD is not set. Please set ARI_PASSWORD in your environment or in .env." >&2
  exit 1
fi

RUNTIME_ARI_CONF="${SCRIPT_DIR}/asterisk/.ari.conf.runtime"
cat > "${RUNTIME_ARI_CONF}" <<EOF
; VoiceShield Asterisk REST Interface Configuration (Generated at runtime)
[general]
enabled = yes
pretty = yes
allowed_origins = *

[${ARI_USER}]
type = user
read_only = no
password = ${ARI_PASSWORD}
password_format = plain
EOF
chmod 600 "${RUNTIME_ARI_CONF}"

echo "Starting VoiceShield Asterisk 20..."
docker rm -f voiceshield_asterisk 2>/dev/null || true

docker run -d --name voiceshield_asterisk --restart unless-stopped \
  -p 5060:5060/udp -p 5060:5060/tcp \
  -p 8088:8088/tcp \
  -p 10000-10020:10000-10020/udp \
  --add-host host.docker.internal:host-gateway \
  -v "${SCRIPT_DIR}/asterisk/pjsip.conf":/etc/asterisk/pjsip.conf:ro \
  -v "${SCRIPT_DIR}/asterisk/extensions.conf":/etc/asterisk/extensions.conf:ro \
  -v "${RUNTIME_ARI_CONF}":/etc/asterisk/ari.conf:ro \
  -v "${SCRIPT_DIR}/asterisk/http.conf":/etc/asterisk/http.conf:ro \
  -v "${SCRIPT_DIR}/asterisk/rtp.conf":/etc/asterisk/rtp.conf:ro \
  -v "${SCRIPT_DIR}/sounds":/var/lib/asterisk/sounds/en:ro \
  -v "${SCRIPT_DIR}/../..":/workspace:ro \
  -e ASTERISK_TERMINAL_OPTS=-n \
  andrius/asterisk:20

echo "Waiting for Asterisk to become ready..."
for i in {1..30}; do
  if curl -s -u "${ARI_USER}:${ARI_PASSWORD}" http://localhost:8088/ari/asterisk/info >/dev/null 2>&1; then
    echo "Asterisk 20 is ready on port 5060 (SIP) and 8088 (ARI)."
    exit 0
  fi
  sleep 1
done

echo "Asterisk failed to start within 30 seconds."
exit 1
