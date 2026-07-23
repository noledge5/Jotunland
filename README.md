# NovaTerrum

Grimdark Solo-Pen-and-Paper-RPG als Web-App fuer einen einzelnen Spieler.
Ein LLM ist der Spielleiter (DM) — aber es erzaehlt nicht frei ins Blaue:
jede Spielmechanik laeuft ueber Tools gegen einen echten, persistenten
Spielzustand auf Disk.

## Kernidee

Drei Prinzipien tragen das Projekt:

1. **Das LLM erzaehlt, der Code rechnet.** Muenzen, HP, XP, Wuerfe,
   Kampfrunden — alles geht durch typisierte Tools mit Validierung.
   Das LLM darf keine Zahl behaupten, die nicht durch ein Tool gelaufen
   ist. Dadurch bleibt der Spielstand konsistent, egal wie das Modell
   halluziniert.
2. **Die Welt ist ein Wiki, kein Prompt.** Jeder Ort, NPC, jede Fraktion
   ist eine Markdown-Datei mit Frontmatter unter `wiki/world/`. Ein
   6-Schichten-Context-Builder stellt pro Zug genau das Weltwissen
   zusammen, das die Szene braucht (Canon, Spielstand, gepinnte
   Eintraege, Ort, anwesende NPCs, Quest-Wissen, letzte Ereignisse).
   Die Welt waechst im Spiel — neue Eintraege entstehen per Tool und
   werden sofort Kanon.
3. **Der Spieler wuerfelt selbst.** Angriffswuerfe blockieren den
   Agent-Loop: das LLM fordert einen d20 an, die UI zeigt den
   Wuerfel-Dialog, erst der echte Wurf setzt die Erzaehlung fort.
   Alles andere wuerfelt der Server.

## Stack

- Backend: **FastAPI** (`app/main.py`), Python 3.11, keine Datenbank —
  Markdown-Wiki + per-PC `gamestate.json` auf Disk, atomare Writes
- Frontend: single-file `app/static/index.html`, inline CSS/JS, kein Framework
- LLM: unified Adapter (`app/llm_adapter.py`) mit Streaming + Tool-Use
  ueber drei Provider: **Anthropic**, **Google** (REST), **OpenRouter**
  (OpenAI-kompatible SSE). Routing ueber Modell-ID-Praefix
  (`or/...`, `gemini-...`, `claude-...`)
- Waehrung: 1 gm = 10 sm = 100 kp, Wechselgeld macht das Backend

## Start

```bash
pip install -r requirements.txt
cp .env.example .env        # mindestens einen API-Key eintragen
python3 -m scripts.seed_world
env $(cat .env | xargs) python3 app/main.py    # Port 3111
```

Dann http://127.0.0.1:3111 oeffnen, PC anlegen, losspielen.
`[META] ...` im Chat gibt Regie-Anweisungen an den DM ohne Erzaehltext.

## Module

| Modul | Aufgabe |
|---|---|
| `app/main.py` | Routen, Agent-Loop mit Continuations, Blocking-Queue fuer Spielerwuerfe, History mit Archiv-Deckel, Session-Protokoll, Wiki-Lint-Fallback |
| `app/gamestate.py` | Spielstand-Schema, atomare Writes, XP/Level, HP-Status, Coin-Math |
| `app/tools.py` | Tool-Registry (19 DM-Tools) + Kampf-State-Machine |
| `app/llm_adapter.py` | Provider-Routing, `stream_with_tools`, Payload-Builder je Provider |
| `app/wiki_context.py` | 6-Schichten-Context-Builder mit Zeichen-Budgets |
| `app/wiki_io.py` | Frontmatter-Markdown-IO, kanonische Slugs (Pinpoint-Regel), Journal |
| `app/wiki_index.py` | Slug-Index-Cache, produced_by/imported_by, Duplikat-Erkennung |
| `scripts/seed_world.py` | Idempotenter Welt-Seed: Canon, 5 Regionen, 40 Subregionen, 11 Staedte, 5 Factions, 4 Lore |
| `scripts/generate_wiki.py` | 4-Stufen-City-Pass (geography/people/politics/institutions), Resume, Provider-Fallback, `--dry-run` |
| `scripts/wiki_lint.py` | dead-link / orphan / bad-slug / duplicate / status-conflict / economy-gap |

## Kampf-Ablauf

```
start_combat -> pc_turn --request_attack_roll--> awaiting_roll
                  ^                                  |
                  |                        (Spieler wuerfelt d20)
                  +------- Treffer/Fehlschlag <------+
pc_turn --end_turn--> npc_turn --npc_action*--> end_turn -> Runde+1
... -> end_combat (XP-Vergabe)
```

## Tests

```bash
python3 -m pytest tests/ -q     # 44 Tests, laufen ohne API-Keys
python3 -m scripts.wiki_lint    # Welt-Konsistenz
```
