# Jotunland — Avarr Solo-RPG

Duesteres Low-Fantasy-Solo-Rollenspiel als Web-App: ein Spieler, ein
LLM als Spielleiter, die Welt **Avarr** (Ostimperium, Jahr 743 IC,
Essenz statt Magie). Das LLM erzaehlt — aber es rechnet nichts selbst:
jede Spielmechanik laeuft ueber typisierte Engine-Tools gegen einen
persistenten Spielstand auf Disk.

Begriffe und Regeln: **CONTEXT.md** (Engine-Glossar),
**world/CONTEXT.md** (Welt-Glossar), **DM.md** (Regelwerk, wird in den
DM-Prompt geladen), **docs/adr/** (Architektur-Entscheidungen).

## Kernprinzipien

1. **Das LLM erzaehlt, der Code rechnet.** Jede Probe laeuft ueber
   `request_skill_roll` (Skill + Difficulty Tier); der Spieler wuerfelt
   seinen W20 physisch, die Engine rechnet Ergebnis, Crits und Ticks.
   Ein regelbasierter Validator prueft jede Erzaehlung (ADR-0001).
2. **Die Welt ist ein Wiki, kein Prompt.** Markdown mit Frontmatter
   unter `wiki/world/`, Meter-Koordinaten (3000x3000 km), Hierarchie
   realm -> region -> city -> zone -> scene. Zwei Schichten: das Wiki
   ist permanenter Weltkanon; Spielfolgen sind Flags pro Durchlauf
   (ADR-0002).
3. **Zeit ist real.** In-Game-Uhr, jede Aktion kostet Minuten, NPCs
   folgen Zeitplaenen — wer keine Schicht hat, ist nicht da.

## Regelwerk (Kurzfassung)

W20 + Attributsmod + Skill-Bonus gegen SG 8-20 (7 Tiers), Nat 20/1
kritisch. 6 Attribute (STR/GES/KON/INT/WEI/CHA), 32 Skills (0-100) mit
Tick-Steigerung (Learning-by-Doing), 10 Skill-Ups = 1 Level. VW statt
Verteidigungswurf, Sterben bei 0 HP (Blutung, tot bei -10, endgueltig).
1 gm = 10 sm = 100 kp, Start 500 kp. Details: DM.md.

## Start

```bash
pip install -r requirements.txt
cp .env.example .env        # mindestens einen API-Key eintragen
python3 -m scripts.seed_world
env $(cat .env | xargs) python3 app/main.py    # Port 3111
```

Charaktererstellung im Wizard: 78 Attributpunkte, 80 Skillpunkte,
Klasse als narratives Label mit Startausruestung.

## Ansichten & Eingabe-Modi

- **Chat** mit vier Modi: Handeln, Sprechen, DM-Frage (Zeit=0),
  Korrektur (Zeit=0). Wuerfel-Dialog bei jeder Probe. Toast-Banner bei
  jeder Aenderung (Muenzen, LP, Inventar, Ticks, Skill-Ups, Ortswechsel);
  die Sidebar aktualisiert sich live nach jedem Tool.
- **Bild-Workflow (ComfyUI/Krea)**: Button "Bild-Prompt" erzeugt einen
  Natural-Language-Prompt (Englisch) fuer die aktuelle Szene oder einen
  Ort im Editor — zum Kopieren in ComfyUI/Krea. Das erzeugte Bild
  importierst du ueber "Bild importieren" (Upload) und es haengt am
  Wiki-Eintrag. Ein optionales Kartenbild (Einstellungen) legt sich als
  Hintergrund massstabsgetreu unter die Orte (Weltflaeche 3000x3000 km).
- **Welt** — ein Editor, zwei Layouts:
  - **Netz**: alle Eintraege als Link-Graph (Force-Layout, Filter, Suche).
  - **Karte**: koordinatengebundene Eintraege an ihrer Meter-Position,
    zoombar von Weltkarte bis Stadt. **Klick auf leere Stelle legt einen
    neuen Eintrag an** (Ort, Zone, Szene, Charakter, Lore, Flora, Fauna),
    Ziehen verschiebt Koordinaten, Klick auf Knoten oeffnet den Editor —
    alles schreibt direkt in die Markdown-Dateien.

## Module

| Modul | Aufgabe |
|---|---|
| `app/main.py` | Routen, Agent-Loop, Blocking-Wuerfe, Validator, History-Deckel |
| `app/rules.py` | Regel-Engine: Proben, Ticks, Level, VW, Sterben (Config: `app/config/`) |
| `app/gamestate.py` | Spielstand, Kalender, Coin-Math, Charaktererstellung |
| `app/tools.py` | 22 DM-Tools inkl. Kampf-State-Machine, Flags, Zeit |
| `app/llm_adapter.py` | Streaming + Tool-Use fuer Anthropic/Google/OpenRouter |
| `app/wiki_context.py` | Layer-Kontext mit Flag-Overlay und Zeitplan-Anwesenheit |
| `app/wiki_io.py` / `wiki_index.py` | Markdown-IO, kanonische Slugs, Index, Duplikat-Erkennung |
| `scripts/seed_world.py` | Avarr-Import aus `world/data/*.json` (81 Eintraege, idempotent) |
| `scripts/generate_wiki.py` | 4-Stufen-City-Generator (Resume, Fallback, --dry-run) |
| `scripts/wiki_lint.py` | 6 Konsistenz-Checks, Exit 1 bei Errors |

## Tests

```bash
python3 -m pytest tests/ -q     # 52 Tests, laufen ohne API-Keys
python3 -m scripts.wiki_lint
```
