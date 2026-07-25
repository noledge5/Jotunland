#!/bin/sh
# Entrypoint: klont die Branch beim ersten Start ins Volume, seedet die Welt,
# startet eine Auto-Update-Schleife (git pull) und uvicorn mit --reload.
# Neue Commits auf der Branch werden so binnen UPDATE_INTERVAL uebernommen,
# ohne Image-Rebuild. Runtime-Daten (wiki/, data/) sind gitignored und
# ueberleben Updates (git reset --hard fasst nur getrackte Dateien an).
set -e

REPO_URL="${REPO_URL:-https://github.com/noledge5/Jotunland}"
BRANCH="${BRANCH:-claude/project-review-documentation-0a2bmp}"
APP_DIR="${APP_DIR:-/app/src}"
INTERVAL="${UPDATE_INTERVAL:-120}"

git config --global --add safe.directory '*'
mkdir -p "$APP_DIR"

# Erststart: in ein Temp klonen und hineinkopieren (robust, falls das Volume
# schon Synology-Metadaten wie @eaDir enthaelt).
if [ ! -d "$APP_DIR/.git" ]; then
  echo "[deploy] Klone $REPO_URL ($BRANCH) ..."
  rm -rf /tmp/clone
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" /tmp/clone
  cp -a /tmp/clone/. "$APP_DIR"/
  rm -rf /tmp/clone
fi

cd "$APP_DIR"
git fetch origin "$BRANCH" --quiet || true
git reset --hard "origin/$BRANCH" || true
pip install --no-cache-dir -r requirements.txt

# Welt seeden, falls noch nicht vorhanden.
if [ ! -d "wiki/world" ]; then
  echo "[deploy] Seede Welt ..."
  python -m scripts.seed_world || echo "[deploy] Seed uebersprungen"
fi

# Auto-Update-Schleife im Hintergrund.
(
  while true; do
    sleep "$INTERVAL"
    git -C "$APP_DIR" fetch origin "$BRANCH" --quiet 2>/dev/null || continue
    LOCAL=$(git -C "$APP_DIR" rev-parse HEAD)
    REMOTE=$(git -C "$APP_DIR" rev-parse "origin/$BRANCH")
    [ "$LOCAL" = "$REMOTE" ] && continue
    echo "[updater] Neue Version $REMOTE — aktualisiere"
    REQ_CHANGED=$(git -C "$APP_DIR" diff --name-only "$LOCAL" "$REMOTE" -- requirements.txt)
    git -C "$APP_DIR" reset --hard "origin/$BRANCH"
    if [ -n "$REQ_CHANGED" ]; then
      echo "[updater] requirements geaendert — installiere neu"
      pip install --no-cache-dir -r "$APP_DIR/requirements.txt" || true
    fi
    # uvicorn --reload uebernimmt die geaenderten .py-Dateien automatisch.
  done
) &

echo "[deploy] Starte Server auf 0.0.0.0:3111 (LAN + Tailscale erreichbar)"
# --reload-dir beschraenkt das Neuladen auf Code — Spielstand-Schreibzugriffe
# (wiki/, data/) loesen KEINEN Reload aus.
exec uvicorn app.main:app --host 0.0.0.0 --port 3111 \
     --reload --reload-dir "$APP_DIR/app" --reload-dir "$APP_DIR/scripts"
