# Review-Handoff: Jotunland / Avarr

Fuer einen zweiten Agenten, der dieses Projekt unabhaengig pruefen und
kritisieren soll. Auftrag des Users: **doppelte Absicherung** — nicht
bestaetigen, sondern zerlegen.

---

## 1. Was das Projekt ist

Solo-RPG-Web-App in der Fantasy-Welt Avarr. Ein Spieler, ein Charakter, ein
LLM als Spielleiter. Laeuft in Docker auf einer Synology-NAS, Port 3111.

Stack: FastAPI + SSE-Streaming, Markdown-Wiki mit YAML-Frontmatter als
Weltkanon, JSON-Spielstand pro Charakter. Keine Datenbank. ~5100 Zeilen
Python, 102 Tests, laeuft ohne API-Keys durch.

**Die zentrale These des Projekts:** Ein LLM darf nichts entscheiden, was
Zahlen erzeugt. Das LLM benennt (Skill, Schwierigkeits-Tier, Gegnertyp,
Verletzungsschwere), die Engine rechnet. Jede Abweichung davon hat in
Playtests zu driftenden Spielstaenden gefuehrt.

## 2. Kanonische Quellen — in dieser Reihenfolge lesen

| Datei | Inhalt |
|---|---|
| `CLAUDE.md` | Konventionen und Architektur-Invarianten. Kurz. Zuerst lesen. |
| `README.md` | Architektur, Start, Modultabelle |
| `docs/adr/0001` … `0005` | Die fuenf Grundsatzentscheidungen samt Begruendung |
| `CONTEXT.md` | Glossar der Engine-Begriffe (Englisch) |
| `world/CONTEXT.md` | Glossar der Welt |
| `DM.md` | Regelwerk — kanonische Regelquelle, geht in den Systemprompt |
| `app/config/rulebook.json` | ALLE Regel-Konstanten. Keine zweite Zahl im Python. |

## 3. Architektur in einem Absatz

Ein Spielzug: Spieler-Eingabe → optionaler Classifier (entscheidet
strukturell ueber Probenpflicht, bevor erzaehlt wird) → Agent-Loop mit
Tool-Use → Tools mutieren den Spielstand → Kontext-Builder baut aus acht
Schichten den naechsten Prompt → Validator prueft die Erzaehlung gegen den
Spielstand → bei Verstoss ein Retry mit Korrektur-Anweisung. Wuerfe des
Spielers blockieren den Loop (`request_skill_roll` gibt `BLOCKING` zurueck),
bis der Spieler seinen physischen W20 meldet.

Seit ADR-0005 gibt es zwei Erzaehler auf derselben Engine: die Web-App mit
einem API-Modell, und Claude Code ueber `scripts/dm_cli.py` (laeuft auf dem
Abo statt pro Token). Gemeinsamer Kern: `app/session.py`.

## 4. Module

| Modul | Zeilen | Aufgabe |
|---|---|---|
| `app/main.py` | 849 | Routen, Agent-Loop, Blocking-Queue, SSE |
| `app/session.py` | ~350 | Prompt, History, Undo, Validator, `finalize_turn` — von Server UND CLI genutzt |
| `app/tools.py` | ~910 | 24 DM-Tools inkl. Kampf-State-Machine |
| `app/rules.py` | ~250 | Proben, Ticks, Level, VW, Ruestung, Verletzungen, Sterben |
| `app/gamestate.py` | ~300 | Spielstand, Kalender, Muenz-Mathematik, Charaktererstellung |
| `app/wiki_context.py` | ~250 | Acht-Schichten-Kontext inkl. Namensregister |
| `app/wiki_io.py` / `wiki_index.py` | ~400 | Markdown-IO, kanonische Slugs, Index mit Disk-Cache |
| `app/classifier.py` | ~150 | Vorgeschaltetes Proben-Gate |
| `app/llm_adapter.py` | ~350 | Streaming + Tool-Use fuer Anthropic/Google/OpenRouter |
| `scripts/dm_cli.py` | ~240 | Engine ohne LLM-Adapter (Claude Code als DM) |

## 5. Die fuenf Invarianten (jede hat ein ADR)

1. **Jede unsichere Aktion laeuft ueber `request_skill_roll`** (ADR-0001).
   Das LLM loest nie in Prosa auf. Validator prueft nach.
2. **Spielfolgen an Bestehendem nur ueber `world_flags`** (ADR-0002).
   Wiki = World-Scope (permanent), Gamestate = Character-Scope (Reset bei
   neuem Charakter). `update_wiki_entry` ist Authoring, kein Spielzug.
3. **Den Kampf fuehrt die Engine** (ADR-0003 + Nachtrag). Runden schalten
   automatisch und werden am Zugende bedingungslos geschlossen; der Kampf
   endet ohne kampffaehige Gegner von selbst; Gegnerwerte werden bei
   `start_combat` gebunden; `roll_dice` ist im Kampf gesperrt.
4. **Namensregister als achte Kontext-Schicht** (ADR-0004). Jeder
   kanonische Eigenname im Umkreis mit Rolle, Fraktion und World-Flags.
   Was drinsteht ist gesetzt, was fehlt existiert nicht.
5. **Zwei Erzaehler, eine Engine** (ADR-0005). Eine Regel, die nur in einem
   der beiden Wege gilt, ist ein Bug.

## 6. Was in Playtests tatsaechlich schiefging

Wichtiger Kontext, weil er zeigt, welche Fehlerklassen real sind. Alle drei
Runden endeten mit derselben Erkenntnis: **die gemeldeten "Modellschwaechen"
waren Engine-Bugs.**

**Playtest 1 (Kampf):** Der Erzaehler wich auf `roll_dice` aus, nachdem
`npc_action` ihn zweimal mit einem Phasenfehler abgewiesen hatte — drei
Gegnerangriffe und ein Schadenswurf liefen an der Engine vorbei, "Du hast
1/10 HP" kam nie im Spielstand an. Drei `[KORREKTUR]`-Zuege aenderten nur
Text. Dann erklaerte der Erzaehler den Spielstand zum "Fehler im System" und
ueberschrieb HP. Ausserdem: eine Wirtin tauchte am falschen Ort auf — kein
Halluzinieren, sondern ein fehlender `set_location`-Aufruf, worauf der
Kontext-Builder korrekt die alte Szene lieferte.

**Playtest 2 (Verfolgung + Verhoer):** Der Spieler steckte in "Du hast
bereits in dieser Runde gehandelt" fest — ein lebender Gegner ohne
`npc_action` blockierte den Rundenwechsel dauerhaft. Der Kampf war nie
beendet worden, also verweigerte `start_combat` jeden neuen und alte und
neue Gegner vermischten sich. Und: der kanonische Wachhauptmann Dura Fenk
wurde im Verhoer zum verschuldeten Hafenmeister, weil abwesende NPCs
ueberhaupt nicht im Prompt standen.

**Muster:** Ueberall, wo der Erzaehler eine Zahl liefern durfte, driftete
sie. Ueberall, wo eine Sperre ohne Ausweg stand, umging er sie. Beides ist
mit Datenhaltung zu loesen, nicht mit Ermahnungen.

## 7. Bekannte Schwachstellen — bitte pruefen, nicht wiederholen

Diese sind bewusst offen oder ungeprueft. Sag, ob die Einschaetzung stimmt.

- **Der Rule-Bypass-Validator ist ein Regex** (`COMBAT_OUTCOME_RE` in
  `session.py`). Er faengt eindeutige Treffer-/Tod-Sprache, aber nicht
  Ueberreden, Schleichen oder Stehlen. Er hat schon einmal versagt, weil er
  nur 2. Person kannte und der Erzaehler in der 3. schrieb.
- **`set_location` bleibt erzwingbar nur bei Spieler-Bewegung.** Der
  Classifier sieht nur die Spieler-Nachricht. Bewegt der Erzaehler die
  Szene selbst weiter (Treppe → Tunnel → Ausgang), faellt es durch. Das ist
  die vermutlich groesste verbleibende Luecke.
- **Der Kampf wurde nie live mit der neuen Engine gespielt.** Alle Fixes
  sind durch Tests und Simulation gedeckt, nicht durch eine echte Session.
- **Die CLI hat kein Proben-Gate.** Der Classifier laeuft dort nicht (siehe
  ADR-0005). Ob die Prompt-Disziplin ohne ihn traegt, ist offen.
- **Der Erzaehler in der CLI hat Shell-Zugriff** und koennte den Spielstand
  direkt editieren, statt Tools zu benutzen. Bewusst akzeptiert, aber die
  Absicherung ist dort schwaecher als im Server.
- **Der Weltkanon ist auf Englisch**, die Ausgabe soll Deutsch sein
  (Original-Import). Uebersetzung steht aus.
- **Das Namensregister nennt Namen, die der Charakter nie gehoert hat.** Es
  ist Autoren-Wissen; die Wissens-Trennung haengt am Prompt.
- **Welt unvollstaendig:** 81 Wiki-Eintraege plus 48 aus dem Bergrand-Import.
  Ziel waren 100 Flora-/Fauna-Arten, aktuell rund 36. Sechs Provinzen fehlen.
- **Token-Budget pro Kontext-Schicht nie gemessen.** Nur der Gesamtkontext
  wurde gemessen (~2600 Token in Salzhaven, dem dichtesten Ort).
- **Kein Multi-Device-Lock.** Zwei offene Browser koennten sich gegenseitig
  ueberschreiben. Bewusst zurueckgestellt (Single-User).

## 8. Womit du anfangen solltest

Der User will Kritik, keine Bestaetigung. Vorschlag fuer die Reihenfolge:

1. **Lies die fuenf ADRs.** Frag bei jeder Entscheidung, ob sie das Problem
   loest oder nur verschiebt. ADR-0003 und sein Nachtrag sind der dichteste
   Teil.
2. **Greif die zentrale These an.** Traegt "LLM benennt, Engine rechnet"
   ueber lange Kampagnen? Wo bricht sie? Gibt es Faelle, in denen die Engine
   zu starr ist und das Spiel kaputtmacht statt es zu sichern?
3. **Such nach Sperren ohne Ausweg.** Das ist die nachweislich gefaehrlichste
   Fehlerklasse in diesem Projekt: Jede hat den Erzaehler aus dem System
   getrieben statt ihn zu disziplinieren. `grep -n "FEHLER:" app/tools.py`
   und frag bei jeder Meldung: Was ist der legale Weg, und steht er dabei?
4. **Prueft der Validator, was er zu pruefen vorgibt?** `validate_narration`
   in `app/session.py`. Welche Verstoesse laufen durch?
5. **Ist `app/session.py` wirklich die einzige Regelquelle?** Such nach
   dupliziertem Wissen zwischen `main.py`, `dm_cli.py` und `tools.py`.
6. **Kontext-Builder unter Last.** `wiki_context.build_context` — was
   passiert bei 500 Wiki-Eintraegen, bei 20 gepinnten, bei einer Stadt mit
   80 NPCs? Die Budgets stehen in `rulebook.json`.
7. **Spielstand-Integritaet.** Was passiert bei einem Absturz mitten im Zug?
   Bei einem offenen Wurf? Bei parallelen Schreibvorgaengen?

## 9. Pruefen und Ausfuehren

```bash
python3 -m pytest tests/ -q                      # 102 Tests, ohne Keys lauffaehig
python3 -m scripts.wiki_lint                     # 1 bekannter Error (orphan 'vermummte-gestalt')
python3 -m scripts.seed_world                    # 81 Eintraege, idempotent
python3 app/main.py                              # Port 3111
python3 -m scripts.dm_cli --help                 # der CLI-Weg
```

Der Lint-Error ist vorbestehend und bekannt; er ist kein Regressionssignal.

## 10. Konventionen, die du einhalten solltest

- Antworten an den User: **Deutsch**, knapp, konkrete Empfehlung mit
  Default, keine Emojis.
- Code-Kommentare und eigene Strings: Deutsch, ASCII (ae/oe/ue). Slugs
  strikt `[a-z0-9-]`. Ausnahme: `app/config/skills.json` traegt echte
  Umlaute (kanonische Config, nicht anfassen).
- `wiki/` und `data/` sind gitignored — **niemals committen.** Der
  Auto-Updater im Container macht `git reset --hard`; versionierte
  Laufzeitdaten wuerden den Spielstand des Users zerstoeren. Die
  Autorenwelt liegt versioniert in `world/data/*.json`.
- Regel-Konstanten ausschliesslich aus `app/config/rulebook.json`.
- Neue Index-Felder brauchen ein hochgezaehltes `wiki_index.INDEX_VERSION`,
  sonst liefert der Disk-Cache still die alte Struktur.
- Entwicklung auf Branch `claude/project-review-documentation-0a2bmp`.

## 11. Stand

Letzte Commits:

```
85b03bb Claude Code als zweiter Spielleiter, eine gemeinsame Engine (ADR-0005)
d505e26 Kampf-Deadlock, Kampf-Ende und Namensregister (ADR-0004)
7c1c951 Bestandsschutz: laufende Kaempfe ueberstehen den ADR-0003-Umbau
d9f8494 Kampf: von der Engine gefuehrt statt prompt-diszipliniert (ADR-0003)
```

102 Tests gruen, `wiki_lint` bei 1 bekanntem Error.
