"""Jotunland Add-on-Server.

- liefert die Oberfläche über Ingress aus
- reicht die WebSocket-API von Home Assistant durch (Anmeldung erledigt der
  Server mit dem Supervisor-Token, Ingress lässt ohnehin nur angemeldete
  HA-Administratoren durch)
- installiert das Automationen-Paket samt Blueprint in /config, prüft die
  Konfiguration, stellt bei Fehlern alles wieder her und startet HA neu
- setzt nach der Installation sinnvolle Startwerte für die Helfer
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("jotunland")

TOKEN = os.environ.get("JOTUNLAND_TOKEN") or os.environ.get("SUPERVISOR_TOKEN", "")
CORE_WS = os.environ.get("JOTUNLAND_CORE_WS", "ws://supervisor/core/websocket")
CORE_API = os.environ.get("JOTUNLAND_CORE_API", "http://supervisor/core/api").rstrip("/")
SUPERVISOR_API = os.environ.get("JOTUNLAND_SUPERVISOR_API", "http://supervisor").rstrip("/")
CONFIG_DIR = Path(os.environ.get("JOTUNLAND_CONFIG_DIR", "/homeassistant"))
DATA_DIR = Path(os.environ.get("JOTUNLAND_DATA_DIR", "/data"))
APP_DIR = Path(__file__).resolve().parent
WWW = Path(os.environ.get("JOTUNLAND_WWW", APP_DIR / "www"))
_BLUEPRINT_REL = "homeassistant/blueprints/automation/jotunland/fenster_offen_heizung_aus.yaml"
# im Container liegt homeassistant/ neben dem Server, im Repository eine Ebene höher
BLUEPRINT_SRC = next((d / _BLUEPRINT_REL for d in (APP_DIR, APP_DIR.parent) if (d / _BLUEPRINT_REL).is_file()), APP_DIR / _BLUEPRINT_REL)
BLUEPRINT_DST = CONFIG_DIR / "blueprints/automation/jotunland/fenster_offen_heizung_aus.yaml"
PORT = int(os.environ.get("JOTUNLAND_PORT", "8099"))
DEV = os.environ.get("JOTUNLAND_DEV") == "1"
INGRESS_IP = "172.30.32.2"
VERSION_RE = re.compile(r"#\s*jotunland-package-version:\s*(\d+)")

# Startwerte nach der ersten Installation. Gesetzt wird nur, was noch auf dem
# Minimalwert steht – eigene Einstellungen bleiben unangetastet.
DEFAULTS: dict[str, float | str] = {
    "input_number.jotunland_wallbox_max_ampere": 16,
    "input_number.jotunland_wallbox_phasen": 3,
    "input_number.jotunland_komfort_temperatur": 21,
    "input_number.jotunland_eco_temperatur": 18,
    "input_number.jotunland_warmwasser_minimum": 45,
    "input_datetime.jotunland_heizen_start": "06:00:00",
    "input_datetime.jotunland_heizen_ende": "22:00:00",
}


class ManualSetup(Exception):
    """configuration.yaml ist so aufgebaut, dass wir sie nicht sicher ändern können."""


class ConfigInvalid(Exception):
    pass


# --------------------------------------------------------------- Zustand ----

STATE_FILE = DATA_DIR / "state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ------------------------------------------------------- Home Assistant ----

def _headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def core(method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, object]:
    async with ClientSession(timeout=ClientTimeout(total=timeout)) as s:
        async with s.request(method, f"{CORE_API}/{path}", headers=_headers(), json=body) as r:
            try:
                data = await r.json(content_type=None)
            except ValueError:
                data = await r.text()
            return r.status, data


async def check_config() -> None:
    status, data = await core("POST", "config/core/check_config", timeout=180)
    if status != 200:
        raise ConfigInvalid(f"Konfigurationsprüfung nicht möglich (HTTP {status}): {data}")
    if not isinstance(data, dict) or data.get("result") != "valid":
        errors = data.get("errors") if isinstance(data, dict) else data
        raise ConfigInvalid(str(errors or "Konfiguration ungültig"))


async def validate_package(package: dict) -> None:
    """Prüft jede Automation und jedes Skript einzeln mit dem Validator des Automations-Editors.

    Nötig, weil die normale Konfigurationsprüfung fehlerhafte Automationen nicht
    meldet – HA lädt sie später einfach nicht.
    """
    checks: list[tuple[str, dict]] = []
    for auto in package.get("automation") or []:
        if not isinstance(auto, dict) or "use_blueprint" in auto:
            continue  # Blueprint-Automationen prüft HA beim Laden des Blueprints
        name = auto.get("alias") or auto.get("id") or "?"
        checks.append(
            (
                f"Automation „{name}“",
                {
                    "triggers": auto.get("triggers", auto.get("trigger", [])),
                    "conditions": auto.get("conditions", auto.get("condition", [])),
                    "actions": auto.get("actions", auto.get("action", [])),
                },
            )
        )
    for key, script in (package.get("script") or {}).items():
        if isinstance(script, dict):
            checks.append((f"Skript „{script.get('alias', key)}“", {"actions": script.get("sequence", [])}))

    errors: list[str] = []
    async with ClientSession(timeout=ClientTimeout(total=60)) as session:
        async with session.ws_connect(CORE_WS, max_msg_size=0) as ws:
            msg = await ws.receive_json()
            if msg.get("type") == "auth_required":
                await ws.send_json({"type": "auth", "access_token": TOKEN})
                msg = await ws.receive_json()
            if msg.get("type") != "auth_ok":
                raise ConfigInvalid("Anmeldung für die Prüfung fehlgeschlagen")
            for msg_id, (label, parts) in enumerate(checks, start=1):
                await ws.send_json({"id": msg_id, "type": "validate_config", **parts})
                while (res := await ws.receive_json()).get("id") != msg_id:
                    pass
                if not res.get("success"):
                    errors.append(f"{label}: {res.get('error', {}).get('message')}")
                    continue
                for part, result in (res.get("result") or {}).items():
                    if result and not result.get("valid"):
                        errors.append(f"{label} ({part}): {result.get('error')}")
    if errors:
        raise ConfigInvalid("; ".join(errors))


async def restart_later(delay: float = 1.5) -> None:
    await asyncio.sleep(delay)
    try:
        await core("POST", "services/homeassistant/restart", {}, timeout=10)
    except Exception:  # noqa: BLE001 – HA trennt beim Neustart die Verbindung, das ist normal
        pass


async def apply_defaults() -> list[str] | None:
    """Setzt Startwerte. None = Helfer existieren (noch) nicht."""
    first = next(iter(DEFAULTS))
    status, _ = await core("GET", f"states/{first}")
    if status != 200:
        return None
    applied = []
    for entity_id, value in DEFAULTS.items():
        status, st = await core("GET", f"states/{entity_id}")
        if status != 200 or not isinstance(st, dict):
            continue
        domain = entity_id.split(".")[0]
        if domain == "input_number":
            try:
                current, minimum = float(st["state"]), float(st["attributes"]["min"])
            except (TypeError, ValueError, KeyError):
                continue
            if current == minimum and current != float(value):
                await core("POST", "services/input_number/set_value", {"entity_id": entity_id, "value": value})
                applied.append(entity_id)
        elif domain == "input_datetime" and st.get("state") in ("00:00:00", "unknown"):
            await core("POST", "services/input_datetime/set_datetime", {"entity_id": entity_id, "time": value})
            applied.append(entity_id)
    return applied


async def load_errors(since: float) -> list[str]:
    """Fehler, die HA beim Laden des Pakets protokolliert hat.

    Die Konfigurationsprüfung lässt z. B. fehlerhafte Template-Sensoren durch –
    HA meldet sie erst beim Laden im Systemprotokoll.
    """
    async with ClientSession(timeout=ClientTimeout(total=30)) as session:
        async with session.ws_connect(CORE_WS, max_msg_size=0) as ws:
            msg = await ws.receive_json()
            if msg.get("type") == "auth_required":
                await ws.send_json({"type": "auth", "access_token": TOKEN})
                await ws.receive_json()
            await ws.send_json({"id": 1, "type": "system_log/list"})
            while (res := await ws.receive_json()).get("id") != 1:
                pass
    return [
        m
        for e in res.get("result") or []
        if e.get("timestamp", 0) >= since and e.get("level") in ("ERROR", "CRITICAL")
        for m in e.get("message", [])
        if "jotunland" in m and re.search(r"Invalid config|Error loading|Setup failed", m)
    ]


async def defaults_loop(_app: web.Application) -> None:
    while True:
        await asyncio.sleep(15)
        state = load_state()
        if not state.get("pending_defaults"):
            continue
        try:
            applied = await apply_defaults()
        except Exception as err:  # noqa: BLE001 – HA startet evtl. noch
            LOG.debug("Startwerte noch nicht möglich: %s", err)
            continue
        if applied is not None:
            LOG.info("Startwerte gesetzt: %s", ", ".join(applied) or "nichts nötig")
            state["pending_defaults"] = False
            try:
                state["load_errors"] = await load_errors(state.get("installed_at", 0))
            except Exception as err:  # noqa: BLE001
                LOG.info("Systemprotokoll nicht lesbar: %s", err)
            if state.get("load_errors"):
                LOG.warning("Paket mit Fehlern geladen: %s", state["load_errors"])
            save_state(state)


# ---------------------------------------------------- configuration.yaml ----

@dataclass
class Plan:
    new_config: str | None  # None = configuration.yaml bleibt unverändert
    package_path: Path
    merge: bool  # !include_dir_merge_named → Datei braucht "jotunland:" als Wurzel
    note: str


HA_LINE = re.compile(r"^homeassistant:\s*(#.*)?$")


def _is_content(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def plan_packages(text: str) -> Plan:
    default_pkg = CONFIG_DIR / "packages" / "jotunland.yaml"
    lines = text.splitlines()
    idx = next((i for i, line in enumerate(lines) if HA_LINE.match(line)), None)

    if idx is None:
        if re.search(r"^homeassistant:", text, re.M):
            raise ManualSetup(
                "Der Abschnitt „homeassistant:“ ist ausgelagert (!include). Bitte dort "
                "„packages: !include_dir_named packages“ ergänzen und erneut installieren."
            )
        sep = "\n\n" if text.strip() else ""
        new = text.rstrip("\n") + sep + "homeassistant:\n  packages: !include_dir_named packages\n"
        return Plan(new, default_pkg, False, "Pakete in configuration.yaml aktiviert")

    block: list[int] = []
    j = idx + 1
    while j < len(lines) and (not _is_content(lines[j]) or lines[j].startswith((" ", "\t"))):
        block.append(j)
        j += 1
    child = next((re.match(r"^(\s+)", lines[k]).group(1) for k in block if _is_content(lines[k])), "  ")

    for k in block:
        m = re.match(rf"^{re.escape(child)}packages:\s*(.*?)\s*(#.*)?$", lines[k])
        if not m:
            continue
        value = m.group(1)
        inc = re.match(r"^!include_dir_(merge_)?named\s+['\"]?([^'\"\s]+)['\"]?$", value)
        if inc:
            return Plan(None, CONFIG_DIR / inc.group(2) / "jotunland.yaml", bool(inc.group(1)), "Pakete bereits aktiv")
        if value == "":
            nxt = next((n for n in range(k + 1, len(lines)) if _is_content(lines[n])), None)
            grand = re.match(r"^(\s*)", lines[nxt]).group(1) if nxt is not None else ""
            if len(grand) <= len(child):
                grand = child + "  "
            if any(re.match(rf"^{re.escape(grand)}jotunland:", line) for line in lines):
                return Plan(None, default_pkg, False, "Paket bereits eingetragen")
            new_lines = lines[: k + 1] + [f"{grand}jotunland: !include packages/jotunland.yaml"] + lines[k + 1 :]
            return Plan("\n".join(new_lines) + "\n", default_pkg, False, "Paket in configuration.yaml eingetragen")
        raise ManualSetup(
            f"„packages: {value}“ in configuration.yaml kann nicht automatisch erweitert werden. "
            "Bitte das Jotunland-Paket von Hand einbinden."
        )

    new_lines = lines[: idx + 1] + [f"{child}packages: !include_dir_named packages"] + lines[idx + 1 :]
    return Plan("\n".join(new_lines) + "\n", default_pkg, False, "Pakete in configuration.yaml aktiviert")


def installed_package() -> tuple[Path | None, int | None]:
    state = load_state()
    candidates = [Path(state["package_path"])] if state.get("package_path") else []
    candidates.append(CONFIG_DIR / "packages" / "jotunland.yaml")
    for path in candidates:
        if path.is_file():
            m = VERSION_RE.search(path.read_text(errors="ignore")[:2000])
            return path, int(m.group(1)) if m else 0
    return None, None


# ------------------------------------------------------------------ Routen ----

@web.middleware
async def only_ingress(request: web.Request, handler):
    if not DEV and request.remote not in (INGRESS_IP, "127.0.0.1"):
        raise web.HTTPForbidden(text="Nur über Home Assistant (Ingress) erreichbar")
    return await handler(request)


async def index(_request: web.Request) -> web.StreamResponse:
    return web.FileResponse(WWW / "index.html", headers={"Cache-Control": "no-cache"})


async def config_json(_request: web.Request) -> web.StreamResponse:
    return web.FileResponse(WWW / "config.json", headers={"Cache-Control": "no-cache"})


async def status(_request: web.Request) -> web.Response:
    path, version = installed_package()
    try:
        cfg = (CONFIG_DIR / "configuration.yaml").read_text()
        plan = plan_packages(cfg)
        setup = {"automatic": True, "note": plan.note}
    except ManualSetup as err:
        setup = {"automatic": False, "note": str(err)}
    except OSError:
        setup = {"automatic": False, "note": "configuration.yaml nicht lesbar"}
    state = load_state()
    return web.json_response(
        {
            "addon": True,
            "package": {
                "installed": path is not None,
                "version": version,
                "path": str(path.relative_to(CONFIG_DIR)) if path else None,
            },
            "blueprint": BLUEPRINT_DST.is_file(),
            "setup": setup,
            "pending_defaults": bool(state.get("pending_defaults")),
            "load_errors": state.get("load_errors") or [],
            "last_install": state.get("installed_at"),
        }
    )


def _snapshot(paths: list[Path]) -> dict[Path, str | None]:
    return {p: (p.read_text() if p.is_file() else None) for p in paths}


def _restore(snapshot: dict[Path, str | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(content)


def _backup(snapshot: dict[Path, str | None]) -> Path:
    target = CONFIG_DIR / "jotunland_backup" / time.strftime("%Y%m%d-%H%M%S")
    for path, content in snapshot.items():
        if content is not None:
            dst = target / path.relative_to(CONFIG_DIR)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content)
    return target


async def install(request: web.Request) -> web.Response:
    body = await request.json()
    text = body.get("yaml", "")
    restart = body.get("restart", True)
    steps: list[str] = []
    try:
        parsed = yaml.safe_load(text)
        if not isinstance(parsed, dict) or "automation" not in parsed:
            raise ValueError("kein Jotunland-Paket")
    except (yaml.YAMLError, ValueError) as err:
        return web.json_response({"ok": False, "error": f"Paket ungültig: {err}"}, status=400)

    try:
        await validate_package(parsed)
    except ConfigInvalid as err:
        return web.json_response({"ok": False, "error": f"Paket abgelehnt, nichts verändert: {err}"}, status=400)

    config_file = CONFIG_DIR / "configuration.yaml"
    try:
        plan = plan_packages(config_file.read_text() if config_file.is_file() else "")
    except ManualSetup as err:
        return web.json_response({"ok": False, "error": str(err), "manual": True}, status=409)

    snapshot = _snapshot([config_file, plan.package_path, BLUEPRINT_DST])
    backup_dir = _backup(snapshot)
    steps.append(f"Sicherung angelegt: {backup_dir.relative_to(CONFIG_DIR)}")
    try:
        if plan.new_config is not None:
            config_file.write_text(plan.new_config)
        steps.append(plan.note)
        content = text
        if plan.merge:
            content = "jotunland:\n" + "\n".join(f"  {line}" if line else line for line in text.splitlines()) + "\n"
        plan.package_path.parent.mkdir(parents=True, exist_ok=True)
        plan.package_path.write_text(content)
        steps.append(f"Paket gespeichert: {plan.package_path.relative_to(CONFIG_DIR)}")
        BLUEPRINT_DST.parent.mkdir(parents=True, exist_ok=True)
        BLUEPRINT_DST.write_text(BLUEPRINT_SRC.read_text())
        steps.append(f"Blueprint gespeichert: {BLUEPRINT_DST.relative_to(CONFIG_DIR)}")
        await check_config()
        steps.append("Konfiguration geprüft: gültig")
    except Exception as err:  # noqa: BLE001
        _restore(snapshot)
        LOG.warning("Installation zurückgerollt: %s", err)
        return web.json_response(
            {"ok": False, "error": str(err), "steps": steps + ["Alles zurückgesetzt – es wurde nichts verändert."]},
            status=500,
        )

    state = load_state()
    state.update(package_path=str(plan.package_path), pending_defaults=True, installed_at=time.time())
    save_state(state)
    if restart:
        asyncio.create_task(restart_later())
        steps.append("Home Assistant wird neu gestartet …")
    LOG.info("Paket installiert: %s", "; ".join(steps))
    return web.json_response({"ok": True, "steps": steps, "restarting": bool(restart)})


async def uninstall(_request: web.Request) -> web.Response:
    path, _ = installed_package()
    snapshot = _snapshot([p for p in (path, BLUEPRINT_DST) if p])
    _backup(snapshot)
    for p in snapshot:
        p.unlink(missing_ok=True)
    try:
        await check_config()
    except Exception as err:  # noqa: BLE001 – z. B. eigene Automationen nutzen den Blueprint noch
        _restore(snapshot)
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    state = load_state()
    state.pop("package_path", None)
    save_state(state)
    asyncio.create_task(restart_later())
    return web.json_response({"ok": True, "restarting": True})


async def set_defaults(_request: web.Request) -> web.Response:
    applied = await apply_defaults()
    return web.json_response({"ok": applied is not None, "applied": applied or []})


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    """WebSocket zur Oberfläche ↔ WebSocket zu Home Assistant.

    Die Oberfläche meldet sich mit einem Platzhalter-Token an; die echte
    Anmeldung gegenüber HA übernimmt der Server mit dem Supervisor-Token.
    """
    client = web.WebSocketResponse(max_msg_size=0, heartbeat=50)
    await client.prepare(request)
    session = ClientSession()
    try:
        async with session.ws_connect(CORE_WS, max_msg_size=0, heartbeat=50) as upstream:
            hello = await upstream.receive_json(timeout=15)
            if hello.get("type") == "auth_required":
                await upstream.send_json({"type": "auth", "access_token": TOKEN})
                hello = await upstream.receive_json(timeout=15)
            if hello.get("type") != "auth_ok":
                LOG.error("Anmeldung bei Home Assistant fehlgeschlagen: %s", hello)
                await client.close()
                return client
            version = hello.get("ha_version")
            await client.send_json({"type": "auth_required", "ha_version": version})
            await client.receive_json(timeout=30)  # Platzhalter-Anmeldung der Oberfläche
            await client.send_json({"type": "auth_ok", "ha_version": version})

            async def pump(src, dst):
                async for msg in src:
                    if msg.type == WSMsgType.TEXT:
                        await dst.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await dst.send_bytes(msg.data)
                    else:
                        break

            tasks = [asyncio.create_task(pump(client, upstream)), asyncio.create_task(pump(upstream, client))]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except Exception as err:  # noqa: BLE001 – HA startet neu o. Ä.; die Oberfläche verbindet sich neu
        LOG.info("WebSocket beendet: %s", err)
    finally:
        await session.close()
        if not client.closed:
            await client.close()
    return client


async def enable_sidebar_once() -> None:
    """Beim allerersten Start "In Seitenleiste anzeigen" einschalten – später gilt die Wahl des Nutzers."""
    state = load_state()
    if state.get("sidebar_done") or not os.environ.get("SUPERVISOR_TOKEN"):
        return
    try:
        async with ClientSession(timeout=ClientTimeout(total=15)) as s:
            async with s.post(f"{SUPERVISOR_API}/addons/self/options", headers=_headers(), json={"ingress_panel": True}) as r:
                ok = r.status == 200
    except Exception as err:  # noqa: BLE001
        LOG.info("Seitenleiste nicht automatisch aktivierbar: %s", err)
        return
    if ok:
        LOG.info("Jotunland in der Seitenleiste aktiviert")
        state["sidebar_done"] = True
        save_state(state)


def make_app() -> web.Application:
    app = web.Application(middlewares=[only_ingress], client_max_size=4 * 1024 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/config.json", config_json)
    app.router.add_get("/api/websocket", websocket_proxy)
    app.router.add_get("/jotunland/status", status)
    app.router.add_post("/jotunland/install", install)
    app.router.add_post("/jotunland/uninstall", uninstall)
    app.router.add_post("/jotunland/defaults", set_defaults)
    if (WWW / "assets").is_dir():
        app.router.add_static("/assets", WWW / "assets")

    async def start_background(app_: web.Application):
        app_["defaults"] = asyncio.create_task(defaults_loop(app_))
        app_["sidebar"] = asyncio.create_task(enable_sidebar_once())

    app.on_startup.append(start_background)
    return app


if __name__ == "__main__":
    LOG.info("Jotunland startet auf Port %s (Konfiguration: %s)", PORT, CONFIG_DIR)
    web.run_app(make_app(), host="0.0.0.0", port=PORT, access_log=None)
