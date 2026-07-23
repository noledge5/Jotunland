# NovaTerrum — Regelwerk (DM.md)

Rekonstruiert 2026-07 aus dem Handoff-Doc; das Original von Mai 2026 ist
verloren. Dieses Dokument ist die kanonische Regelquelle: `app/main.py`
laedt es in den System-Prompt des Spielleiters.

## Proben

- Grundprobe: **d20 + Attributsmodifikator gegen Schwierigkeit.**
- Schwierigkeiten: 8 leicht, 10 normal, 13 schwer, 16 sehr schwer.
- Der Spieler wuerfelt **nur seine Angriffe selbst** (d20, blockierender
  Wurf). Alle anderen Wuerfe macht der Server (`roll_dice`).
- Attribute: staerke, geschick, verstand, wille. Spanne -2 bis +4.
  Startwert 0, Steigerung nur durch Level-Up oder erzaehlte Marken.

## Kampf

- Runden mit fester Phasenfolge: `pc_turn -> npc_turn -> naechste Runde`.
- Im pc_turn: eine Aktion (Angriff via request_attack_roll, Manoever,
  Flucht, Verhandlung). Im npc_turn: jeder kampffaehige Gegner eine
  Aktion (`npc_action`).
- Schadenswuerfel nach Waffe: 1d4 improvisiert/klein, 1d6 Standard,
  1d8 schwer/zweihaendig, 2d6 brutal (selten, meist Monster).
- Ruestung erhoeht die Schwierigkeit des Angriffs (+1 leicht, +2 schwer),
  sie schluckt keinen Schaden.
- 0 HP: kampfunfaehig, todgeweiht. Ohne Versorgung binnen Stunden tot.
  **Der Tod ist endgueltig** — kein Zauber holt jemanden zurueck.

## HP, XP, Level

- Start: 12 HP. Level-Up: +3 HP max, volle Heilung.
- HP-Status: unversehrt (>=90%), angeschlagen (>=60%), verwundet (>=30%),
  schwer verwundet (<30%), todgeweiht (<=0).
- XP-Schwellen: 100/300/600/1000/1500/2100/2800/3600/4500 (Level 2-10).
- XP-Vergabe: 10-30 kleine Szene, 50-100 gefaehrlicher Kampf oder
  gelostes Kapitel, 150+ nur fuer Meilensteine.
- Heilung: Wundnaht und Ruhe (1d4 HP pro voller Rasttag mit Versorgung),
  Kraeuter/Wundarzt beschleunigen. Keine Heiltraenke von der Stange.

## Muenzen

- **1 Goldmark (gm) = 10 Silbermark (sm) = 100 Kupferpfennig (kp).**
- Alle Zahlungen ueber `pay` (Betrag in kp), Einnahmen ueber
  `receive_coins`. Das Backend macht das Wechselgeld — nie Muenzsorten
  einzeln verrechnen.
- Preisanker: Tagelohn 8-12 kp, Nachtlager 2-5 kp, warme Mahlzeit 1-2 kp,
  einfaches Schwert 30-60 sm, Maultier 8-15 gm. Gold sieht ein einfacher
  Mann selten — wer mit gm zahlt, wird erinnert.

## Magie — die Duennung

- Magie schwindet seit dem Aschekrieg (Lore: die-duennung). Sie ist
  selten, koerperlich teuer und gesellschaftlich geaechtet
  (Edikt der Asche).
- Jeder Zauber kostet den Wirker etwas Reales: HP, einen Status-Effekt
  ("ausgezehrt", "aschgrau"), Lebenszeit. Kein Feuerball loest ein
  Problem, das ein Messer loesen kann.
- NPCs reagieren auf offene Magie mit Angst, Anzeige oder Preistreiberei.

## Grimdark-Prinzipien

- Konsequenz statt Grausamkeit: die Welt ist hart, nicht sadistisch.
  Jede Tat hat einen Preis, jeder Vorteil einen Haken.
- Jede Institution hat Interessen und einen Preis; niemand hilft aus
  reiner Guete, aber jeder ist kaeuflich, erpressbar oder muede.
- Kein Deus ex machina. Rettung kommt aus dem, was etabliert ist —
  Wiki und Journal sind kanonisch.
- NPCs luegen, irren sich und haben unvollstaendiges Wissen. Was ein
  NPC sagt, ist Aussage, nicht Weltfakt.

## Welt-Verwaltung

- Neue Orte, Personen, Fraktionen: **erst `add_wiki_entry`, dann
  erzaehlen.** Stadt-Institutionen mit `stadt`-Parameter (kanonische
  Slugs: stadtwache-hartfeld, tempel-grauwall, ...).
- Ortswechsel ueber `set_location`, Anwesenheit ueber `npc_present`.
- Wichtige Wendungen ins Journal (`append_journal`) — das Journal ist
  das Gedaechtnis ueber Sessions hinweg.
- Quests ueber `manage_quest` fuehren, verknuepfte Wiki-Slugs als
  entities pflegen.
