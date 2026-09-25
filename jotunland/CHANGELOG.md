# Changelog

## 0.4.0
- Hausbatterie: eigener Knoten im Energiefluss (Laden/Entladen, Ladestand) und
  Batterie-Karte unter Energie; Hausverbrauch und Autarkie berücksichtigen die Batterie
- PV-Überschussladen berücksichtigt Batterie und Warmwasser: Reihenfolge
  Haus → Batterie (bis „Batterie-Vorrang“) → Auto → Warmwasser; für PV-Laden wird nie
  Netzstrom gekauft oder die Batterie entladen (Paket-Version 5, neue Platzhalter für
  Netz, Batterie und Warmwasserleistung)
- Erkennung: Stichwörter werden nur noch in Name/ID gesucht, nicht in der Modellbezeichnung
  (Enphase-Modelle heißen „…net-consumption CT“ und wurden dadurch alle ausgeschlossen);
  deutsche Envoy-Namen („Nettostromverbrauch“) werden erkannt, OCPP-Wallboxen ebenso

## 0.3.0
- go-e Charger: Gesamtleistung (nrg_11) wird sicher erkannt, Ladefreigabe
  funktioniert auch mit Rohwerten (frc 1/2)
- Nach der Installation prüft das Add-on das Systemprotokoll und zeigt
  Ladefehler des Pakets im Assistenten an
- Werkzeuge für die Arbeit im Heimnetz (tools/): Geräte finden, Signale
  beobachten, Automationen prüfen, einspielen und nachverfolgen

## 0.2.0
- Jotunland als Home-Assistant-Add-on (Ingress, automatische Anmeldung)
- Einrichtungs-Assistent: Geräte benennen, Automationen installieren,
  Startwerte, PV-Laden – jeweils mit einem Klick
- Installation mit Sicherung, Konfigurationsprüfung und automatischem Zurücksetzen
- Fenster-Automationen werden pro Raum automatisch erzeugt
- Thermostate werden einzeln und fehlertolerant gestellt; Sommerbetrieb merkt
  sich den vorherigen Zustand
- Meldungen gehen immer an Home Assistant, aufs Handy sobald die App verbunden ist

## 0.1.0
- Erste Version: Übersicht, Heizung, Energie, Geräte, Automationen, Einrichtung
