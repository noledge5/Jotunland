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
| **Einrichtung** | Automatische Geräteerkennung und Zuordnung, Namens- und Raumvorschläge, fertig ausgefülltes HA-Paket |

Die Oberfläche spricht direkt über die WebSocket-API mit Home Assistant. Es gibt
keinen eigenen Server und keine Cloud. Home Assistant bleibt das Gehirn, Jotunland
ist das Gesicht.

```
frontend/                  React + Vite + TypeScript Oberfläche
  public/config.json       optionale feste Zuordnung von Geräten (entity_ids)
homeassistant/
  packages/jotunland.yaml  Helfer, Automationen, Skripte
  blueprints/…             Blueprint "Fenster offen → Heizung aus"
scripts/deploy.sh          baut und kopiert die Oberfläche nach Home Assistant
```

---

## 1. Ausprobieren ohne Home Assistant (Demo)

```bash
cd frontend
npm install
npm run dev
```

Öffne `http://localhost:5173/?demo`. Alles ist simuliert, du kannst aber schon
alles anklicken.

## 2. In Home Assistant installieren

1. **Bauen & kopieren.** Mit dem SSH-Add-on geht das automatisch:
   ```bash
   HA_HOST=root@homeassistant.local ./scripts/deploy.sh
   ```
   Alternativ: `cd frontend && npm run build` und den Inhalt von `frontend/dist/`
   (z. B. per Samba-Add-on) nach `/config/www/jotunland/` kopieren. Existiert der
   Ordner `www` noch nicht, Home Assistant danach einmal neu starten.
2. **Aufrufen:** `http://homeassistant.local:8123/local/jotunland/index.html`.
   Die Anmeldung läuft über den normalen Home-Assistant-Login, ein Token ist nicht nötig.
3. **In die Seitenleiste und die HA-App:** *Einstellungen → Dashboards →
   Dashboard hinzufügen → Webseite*, URL `/local/jotunland/index.html`, Titel
   „Jotunland“. Damit ist die Oberfläche auch in der Companion-App auf dem Handy.

### Von unterwegs

Jotunland ist unter jeder Adresse erreichbar, unter der auch dein Home Assistant
erreichbar ist. Mit **Home Assistant Cloud (Nabu Casa)** also z. B.
`https://<deine-id>.ui.nabu.casa/local/jotunland/index.html`. Alternativ geht
das über die Companion-App oder einen eigenen Reverse-Proxy bzw. VPN (WireGuard,
Tailscale). Die Anmeldung ist in jedem Fall der Home-Assistant-Login.

> Dateien unter `/local/` sind ohne Anmeldung abrufbar. Das ist unkritisch, denn
> dort liegt nur die Oberfläche selbst. Daten und Steuerung gibt es erst nach dem
> HA-Login. Schreibe deshalb nie ein Token in `config.json`.

## 3. Geräte zuordnen (automatisch)

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

## 4. Automationen installieren

1. In `configuration.yaml` Pakete aktivieren (falls noch nicht geschehen):
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. **Einrichtung → HA-Paket** öffnen. Dort ist `jotunland.yaml` schon mit deinen
   erkannten entity_ids ausgefüllt. Herunterladen und als
   `/config/packages/jotunland.yaml` speichern.
   (Die Vorlage liegt in `homeassistant/packages/jotunland.yaml`. Nicht
   zugeordnete Stellen heißen `…anpassen_…`.)
3. *Entwicklerwerkzeuge → YAML → Konfiguration prüfen*, dann neu starten.
4. Einmalig die Stellschrauben setzen (Seite **Automationen** oder **Energie**):
   Wallbox max. Strom (z. B. 16 A), Phasen (1 oder 3), Komfort- und
   Absenktemperatur, Heizzeiten, Warmwasser-Minimum.
5. Blueprint `homeassistant/blueprints/automation/jotunland/fenster_offen_heizung_aus.yaml`
   nach `/config/blueprints/automation/jotunland/` kopieren und pro Raum eine
   Automation daraus anlegen.

### Was die Automationen tun

| Automation | Funktion |
|---|---|
| **PV-Überschussladen** | Berechnet jede Minute den Überschuss (PV − Verbrauch + aktuelle Ladeleistung) und stellt den Ladestrom passend ein. Pausiert, wenn 5 Minuten lang zu wenig Sonne da ist. Bei *Min + PV* wird immer mindestens mit dem Mindeststrom geladen. |
| **Modus Sofort / Aus** | *Sofort* lädt mit Maximalstrom und schaltet nach dem Ladeende automatisch zurück auf *PV-Überschuss*. Dazu kommt eine Push-Nachricht mit der geladenen Energie. |
| **Heizzeiten** | Stellt alle Thermostate zur Heizzeit auf Komfort, sonst auf Absenktemperatur. Bei *Abwesend* bleibt es bei der Absenktemperatur. |
| **Sommerbetrieb** | Schaltet die Thermostate aus. Warmwasser kommt dann vom AC THOR per PV. |
| **Warmwasser-Nachheizung** | Liegt das Warmwasser 30 Minuten unter dem Minimum und scheint kaum Sonne, wird der Pelletkessel angefordert. |
| **Kessel-Störung / Pelletvorrat** | Push-Nachricht bei einer Störung und bei weniger als 20 % Pellets. |
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

## Entwicklung

```bash
cd frontend
cp .env.example .env.local   # HA-Adresse + langlebiges Token eintragen
npm run dev                  # http://localhost:5173
npm run build                # Typprüfung + Produktions-Build nach dist/
```

Die Erkennungsregeln stehen in `frontend/src/discovery.ts` (`SLOTS`). Neue
Geräte kommen dort als weiterer Eintrag hinzu. Karten und Seiten liegen unter
`frontend/src/components` bzw. `frontend/src/views`.
