# Jotunland – Hinweise für Claude Code

Smarthome-Oberfläche und Automationen für ein Haus mit Home Assistant OS.
Sprache im Projekt: Deutsch (Oberfläche, Kommentare, Commit-Nachrichten).

## Das Haus

| Gerät | Anbindung | Bekannte Details |
|---|---|---|
| Enphase PV (Envoy) | HA-Integration „Enphase Envoy“ | Ab Firmware 7 Token nötig; lokal `https://<IP>/production.json?details=1` (selbst signiertes Zertifikat) |
| go-e Charger (Nutzer nennt ihn „freecharge go“) | HACS „go-eCharger (APIv2)“ oder REST | HTTP API v2 muss in der go-e App aktiv sein. `GET http://<IP>/api/status` – `car` (1 bereit, 2 lädt, 3 wartet, 4 fertig), `amp` (A), `frc` (0 neutral, 1 aus, 2 an), `nrg[11]` (Gesamtleistung W), `wh` (Wh seit Anstecken), `psm` (1/2 = 1-/3-phasig). Setzen: `GET /api/set?amp=10`, `/api/set?frc=1` |
| my-PV AC THOR (steuert Heizstab/„Tubratherm“ für Warmwasser) | noch offen – HACS, REST (`/data.jsn`) oder Modbus TCP | Temperaturen meist in Zehntel-Grad. Feldnamen erst am echten Gerät prüfen |
| Fröling Pelletkessel | noch offen – Fröling Connect (Cloud) oder Modbus | Warmwasser-Anforderung ist im Paket nur als Meldung umgesetzt (`script.jotunland_pellet_anfordern`) |
| Zigbee (Heizkörperthermostate, Fensterkontakte …) | ZHA oder Zigbee2MQTT | Namen oft technisch (`0x…`, `TS0601`) – die Oberfläche schlägt bessere vor |

## Aufbau

```
jotunland/                      Home-Assistant-Add-on (Ingress)
  config.yaml                   Add-on-Version – bei jeder Änderung am Add-on erhöhen
  server/jotunland_server.py    liefert Oberfläche aus, WebSocket-Proxy, installiert das Paket
  frontend/                     React/Vite/TypeScript
    src/discovery.ts            Erkennungsregeln (SLOTS) für Geräte → Funktionen
    src/haPackage.ts            füllt Platzhalter im Paket mit den erkannten entity_ids
  homeassistant/packages/jotunland.yaml   Vorlage mit Platzhaltern sensor.anpassen_… –
                                          Kopfzeile "jotunland-package-version" bei Änderungen erhöhen
  homeassistant/blueprints/…    Blueprint „Fenster offen → Heizung aus“
tools/                          Werkzeuge für die Arbeit im Heimnetz (Node ≥ 22)
  ha.mjs                        Home Assistant: states, watch, call, validate, check, trace, reload, deploy
  geraete.mjs                   Geräte finden und direkt per IP auslesen (nur lesend)
haus/                           hausbezogene Pakete (nicht im Git, Repo ist öffentlich)
lokal/                          Ausgaben der Werkzeuge (nicht im Git)
```

Zugangsdaten stehen in `.env.local` (Vorlage `.env.example`), nie im Code.

## Arbeiten mit echten Signalen

1. Überblick: `node tools/geraete.mjs` (IPs aus `.env.local`) bzw.
   `node tools/geraete.mjs suchen` – zeigt die Rohwerte der Geräte.
2. Entitäten finden: `node tools/ha.mjs states "goe|envoy|thor|froeling"`,
   Details mit `node tools/ha.mjs get <entity_id>`.
3. Verhalten beobachten, bevor eine Automation gebaut wird:
   `node tools/ha.mjs watch "<muster>" 600` – z. B. wie schnell die PV-Leistung schwankt.
4. Hausbezogene Automationen in `haus/jotunland_haus.yaml` schreiben (HA-Paketformat:
   `automation:`, `script:`, `template:` …). Allgemeine Verbesserungen gehören in die Vorlage
   `jotunland/homeassistant/packages/jotunland.yaml` – dort nur Platzhalter, keine echten IDs.
5. `node tools/ha.mjs validate haus/jotunland_haus.yaml` – prüft jede Automation mit dem
   HA-Validator und meldet unbekannte entity_ids.
6. `node tools/ha.mjs deploy haus/jotunland_haus.yaml` – kopiert per SSH nach
   `/config/packages/`, prüft, lädt neu und setzt bei Fehlern automatisch zurück.
   `packages/jotunland.yaml` gehört dem Add-on – nicht überschreiben.
7. Testen: `watch` für die Signale, `trace <automation>` für den letzten Durchlauf
   (welcher Zweig, welche Dienstaufrufe, welche Fehler).

Wichtig: `check_config` von Home Assistant meldet fehlerhafte Automationen und Template-Sensoren
**nicht** – deshalb immer `validate` vorher und das Systemprotokoll nachher (macht `deploy` selbst).

## Regeln

- **Echte Geräte nur nach Rückfrage schalten.** Lesen (`states`, `get`, `watch`, `trace`,
  `geraete.mjs`) ist immer in Ordnung. Bevor `call`, `deploy` oder ein direkter HTTP-Befehl an
  ein Gerät etwas verändert (Wallbox-Strom, Laden an/aus, Heizmodus, Kessel), kurz sagen, was
  passiert, und auf ein Ja warten.
- Beim Testen von Wallbox-Automationen den Lademodus beachten: im Modus „Aus“ greift nichts.
- `configuration.yaml` in Home Assistant nicht per SSH ändern – das Add-on richtet `packages` ein.
- Nie `.env.local`, Tokens, `haus/` oder `lokal/` committen oder in Logs ausgeben.
- Vor dem Commit: `cd jotunland/frontend && npm run build` (Typprüfung) und bei Paketänderungen
  `node tools/ha.mjs validate jotunland/homeassistant/packages/jotunland.yaml`.
- Nach Änderungen am Add-on `version` in `jotunland/config.yaml` erhöhen und `CHANGELOG.md`
  ergänzen – sonst bietet Home Assistant kein Update an.

## Befehle

```bash
cd tools && npm install                     # einmalig
node tools/ha.mjs hilfe                     # alle HA-Befehle
cd jotunland/frontend && npm run dev        # Oberfläche mit echtem HA (VITE_HA_URL/TOKEN in .env.local)
cd jotunland/frontend && npm run dev -- --open "/?demo"   # Demo ohne HA
```
