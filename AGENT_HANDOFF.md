# Agent Handoff — Jotunland / Avarr Solo RPG

Stand: 2026-07-23. Dieser Handoff ist für einen neuen Agenten der die Arbeit an diesem Projekt fortsetzt.

---

## Was ist das Projekt?

Ein **Solo-RPG-Engine** namens "Avarr" / "Jotunland". Spieler spielt allein gegen einen LLM-Erzähler. Deutsch. Düsteres Low-Fantasy-Setting (Jahr 743 IC, Ostimperium). Stack:

- **Backend**: Python 3 / Flask, SQLite (`rpg.db`)
- **Frontend**: Single-Page HTML/JS/CSS (`templates/index.html`, `static/style.css`)
- **LLM**: Anthropic Claude (direkt oder via OpenRouter). API-Key wird im Browser-localStorage gespeichert, nie am Server.
- **Laufort**: Lokal auf Mac des Users. Port **5001** (Port 5000 ist durch AirPlay blockiert).

Starten: `cd ~/Jotunland/rpg_engine && python3 app.py`  
iPhone-Zugriff: `http://192.168.1.27:5001`

---

## Repo-Struktur

```
Jotunland/
├── CONTEXT.md               ← Glossar aller Spielbegriffe (LESEN!)
├── CONTEXT-MAP.md
├── bug_log.jsonl            ← Player-gemeldete Bugs mit Trace (append-only)
├── rpg_engine/
│   ├── app.py               ← Flask-App, alle API-Endpoints
│   ├── engine.py            ← Spielmechanik: Würfe, Kampf, Skills, HP
│   ├── context_builder.py   ← Baut den LLM-Prompt (5 Layer A–E)
│   ├── llm.py               ← LLM-Calls: classify_action, generate_narration
│   ├── trace.py             ← Turn-Tracer (terminal + /api/debug/trace)
│   ├── db.py                ← Schema-Init, get_db()
│   ├── world_importer.py    ← Importiert world/data/*.json beim Start
│   ├── config/
│   │   ├── rulebook.json    ← Spielregeln: SG-Werte, Tick-Schwellen, starting_gold=500
│   │   └── skills.json      ← Skill-Liste mit Attributen
│   ├── templates/index.html ← Komplette SPA (Landing, Wizard, Game)
│   └── static/style.css
└── world/data/              ← Weltdaten (Salzhaven, Regionen, NSCs)
```

---

## Architektur-Überblick

### Turn-Flow (normal, kein Kampf)

```
POST /api/turn
  ├─ input_mode == 'dm'         → _handle_dm_query()    (kein Classifier, Zeit=0)
  ├─ input_mode == 'korrektur'  → _handle_korrektur()   (kein Classifier, Zeit=0)
  └─ input_mode == 'handeln'/'sprechen'
       → classify_action() [LLM #1]
       → needs_roll? → request_roll() → return {awaiting_roll}
       → no roll?    → build_context() → generate_narration() [LLM #2]
                     → apply_narrator_output() → return narration

POST /api/roll  (Spieler würfelt physisch, gibt Ergebnis ein)
  → resolve_player_roll()
  → in_combat? → resolve_combat_after_roll()  ← NEU, war vorher dead code
  → build_context() → generate_narration() [LLM #2]
  → apply_narrator_output()
```

### Kontext-Layer (context_builder.py)

```
Layer A: Weltkonstanten (world_constants.json)
Layer B: Region (layer_b_text)
Layer C: Zone (layer_c_text)
Layer D: Szene (layer_d_text + world_state_flags)
Layer E: Aktiv-Kontext:
  - Spieler-Stats (HP, Attribute, Skills, Münzen in KUPFER, Inventar, Verletzungen)
  - KAMPFZUSTAND (wenn in_combat=true: alle Kämpfer mit HP/Status)  ← NEU
  - Anwesende NSCs (schedule-basiert)
  - Letzte 4 Turns + Session-Synopsen
  - Mechanisches Ergebnis des aktuellen Turns
```

### Narrator Output Schema (was der LLM zurückgeben muss)

```json
{
  "narration": "...",
  "time_delta_minutes": 5,
  "gold_delta": 0,
  "inventory_changes": [{"op": "add|remove", "item_name": str, "quantity": int}],
  "enter_combat": [{"id": slug, "name": str, "hp_max": int, "stats": {"combat_skill": int}}],
  "generated_locations": [...],
  "generated_npcs": [...],
  "generated_groups": [...],
  "world_state_changes": [...]
}
```

**`enter_combat`** ist NEU: Wenn der Erzähler einen Kampf beginnt, liefert er die Gegner-Liste. `apply_narrator_output()` ruft `start_combat()` auf → befüllt `combat_combatants`, setzt `in_combat=1`.

---

## Kampf-System (WICHTIG — war lange broken, jetzt gefixt)

**Vorher**: `combat_combatants` war nie befüllt, `resolve_combat_after_roll` war dead code. Erzähler hat alles erfunden.

**Jetzt**:
- Kampf-Start: Erzähler gibt `enter_combat` zurück → `start_combat()` in engine.py
- Kampf-Runde: `/api/roll` → `resolve_combat_after_roll()` → alle aktiven Gegner greifen zurück
- Kontext: `=== KAMPFZUSTAND ===` Block im Prompt (HP, Wundzustand je Gegner)
- Erzähler darf Outcomes nicht erfinden — er bekommt exakte Werte im `=== MECHANISCHES ERGEBNIS ===`

Relevante Funktionen in `engine.py`:
- `start_combat(playthrough_id, combatants)` — initialisiert combat_combatants
- `get_combatants(playthrough_id)` — liest für Kontext-Block
- `get_primary_combat_target(playthrough_id, target_hint)` — löst Ziel auf
- `resolve_combat_after_roll(playthrough_id, engine_result, target_npc_id)` — Schaden + Konter

---

## Währung

DB-Spalte `gold` speichert **Kupfer** als Basiseinheit.  
`1 Gold = 100 Kupfer`, `1 Silber = 10 Kupfer`.  
Startkapital: 500 Kupfer (= 5 Gold). Konfiguriert in `rulebook.json: starting_gold: 500`.  
UI zeigt Denomination: `5G`, `3S 4Kpf`, `47Kpf` via `formatCoins()` in index.html.  
LLM bekommt: `"Münzen: X Kupfer (1 Gold = 100 Kupfer, 1 Silber = 10 Kupfer)"`.

---

## Input-Modi (UI)

Vier Buttons über dem Eingabefeld:
| Modus | Icon | Verhalten |
|-------|------|-----------|
| Handeln | ⚔ | Normaler Turn mit Classifier |
| Sprechen | 💬 | Classifier bekommt Social-Hint |
| DM-Frage | 🎲 | Bypass Classifier, LLM antwortet aus Gamestate, Zeit=0 |
| Korrektur | 🔧 | Bypass Classifier, korrigiert letzten Erzähler-Fehler, Zeit=0 |

---

## Bug-Log

User kann Bugs über das Panel im rechten Sidebar einmelden.  
`POST /api/bugs` → schreibt in `Jotunland/bug_log.jsonl` (append-only JSONL).  
Jeder Eintrag enthält: `ts`, `text`, `playthrough_id`, `trace` (letzter LLM/DB-Trace).  
**Als neuer Agent: `bug_log.jsonl` immer zuerst lesen** um laufende Probleme zu kennen.

---

## LLM-Provider

Drei Provider unterstützt, konfiguriert via Settings-Modal im UI (localStorage):
- `anthropic` — direkt, `sk-ant-...`
- `openrouter` — OpenAI-compat, `sk-or-...`, unterstützt Gemini via `google/gemini-...`
- Gemini wird via OpenRouter genutzt, nicht direkt

Modell-Default: `claude-haiku-4-5-20251001` (Classifier), `claude-haiku-4-5-20251001` (Narrator). Im UI wählbar.

---

## Offene Ziele (priorisiert)

Der User hat eine Roadmap festgelegt:

### ✅ Ziel 1 — Input-Typ-Selektor
Fertig. Vier Modi: Handeln, Sprechen, DM-Frage, Korrektur.

### 🔲 Ziel 2 — Narrator Validator
**Was**: Nach jeder Narration validiert eine Prüfschicht ob die Narration dem Gamestate widerspricht.  
**Warum**: Erzähler erfindet Preise, NSC-Wissen, Weltfakten. Das ist der häufigste Bug.  
**Ansatz**: Nach `generate_narration()` einen zweiten lightweight LLM-Call der prüft:
- Stimmen genannte Preise mit gold_delta überein?
- Weiß der NSC etwas das er laut `npc_knows` nicht wissen kann?
- Widerspricht die Narration einem `world_state_flag`?
- Wenn Fehler → Retry oder Flag setzen  
**Alternativ**: Regel-basierte Checks (Preis-Konsistenz, HP-Konsistenz) ohne LLM.

### 🔲 Ziel 3 — Test-Suite
**Was**: Golden Path Tests die den kompletten Spielfluss abdecken.  
**Warum**: Jede Änderung bricht etwas anderes. Kein Vertrauen ohne Tests.  
**Scope**:
- Turn ohne Probe: Input → Narration → State-Update korrekt
- Turn mit Probe: Zwei-Schritt, pending_roll korrekt gesetzt/gelöscht
- Kampf: enter_combat → Runde → HP-Update → combat_ended
- Währung: gold_delta korrekt verbucht
- DM-Frage: Zeit=0, kein State-Update

### 🔲 Ziel 4 — Context Token-Budget
**Was**: Sicherstellen dass der Prompt unter ~1400 Tokens bleibt.  
**Warum**: Zu große Prompts → LLM verliert Fokus auf wichtige Infos (aktueller HP, Gegner-Status).  
**Ansatz**: Token-Zähler pro Layer, älteste Turns kürzen wenn Budget überschritten.

---

## Bekannte Probleme / Restbugs

1. **Kampf noch ungetestet** — `enter_combat` ist neu, noch nie in echtem Spiel verwendet. Erzähler muss das Feld korrekt befüllen, das ist eine Prompt-Engineering-Frage.

2. **NSC-Wissen-Drift** — Erzähler gibt NSCs Wissen das sie nicht haben können (z.B. kennt Spieler-Name bevor Vorstellung). → Ziel 2 soll das fixen.

3. **Classifier wählt falsche Skills** — Manchmal "Athletik" für einen Messerwurf statt "Wurfwaffen". Skill-List im Prompt aber keine Beispiele.

4. **combat_combatants nie gelöscht nach Kampfende** — `in_combat=0` wird gesetzt, aber alte Einträge bleiben in der Tabelle. Beim nächsten Kampf macht `start_combat()` ein DELETE vorher — das ist korrekt, aber Altlasten aus abgebrochenem Kampf könnten Probleme machen.

5. **Keine Flee/Surrender-Logik im Kampf** — Spieler kann "Ich fliehe" sagen, Classifier macht needs_roll=true, aber Engine hat kein spezielles Handling für Flucht. Erzähler muss das erfinden.

---

## DB-Schema (wichtigste Tabellen)

```sql
player          -- name, class, level, hp_current, hp_max, gold (Kupfer!),
                   current_scene_id, in_game_*, in_combat, pending_roll (JSON)
player_attributes -- playthrough_id, attr_name (STR/GES/KON/INT/WEI/CHA), value
player_skills   -- playthrough_id, skill_name, level, ticks
inventory       -- playthrough_id, item_name, quantity, equipped, properties (JSON)
injuries        -- playthrough_id, entity_type, entity_id, injury_name, modifier
combat_combatants -- playthrough_id, entity_id, combat_status, hp_current, hp_max, is_player
npcs            -- id (slug), name, role, description, personality, stats (JSON), tier
npc_schedules   -- npc_id, scene_id, hour_start, hour_end
npc_relations   -- npc_id, playthrough_id, met, relation_score, player_knows, npc_knows
scenes          -- id, zone_id, name, layer_d_text, x, y
zones           -- id, city_area_id, region_id, name, layer_c_text
regions         -- id, name, layer_b_text
turn_log        -- playthrough_id, turn_number, player_input, engine_result (JSON),
                   narration, time_delta_minutes, in_game_timestamp
session_log     -- playthrough_id, summary (Synopsen)
world_state_flags -- playthrough_id, entity_type, entity_id, flag_name, flag_value
quests          -- playthrough_id, title, description, status
```

---

## Git-Branches

- `main` — aktuell, enthält alle Änderungen
- `claude/import-dkills-main-ZS45N` — Feature-Branch, identisch mit main

Beide sind aktuell auf Commit `801a353`.

---

## Wichtige Code-Stellen

| Was | Wo |
|-----|----|
| Turn-Dispatcher | `app.py:take_turn()` ~L380 |
| DM-Handler | `app.py:_handle_dm_query()` ~L310 |
| Korrektur-Handler | `app.py:_handle_korrektur()` ~L343 |
| Bug-Log-Endpoint | `app.py:add_bug()` ~L330 |
| Kampf-Start | `engine.py:start_combat()` ~L605 |
| Kampf-Auflösung | `engine.py:resolve_combat_after_roll()` ~L740 |
| Narrator-Output anwenden | `engine.py:apply_narrator_output()` ~L488 |
| Kontext bauen | `context_builder.py:build_context()` ~L230 |
| KAMPFZUSTAND-Block | `context_builder.py:get_active_context()` ~L120 |
| LLM classify | `llm.py:classify_action()` ~L75 |
| LLM narrate | `llm.py:generate_narration()` ~L128 |
| formatCoins() | `templates/index.html` ~L632 |
| sendTurn() | `templates/index.html` ~L1150 |

---

## Erstes was ein neuer Agent tun soll

1. `cat /home/user/Jotunland/bug_log.jsonl` lesen — aktuelle Player-Bugs
2. `CONTEXT.md` lesen — Glossar aller Spielbegriffe
3. Ziel 2 (Narrator Validator) oder Ziel 3 (Test-Suite) angehen je nach User-Wunsch
