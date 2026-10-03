# Hausregeln

Hausbezogene Home-Assistant-Pakete, z. B. die AC-THOR-Regelung (`ac_thor.yaml`).
Das Add-on spielt jede `*.yaml` hier beim Installieren/Aktualisieren nach
`/config/packages/<gleicher Name>` – mit Sicherung, Prüfung und automatischem
Zurücksetzen. Dateien, die mit `_` beginnen, sind Vorlagen und werden nicht installiert.

**Das Repository ist öffentlich.** Deshalb gehören hier keine IP-Adressen, Passwörter
oder Tokens hinein, sondern Verweise auf die `secrets.yaml` von Home Assistant:

```yaml
modbus:
  - name: ac_thor
    type: tcp
    host: !secret ac_thor_ip
    port: 502
```

Fehlt ein Geheimwert, zeigt der Einrichtungs-Assistent ein Eingabefeld und trägt ihn
in `/config/secrets.yaml` ein (vorhandene Werte werden nie überschrieben).

`signale.json` (welche Entität welches Signal ist, für `tools/auswertung.mjs`) liegt
ebenfalls hier.
