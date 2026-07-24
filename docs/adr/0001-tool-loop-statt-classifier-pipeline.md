# ADR-0001: Tool-Loop mit Pflicht-Proben-Tool statt Classifier-Pipeline

Status: akzeptiert (2026-07-23, Grill-Session mit User)

## Kontext

Der urspruengliche Avarr-Stand (Flask/SQLite, Branch
`claude/import-dkills-main-ZS45N`) erzwang Mechanik strukturell:
ein separater Classifier-LLM-Call entschied vor jeder Narration
`needs_roll` + Skill + Difficulty Tier, die Engine rechnete, erst dann
erzaehlte der Narrator das fertige Ergebnis. Motivation war der
haeufigste Bug: Rule Bypass (Erzaehler laesst Aktionen ohne Probe
gelingen, erfindet Preise und Outcomes).

Der NovaTerrum-Rebuild (FastAPI/Markdown) nutzt stattdessen einen
einzelnen DM-LLM mit Tool-Use-Loop: das LLM ruft Engine-Tools selbst
auf, blockierende Wuerfe pausieren den Stream.

## Entscheidung

Der Tool-Loop bleibt. Statt der Classifier-Pipeline gilt:

1. **Pflicht-Proben-Tool**: Jede Aktion mit unsicherem Ausgang MUSS
   ueber `request_skill_roll(skill, tier)` laufen. Das Tool blockiert
   bis zum physischen W20 des Spielers; die Engine berechnet Ergebnis,
   Crits, Ticks und Schaden. Der System-Prompt verbietet Prosa-Aufloesung.
2. **Regelbasierter Validator**: Nach jeder Narration prueft eine
   LLM-freie Schicht die Erzaehlung gegen den Gamestate (Muenzbetraege
   ohne pay/receive-Call, HP-Nennungen die nicht stimmen, unbekannte
   NPC-Namen) und meldet Verstoesse sichtbar an den Spieler.

## Begruendung

- Ein LLM-Call weniger pro Zug (Latenz und Kosten), ein Prompt statt
  zwei zu pflegen.
- Der Tool-Loop traegt bereits Weltbau, Kampf und Wirtschaft — eine
  parallele Classifier-Strecke wuerde zwei Mechanik-Autoritaeten schaffen.
- Moderne Tool-Use-Modelle folgen einem harten "immer Tool X fuer Y"-
  Gebot zuverlaessig genug, wenn der Validator Verstoesse sichtbar macht.

## Konsequenzen

- Rule Bypass ist nicht mehr strukturell unmoeglich, sondern
  prompt-diszipliniert + validator-ueberwacht.
- Der Validator braucht Pflege, waechst aber regelbasiert (billig).

## Nachtrag (2026-07-24): Classifier-Gate aktiviert

Der erste Live-Playtest (Sonnet 4.5) bestaetigte die vorhergesehene
Schwaeche: der Erzaehler loeste sozialen Druck teils in Prosa auf, ohne
`request_skill_roll` — und ohne Probe fiel auch der Tick weg. Der im
Rueckweg beschriebene Hybrid ist jetzt umgesetzt:

- `app/classifier.py` entscheidet vor der Erzaehlung (nur Handeln/
  Sprechen, ausserhalb Kampf) `braucht_probe + Skill + Tier`. Bei "ja"
  setzt die Engine die Probe als synthetischen `request_skill_roll` an
  und blockiert auf den Spielerwurf, BEVOR erzaehlt wird. Der Tool-Loop
  bleibt darunter als zweite Verteidigungslinie.
- Abschaltbar ueber `settings.use_classifier`; eigenes (billigeres)
  Modell ueber `settings.classifier_model`. Faellt der Call aus, uebernimmt
  der Erzaehler-Tool-Loop.
- Der Validator wurde geschaerft: erfundene Mechanik-Zahlen (Ticks/XP/
  Level/VW) und Geldfluesse ohne pay/receive_coins werden geflaggt.
