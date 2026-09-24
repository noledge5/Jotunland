# Jotunland – Smarthome-Oberfläche für Home Assistant

Eine moderne, schlichte Oberfläche für dein Zuhause auf Basis von Home Assistant.
Sie ist fürs Handy und den Desktop gebaut und zeigt alle Geräte an einem Ort:

| Bereich | Was du siehst & steuerst |
|---|---|
| **Übersicht** | Energiefluss (PV → Haus / Netz / Wallbox / Warmwasser), Räume, Wallbox, AC THOR, Pelletkessel, Schnellaktionen, Abwesend-Schalter |
| **Heizung** | Jedes Heizkörperthermostat mit ± Solltemperatur, Modus, Fenster-offen-Hinweis und Batteriewarnung; Fröling-Kessel mit Pufferspeicher; Heizprogramm (Komfort-/Absenkzeiten) |
| **Energie** | Enphase-PV mit Tagesertrag und Autarkie, Wallbox mit Lademodus (Aus / Sofort / PV-Überschuss / Min + PV), AC THOR / Warmwasser |
| **Geräte** | Alle Zigbee- und sonstigen Geräte nach Raum gruppiert: Licht (mit Dimmer), Steckdosen, Rollläden, Sensoren. Namen antippen zum Umbenennen |
| **Automationen** | Automationen an/aus und manuell auslösen, Skripte starten, alle Stellschrauben (Temperaturen, Zeiten, Ladestrom …) |
| **Einrichtung** | Assistent mit Ein-Klick-Aktionen, automatische Geräteerkennung und Zuordnung, Namens- und Raumvorschläge, Installation der Automationen |

Jotunland läuft als Home-Assistant-Add-on und spricht über die WebSocket-API mit
Home Assistant. Es gibt keine Cloud. Home Assistant bleibt das Gehirn, Jotunland
ist das Gesicht.

```
repository.yaml                 macht das Repository zur Add-on-Quelle
jotunland/                      das Add-on
  config.yaml, Dockerfile       Add-on-Beschreibung und Bauanleitung
  server/                       kleiner Python-Server (Ingress, Installation)
  frontend/                     React + Vite + TypeScript Oberfläche
  homeassistant/packages/       Helfer, Automationen, Skripte
  homeassistant/blueprints/     Blueprint "Fenster offen → Heizung aus"
scripts/deploy.sh               Alternative ohne Add-ons (HA Container/Core)
```

---

## Installation (Home Assistant OS) – 3 Klicks

[![Add-on-Repository zu Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnoledge5%2FJotunland)

1. Auf den Knopf oben klicken (öffnet dein Home Assistant) → **Hinzufügen**.
   Ohne Knopf: *Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories* →
   `https://github.com/noledge5/Jotunland`.
2. **Jotunland** im Add-on-Store öffnen → **Installieren** → **Starten**.
3. **Jotunland** in der Seitenleiste öffnen → *Einrichtung → Assistent* und die
   offenen Punkte antippen. Das Add-on:
   - meldet sich selbst an (kein Token, kein Passwort),
   - erkennt Enphase, Wallbox, AC THOR, Fröling und alle Thermostate,
   - benennt technisch benannte Zigbee-Geräte auf Wunsch um und ordnet Räume zu,
   - installiert die Automationen: Sicherung → `packages` in der
     `configuration.yaml` aktivieren → Paket und Blueprint ablegen →
     Konfiguration prüfen (bei Fehler automatisch zurück) → Neustart,
   - legt für jeden Raum mit Fensterkontakt „Fenster offen → Heizung aus“ an,
   - setzt Startwerte (16 A, 3 Phasen, 21/18 °C, 6–22 Uhr, Warmwasser 45 °C).

Jotunland steht danach in der Seitenleiste – und damit auch in der
Home-Assistant-App auf dem Handy. Von unterwegs geht es überall dort, wo
Home Assistant erreichbar ist (Home Assistant Cloud / Nabu Casa oder VPN).

> Home Assistant liest Add-ons aus dem Standard-Branch (`main`) des Repositorys.

### Ohne Add-ons (Home Assistant Container/Core)

```bash
HA_HOST=root@homeassistant.local ./scripts/deploy.sh
```

Danach `http://homeassistant.local:8123/local/jotunland/index.html` öffnen und
unter *Einstellungen → Dashboards → Webseite* in die Seitenleiste legen. Das
Automationen-Paket gibt es dann unter *Einrichtung → HA-Paket* zum Herunterladen
(schon mit deinen Geräten ausgefüllt).

### Ausprobieren ohne Home Assistant

```bash
cd jotunland/frontend && npm install && npm run dev
```

`http://localhost:5173/?demo` zeigt ein simuliertes Zuhause.

## Geräte zuordnen (automatisch)

Unter **Einrichtung → Zuordnung** sucht Jotunland selbst nach deinen Geräten. Für
jede Funktion (z. B. „PV-Leistung aktuell“ oder „Wallbox Ladestrom“) bewertet es
alle Entitäten nach folgenden Kriterien:

- **Integration und Hersteller** aus der Geräte-Registry (Enphase Envoy, go-e,
  my-PV, Fröling …)
- **Einheit und Typ** (W, kWh, °C, A; Sensor, Schalter, Zahl …)
- **Stichworten** in ID und Namen, auch deutschen („Kessel“, „Puffer oben“,
  „Ladestrom“ …)

Der beste Treffer wird automatisch verwendet. Liegt die Erkennung daneben, wählst
du im Dropdown eine andere Entität. Die Auswahl wird in deinem Home-Assistant-
Benutzerkonto gespeichert und gilt damit auf allen Geräten. Alternativ trägst du
die entity_ids fest in `config.json` ein; der Button *Als config.json
exportieren* erzeugt die Datei.

**Einrichtung → Geräte benennen** findet Geräte mit technischen Namen wie
`0x00158d0004a1b2c3`, `TS0601` oder `lumi.sensor_magnet.aq2`. Es erkennt den
Gerätetyp (Thermostat, Fensterkontakt, Steckdose, Klimasensor …) und schlägt
Namen wie *„Thermostat Wohnzimmer“* vor. Fehlt der Raum, wird er aus Namen und
IDs erraten. *Übernehmen* schreibt Name und Raum direkt in Home Assistant, einzeln
oder für alle auf einmal. Das braucht einen Admin-Benutzer.

Räume für die Heizungsseite entstehen automatisch: Jedes Thermostat wird mit dem
Fensterkontakt und dem Feuchtesensor aus demselben HA-Bereich kombiniert.

## Automationen

Mit dem Add-on installiert der Assistent alles selbst. Ohne Add-on: `packages`
in der `configuration.yaml` aktivieren (`homeassistant: packages:
!include_dir_named packages`), die Datei aus *Einrichtung → HA-Paket* als
`/config/packages/jotunland.yaml` speichern, den Blueprint aus
`jotunland/homeassistant/blueprints/` nach `/config/blueprints/automation/jotunland/`
kopieren und Home Assistant neu starten.

### Was die Automationen tun

| Automation | Funktion |
|---|---|
| **PV-Überschussladen** | Berechnet jede Minute den Überschuss (PV − Verbrauch + aktuelle Ladeleistung) und stellt den Ladestrom passend ein. Pausiert, wenn 5 Minuten lang zu wenig Sonne da ist. Bei *Min + PV* wird immer mindestens mit dem Mindeststrom geladen. |
| **Modus Sofort / Aus** | *Sofort* lädt mit Maximalstrom und schaltet nach dem Ladeende automatisch zurück auf *PV-Überschuss*. Dazu kommt eine Push-Nachricht mit der geladenen Energie. |
| **Heizzeiten** | Stellt alle heizenden Thermostate zur Heizzeit auf Komfort, sonst auf Absenktemperatur. Bei *Abwesend* bleibt es bei der Absenktemperatur. Ausgeschaltete (Fenster offen) bleiben aus. |
| **Sommerbetrieb** | Schaltet die Heizkörper aus, Warmwasser kommt dann vom AC THOR per PV. Beim Ausschalten wird der vorige Zustand wiederhergestellt. |
| **Warmwasser-Nachheizung** | Liegt das Warmwasser 30 Minuten unter dem Minimum und scheint kaum Sonne, wird der Pelletkessel angefordert. |
| **Kessel-Störung / Pelletvorrat** | Meldung bei einer Störung und bei weniger als 20 % Pellets – in Home Assistant und aufs Handy, sobald die App verbunden ist. |
| **Fenster offen** (Blueprint) | Schaltet das Thermostat bei offenem Fenster aus und stellt danach Modus und Temperatur wieder her. |

Gerätespezifische Befehle stecken nur in den **Adapter-Skripten**
`jotunland_wallbox_start/stop/strom` und `jotunland_pellet_anfordern`. Bei einer
anderen Wallbox-Integration oder für die Fröling-Warmwasseranforderung passt du
nur diese Skripte an.

## Geräte & Integrationen

| Gerät | Empfohlene Integration |
|---|---|
| Enphase PV | *Enphase Envoy* (in HA enthalten). Für Hausverbrauch und Netz braucht der Envoy Verbrauchs-Stromwandler (CTs). |
| Heizkörperthermostate, Zigbee | ZHA oder Zigbee2MQTT |
| AC THOR (my-PV) | *my-PV* (HACS) oder Modbus TCP |
| Fröling Pelletheizung | *Fröling Connect* (HACS) oder Modbus über die Lambdatronic |
| Wallbox | go-e: *go-eCharger (APIv2)* (HACS); sonst die Integration deines Herstellers |

## Mit echten Geräten weiterbauen (Claude Code auf deinem PC)

Automationen mit echten IPs und Signalen baust du am besten mit Claude Code auf
einem PC in deinem Heimnetz. Von dort erreicht es Home Assistant **und** die
Geräte direkt. Die Datei `CLAUDE.md` erklärt Claude Code das Projekt und die
Regeln; zum Beispiel wird nichts an echten Geräten geschaltet, ohne dich zu fragen.

**Einmalig einrichten** (Node.js ab Version 22 und Git müssen installiert sein):

```bash
git clone https://github.com/noledge5/Jotunland.git
cd Jotunland
cd tools && npm install && cd ..
cp .env.example .env.local        # Windows: copy .env.example .env.local
```

In `.env.local` eintragen:

- `HA_URL` und `HA_TOKEN`: Token in Home Assistant unter *Profil → Sicherheit →
  Langlebiges Zugriffstoken erstellen*.
- Für `deploy` zusätzlich SSH: Add-on **Terminal & SSH** installieren, in dessen
  Konfiguration deinen öffentlichen SSH-Schlüssel eintragen, starten. Dann
  `HA_SSH=root@homeassistant.local`.
- Die Geräte-IPs findet `node tools/geraete.mjs suchen` selbst.

Danach im Ordner `Jotunland` Claude Code starten (Desktop-App oder `claude` im
Terminal) und loslegen, z. B.: *„Such meine Geräte, zeig mir die echten Werte der
Wallbox und bau das PV-Überschussladen so, dass es bei Wolken nicht ständig
schaltet.“*

**Die Werkzeuge**, die Claude Code (oder du) dabei benutzt:

| Befehl | Zweck |
|---|---|
| `node tools/geraete.mjs suchen` | Heimnetz nach Home Assistant, go-e, Envoy und AC THOR durchsuchen und Rohwerte zeigen (nur lesend) |
| `node tools/ha.mjs states <muster>` | Entitäten und Zustände auflisten |
| `node tools/ha.mjs watch <muster> [sek]` | Signale live mitschreiben |
| `node tools/ha.mjs validate <datei>` | Automationen/Skripte mit dem HA-Validator prüfen, unbekannte entity_ids melden |
| `node tools/ha.mjs deploy <datei>` | prüfen → per SSH nach `/config/packages/` → Konfiguration prüfen → neu laden; bei Fehlern automatisch zurück |
| `node tools/ha.mjs trace <automation>` | letzten Durchlauf zeigen: welcher Zweig, welche Aufrufe, welche Fehler |

Eigene, hausbezogene Automationen kommen nach `haus/jotunland_haus.yaml`. Der
Ordner wird nicht eingecheckt, weil das Repository öffentlich ist.

## Entwicklung

```bash
cd jotunland/frontend
npm run dev                  # http://localhost:5173 – nutzt VITE_HA_URL/VITE_HA_TOKEN aus .env.local
npm run build                # Typprüfung + Produktions-Build nach dist/ (ohne Token)
```

Die Erkennungsregeln stehen in `jotunland/frontend/src/discovery.ts` (`SLOTS`).
Neue Geräte kommen dort als weiterer Eintrag hinzu. Karten und Seiten liegen
unter `jotunland/frontend/src/components` bzw. `…/views`, der Add-on-Server unter
`jotunland/server/`. Nach Änderungen am Add-on die `version` in
`jotunland/config.yaml` erhöhen – Home Assistant bietet dann ein Update an.
