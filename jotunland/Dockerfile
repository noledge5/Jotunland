ARG BUILD_FROM

# --- Oberfläche bauen ---------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend frontend
COPY homeassistant homeassistant
RUN cd frontend && npm run build

# --- Add-on -------------------------------------------------------------------
FROM ${BUILD_FROM}
RUN apk add --no-cache python3 py3-aiohttp py3-yaml
COPY server/ /app/
COPY homeassistant/ /app/homeassistant/
COPY --from=frontend /src/frontend/dist /app/www
# with-contenv: unter s6 sieht das Programm sonst die Add-on-Umgebung (SUPERVISOR_TOKEN) nicht
CMD ["/usr/bin/with-contenv", "python3", "-u", "/app/jotunland_server.py"]
