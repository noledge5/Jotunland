"""Action-Classifier (ADR-0001, Fallback-Pfad): entscheidet vor der
Erzaehlung strukturell, ob eine Spieler-Aktion eine Probe braucht und
welchen Skill/Tier. Die Engine setzt die Probe dann an, bevor das
Erzaehler-LLM den Ausgang formuliert — so kann der Erzaehler eine
unsichere Aktion nicht mehr versehentlich in Prosa aufloesen.

Liefert {"braucht_probe": bool, "skill": str|None, "tier": str|None,
"grund": str}. Bei Fehlern faellt der Aufrufer auf "keine Probe" zurueck
(der Erzaehler-Tool-Loop bleibt als zweite Verteidigungslinie).
"""
from __future__ import annotations

import json
import re

from . import llm_adapter, rules

SYSTEM = """Du bist der Regel-Schiedsrichter eines Pen-and-Paper-RPG. Du erzaehlst
NICHT. Du entscheidest nur, ob die beschriebene Spieler-Aktion eine
Wuerfelprobe braucht, und wenn ja: welchen Skill und welche Schwierigkeit.

Eine Probe ist noetig, wenn der Ausgang UNSICHER ist und Bedeutung hat:
- Ueberzeugen/Taeuschen/Einschuechtern/Feilschen gegen einen NPC mit
  eigenem Willen oder Interesse (nicht bei blossem Smalltalk).
- Schleichen, Stehlen, Schloesser knacken, Taschendiebstahl.
- Angriff, Parade, Ausweichen im Kampf.
- Wahrnehmung/Suche nach Verborgenem; Faehrtenlesen; Klettern/Springen
  unter Druck; Erste Hilfe; Handwerk/Alchemie mit Risiko.

KEINE Probe bei: reinem Reden ohne Widerstand, Fragen stellen, Gehen,
Umsehen ohne Gefahr, Kaufen zum genannten Preis, trivialen Handlungen,
Aktionen ohne Gegenspieler oder Risiko.

Whitelist der Skills (exakt so schreiben):
{skills}

Schwierigkeits-Tiers (exakt so): {tiers}
Waehle den Tier nach Widerstand/Gefahr: Durchschnitt als Standard,
Schwer wenn der NPC misstrauisch/im Vorteil ist, Leicht wenn die Lage
guenstig ist.

Antworte NUR mit JSON, nichts sonst:
{{"braucht_probe": true|false, "skill": "<Skill oder null>", "tier": "<Tier oder null>", "grund": "<max 12 Woerter>"}}"""


def _context(gs: dict) -> str:
    lines = []
    if gs.get("location"):
        lines.append(f"Ort: {gs['location']['name']}")
    npcs = gs.get("anwesende_npcs") or []
    if npcs:
        lines.append("Anwesend: " + ", ".join(npcs))
    skills = {n: s["wert"] for n, s in (gs.get("skills") or {}).items() if s["wert"] > 0}
    if skills:
        lines.append("PC-Skills: " + ", ".join(f"{n} {w}" for n, w in skills.items()))
    if gs.get("combat"):
        lines.append("KAMPF AKTIV")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("kein JSON")
    return json.loads(m.group(0))


async def classify(gs: dict, user_message: str, model_id: str) -> dict:
    """Entscheidet ueber Probenpflicht. Wirft bei Provider-/Parse-Fehlern."""
    system = SYSTEM.format(skills=", ".join(sorted(rules.SKILLS)),
                           tiers=", ".join(rules.TIERS))
    user = f"{_context(gs)}\n\nSpieler-Aktion: {user_message.strip()}"
    raw = await llm_adapter.complete(model_id, system, user, max_tokens=200)
    data = _extract_json(raw)
    # Validieren: nur bekannte Skills/Tiers zaehlen als echte Probe
    if data.get("braucht_probe"):
        skill = data.get("skill")
        tier = data.get("tier")
        if skill not in rules.SKILLS or rules.sg_for_tier(tier) is None:
            return {"braucht_probe": False, "skill": None, "tier": None,
                    "grund": "Skill/Tier ungueltig"}
        return {"braucht_probe": True, "skill": skill, "tier": tier,
                "grund": data.get("grund", "")}
    return {"braucht_probe": False, "skill": None, "tier": None,
            "grund": data.get("grund", "")}
