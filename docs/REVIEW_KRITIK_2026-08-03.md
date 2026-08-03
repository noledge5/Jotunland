# Zweite Meinung: Jotunland / Avarr

Unabhaengige Pruefung auf Basis von `docs/REVIEW_HANDOFF.md`, Stand e3d45cb.
Auftrag war Zerlegen, nicht Bestaetigen. Alles unten ist am Code nachgestellt,
nicht aus der Dokumentation abgeschrieben.

Verifiziert vorab: `102 passed` (pytest), Systemprompt 12.841 Zeichen
(~3.700 Token) pro Anfrage.

---

## Kurzfassung

Die Architektur ist gut. Die Trennung "LLM benennt, Engine rechnet" ist die
richtige Antwort auf das Problem, die ADRs sind ehrlicher als das meiste, was
man in Firmencodebasen findet, und die Playtest-Diagnose ("die gemeldeten
Modellschwaechen waren Engine-Bugs") ist die wertvollste Einsicht des Projekts.

Das Problem ist nicht die These. Das Problem ist, dass sie an drei Stellen
nicht angewendet wurde, und zwar an genau den drei Stellen, an denen es teuer
ist:

1. **`start_combat` laesst das LLM rohe Zahlen erfinden** (hp, angriffsbonus,
   schaden). Das ist die letzte Stelle im System, an der der Erzaehler eine
   Zahl liefert — und die Begruendung von ADR-0003 sagt selbst, dass genau das
   driftet. Die Daten fuer die saubere Loesung liegen bereits im Wiki und
   werden ignoriert.
2. **Der Rule-Bypass-Validator ist im Kampf abgeschaltet.** Nicht schwach —
   aus. Der Beispieltext aus Playtest 1 laeuft im Kampf ohne einen einzigen
   Tool-Call sauber durch.
3. **Der Retry wendet Zustandsaenderungen doppelt an** und laesst die
   verworfene Erzaehlung in der History stehen, wo sie der Spieler nach einem
   Reload zu sehen bekommt.

Dazu ein reproduzierter Kampf-Bug, der jeden Kampf gegen mehr als einen
gleichnamigen Gegner falsch aufloest.

Als DM gelesen fehlt dem System ausserdem eine ganze Achse: Es fuehrt HP,
Muenzen und Zeit mit eiserner Disziplin und **NPC-Haltung ueberhaupt nicht** —
obwohl die Autorenwelt `relation_score_default` fuer jeden NPC mitliefert.
Fuer ein Spiel, dessen zweiter Playtest ein Verhoer war, ist das die groessere
Luecke als das fehlende `set_location`.

---

## Teil A — Die zentrale These

### A1. Wo sie traegt

"Das LLM darf nichts entscheiden, was Zahlen erzeugt" ist richtig und
funktioniert dort, wo sie konsequent umgesetzt ist: Difficulty Tiers,
Verletzungsstufen, Ruestungstypen, Waffenschaden ueber den Skill. Das Muster
ist immer dasselbe — das LLM sagt ein Wort, das Rulebook kennt die Zahl —, es
ist testbar, und es haelt. Ueber lange Kampagnen traegt es *besser* als am
Anfang, weil Drift kumulativ ist und diese Konstruktion sie bei null haelt.

Die These ist nicht das Risiko. Ihre Luecken sind es.

### A2. Wo sie bricht: `start_combat`

`app/tools.py:186-197` nimmt `hp`, `angriffsbonus` und `schaden` direkt aus
den LLM-Argumenten. ADR-0003 Punkt 2 nennt das "Gegnerwerte werden bei
`start_combat` gebunden" — das stimmt, aber es bindet nur *innerhalb* eines
Kampfs. Zwischen zwei Begegnungen ist es voellig frei:

- Derselbe Klippenwolf hat heute 12 HP und 1d6, naechste Woche 8 HP und 1d8.
- Der Spieler kann das nicht bemerken (er sieht die Werte nie), also kann er
  es auch nicht als Fehler melden. Diese Drift ist unsichtbar, im Gegensatz
  zu einer falschen Szene oder falschen HP.
- Kampfschwierigkeit haengt damit an der Tagesform des Modells. Das ist genau
  die Klasse Fehler, gegen die das ganze Projekt gebaut ist.

Das Aergerliche daran: **die Daten sind schon da.** `scripts/seed_world.py:88`
schreibt `meta["stats"]` ins Frontmatter jedes NPCs. Dura Fenk traegt
`{"perception": 15, "combat_skill": 14, "persuasion": 11}` — im Wiki, seit dem
Seed. `app/wiki_index.py:56-78` extrahiert das Feld nicht, und `start_combat`
fragt nie danach. Der kanonische Wachhauptmann hat Kampfwerte, und wenn man
gegen ihn kaempft, wuerfelt das LLM neue aus.

Dasselbe fuer das Bestiarium: 48 importierte Eintraege
(`scripts/import_bergrand_bestiary.py`), null Kampfwerte darin.

**Empfehlung (Default):** `start_combat` bekommt einen Parameter `gegnertyp`
(Wiki-Slug) und/oder `stufe` (mook/soldat/veteran/elite). Werte kommen aus dem
Frontmatter des Eintrags, sonst aus einer Tier-Tabelle im `rulebook.json`. Die
LLM-Argumente `hp`/`angriffsbonus`/`schaden` fallen weg — genau wie `schaden`
und `angriffsbonus` bei `npc_action` weggefallen sind. Das ist dieselbe
Bewegung wie ADR-0003 Punkt 5, nur eine Ebene hoeher, und sie kostet zwei
Handgriffe: ein Feld im Index, eine Tabelle im Rulebook.

### A3. Wo die These zu starr ist (DM-Sicht)

Die Frage aus dem Handoff war ausdruecklich, ob die Engine irgendwo das Spiel
kaputtmacht statt es zu sichern. Drei Stellen:

**Waffen sind mechanisch bedeutungslos.** `rules.schaden_fuer_skill` haengt
den Schaden am Skill (`app/rules.py:57`). Dolch und Langschwert sind beide
"Klingenwaffen", beide 1d6. ADR-0003 weiss das ("Waffenqualitaet ist vorerst
Erzaehlung") und unterschaetzt es. In einem Spiel ohne Magie, ohne Goetter und
mit knappem Geld ist die Ausruestung **der** Fortschrittsmotor. Wenn das
erbeutete Schwert des Hauptmanns sich exakt wie der rostige Dolch anfuehlt,
hat Beute keinen Zweck, hat Einkaufen keinen Zweck, und ein ganzes
Spielsystem — Wirtschaft, Handwerk, Feilschen — laeuft ins Leere. Das ist
kein fehlendes Feature, das ist eine Luecke im Belohnungskreislauf.
*Empfehlung:* eine Qualitaetsstufe pro Item (`stumpf/normal/gut/meisterlich`
-> -1/0/+1/+2 auf Schaden), Tabelle im Rulebook, LLM benennt die Stufe. Zwei
Stunden Arbeit, und die halbe Wirtschaft bekommt einen Sinn.

**Der Kampf kennt genau zwei Verben.** Angreifen und Verteidigen. Alles
andere — die Laterne werfen, das Seil kappen, den Tisch umstossen, jemanden
entwaffnen, in Deckung gehen — ist regeltechnisch unsichtbar. `roll_dice` ist
im Kampf gesperrt (richtig!), aber es gibt keinen legalen Ersatz fuer die
kreative Aktion. Der Spieler lernt in drei Kaempfen, dass nur "ich greife an"
zaehlt, und dann ist der Kampf ein Rechenspiel. Fuer ein *Solo*-RPG, in dem
der Kampf ohnehin schon durch den physischen W20 langsam ist, ist das teuer.
*Empfehlung:* `request_skill_roll` mit `ziel` und `wirkung`
(`schaden|behindern|entwaffnen|verschieben`) — die Engine kennt die Wirkung
(z.B. behindern = Gegner verliert naechste Aktion, verschieben = +1 Zone), das
LLM benennt sie nur. Deckt 80 Prozent der kreativen Aktionen ab, ohne dass das
LLM eine Zahl anfasst.

**Das Zonenmodell ist eine Regel ohne Entscheidung.** Distanz 0-3, die Engine
schliesst pro Runde eine Zone auf (`app/tools.py:144-147`). Der Spieler kann
nicht zurueckweichen, nicht Abstand halten, nicht fliehen — er kann nur
warten, bis der Nahkaempfer da ist. Damit ist die Zone kein taktisches
Element, sondern ein Timer. ADR-0003 nennt sie selbst "die einzige
Entscheidung, die eine Regel hinzufuegt statt eine Luecke zu schliessen" — das
ist die richtige Selbsteinschaetzung, und die Konsequenz waere, sie entweder
spielbar zu machen (Rueckzug als Aktion) oder zu streichen.

### A4. Was die These gar nicht abdeckt: soziale Zustaende

Das System fuehrt HP, Muenzen, Zeit, Verletzungen, Position und Inventar mit
eiserner Disziplin — und **NPC-Haltung ueberhaupt nicht**. Es gibt kein Feld
dafuer im Gamestate, kein Tool, keine Regel.

`world/data/salzhaven.json` liefert fuer jeden NPC ein
`relation_score_default` (Dura Fenk: 5). `scripts/seed_world.py` schreibt es
nirgendwohin. Es existiert in der Autorenwelt und verschwindet beim Import.

Damit gilt fuer den gesamten sozialen Teil des Spiels genau das, was fuer den
Kampf vor ADR-0003 galt: Der Erzaehler fuehrt ihn im Kopf, ueber das
Kontextfenster, und wenn das Fenster rollt, ist er weg. Ob der Hafenmeister
dem PC noch traut, steht in keiner Datei — bestenfalls in einer Synopse, die
alle 20 Zuege geschrieben wird und von der zwei im Kontext stehen.

Fuer ein Spiel, in dem es keine Magie gibt und Politik der Kern ist, ist das
die grosse Baustelle. Playtest 2 war ein Verhoer, nicht ein Kampf.

*Empfehlung:* `world_flags` kann das schon — es fehlt nur die Pflicht. Ein
Tool `npc_haltung(slug, richtung: besser|schlechter, grund)`, das eine Stufe
auf einer festen Skala verschiebt (feindselig/misstrauisch/neutral/
gewogen/verbuendet), die Zahl im Rulebook, die Stufe im Register sichtbar. Und
der Classifier meldet ohnehin schon, ob eine soziale Probe lief — daran laesst
sich die Pflicht haengen, genau wie `ortswechsel` an `set_location` haengt.

---

## Teil B — Befunde am Code, nach Schwere

### B1. Gleichnamige Gegner teilen einen Slug — ein Angriff trifft alle

`app/tools.py:184` bildet den Slug aus dem Namen, ohne Eindeutigkeitspruefung.
`resolve_player_roll` (`app/tools.py:371-378`) laeuft ueber **alle** Gegner mit
diesem Slug ohne `break`.

Reproduziert:

```
start_combat: drei Gegner namens "Wache", je 8 HP
Slugs: ['wache', 'wache', 'wache']
ein Treffer, 4 Schaden
-> [('Wache', 4), ('Wache', 4), ('Wache', 4)]
```

Ein Schlag, drei getroffene Gegner. Zusaetzlich handelt bei `npc_action` immer
nur der erste Treffer der Liste (`next(...)`, `app/tools.py:410`), die beiden
anderen gelten jede Runde als saeumig und verlieren ihre Aktion stillschweigend
im Log. Und da alle drei gemeinsam auf 0 fallen, endet der Kampf nach einem
Drittel der Gegner von selbst.

"Drei Stadtwachen", "zwei Schmuggler", "vier Doerfler" — das ist keine
Randbedingung, das ist der Normalfall in einer Low-Fantasy-Welt. Der Kampf
wurde nie live gespielt; das hier faellt beim ersten Mob auf.

*Fix:* Slug bei Kollision durchnummerieren (`wache`, `wache-2`, `wache-3`) und
den Namen fuer den Erzaehler mit Ordnungszahl ausgeben ("Wache (links)"). Im
`start_combat`-Ergebnis den Slug mitliefern, damit `npc_action` und `ziel`
eindeutig adressieren koennen.

### B2. Der Rule-Bypass-Validator ist im Kampf abgeschaltet

`app/session.py:249`:

```python
if (COMBAT_OUTCOME_RE.search(text) and not gs.get("combat")
        and not {"request_skill_roll", "start_combat"} & set(tool_names)):
```

`not gs.get("combat")` heisst: Die Pruefung feuert **nur ausserhalb des
Kampfes**. Reproduziert mit dem Beispieltext aus Playtest 1:

```
Text: "Du triffst den Schmuggler hart an der Schulter, er geht zu Boden ..."
ausserhalb Kampf, keine Tools -> ['... moeglicher Regelverstoss (Rule Bypass)',
                                  'Kein Zeitfortschritt ...']
IM Kampf, derselbe Text, keine Tools -> []
```

Im Kampf ist `_needs_time_tool` ebenfalls aus (`app/session.py:218`), also
bleibt von `validate_narration` dort nur: roll_dice-im-Kampf, Muenzen,
Mechanik-Zahlen, HP-Abgleich. Die Kernpruefung — hat die Erzaehlung einen
Ausgang behauptet, den die Engine nicht kennt — ist genau dort aus, wo sie
historisch versagt hat.

Der Grund ist nachvollziehbar: Der Zug, in dem eine Kampf-Erzaehlung entsteht,
ist der Resume-Zug nach `/api/roll`, und dessen `turn_tools` ist leer — die
Pruefung auf Tool-Namen wuerde in jedem legalen Kampfzug falsch anschlagen.
Die Konsequenz bleibt trotzdem: Der Schutz ist aus.

*Fix:* Im Kampf nicht gegen Tool-Namen pruefen, sondern gegen den Kampfzustand.
Die Engine weiss, was in dieser Runde passiert ist — `c["log"]`, `pc_gehandelt`,
die HP-Deltas der Gegner. Regel: Wenn der Text Treffer-/Tod-Sprache enthaelt,
aber weder ein aufgeloester Wurf noch ein `npc_action` in dieser Runde im Log
steht, ist es ein Bypass. Das ist praeziser als das Regex je sein kann und
kostet keine Fehlalarme.

### B3. Der Retry wendet Tool-Effekte doppelt an

`app/main.py:602-614`. Ablauf bei einem verworfenen Zug:

1. Der Tool-Loop fuehrt alle Tools aus und persistiert (`gsm.save_pc(gs)`,
   `app/main.py:598`).
2. Der Validator findet einen Verstoss.
3. `_agent_stream` ruft sich rekursiv auf; die Rekursion laedt den Spielstand
   frisch von Disk (`app/main.py:522`) — also **mit** den Effekten des
   verworfenen Zugs.
4. Der Erzaehler erzaehlt neu und ruft die Tools erneut auf.

Kampf-Tools sind durch `gehandelt_runde` und `pc_gehandelt` gegen den zweiten
Aufruf geschuetzt. Nicht geschuetzt sind: `adjust_hp`, `pay`, `receive_coins`,
`advance_time`, `rest`, `manage_inventory`, `set_injury`, `status_effect`.

Der Modus `korrektur` ist immer gepuffert und **verlangt** einen
zustandsaendernden Tool-Call (`app/session.py:229`). Eine Korrektur, die
`adjust_hp` aufruft und dabei eine zweite Regel verletzt, wird verworfen und
wiederholt — und zieht die HP zweimal ab. Das Feature, das den Spielstand vor
der Erzaehlung schuetzen soll, beschaedigt ihn.

*Fix:* Vor einem gepufferten Zug einen Snapshot ziehen (`snapshot_turn`
existiert bereits) und beim Verwerfen den Spielstand zuruecksetzen, nicht nur
den Text. Ein verworfener Zug muss vollstaendig verworfen werden, sonst ist
"verworfen" eine Luege gegenueber dem Spielstand.

### B4. Verworfene Erzaehlung und Systemruege bleiben sichtbar

Im selben Pfad wird die abgelehnte Antwort **vor** der Validierung in die
History geschrieben (`app/main.py:562`) und nie entfernt. Dazu kommt die
Korrekturanweisung als `role: user` (`app/main.py:610`).

Folgen:

- `GET /api/history` (`app/main.py:451-455`) filtert nur auf Rolle und
  nichtleeren Inhalt. Nach einem Reload sieht der Spieler **die verworfene
  Erzaehlung und den `[SYSTEM] REGELVERSTOSS ...`-Text im Chat**. Der Zug, den
  er nie sehen sollte, ist einen Refresh entfernt.
- Das Modell hat die verworfene Prosa im naechsten Kontextfenster und haelt
  sie fuer Gesagtes. Es wird sich in spaeteren Zuegen darauf beziehen. Damit
  driften Spieler-Wahrnehmung und Modell-Gedaechtnis auseinander — dieselbe
  Fehlerklasse wie ein driftender Spielstand, nur eine Ebene hoeher.

*Fix:* Beim Verwerfen die betroffenen History-Eintraege (Assistant-Text plus
zugehoerige Tool-Results) abschneiden, bevor die Korrekturanweisung angehaengt
wird. Die Anweisung selbst als `[META]`-Rolle fuehren und aus `/api/history`
ausfiltern.

### B5. Fehlgeschlagene Tool-Calls zaehlen fuer den Validator (nur im Server)

`app/main.py:561` sammelt die Tool-Namen **vor** der Ausfuehrung:

```python
turn_tools += [t["name"] for t in tool_calls]
```

Ob der Handler `FEHLER: ...` zurueckgibt, spielt keine Rolle. Ein
`pay`-Aufruf, der an `Nicht genug Muenzen` scheitert, befriedigt die
Muenz-Pruefung des Validators. Ein `advance_time` mit `minuten: 0` scheitert
und gilt trotzdem als Zeitfortschritt. Auch die Tools, die wegen eines
Blocking-Calls uebersprungen werden (`app/main.py:580`), stehen in der Liste.

Die CLI macht es richtig: `scripts/dm_cli.py:113` merkt sich einen Tool-Namen
nur, wenn das Ergebnis nicht mit `FEHLER` beginnt.

Damit gilt derselbe Validator auf beiden Wegen unterschiedlich streng — nach
ADR-0005 ("Eine Regel, die nur in einem der beiden Wege gilt, ist ein Bug")
ist das per Definition ein Bug, und zwar der einzige gefundene, der es
woertlich ist.

*Fix:* Tool-Namen erst nach erfolgreicher Ausfuehrung sammeln, in `main.py`
wie in `dm_cli.py`.

### B6. Die CLI hat keinen Zwang, nur gute Absichten

Das Handoff nennt zwei Schwaechen der CLI (kein Proben-Gate, Shell-Zugriff).
Die eigentliche ist eine dritte: **`zugende` ist freiwillig.**

`scripts/dm_cli.py:135` ist ein Befehl, den der Erzaehler aufrufen kann. Ruft
er ihn nicht, passiert nichts von dem, was `finalize_turn` garantiert: kein
`close_combat_round`, kein Zeit-Enforcement, kein `turn_count`, keine
History-Persistenz, keine Validierung. Der Snapshot fuer Undo ist ebenfalls ein
eigener Befehl (`schnappschuss`), den niemand erzwingt — im Server passiert er
automatisch vor jedem Zug (`app/main.py:728`).

Anders gesagt: Der eine Erzaehler mit Shell-Zugriff ist auch der, dessen
Zugabschluss auf Selbstdisziplin beruht. Genau die Annahme, die ADR-0003
verworfen hat.

Das ist kein Grund, die CLI zu streichen — sie ist ein guter Weg. Aber
"gemeinsamer Kern" heisst hier: gemeinsame *Funktionen*, nicht gemeinsamer
*Kontrollfluss*. Der Kontrollfluss lebt weiter nur in `main.py`.

*Fix (klein):* `dm_cli call` prueft beim Start, ob seit dem letzten `zugende`
mehr als N Tool-Calls liefen, und weist darauf hin. *Fix (richtig):* ein
Befehl `zug --spieler '...' --text '...'`, der Snapshot, Tools, Validierung
und Abschluss in einem Aufruf kapselt, und `call` nur noch als Unterbefehl
innerhalb eines offenen Zugs erlaubt.

### B7. Kontext-Budgets sind Untergrenzen, keine Obergrenzen

Antwort auf Frage 6 des Handoffs, gerechnet:

```
Summe aller Layer-Budgets: 82.000 Zeichen (~23.400 Token)

 25 NPCs am Ort -> je  400 Zeichen -> 10.000  (Budget 10.000, 1.0x)
 40 NPCs am Ort -> je  400 Zeichen -> 16.000  (Budget 10.000, 1.6x)
 80 NPCs am Ort -> je  400 Zeichen -> 32.000  (Budget 10.000, 3.2x)
 40 gepinnt     -> je  500 Zeichen -> 20.000  (Budget 15.000, 1.3x)
```

`app/wiki_context.py:236` rechnet `per = max(BUDGETS["npcs"] // len(npcs), 400)`.
Der `max` ist als Mindestqualitaet pro Eintrag gedacht und macht das Budget
oberhalb von 25 Eintraegen wirkungslos. Dasselbe Muster bei `pinned` (Boden
500) und `locations` (Boden 500). Es gibt keinen Deckel ueber allen Schichten,
und die NPC-Liste ist die einzige, die weder gekappt (`quests_lore` nimmt
`[:10]`) noch begrenzt ist. Bei 500 Wiki-Eintraegen ist nicht die Anzahl das
Problem, sondern eine dichte Stadt mit vielen Zeitplan-NPCs zur selben Stunde.

Gemessen wurden ~2.600 Token in Salzhaven. Das ist der Stand einer duennen
Welt, nicht die Belastungsgrenze. Der Systemprompt allein ist heute schon
3.700 Token.

*Fix:* Nach dem Zusammenbau global kappen und die Schichten in
Prioritaetsreihenfolge fuellen, bis das Gesamtbudget erschoepft ist — statt
jede Schicht einzeln zu deckeln. Und die NPC-Liste hart begrenzen (die zehn
naechsten, Rest ins Register).

### B8. Das Namensregister macht bei Abschnitt eine falsche Aussage wahr

`entity_register` endet mit `_clip(..., BUDGETS["register"])`
(`app/wiki_context.py:148`), und der Prompt sagt dazu: "Ein Name, der hier
oder oben nicht steht, existiert noch nicht — leg ihn erst mit add_wiki_entry
an."

Sobald das Register laenger wird als 8.000 Zeichen, ist dieser Satz falsch:
Die alphabetisch spaeten Eintraege fallen still weg, und der Erzaehler legt
pflichtgemaess Figuren neu an, die es schon gibt. `add_wiki_entry` faengt das
als `WARNUNG` ab — mit dem Hinweis, bei echter Neuheit erneut mit explizitem
Slug aufzurufen. Der Erzaehler hat keine Moeglichkeit zu wissen, dass die
Figur existiert, also wird er genau das tun. Das Duplikat entsteht durch die
Regel, die es verhindern soll.

*Fix:* Beim Kuerzen sichtbar machen, dass gekuerzt wurde (`[... N weitere
Namen nicht gelistet — vor dem Anlegen add_wiki_entry-Warnung beachten ...]`),
und nach Naehe sortieren statt alphabetisch, damit das Wichtige ueberlebt.

### B9. Kleineres

- **Server und CLI schreiben denselben Spielstand ohne Lock.** Das Handoff
  nennt "zwei Browser" als zurueckgestelltes Risiko; ADR-0005 laedt aber
  ausdruecklich dazu ein, mitten in einer Kampagne zwischen Web und CLI zu
  wechseln. Der Server haelt `gs` ueber einen ganzen Zug im Speicher und
  schreibt am Ende — jeder CLI-Aufruf dazwischen ist verloren. Ein
  Lockfile pro PC waere zwanzig Zeilen.
- **Keine Authentifizierung**, und `HOST=0.0.0.0` ist ein dokumentierter
  Schalter fuers LAN-Spiel. Auf einer Synology, die haeufig portgeforwarded
  ist, sollte das mindestens im DEPLOY.md als "nie ins Internet" stehen.
- **`MAX_CONTINUATIONS = 12`** bricht den Tool-Loop stillschweigend ab
  (`app/main.py:542`). Weder Spieler noch Modell erfahren, dass der Zug
  abgeschnitten wurde.
- **`update_wiki_entry` steht dem LLM als Tool zur Verfuegung**, obwohl
  ADR-0002 sagt, es sei Authoring und kein Spielzug. Die Invariante haengt
  allein am Prompt. Wenn die Regel gilt, gehoert das Tool aus der Registry —
  der Web-Editor braucht es ohnehin nicht ueber diesen Weg.
- **`set_enemy_status` kann einen geflohenen Gegner wieder auf `active`
  setzen** und damit einen von der Engine beendeten Kampf-Zustand
  rekonstruieren. Unwahrscheinlich, aber die Statusliste ist unsortiert und
  ohne Richtungslogik.
- **Das Register injiziert Englisch in einen deutschen Prompt.** Die Rollen
  kommen woertlich aus der Autorenwelt: `Dura Fenk [character] (dura-fenk) —
  Stadtwatch-Hauptmann, Salzhaven | Fraktion: ostimperium_city_watch`. Der
  Fraktionsname ist ein Slug mit Unterstrichen, die Rolle ein
  Deutsch-Englisch-Hybrid mit Tippfehler. Das ist die Uebersetzungs-Baustelle
  an ihrer sichtbarsten Stelle — nicht die Body-Texte, sondern die Zeile, die
  in jedem einzelnen Prompt steht.

---

## Teil C — Sperren ohne Ausweg (Frage 3 des Handoffs)

Nachgezaehlt: 49 `FEHLER:`-Meldungen in `app/tools.py`.

Die **harten** Deadlocks sind weg. `close_combat_round` schliesst die Runde
bedingungslos, der Kampf endet von selbst, ein zweites `start_combat` ist
Verstaerkung. Die drei Sackgassen aus Playtest 2 sind strukturell geschlossen,
nicht nur bepromptet. Das ist saubere Arbeit.

Was bleibt, ist die zweite Haelfte derselben Lektion: **etwa ein Drittel der
Meldungen nennt den legalen Weg nicht.** Das Muster ist inkonsistent — dort,
wo es jemand bewusst gemacht hat, ist es vorbildlich (`roll_dice` im Kampf
nennt alle drei Alternativen; die Reichweiten-Fehler nennen "Fernkampf nutzen
oder warten"), und daneben steht:

| Zeile | Meldung | Was fehlt |
|---|---|---|
| 290, 329 | "Der PC hat in dieser Runde bereits gehandelt." | Dass die Runde am Zugende automatisch schliesst — also: erzaehlen und den Zug beenden |
| 414 | "{Name} hat in Runde N bereits gehandelt." | Dasselbe, aus Gegnersicht |
| 417 | "ist noch N Zone(n) entfernt" | Dass die Engine ihn pro Runde selbst aufschliessen laesst |
| 308, 327 | "Es steht bereits ein Wurf aus." | Dass nur der Spielerwurf ihn aufloest |
| 484, 676 | "existiert nicht" (Flag/Pin) | `add_wiki_entry` zuerst |
| 474 | "minuten muss 1-4320 sein" | Fuer laengere Zeitraeume `rest` |

Das ist billig zu beheben und laut ADR-0003 die nachweislich gefaehrlichste
Fehlerklasse des Projekts. Ich wuerde daraus eine Konvention machen: **jede
`FEHLER:`-Meldung besteht aus zwei Saetzen — was falsch war, und was
stattdessen zu tun ist.** Ein Test, der alle `FEHLER`-Strings gegen eine
Heuristik prueft (enthaelt einen Tool-Namen oder ein Imperativ), haelt das
dauerhaft.

---

## Teil D — Die bekannten Schwachstellen, nachgeprueft

| Einschaetzung im Handoff | Urteil |
|---|---|
| Rule-Bypass-Validator ist ein Regex, faengt Ueberreden/Schleichen nicht | **Zu milde.** Er ist im Kampf komplett aus (B2). Ausserhalb bestaetigt: "Der Torwaechter nickt und laesst dich passieren" mit nur `advance_time` laeuft sauber durch. |
| `set_location` nur bei Spieler-Bewegung erzwingbar; "vermutlich groesste verbleibende Luecke" | Stimmt im Mechanismus, **aber nicht in der Rangfolge.** Diese Luecke ist selbstheilend: Der Kontext liefert die alte Szene, der Spieler sieht sofort Unsinn und korrigiert. Falsche Gegnerwerte (A2) und fehlende NPC-Haltung (A4) sieht niemand — die driften unbemerkt ueber die ganze Kampagne. |
| Kampf nie live mit der neuen Engine gespielt | Stimmt, und B1 ist der Beweis, dass Tests das nicht ersetzen: 17 Kampf-Tests, alle gruen, alle mit eindeutig benannten Gegnern. |
| CLI hat kein Proben-Gate | Stimmt, ist aber das kleinere Problem — siehe B6. |
| CLI-Erzaehler hat Shell-Zugriff, Absicherung schwaecher | Stimmt, aber die Diagnose greift daneben: Nicht die Shell ist das Risiko, sondern der fehlende Zwang zum Zugabschluss. Ein Erzaehler, der `zugende` vergisst, braucht keine Shell, um den Zustand auseinanderlaufen zu lassen. |
| Weltkanon Englisch, Ausgabe Deutsch | Stimmt, und die teuerste Stelle ist das Namensregister, nicht die Body-Texte (B9). |
| Namensregister nennt Namen, die der Charakter nie gehoert hat | Stimmt und ist vermutlich der richtige Kompromiss. Ein Erzaehler, der einen kanonischen Namen zu frueh nennt, ist ein kleinerer Schaden als einer, der ihn neu erfindet. Ich wuerde es so lassen. |
| Token-Budget pro Schicht nie gemessen | Stimmt; gerechnet in B7. Die Budgets sind ausserdem Boeden statt Deckel. |
| Kein Multi-Device-Lock, bewusst zurueckgestellt | Stimmt fuer zwei Browser, **unterschaetzt** den Server-gegen-CLI-Fall, den ADR-0005 gerade erst geschaffen hat (B9). |
| Lint-Error `vermummte-gestalt` vorbestehend | Bestaetigt, kein Regressionssignal. |
| 102 Tests gruen | Bestaetigt (`102 passed`). |

---

## Teil E — Was ich zuerst bauen wuerde

In dieser Reihenfolge, mit Begruendung aus dem Schadenspotential:

1. **B1 (gleichnamige Gegner).** Ein halber Tag. Verfaelscht sonst jeden Kampf
   gegen mehr als einen Gegner desselben Typs — also fast jeden.
2. **B3/B4 (Retry).** Ein Tag. Doppelte Zustandsaenderungen und ein Chat, der
   nach dem Reload verworfene Zuege zeigt, sind schlimmer als der Verstoss, den
   der Retry verhindern soll.
3. **B2 (Validator im Kampf).** Ein Tag, mit der Umstellung auf den
   Kampfzustand als Anker. Ohne das ist der Kampf ungeschuetzt.
4. **A2 (Gegnerwerte aus dem Kanon).** Zwei Tage inklusive Stat-Bloecke fuers
   Bestiarium. Danach ist die zentrale These tatsaechlich vollstaendig
   umgesetzt, und das ist die Aussage, die dieses Projekt tragen soll.
5. **Teil C (Fehlermeldungen mit Ausweg).** Ein halber Tag, plus ein Test.
6. **B5/B6 (die zwei Wege angleichen).** Ein Tag.
7. **A4 (NPC-Haltung).** Zwei bis drei Tage. Das ist die naechste Ausbaustufe,
   nicht ein Bugfix — aber es ist die Achse, auf der dieses Spiel eigentlich
   stattfindet.
8. **A3 (Waffenqualitaet, Kampfmanoever).** Danach, als Spielgestaltung.

Und dann, vor allem anderen: **einen Kampf spielen.** Drei Runden gegen drei
Wachen, mit dem physischen W20. B1 haette sich in der ersten Runde gezeigt.

---

## Zum Schluss

Was hier gut ist, ist selten: ein Projekt, das seine Playtest-Fehler
nachgestellt hat, bevor es sie behoben hat, und das seine Entscheidungen
begruendet aufschreibt, inklusive der Nachteile. Die Nachtraege in ADR-0003
sind das beste Dokument im Repo, weil sie zugeben, dass zwei Entscheidungen
desselben ADR zu schwach umgesetzt waren.

Der Befund dieser zweiten Meinung ist deshalb nicht "die These ist falsch",
sondern: **an drei Stellen ist sie noch gar nicht angewendet, und an einer
vierten (soziale Zustaende) ist noch nicht bemerkt worden, dass sie dort auch
gilt.** Das Muster, das die Kaempfe gerettet hat — das LLM nennt ein Wort, die
Engine kennt die Zahl —, ist die Loesung fuer alle vier.
