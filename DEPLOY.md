# Deployment auf Synology NAS

Jotunland laeuft als Docker-Container. Der Container klont die Branch beim
Start und **aktualisiert sich alle 2 Minuten automatisch** auf neue Commits
(`git pull` + uvicorn-Reload) — pushe ich einen Fix, uebernimmt die NAS ihn
von selbst, ohne Image-Rebuild. Erreichbar aus dem WLAN und ueber Tailscale.

## Voraussetzungen

- Synology mit **Container Manager** (DSM 7.2+) oder Docker.
- Ein OpenRouter-Key (`sk-or-...`) — oder Anthropic/Google.
- Optional: Tailscale (Synology-Paket) fuer Zugriff von unterwegs.

## Einrichtung (SSH, empfohlen — am wenigsten Klicks)

SSH in die NAS (DSM: Systemsteuerung -> Terminal & SNMP -> SSH aktivieren),
dann:

```sh
sudo -i
mkdir -p /volume1/docker/jotunland && cd /volume1/docker/jotunland
git clone -b claude/project-review-documentation-0a2bmp \
  https://github.com/noledge5/Jotunland .
printf 'OPENROUTER_API_KEY=DEIN_KEY\n' > .env
docker compose up -d --build
```

Fertig. Erreichbar auf `http://<NAS-LAN-IP>:3111`.

Logs / Status:
```sh
docker compose logs -f
docker compose ps
```

## Einrichtung (Container Manager GUI, ohne SSH)

1. **Dateistation**: Ordner `docker/jotunland` anlegen. Dort eine Datei
   `.env` mit dem Inhalt `OPENROUTER_API_KEY=DEIN_KEY` ablegen, und die
   Projektdateien hineinlegen (Repo als ZIP von GitHub laden, Branch
   `claude/project-review-documentation-0a2bmp`, entpacken).
2. **Container Manager -> Projekt -> Erstellen**:
   - Projektname: `jotunland`
   - Pfad: der Ordner `docker/jotunland`
   - Quelle: `docker-compose.yml` (wird erkannt).
3. **Erstellen** und starten. Der erste Build dauert ein paar Minuten
   (Python-Image + Abhaengigkeiten).

## Zugriff

- **Gleiches WLAN**: `http://<NAS-LAN-IP>:3111`
  (LAN-IP steht in DSM unter Systemsteuerung -> Info-Center, oder
  Netzwerk). Beispiel: `http://192.168.1.20:3111`.
- **Tailscale**: Ist die NAS in deinem Tailnet, dann
  `http://<nas-name>:3111` (MagicDNS) oder `http://<tailscale-ip>:3111`.
  Nichts weiter noetig — der Container lauscht auf allen Interfaces, der
  Host-Port 3111 ist damit auch ueber Tailscale erreichbar.
  Optional per HTTPS ohne Portangabe: `tailscale serve --bg 3111`
  (im Synology-Tailscale-Paket bzw. per SSH).

Auf dem iPhone/iPad einfach die URL im Browser oeffnen, Charakter im
Wizard anlegen, spielen. Der Spielstand liegt auf der NAS (`appdata/`),
also teilen sich alle Geraete denselben Stand.

## Auto-Update

Der Container prueft alle `UPDATE_INTERVAL` Sekunden (Default 120) die
Branch. Neue Commits werden per `git reset --hard` uebernommen; uvicorn
laedt den geaenderten Code automatisch neu. Aendert sich `requirements.txt`,
installiert der Container die Abhaengigkeiten selbst nach.

- Intervall aendern: in `docker-compose.yml` `UPDATE_INTERVAL` setzen.
- Andere Branch (z.B. nach einem Merge nach `main`): `BRANCH` in
  `docker-compose.yml` anpassen und `docker compose up -d` erneut.
- Manuell sofort aktualisieren: `docker compose restart` (zieht beim
  Start den neuesten Stand).

Spielstand und Welt (`appdata/wiki/`, `appdata/data/`) bleiben bei Updates
erhalten — sie sind gitignored und werden von `git reset` nicht angefasst.

## Sicherheit

- Die App hat **keine Anmeldung**. Gib den Port 3111 nur in vertrauten
  Netzen frei (WLAN, Tailscale) — **niemals per Portweiterleitung ins
  offene Internet**.
- Der API-Key liegt server-seitig in `.env` auf der NAS und verlaesst sie
  nicht; Clients bekommen ihn nie zu sehen.

## Aendern des Keys / der Einstellungen

- Key aendern: `.env` bearbeiten, dann `docker compose up -d` (oder im
  Container Manager neu starten).
- Modell, Proben-Gate, Kartenbild usw. stellst du im Spiel ueber das
  Zahnrad **Einstellungen** ein (liegt im Spielstand, bleibt erhalten).

## Zuruecksetzen

- Kompletter Reset (neuer Charakter/Welt): den Ordner `appdata/wiki` und
  `appdata/data` loeschen und Container neu starten — die Welt wird neu
  geseedet.
