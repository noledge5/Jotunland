# ADR-0006: Der Validator prueft Zustands-Deltas, nicht Prosa

Status: akzeptiert (2026-08-03, nach zwei unabhaengigen Code-Reviews)

## Kontext

Der Validator aus ADR-0001 hat die Erzaehlung rueckwaerts auf
Regelkonformitaet geprueft: Regex ueber den Text, plus ein Abgleich mit den
Namen der Tools, die im Zug aufgerufen wurden. Beide Haelften sind falsch.

**Sprache laesst sich nicht vollstaendig validieren.** "Der Raeuber taumelt
zurueck" kann Schaden sein, Flavor, ein Zustand oder gar nichts. Der
Rule-Bypass-Regex ist bereits einmal daran gescheitert, dass er nur die
zweite Person kannte und der Erzaehler in der dritten schrieb. Jede
Verschaerfung erzeugt Fehlalarme, jede Lockerung neue Luecken.

**Tool-Namen sind kein Beleg.** Der Server sammelte sie, bevor die Tools
liefen (`main.py`, vor dem Fix). Ein an "Nicht genug Muenzen" gescheitertes
`pay` stand damit im Protokoll und befriedigte die Muenz-Regel — die
Erzaehlung durfte Geld den Besitzer wechseln lassen, obwohl die Boerse
unveraendert blieb. Die CLI machte es strenger, also galten zwei
Strengegrade fuer denselben Validator (ADR-0005-Verstoss).

Dazu kam eine dritte Luecke: Die Rule-Bypass-Pruefung war im Kampf
komplett abgeschaltet (`not gs.get("combat")`) — also genau dort, wo sie
im ersten Playtest gebraucht worden waere. Der Grund war technisch
nachvollziehbar (der Resume-Zug nach einem Wurf hat keine Tool-Namen),
aber die Konsequenz war, dass der Schutz an seiner wichtigsten Stelle fehlte.

## Entscheidung

Der Validator unterscheidet ab jetzt zwei Arten von Pruefungen:

**Behauptungs-Pruefungen** — "Geld wechselt den Besitzer", "der Gegner
faellt", "Zeit vergeht", "der Ort wechselt". Sie werden gegen den
**Zustands-Delta** geprueft: `state_fingerprint(gs)` vor dem Zug,
Vergleich danach. Der Fingerprint traegt HP, Muenzen (Gesamt-Kupferwert),
Ortsslug, Uhrzeit in Minuten, Kampfstatus, Laenge des Kampflogs, Summe der
Gegner-HP und Anzahl der Verletzungen.

**Verbots-Pruefungen** — "keine Ticks/XP/VW in der Prosa", "keine HP-Zahl,
die nicht zum Spielstand passt". Sie bleiben Textpruefungen, und das ist
richtig: Sie fragen nicht, ob etwas passiert ist, sondern was im Text
steht. Dort ist der Text die zutreffende Ebene.

Der Fingerprint wird an drei Stellen genommen: im Agent-Loop vor dem Zug,
in `/api/roll` **vor** der Aufloesung des Wurfs (sonst waere der Treffer
schon verrechnet und der Zug saehe bewegungslos aus), und in der CLI beim
ersten Tool eines Zugs, abgelegt in `data/pcs/<slug>/cli_turn.json`.

Fehlt der Fingerprint, faellt die Pruefung auf die alte Namenslogik zurueck
— schwaecher, aber nie strenger. Kein Aufrufer wird dadurch ueberrascht.

## Begruendung

- Die Regel des Projekts lautet: der Spielstand ist die Wahrheit. Dann muss
  auch der Validator ihn befragen und nicht den Text.
- Der Delta kennt den Unterschied zwischen einem Tool, das lief, und einem,
  das etwas bewirkt hat. Das schliesst die Luecke des gescheiterten `pay`
  ohne eine einzige Sonderregel.
- Die Pruefung funktioniert im Kampf genauso wie ausserhalb, weil sie nicht
  mehr von Tool-Namen abhaengt. Die Ausnahme `not gs.get("combat")` entfaellt.
- Der Fingerprint ist neun Zahlen. Er kostet nichts und ist deterministisch.

## Konsequenzen

- Der Delta sieht, DASS gekaempft wurde, nicht WIE HART. Eine Erzaehlung,
  die "du toetest ihn" sagt, waehrend der Gegner bei 9/12 steht, laeuft
  weiterhin durch — der Treffer hat ja stattgefunden. Das ist ein bewusst
  in Kauf genommener Rest: Die Gegner-HP stehen im Zustandspanel, die
  Korrektur liegt beim Erzaehler.
- `state_fingerprint` muss mitwachsen, wenn neue Zustandsklassen dazukommen
  (Ruf, NPC-Haltung, Fraktionsstand). Fehlt ein Feld, ist die zugehoerige
  Behauptung ungedeckt pruefbar — der Validator wird dann still zu lasch.
- Der `korrektur`-Modus prueft jetzt ebenfalls den Delta statt nur die
  Tool-Namen. Eine Korrektur, deren Tool fehlschlug, gilt damit korrekt als
  wirkungslos.
- Zwei weitere Befunde derselben Review-Runde sind mit behoben und gehoeren
  in denselben Zusammenhang, weil sie dieselbe Ursache haben — Zustand und
  Erzaehlung liefen auseinander:
  - Der Retry setzt den verworfenen Zug jetzt zurueck (Zustand und History).
    Vorher lief der zweite Versuch auf den Wirkungen des ersten weiter und
    zog z.B. Schaden doppelt ab, waehrend die verworfene Prosa in der
    History stehenblieb und das Modell sie fuer Gesagtes hielt.
  - Gleichnamige Kampfgegner bekommen eigene Identitaeten ("Wache",
    "Wache 2", "Wache 3"). Der Slug ist im Wiki eindeutig, eine
    Kampfinstanz ist es nicht: Drei Wachen teilten sich den Slug `wache`,
    ein Treffer schaedigte alle drei, und `npc_action` erwischte immer nur
    die erste. Der Kanon-Slug bleibt als `kanon_slug` erhalten.
