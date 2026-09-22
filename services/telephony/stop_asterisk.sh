#!/usr/bin/env bash
# Stop VoiceShield Asterisk 20 container
set -euo pipefail

echo "Stopping VoiceShield Asterisk 20..."
docker rm -f voiceshield_asterisk 2>/dev/null || true
echo "Stopped."
