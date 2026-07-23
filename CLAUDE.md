# NovaTerrum — Projektnotizen

Grimdark Solo-RPG-Web-App. Architektur und Startanleitung: README.md.

## Konventionen

- Antworten an den User: Deutsch, knapp, konkrete Empfehlung mit Default,
  keine Emojis.
- Code-Kommentare und Strings: Deutsch, ASCII (ae/oe/ue statt Umlaute) —
  Slugs sind strikt `[a-z0-9-]`.
- Keine Dateien ausserhalb des Projekts ohne Rueckfrage.
- Laufzeitdaten (`wiki/`, `data/`) sind gitignored — nie committen.

## Architektur-Invarianten

- **Settings immer frisch von Disk lesen** (`gamestate.load_settings`),
  nie modulweit cachen — alter Race-Bug.
- **Muenzen nur ueber Gesamt-Kupferwert** (`pay_copper`/`add_coins`),
  nie einzelne Sorten direkt anfassen — alter Currency-Bug.
- **Gemini-Tool-Results als Objekt** senden (`build_google_payload`
  parst JSON), nie als String — alter Double-Encoding-Bug.
- **Slugs kanonisch** ueber `canonical_slug()` mit Stadt-Parameter,
  sonst entstehen Duplikate wie `hartfeld-wache` vs `stadtwache-hartfeld`.
- **history.json ist gedeckelt** (Archiv-Rotation in `save_history`),
  Rolling Window schneidet nie ein Tool-Result von seinem Call ab.
- Wiki-Lint feuert nach jedem Zug, aber nicht bei `[META]`-Nachrichten.

## Testen & Pruefen

```bash
python3 -m pytest tests/ -q                          # ohne Keys lauffaehig
python3 -m scripts.wiki_lint                          # Exit 1 bei Errors
python3 -m scripts.generate_wiki --city X --dry-run   # Pipeline ohne LLM
```

Nach Aenderungen an tools.py oder llm_adapter.py: kompletten
Kampf-Zyklus in tests/test_combat.py gegenlesen — die State-Machine
ist die fehleranfaelligste Stelle.

## Bekannter Stand (2026-07)

- Rebuild aus Handoff-Doc vom 2026-07-02; Original-Code von Mai 2026
  existierte nicht mehr. Welt-Seed liefert 66 Eintraege, der alte Stand
  (~430 Eintraege, 11 generierte Staedte) muss per
  `scripts/generate_wiki.py --all` mit echten Keys neu erzeugt werden.
- Google Free Tier ist per-Modell rate-limited (250 RPD flash) —
  OpenRouter ist der zuverlaessige Weg.
- Deployment-Ziel Docker/Synology ist weiterhin offen; lokal laeuft
  alles ueber `python3 app/main.py` auf Port 3111.
