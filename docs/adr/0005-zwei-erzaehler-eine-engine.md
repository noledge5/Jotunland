# ADR-0005: Zwei Erzaehler, eine Engine

Status: akzeptiert (2026-08-03)

## Kontext

Der Erzaehler lief bisher ausschliesslich als API-Modell im Agent-Loop des
FastAPI-Servers, abgerechnet pro Token. Das hat zwei Nachteile, die sich
gegenseitig verstaerken: Starke Modelle sind pro Zug teuer, und guenstige
Modelle produzieren genau die Regelverstoesse, gegen die dieses Projekt seit
ADR-0001 anbaut. Der User hat ein Claude-Abo, das claude.ai und Claude Code
abdeckt.

Das Abo stellt keine API-Credentials aus — eine eigene App kann nicht dagegen
abrechnen, egal wie sie gebaut ist. Was das Abo abdeckt, ist Claude Code:
ein Agent mit Shell- und Datei-Zugriff auf dieses Repo. Damit ist der
Erzaehler erreichbar, ohne dass ein Token ueber die API laeuft.

Die naheliegende Alternative — die Welt als Wissensdateien in ein Projekt
kippen und den Chat erzaehlen lassen — wurde verworfen: Sie wirft genau die
mechanische Absicherung weg (Proben-Pflicht, Validator, Kampf-State-Machine,
Spielstand als Wahrheit), die die Playtests als notwendig erwiesen haben.

## Entscheidung

Der Erzaehler wird austauschbar, die Engine bleibt eine.

1. **`app/session.py` als gemeinsame Zug-Maschinerie.** Systemprompt,
   History mit Deckel, Undo-Ringpuffer, Validator und Zugabschluss
   (`finalize_turn`) sind aus `app/main.py` herausgeloest. Der Server nutzt
   sie, die CLI nutzt sie. Was dort NICHT hingehoert: HTTP, SSE, Agent-Loop,
   LLM-Adapter.
2. **`scripts/dm_cli.py` als zweiter Zugang.** Dieselben Tools, derselbe
   Validator, derselbe Spielstand unter `data/pcs/<slug>/` — nur ohne
   LLM-Adapter, weil der Erzaehler die CLI selbst bedient.
3. **`.claude/skills/dm/SKILL.md` als DM-Anleitung fuer Claude Code.** Sie
   beschreibt den Ablauf, nicht die Regeln; die kanonische Regelquelle
   bleibt `DM.md`, abrufbar ueber `dm_cli regeln`.
4. **Kein zweiter Regelsatz.** Jede Regel, die nur in einem der beiden Wege
   gilt, ist ein Bug. Die CLI-Tests pruefen deshalb nicht die Befehle,
   sondern dass die CLI dieselben Verstoesse ablehnt wie der Server.

## Begruendung

- Die Playtests haben gezeigt, dass die Engine der wertvolle Teil ist, nicht
  der Prompt: Von den drei zuletzt gemeldeten "Modellschwaechen" waren alle
  drei Engine-Bugs. Ein Umbau, der die Engine aufgibt, um ein staerkeres
  Modell zu bekommen, taeuscht genau ueber die Ursache hinweg.
- Ein staerkeres Modell hilft trotzdem — bei Sprache, Kontinuitaet ueber
  lange Boegen und beim Befolgen der Tool-Disziplin. Beides zusammen ist
  besser als eins von beidem.
- Die CLI ist die kleinste Schnittstelle, die reicht. Ein MCP-Server waere
  komfortabler (Spielen direkt in claude.ai), braucht aber Hosting und
  einen zweiten Transport. Er bleibt als Erweiterung offen und wuerde
  dieselbe `session.py` benutzen.

## Konsequenzen

- Der Zustand eines laufenden Zugs kann nicht im Speicher liegen: Jeder
  CLI-Aufruf ist ein eigener Prozess. Die Liste der Tools dieses Zugs
  wandert deshalb nach `data/pcs/<slug>/cli_turn_tools.json` und wird bei
  `zugende` geleert. Bricht ein Zug ab, steht die Datei noch — der naechste
  `zugende` zieht sie mit ein.
- Der Erzaehler in der CLI hat Shell-Zugriff und koennte den Spielstand
  direkt editieren. Das ist keine Sicherheitsluecke, sondern dieselbe
  Vertrauensstellung wie beim Spielleiter am Tisch — aber es heisst, dass
  die Disziplin hier staerker am Prompt haengt als im Server, wo der
  Transport die Tools erzwingt.
- Synopsen schreibt in der CLI der Erzaehler selbst (`dm_cli synopse`),
  statt sie ueber einen zweiten API-Call zu erzeugen. `finalize_turn`
  meldet nur, dass eine faellig ist.
- Der Classifier (das vorgeschaltete Proben-Gate, ADR-0001) laeuft in der
  CLI nicht. Er war ein Werkzeug gegen schwache Modelle; sein Zweck —
  strukturell ueber Probenpflicht entscheiden, bevor erzaehlt wird — liegt
  hier beim Erzaehler selbst. Ob das traegt, muss ein Playtest zeigen.
