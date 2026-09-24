#!/usr/bin/env bash
# Baut das Frontend und kopiert es nach Home Assistant (/config/www/jotunland).
# Voraussetzung: Add-on "Advanced SSH & Web Terminal" (oder "Terminal & SSH") mit SSH-Zugang.
#
#   HA_HOST=root@homeassistant.local ./scripts/deploy.sh
#
# Danach erreichbar unter http://homeassistant.local:8123/local/jotunland/index.html
set -euo pipefail

HA_HOST="${HA_HOST:-root@homeassistant.local}"
HA_PORT="${HA_PORT:-22}"
TARGET="${HA_TARGET:-/config/www/jotunland}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/frontend"
[ -d node_modules ] || npm ci
npm run build

# tar über SSH statt rsync – funktioniert auch mit dem schlanken SSH-Add-on
ssh -p "$HA_PORT" "$HA_HOST" "mkdir -p '$TARGET' && rm -rf '$TARGET/assets'"
# config.json nur beim ersten Mal kopieren – danach gehört sie dir
if ssh -p "$HA_PORT" "$HA_HOST" "test -f '$TARGET/config.json'"; then
  tar -C dist --exclude=./config.json -cf - . | ssh -p "$HA_PORT" "$HA_HOST" "tar -C '$TARGET' -xf -"
else
  tar -C dist -cf - . | ssh -p "$HA_PORT" "$HA_HOST" "tar -C '$TARGET' -xf -"
fi
echo "Fertig: /local/jotunland/index.html"
