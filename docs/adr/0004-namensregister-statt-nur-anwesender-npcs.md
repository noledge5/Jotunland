# ADR-0004: Namensregister im Kontext statt nur anwesender NPCs

Status: akzeptiert (2026-08-03, nach dem zweiten Kampf-Playtest)

## Kontext

Der Context-Builder lieferte NPCs ausschliesslich ueber Anwesenheit: den
Zeitplan-Treffer am aktuellen Ort plus manuelle Overrides. Wer nicht in der
Szene stand, kam im Prompt nicht vor — auch nicht mit einer Zeile.

Im zweiten Playtest verhoerte der Spieler einen sterbenden Schmuggler. Der
nannte einen Hintermann: **Dura Fenk, der Hafenmeister**, verschuldet, der
den Kristallschmuggel organisiert. Im Wiki ist Dura Fenk **Wachhauptmann
von Salzhaven**, Fraktion Stadtwache. Die Figur war korrekt erinnert, ihr
Amt komplett neu erfunden.

Das ist kein Halluzinieren aus dem Nichts, sondern die vorhersehbare Folge
der Datenlage: Der Erzaehler hatte den Namen aus dem Gespraechsverlauf, aber
null Kanon zu ihm im Kontext. Er musste erfinden — es gab nichts zu lesen.
Dieselbe Luecke traf jeden abwesenden Ort, jede Fraktion, jeden Kult.

Der zweite Teil des Problems: Ein im Spiel getoeteter oder entlarvter NPC
haelt seinen Zustand in `world_flags` (ADR-0002). Die Flags wurden nur auf
Volltext-Bloecke gelegt — also wieder nur auf Anwesende. Ueber einen
abwesenden Toten sprach der Erzaehler, als lebe er noch.

## Entscheidung

Eine achte Kontext-Schicht: das **Namensregister**. Eine Zeile je
kanonischem Eigennamen im Umkreis des aktuellen Ortes:

    - Dura Fenk [character] (wachhauptmann-dura-fenk) — Wachhauptmann,
      Salzhaven | Fraktion: ostimperium_city_watch
    - Silas Keyn [character] (silas-keyn) — Essenzhaendler | AKTUELL: tot=True

Vier Festlegungen:

1. **Umkreis ist die Region abwaerts.** Das Realm mitzuzaehlen holte im
   Test jede Stadt des Ostimperiums ins Register und sprengte das Budget.
   Realms und Regionen selbst stehen immer drin — es sind wenige, und sie
   verorten alles andere.
2. **Rolle schlaegt Fliesstext.** Bei Figuren ist die erste Body-Zeile eine
   Beschreibung des Aussehens; driften tut das Amt. Das Register nimmt
   `rolle` und `faction` aus dem Frontmatter, den Body nur als Rueckfall.
   Dafuer wandern beide Felder neu in den Index-Cache.
3. **World-Flags gelten auch hier.** Was dieser Durchlauf veraendert hat,
   steht als `AKTUELL:`-Anhang an der Registerzeile — derselbe Overlay wie
   auf den Volltext-Bloecken (ADR-0002).
4. **Das Register ist die Grenze zwischen Drift und Erfindung.** Der Prompt
   sagt es explizit: Was drinsteht, ist gesetzt und wird woertlich
   uebernommen. Was fehlt, existiert noch nicht und muss erst durch
   `add_wiki_entry`.

Volltext-Eintraege (gepinnt, Location-Stack, anwesende NPCs) bleiben aus dem
Register raus — sie stehen bereits ausfuehrlich im Kontext.

## Begruendung

- Der Fehler war ein Datenloch, keine Modellschwaeche. Ein staerkeres Modell
  haette denselben Namen ohne Kanon vorgefunden und ebenso erfunden.
- Der Preis ist klein: gemessen an der geseedeten Welt kostet das Register
  in Salzhaven (dichtester Ort, 81 Eintraege) rund 5000 Zeichen, der
  gesamte Kontext bleibt bei etwa 2600 Token. Volltext fuer alle waere um
  Groessenordnungen teurer gewesen und haette denselben Zweck erfuellt.
- Der Index traegt die Kurzfassung bereits mit: Sie wird einmal beim Scan
  berechnet und mitgecacht. Zur Laufzeit kostet das Register keinen
  einzigen Datei-Read.
- Die Sortierung setzt Figuren nach vorn. Wird das Budget doch einmal
  erreicht, faellt hinten Landschaft weg, nie eine Person.

## Konsequenzen

- `INDEX_VERSION` wurde eingefuehrt und auf 2 gesetzt. Ein laufender Server
  mit altem `_index.json` haette sonst weiter die Struktur ohne `kurz`,
  `rolle` und `faction` geliefert, und das Register waere still leer
  geblieben statt zu greifen.
- Der Umkreis haengt an sauberen Eltern-Ketten. Eintraege ohne `parent` und
  ohne `region` haengen im Nichts und tauchen nirgends auf — `wiki_lint`
  meldet solche Waisen bereits.
- Das Register nennt Namen, die der PC im Spiel noch nie gehoert hat. Es ist
  Autoren-Wissen fuer den Erzaehler, keine Figurenkenntnis; die bestehende
  Prompt-Regel "Ein NPC weiss nur, was er wissen kann" gilt unveraendert
  auch fuer den PC. Das ist eine bewusst in Kauf genommene Schwaeche:
  Konsistenz war hier wichtiger als perfekte Wissens-Trennung.
