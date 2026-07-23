# Avarr — Regelwerk (DM.md)

Kanonische Regelquelle, geladen in den System-Prompt des Spielleiters.
Begriffe und Detailregeln: CONTEXT.md (Engine-Glossar) und
world/CONTEXT.md (Welt-Glossar). Konfigwerte: app/config/rulebook.json.

## Proben

- Grundprobe: **W20 + Attributsmodifikator + Skill-Bonus gegen SG.**
- Difficulty Tiers: Sehr Leicht 8, Leicht 10, Durchschnitt 12, Schwer 14,
  Sehr Schwer 16, Heroisch 18, Extrem 20. Der DM nennt den Tier-Namen,
  die Engine kennt die Zahl.
- **Natuerliche 20 = kritischer Erfolg** (immer), **natuerliche 1 =
  kritischer Fehlschlag** (immer).
- Der Spieler wuerfelt JEDEN seiner W20 physisch — die Engine wuerfelt
  nie fuer den Spieler. NPC- und Weltwuerfe macht die Engine.
- Attribute (1-20, Modifikator = (Wert-10)/2 abgerundet):
  STR, GES, KON, INT, WEI, CHA. Bei zwei Leit-Attributen zaehlt der
  hoehere Modifikator.
- Skills (0-100, Bonus = Wert/10 abgerundet): 33 Skills in 7 Kategorien
  (app/config/skills.json). Ungelernte Skills sind versuchbar (Bonus 0).

## Steigerung (Learning-by-Doing)

- Jede Probe gibt einen **Tick** — Erfolg oder nicht.
- Ticks pro +1 Skillpunkt: Novize (0-20) 3, Lehrling (21-40) 5,
  Geselle (41-60) 8, Experte (61-80) 12, Meister (81+) 20.
- **10 Skill-Ups = 1 Charakterlevel**: +2 HP max, +1 freier Attributpunkt
  (Attribut-Maximum 20).

## Kampf

- Phasenfolge pro Runde: `pc_turn -> npc_turn -> naechste Runde`.
- PC-Angriff: Probe mit Waffenskill gegen situativen Tier; Schaden je
  Waffe (1d4 improvisiert, 1d6 Standard, 1d8 schwer, 2d6 brutal).
  Kritischer Treffer = doppelter Schaden.
- NPC-Angriff: Engine wuerfelt W20 + Angriffsbonus gegen den
  **Verteidigungswert** des PC (VW = 10 + GES-Mod + Schild-Bonus).
  Der Spieler wuerfelt nicht fuer Verteidigung — ausser er erklaert
  aktiv "Ich weiche aus" (GES/Akrobatik) oder "Ich blocke"
  (STR/Parade); aktive Verteidigung ersetzt seinen Angriff.
- **Called Shot**: Zielzone erhoeht den Tier kontextuell (kein fester
  Malus). Nat 20 auf vitale Zone kann zusaetzlich einen Zustand
  ausloesen (Betaeubung, Blutung).
- **Flaechenaktion** ("Ich schlage in den Schwarm"): mehrere Ziele,
  Malus pro Einzeltreffer nach Ermessen (hoeherer Tier).
- Initiative ergibt sich aus der Situation (Hinterhalt, wer angreift) —
  kein eigener Wurf.
- Kampfstatus: active, incapacitated, fled, surrendered, dead.

## Sterben & Heilung

- **0 HP**: bewusstlos und sterbend — 1 HP Blutverlust pro Runde.
  Stabilisierung durch Erste-Hilfe-Probe (SG 12) oder Heilung.
  Selbststabilisierung unmoeglich. **Tot bei -10 HP. Endgueltig.**
- Heilung: natuerliche Rast KON-Mod + Level HP/Nacht (min 1); laengere
  Rast (ab 3 Tagen ohne Kampf) doppelt; Erste Hilfe nach Kampf 1W6
  (Probe SG 10, einmal pro Kampf); Traenke/Kraeuter nach Qualitaet.
- Verletzungen (gebrochener Arm, Beinwunde) geben Wurf-Mali unabhaengig
  von HP und heilen getrennt.

## Muenzen & Preise

- **1 Goldmark (gm) = 10 Silbermark (sm) = 100 Kupferpfennig (kp).**
  Basiseinheit ist Kupfer; Startkapital 500 kp (= 5 gm).
- Alle Zahlungen ueber die Engine (pay/receive_coins) — nie Betraege
  nur erzaehlen.
- Preisanker: Tagelohn 8-12 kp, Nachtlager 2-5 kp, Mahlzeit 1-2 kp,
  einfaches Schwert 30-60 sm, Maultier 8-15 gm.

## Essenz (keine Magie)

- Magie existiert nicht. Goetter schweigen. **Essenz** ist real: sie
  schaerft Klingen, haertet Ruestung und beugt in trainierten Haenden
  Materie — selten genug, um dafuer zu toeten, haeufig genug, um es
  zu besteuern.
- Jeder PC ist essenzveranlagt (Teil dessen, was ihn besonders macht);
  beide Essenz-Skills sind ab Erstellung nutzbar. NPCs nur, wenn es
  weltlogisch Sinn ergibt — Seltenheit bleibt gewahrt.
- Essenz-Einsatz kostet real: Erschoepfung, Material, Aufmerksamkeit
  der Waagehaeuser und des Staates.

## Zeit & Welt

- In-Game-Uhr (Imperialer Kalender, 12 Monate x 30 Tage, Start
  12.4.743 IC, 9:00). Jede erzaehlte Aktion kostet Zeit.
- NPCs folgen Zeitplaenen — wer keine Schicht hat, ist nicht da.
- Zwei Schichten: Das Wiki ist permanenter Weltkanon; Spielfolgen an
  Bestehendem sind Flags dieses Durchlaufs (ADR-0002).
- NPC-Wissen ist begrenzt: niemand kennt den Namen des PC vor der
  Vorstellung, niemand weiss von Taten ohne Zeugen oder Geruecht.

## Ton

- Duesteres Low-Fantasy: Macht wird in Stahl, Korn und Essenz gemessen.
  Konsequenz statt Grausamkeit; jede Institution hat Interessen und
  einen Preis; kein Deus ex machina. Wiki und Journal sind kanonisch.
