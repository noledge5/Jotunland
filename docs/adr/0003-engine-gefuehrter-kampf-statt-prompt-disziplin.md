# ADR-0003: Engine-gefuehrter Kampf statt Prompt-Disziplin

Status: akzeptiert (2026-08-02, Grill-Session mit User nach dem ersten
Live-Kampf-Playtest)

## Kontext

ADR-0001 setzte darauf, dass der Erzaehler ein hartes "immer Tool X fuer Y"
einhaelt, ueberwacht von einem regelbasierten Validator. Der erste echte
Kampf-Playtest (Gemini Flash, spaeter Haiku 4.5) hat gezeigt, dass das im
Kampf nicht traegt. Aus dem Transkript:

- Drei Gegnerangriffe und der Schaden liefen ueber `roll_dice`, das
  Ergebnis wurde in Prosa verrechnet: "6 Schaden. Du hast 1/10 HP." Kein
  `npc_action`, kein `adjust_hp` — die Punkte kamen nie im Spielstand an.
- Der Erzaehler wich auf `roll_dice` aus, NACHDEM `npc_action` ihn zweimal
  mit "nur in Phase npc_turn" abgewiesen hatte. Die Sperre hat ihn nicht
  diszipliniert, sie hat ihn aus dem System getrieben.
- Angriffsbonus und Schaden wurden pro Angriff neu erfunden (mal +1, mal
  +2), weil der Gegner-Datensatz nur HP kannte.
- Drei `[KORREKTUR]`-Zuege aenderten nur den Text, nie den Zustand. Danach
  meldete die Engine folgerichtig `pc_sterbend`, waehrend die Prosa 10/10
  behauptete — woraufhin der Erzaehler den Spielstand als "Fehler im
  System" bezeichnete und per `adjust_hp` ueberschrieb.
- Mitten im Kampf am Leuchtturm tauchte die Wirtin aus dem Goldenen Schiff
  auf. Kein Halluzinieren: Beim Verfolgen der Schmuggler lief nie
  `set_location`, also lieferte der Context-Builder weiter die alte Szene
  samt anwesender NPCs. Die Engine hat falsche Daten geliefert, der
  Erzaehler hat sie korrekt vorgelesen.

## Entscheidung

Der Kampf wird von der Engine gefuehrt statt vom Prompt erbeten. Elf
Einzelentscheidungen, gemeinsam durchgegrillt:

1. **Runden schaltet die Engine.** `end_turn` entfaellt als Tool. Statt
   einer Phasensperre traegt jeder Handelnde ein Flag; sind PC und alle
   handlungsfaehigen Gegner durch, beginnt die naechste Runde automatisch.
2. **Gegnerwerte werden bei `start_combat` gebunden** (hp, angriffsbonus,
   schaden, distanz, fernkampf). `npc_action` liest nur noch von dort und
   ignoriert entsprechende Argumente.
3. **Aktive Verteidigung** als eigenes Blocking-Tool: Ansage im eigenen
   Zug, ein Wurf, ersetzt Angriff und VW fuer die ganze Runde — auch wenn
   er schlechter ausfaellt.
4. **Ruestung und Verletzungen als Tabellen** im Rulebook. Der Erzaehler
   benennt Typ und Schwere, die Zahl kennt nur die Engine. Ruestung wirkt
   auf Parade positiv, auf Ausweichen und Schleichen negativ;
   `Ruestungsgewoehnung` rechnet das Handicap gegen.
5. **Waffenschaden haengt am Kampf-Skill**, nicht an einem Argument.
   skills.json ist bereits eine Waffentaxonomie.
6. **`roll_dice` ist im Kampf gesperrt** und verweist auf den richtigen Weg.
7. **Ein Retry bei nicht heilbaren Verstoessen.** Im Kampf und bei
   Angriffs-Aktionen wird die Erzaehlung gepuffert, geprueft und
   gegebenenfalls einmal verworfen, bevor der Spieler sie sieht.
8. **`[KORREKTUR]` muss den Zustand anfassen**, sonst greift der Retry.
   Der Spielstand ist ausnahmslos die Wahrheit.
9. **Undo** ueber einen Ringpuffer der letzten zehn Zuege.
10. **`set_location` legt unbekannte Orte mit an**, und der Classifier
    meldet `ortswechsel`, damit ein fehlender Aufruf auffaellt.
11. **Zonenmodell (0-3)** fuer Reichweite, von der Engine fortgeschrieben.

## Begruendung

- Die Fehler waren nicht zufaellig, sondern strukturell: Ueberall, wo der
  Erzaehler eine Zahl liefern durfte, driftete sie; ueberall, wo eine
  Sperre ohne Ausweg stand, hat er sie umgangen. Beides ist mit
  Datenhaltung statt mit Ermahnungen zu loesen.
- Das Muster gab es im Projekt bereits und funktioniert: Bei den
  Difficulty Tiers nennt das LLM einen Namen und die Engine kennt die
  Zahl. Gegnerwerte, Ruestung, Verletzungen und Waffenschaden folgen jetzt
  demselben Prinzip.
- Weniger Pflicht-Aufrufe pro Runde heisst weniger Gelegenheit, etwas
  falsch zu machen: `end_turn` faellt weg, `schaden` faellt weg,
  `angriffsbonus` faellt weg.

## Konsequenzen

- Der Erzaehler kann keinen "besonders wuchtigen Schlag" mit erhoehtem
  Schaden mehr ansagen. Varianz kommt aus dem Wuerfel, Dramatik aus der
  Sprache. Waffenqualitaet ist vorerst Erzaehlung; eine Qualitaetsstufe
  pro Item waere die saubere Erweiterung.
- Gepufferte Kampfzuege erscheinen am Stueck statt live zu streamen. Das
  kostet ein paar Sekunden gefuehlte Reaktionszeit und wurde bewusst auf
  Kampf- und Angriffszuege begrenzt, damit Erkundung und Gespraech
  fluessig bleiben.
- Das Zonenmodell ist die einzige Entscheidung, die eine Regel hinzufuegt
  statt eine Luecke zu schliessen. Es macht Fernkampf planbar, schraenkt
  aber die erzaehlerische Freiheit bei Distanzen ein.
- Undo revertiert bewusst keine Wiki-Eintraege: Sie sind World-Scope und
  ueberdauern den Charakter (ADR-0002). Zurueckgenommene Zuege koennen
  verwaiste Eintraege hinterlassen, die `wiki_lint` meldet.
- Das Proben-Gate bleibt im Kampf abgeschaltet: Dort hat der Erzaehler fuer
  Angriffe ohnehin nur einen Weg, und die Luecke lag auf der Gegnerseite.
