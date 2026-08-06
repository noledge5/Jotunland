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
- **Kampf fuehrt die Engine** (ADR-0003) — Runden schalten automatisch
  (kein end_turn) und werden am Zugende bedingungslos geschlossen, der
  Kampf endet ohne kampffaehige Gegner von selbst, ein zweites
  start_combat ist Verstaerkung. Gegnerwerte werden bei start_combat
  gebunden, Waffenschaden haengt am Skill, roll_dice ist im Kampf
  gesperrt. Das LLM benennt Typen und Stufen, nie Zahlen.
- **Namensregister als achte Kontext-Schicht** (ADR-0004) — jeder
  kanonische Eigenname im Umkreis mit Rolle, Fraktion und World-Flags,
  eine Zeile pro Eintrag. Was drinsteht, ist gesetzt; was fehlt, muss
  erst ueber add_wiki_entry entstehen. Neue Index-Felder brauchen ein
  hochgezaehltes wiki_index.INDEX_VERSION, sonst liefert der Disk-Cache
  still die alte Struktur.
- **Zwei Erzaehler, eine Engine** (ADR-0005) — Web-App (API-Modell) und
  Claude Code (`scripts/dm_cli.py`, Skill in `.claude/skills/dm/`) teilen
  sich `app/session.py`: Prompt, History, Undo, Validator, Zugabschluss.
  Eine Regel, die nur in einem der beiden Wege gilt, ist ein Bug.
- **Validator prueft Deltas, nicht Prosa** (ADR-0006) — Behauptungen
  (Geld, Treffer, Zeit, Ortswechsel) gegen `state_fingerprint` vor/nach dem
  Zug; nur Verbote (Mechanik-Zahlen im Text) bleiben Textpruefungen. Neue
  Zustandsklassen gehoeren in den Fingerprint, sonst wird er still zu lasch.
- **Kampfgegner haben Instanz-Identitaeten** — gleichnamige werden
  durchnummeriert ("Wache 2"), `kanon_slug` haelt den Wiki-Bezug. Ein
  Wiki-Slug ist eindeutig, eine Kampfinstanz nicht.
- **Bestiarium ist pruefbar, nicht behauptet** — `parent` bleibt Geografie,
  `gattung` traegt die Abstammung; `frisst`/`biom`/`rang` spannen das
  Nahrungsnetz. wiki_lint prueft Taxonomie, Nahrungsnetz und Trophie.
- **Obsidian-Vault ueber `scripts/obsidian_sync.py`** — Anker der
  Rueckrichtung ist immer `slug` im Frontmatter, nie der Dateiname
  (Obsidian benennt Links beim Umbenennen mit um). Der Spielstand wird
  exportiert, aber nie importiert: er gehoert der Engine (ADR-0001).
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

## Bekannter Stand (2026-08-05)

**Offene Punkte, Reihenfolge und Begruendungen stehen in docs/ROADMAP.md —
dort zuerst nachsehen.** Kurzfassung:

- Avarr ist Kanon. Seed importiert 81 Eintraege (7 Realms, 9 Provinzen,
  Salzhaven voll, Vareth); dazu 48 aus scripts/import_bergrand_bestiary.py.
- Zwei Spielwege: Web-App mit API-Modell, und Claude Code ueber
  `scripts/dm_cli.py` auf dem Abo (`/dm`-Skill).
- Obsidian: am Rechner direkt auf `wiki/world/`, unterwegs ueber
  `scripts/obsidian_sync.py`. Spielstand wird nie zurueckimportiert.
- Bestiarium: Schema und Lint-Checks stehen, die Arten selbst fehlen noch.
  Ziel 100+, biologisch stimmig (Gattungen, Nahrungsnetz, Trophie).
- Groesste offene Luecken: Gegnerwerte kommen noch vom LLM statt aus dem
  Kanon, NPC-Haltung fehlt ganz, Kampf nie live gespielt.
