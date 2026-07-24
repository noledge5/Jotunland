# Jotunland / Avarr — Projektnotizen

Solo-RPG-Web-App in der Welt Avarr. Architektur und Start: README.md.
Glossare: CONTEXT.md (Engine), world/CONTEXT.md (Welt). Regelwerk: DM.md.
Entscheidungen: docs/adr/.

## Konventionen

- Antworten an den User: Deutsch, knapp, konkrete Empfehlung mit Default,
  keine Emojis.
- Code-Kommentare und eigene Strings: Deutsch, ASCII (ae/oe/ue) — Slugs
  strikt `[a-z0-9-]`. Ausnahme: Skill-Namen aus app/config/skills.json
  tragen echte Umlaute (kanonische Config, nicht anfassen).
- Keine Dateien ausserhalb des Projekts ohne Rueckfrage.
- Laufzeitdaten (`wiki/`, `data/`) sind gitignored — nie committen.
  Autorenwelt liegt in `world/data/*.json` (versioniert), der Seed
  importiert sie.

## Architektur-Invarianten

- **Jede Probe ueber request_skill_roll** (ADR-0001) — das LLM loest
  nie unsichere Aktionen in Prosa; Validator prueft nach. Ein
  vorgeschalteter Classifier (app/classifier.py, settings.use_classifier)
  entscheidet strukturell ueber Probenpflicht und setzt die Probe an,
  bevor erzaehlt wird. Mechanik-Zahlen (Ticks/XP/HP/VW/Boerse) gehoeren
  nie in die Prosa — nur ins Zustandspanel.
- **Spielfolgen an Bestehendem nur als world_flags** (ADR-0002) —
  update_wiki_entry ist Authoring, nicht Spielzug. Wiki = World-Scope
  (permanent), Gamestate = Character-Scope (Reset bei neuem PC).
- **Settings immer frisch von Disk lesen** (`gamestate.load_settings`).
- **Muenzen nur ueber Gesamt-Kupferwert** (`pay_copper`/`add_coins`).
- **Gemini-Tool-Results als Objekt** (`build_google_payload` parst JSON).
- **Slugs kanonisch** ueber `canonical_slug()` mit Stadt-Parameter.
- **history.json ist gedeckelt** (Archiv-Rotation), Rolling Window
  schneidet nie ein Tool-Result von seinem Call ab.
- Regel-Konstanten NUR aus app/config/rulebook.json (Engine liest sie
  via app/rules.py; das LLM bekommt Tier-NAMEN, nie rohe SGs).

## Testen & Pruefen

```bash
python3 -m pytest tests/ -q                          # ohne Keys lauffaehig
python3 -m scripts.wiki_lint                          # Exit 1 bei Errors
python3 -m scripts.generate_wiki --city salzhaven --dry-run
```

Nach Aenderungen an tools.py, rules.py oder llm_adapter.py: Kampf- und
Proben-Zyklus in tests/test_combat.py gegenlesen.

## Bekannter Stand (2026-07-23)

- Avarr ist Kanon (Grill-Session): Welt + Regeln aus dem Original-Stand
  (Branch claude/import-dkills-main-ZS45N, Flask/SQLite) in die
  FastAPI/Markdown-Architektur uebernommen. Die zwischenzeitliche
  NovaTerrum-Eigenwelt wurde verworfen.
- Seed importiert 81 Eintraege: 7 Realms, 9 Ostimperium-Provinzen,
  Salzhaven voll (5 Zonen, 14 Szenen, 8 NPCs mit Zeitplaenen), Vareth.
  Lint 0/0. Verdichtung weiterer Provinzen: world/GENERATION_GUIDE.md
  + scripts/generate_wiki.py.
- Frontend: Chat (4 Eingabe-Modi), Welt-Editor mit Netz- und
  Karten-Layout (Klick-to-Add mit Meter-Koordinaten), Charakter-Wizard.
- Offen laut altem Handoff: Kampf nie live gespielt (Tools getestet,
  Prompt-Disziplin unbewiesen), Token-Budget-Messung pro Layer (Ziel 4),
  Session-Synopsen. bug_log-Panel des Originals nicht uebernommen.
- Google Free Tier per-Modell rate-limited — OpenRouter ist der
  zuverlaessige Weg. Lokal: `python3 app/main.py`, Port 3111.
