# Jotunland

Moderne Oberfläche für dein Zuhause: Energiefluss (Enphase-PV, Wallbox,
AC THOR), Heizung (Thermostate, Fröling-Pelletkessel), alle Zigbee-Geräte,
Automationen – am Handy und am PC.

## Erste Schritte

1. **Starten** und **Jotunland** in der Seitenleiste öffnen (der Eintrag wird
   beim ersten Start automatisch angelegt).
2. Unter **Einrichtung → Assistent** die offenen Punkte antippen:
   - **Geräte erkannt** – Jotunland findet Enphase, Wallbox, AC THOR und Fröling
     selbst. Falls etwas fehlt: unter *Zuordnung* auswählen.
   - **Geräte verständlich benennen** – aus „0x00158d…“ oder „TS0601“ wird
     z. B. „Thermostat Wohnzimmer“, fehlende Räume werden ergänzt.
   - **Automationen installieren** – ein Klick. Jotunland
     - legt eine Sicherung unter `/config/jotunland_backup/` an,
     - aktiviert `packages` in der `configuration.yaml` (falls nötig),
     - speichert `packages/jotunland.yaml` und den Fenster-Blueprint,
     - lässt Home Assistant die Konfiguration prüfen – bei einem Fehler wird
       alles automatisch zurückgesetzt,
     - startet Home Assistant neu und setzt danach sinnvolle Startwerte.
   - **PV-Überschussladen einschalten** – ein Klick.

Mehr ist nicht zu tun.

## Was die Automationen tun

- **PV-Überschussladen:** Ladestrom folgt jede Minute dem Solarüberschuss, Pause
  nach 5 Minuten ohne genug Sonne. *Min + PV* lädt immer mit Mindeststrom.
- **Sofort laden:** volle Leistung; nach dem Ladeende Meldung und zurück auf
  PV-Überschuss.
- **Heizzeiten & Abwesenheit:** Komfort- oder Absenktemperatur für alle
  Heizkörper, die gerade heizen.
- **Fenster offen → Heizung aus:** pro Raum mit Fensterkontakt automatisch
  angelegt, danach wird der vorige Zustand wiederhergestellt.
- **Sommerbetrieb:** Heizkörper aus, Warmwasser macht der AC THOR; im Herbst
  kommt alles zurück wie vorher.
- **Warmwasser-Nachheizung, Kesselstörung, Pelletvorrat:** Meldungen in Home
  Assistant und – wenn die Home-Assistant-App verbunden ist – aufs Handy.

Alle Werte (Temperaturen, Zeiten, Ladestrom, Phasen …) stellst du in Jotunland
unter **Automationen → Stellschrauben** ein.

## Zugriff von unterwegs

Jotunland läuft über den Ingress von Home Assistant. Überall, wo du Home
Assistant erreichst (Home Assistant Cloud / Nabu Casa, VPN, Home-Assistant-App),
ist auch Jotunland da – mit deiner normalen Anmeldung.

## Rückgängig machen

- Paket entfernen: `packages/jotunland.yaml` löschen und neu starten.
- Jede Änderung an der `configuration.yaml` liegt als Sicherung in
  `/config/jotunland_backup/<Datum>/`.
- Umbenennungen von Geräten sind normale Home-Assistant-Namen und lassen sich
  unter *Einstellungen → Geräte* ändern.
