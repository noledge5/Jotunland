# Duennes Image: Python + git. Der App-Code wird beim Start in ein Volume
# geklont und laeuft von dort (siehe deploy/entrypoint.sh) — so kann sich
# die NAS ohne Image-Rebuild selbst auf neue Commits aktualisieren.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Abhaengigkeiten vorinstallieren (warmer Cache); der Entrypoint prueft beim
# Start nochmal gegen die geklonte requirements.txt.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    APP_DIR=/app/src \
    BRANCH=claude/project-review-documentation-0a2bmp \
    UPDATE_INTERVAL=120

EXPOSE 3111
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3111/api/state >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
