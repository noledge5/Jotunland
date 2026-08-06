# Roadmap und offene Entscheidungen

Stand 2026-08-05. Diese Datei ist der Gedaechtnisspeicher zwischen Sitzungen:
was gebaut ist, was ansteht, und warum. Sie wird fortgeschrieben, nicht neu
geschrieben — die Begruendungen sind wertvoller als der Status.

## 1. Wo das Projekt steht

Gebaut und gepusht (Branch `claude/project-review-documentation-0a2bmp`,
den auch der NAS-Container trackt und alle 120 s zieht):

- **ADR-0003 + Nachtrag** — Kampf fuehrt die Engine. Runden schliessen am
  Zugende bedingungslos, der Kampf endet ohne kampffaehige Gegner von
  selbst, ein zweites `start_combat` ist Verstaerkung.
- **ADR-0004** — Namensregister als achte Kontext-Schicht.
- **ADR-0005** — Zwei Erzaehler, eine Engine: Web-App (API-Modell) und
  Claude Code (`scripts/dm_cli.py` + `.claude/skills/dm/`) teilen
  `app/session.py`. Claude Code laeuft aufs Pro-Abo statt pro Token.
- **ADR-0006** — Validator prueft Zustands-Deltas statt Prosa.
- **Kampfgegner-Identitaeten** — gleichnamige werden durchnummeriert.
- **Bestiarium-Schema** — `gattung`/`frisst`/`biom`/`rang`/`essenz`, dazu
  drei Lint-Checks (taxonomie, nahrungsnetz, trophie).
- **Obsidian-Rundlauf** — `scripts/obsidian_sync.py` export/import.
- **Index-Frische** — externe Bearbeitung wird erkannt.

116 Tests, `wiki_lint` 0/0.

## 2. Obsidian — Stand der Entscheidung

**Der Vault-Anker ist immer `slug` im Frontmatter, nie der Dateiname.**
Obsidian schreibt beim Umbenennen alle Links mit um; ohne eine Karte der
Vault-Dateinamen zeigt danach jeder Verweis ins Leere. Das war ein echter
Bug beim Bauen, ist behoben und durch Tests gedeckt.

Zwei Betriebsarten, bewusst getrennt:

- **Am Rechner: direkt.** Obsidian auf `wiki/world/` zeigen lassen. Kein
  Export, kein Import, keine Drift — Vault und Engine-Wiki sind dieselben
  Dateien. Nachteil: Slugs als Dateinamen, haesslicherer Graph.
- **Unterwegs: projiziert.** `obsidian_sync export` erzeugt einen Vault mit
  sprechenden Titeln und Ordnern; `import` holt Aenderungen zurueck. Nur
  hier braucht es Sync, und nur hier drohen Konfliktkopien.

Der Spielstand wird exportiert, aber **nie importiert**. Ein Vault, aus dem
man HP zurueckschreiben koennte, waere genau die Tuer, die ADR-0001 zuhaelt.

## 3. MCP — die Entscheidung, die noch aussteht

Ein **Obsidian**-MCP-Server waere der falsche: Er schriebe Markdown an
`add_wiki_entry` vorbei und damit an Slug-Kanonisierung, Duplikat-Erkennung
und Koordinaten-Vergabe. Zweiter Schreiber ohne Regelkenntnis — die Klasse
Problem, gegen die ADR-0002 gebaut ist.

Der richtige waere **die eigene Engine als MCP-Server**. Dann ruft claude.ai
`add_wiki_entry`, `set_location`, `request_skill_roll` auf — mit Validator,
Kampf-Maschine und Wiki-Garantien. Das ist der Weg zu "im Chat spielen, mit
Karte im zweiten Fenster, auf dem Abo". Groesster offener Brocken.

Fuer Claude Code braucht es kein MCP: dort ist der Dateizugriff direkt da.
Das gilt aber nur, wenn Claude Code **auf dem Rechner mit den Dateien**
laeuft — aus einer Cloud-Session ist der Vault des Users unerreichbar.

## 4. Reihenfolge

1. ~~Index-Frische~~ (fertig)
2. ~~Obsidian-Rundlauf~~ (fertig)
3. **Bestiarium** — Fundament liegt (13 Biome, Essenz-Oekologie als Lore in
   `world/data/bestiarium.json`). Offen: die Arten selbst, biomweise, plus
   Migration der 36 Altbestaende aus `scripts/import_bergrand_bestiary.py`
   (haben weder Gattung noch Nahrungsnetz). Ziel: 100+ Arten, Pyramide
   richtig herum — heute 28 Tiere auf 8 Pflanzen.
4. **Frische-Lint** — aendert sich eine Gattung, melden abgeleitete Arten
   sich als pruefbeduerftig. Der Ledger-Gedanke auf Ableitung statt Quellen.
5. **Retrieval** — Suche und Tags im Kontext-Builder. Ab ~500 Eintraegen
   reichen Regeln (Location-Stack, Zeitplan, Register) nicht mehr.
6. **Figurenwissen als Etikett** — Registerzeilen bekommen `bekannt` /
   `gehoert` / `unbekannt`. Der Erzaehler sieht alles (Konsistenz), der PC
   nutzt nur, was er kennt. Character-Scope ueber World-Scope wie Flags.
7. **Spielbrett** — Web-App pollt im Leerlauf, damit Karte und Zustand live
   sind, waehrend Claude Code erzaehlt. Kleinste Loesung fuer "Abo + Karte".
8. **Engine als MCP** (siehe 3).

## 5. Offen aus den beiden Code-Reviews

Bereits behoben: Retry-Rollback, Gegner-Identitaeten, Delta-Validator,
`turn_tools` erst nach Erfolg, CLI-Undo-Punkt automatisch.

Noch offen, nach Schwere:

- **Gegnerwerte aus dem Kanon.** `start_combat` nimmt hp/angriffsbonus/
  schaden weiterhin vom LLM. Zwischen zwei Begegnungen driften sie frei —
  unsichtbar, weil der Spieler die Werte nie sieht. Die Daten liegen schon
  da: der Seed schreibt `stats` ins Frontmatter (Dura Fenk hat
  `combat_skill: 14`), der Index las es bis zum Bestiarium-Schema nicht aus.
  Das Bestiarium braucht dieselben Felder — beides zusammen erledigen.
- **NPC-Haltung fehlt ganz.** `world/data/salzhaven.json` liefert pro NPC
  ein `relation_score_default` (Dura Fenk: 5), der Seed verwirft es. Damit
  gilt fuer den sozialen Teil, was fuer den Kampf vor ADR-0003 galt: der
  Erzaehler fuehrt ihn im Kopf, und mit dem Kontextfenster ist er weg.
- **Kontext-Budgets sind Untergrenzen.** `per = max(BUDGET // n, 400)` —
  bei 80 NPCs also 32 000 statt 10 000 Zeichen. Global kappen und nach
  Prioritaet fuellen.
- **Namensregister wird still gekuerzt** (bei 8000 Zeichen). Das macht den
  Prompt-Satz "was hier nicht steht, existiert nicht" zur Falschaussage und
  erzeugt genau die Duplikate, die die Regel verhindern soll.
- **Fehlermeldungen ohne Ausweg.** Rund ein Drittel der `FEHLER:`-Strings in
  `tools.py` nennt den legalen Weg nicht. Vorbild ist die roll_dice-Sperre,
  die alle drei Alternativen aufzaehlt. Konvention plus Test ueber alle Strings.
- **Waffen sind mechanisch bedeutungslos** — Schaden haengt am Skill, Dolch
  und Langschwert beide 1d6. In einer Welt ohne Magie ist Ausruestung der
  Fortschrittsmotor; eine Qualitaetsstufe pro Item waere die Reparatur.
- **Kampf kennt zwei Verben** (angreifen, verteidigen). Entwaffnen, in
  Deckung gehen, Tisch umstossen sind regeltechnisch unsichtbar.
- **Event-Log fehlt.** World-Flags sind Zustand ohne Kausalitaet: sie sagen,
  dass die Bruecke zerstoert ist, nicht wer sie zerstoert hat. Beide
  Reviewer nannten das unabhaengig. Journal existiert, ist aber Prosa.
- **Weltkanon ist auf Englisch**, die Ausgabe soll Deutsch sein.
- **Kampf nie live gespielt.** Alle Fixes sind durch Tests und Simulation
  gedeckt, nicht durch eine echte Sitzung. Der Gegner-Identitaets-Bug haette
  sich in Runde eins gezeigt; 17 gruene Kampf-Tests fanden ihn nicht.

## 6. Wie der User spielt

- **Web-App auf der NAS** — laeuft, aktualisiert sich selbst, kostet
  OpenRouter-Guthaben.
- **Claude Code als DM** — `/dm` im Repo-Ordner, laeuft aufs Pro-Abo.
  Voraussetzung: `claude` muss im PATH sein (war zuletzt der Stolperstein).
- **Cloud-Session** (wie diese) — spielbar, aber der Spielstand lebt nur im
  Container. Vor Sitzungsende exportieren, sonst ist er weg.

Marek auf der NAS ist unberuehrt. Der Charakter in einer Cloud-Session ist
ein eigener Durchlauf.
