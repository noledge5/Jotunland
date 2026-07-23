# ADR-0002: Markdown-Wiki mit Flag-Overlay statt SQLite

Status: akzeptiert (2026-07-23, Grill-Session mit User)

## Kontext

Der Avarr-Stand speicherte die Welt in SQLite (Tabellen scenes/zones/
regions/npcs, world_state_flags pro Playthrough). Der NovaTerrum-Rebuild
speichert die Welt als Markdown-Wiki mit YAML-Frontmatter plus per-PC
`gamestate.json`. Der User will die Welt selbst pflegen: visuell ueber
Netz- und Karten-Editor, direkt auf den Dateien.

## Entscheidung

Markdown-Wiki bleibt die World-Scope-Autoritaet. Das Zwei-Schichten-
Modell des alten Stands wird darauf uebertragen:

- **World Scope = Wiki** (`wiki/world/*.md`): Orte, grosse NPCs, Lore,
  Geografie mit Meter-Koordinaten. Waechst permanent — durch Spiel
  (neue Orte sind sofort World-Scoped) und durch Editor-Arbeit.
  Kein Reset bei neuem Playthrough.
- **Character Scope = Gamestate**: World State Flags (Aenderungen an
  bestehenden Welt-Eintraegen), kleine generierte NPCs, Beziehungen,
  Journal. Der Context-Builder ueberlagert das Wiki mit den Flags des
  aktiven PC. Neuer PC = kanonische Welt ohne fremde Narben.
  Promotion macht Charakter-Inhalte auf Wunsch permanent.

## Begruendung

- Markdown ist direkt editierbar (Editor, Git-Diff, Handarbeit) —
  zentral fuer den Workflow des Users; SQLite waere eine Blackbox
  hinter dem Editor.
- Versionierbarkeit: Weltstand und Regelwerk leben im Repo,
  Spielstaende bleiben lokal.
- Die Flag-Schicht erhaelt die bewaehrte Playthrough-Isolation des
  alten Designs, ohne die wachsende Welt aufzugeben.

## Konsequenzen

- Kein SQL: Abfragen laufen ueber den Slug-Index-Cache; bei sehr
  grossen Welten (>10k Eintraege) muesste der Index ausgebaut werden.
- Waehrend des Spiels aendert der DM bestehende Welt-Eintraege NUR
  ueber Flags (`set_world_flag`) — direkte Wiki-Schreibzugriffe im
  Spiel sind auf neue Eintraege beschraenkt. Der Editor (User) schreibt
  direkt ins Wiki; das ist Authoring, kein Spielzug.
