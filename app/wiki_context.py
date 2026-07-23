"""6-Schichten-Context-Builder fuer den DM-Prompt.

Schichten (in Prioritaetsreihenfolge, je mit Zeichen-Budget):
  1. Canon (Weltgesetze, immer vollstaendig)
  2. Gamestate-Zusammenfassung des aktiven PC
  3. Gepinnte Eintraege (volltext)
  4. Location-Stack (Region -> Subregion -> aktueller Ort)
  5. Anwesende NPCs
  6. Quest-Entities + Status-Lore + letzte Ereignisse (Journal-Tail)
"""
from __future__ import annotations

from . import rules, wiki_index
from .gamestate import format_coins, format_kalender, hp_status_tag
from .wiki_io import read_journal_tail, read_world_entry

BUDGETS = {
    "canon": 4000,
    "gamestate": 2000,
    "pinned": 6000,
    "locations": 6000,
    "npcs": 4000,
    "quests_lore": 5000,
    "events": 3000,
}


def _clip(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[:budget].rsplit("\n", 1)[0] + "\n[... gekuerzt ...]"


def _entry_block(slug: str, budget: int, flags: dict | None = None) -> str:
    entry = read_world_entry(slug)
    if entry is None:
        return f"### {slug}\n(Eintrag fehlt im Wiki)"
    meta, body = entry
    head = f"### {meta.get('name', slug)} [{meta.get('type', '?')}] ({slug})"
    if meta.get("status"):
        head += f" — Status: {meta['status']}"
    block = f"{head}\n{body.strip()}"
    # Character-Scope-Overlay (ADR-0002): Flags dieses Durchlaufs
    # ueberschreiben den statischen Welt-Text.
    entity_flags = (flags or {}).get(slug)
    if entity_flags:
        overlay = ", ".join(f"{k}={v}" for k, v in entity_flags.items())
        block += f"\nAKTUELLER ZUSTAND (dieser Durchlauf): {overlay}"
    return _clip(block, budget)


def scheduled_npcs(gs: dict) -> list[str]:
    """NPCs, die laut Zeitplan JETZT am aktuellen Ort sind."""
    loc = gs.get("location")
    if not loc:
        return []
    here = set(gs.get("location_stack") or []) | {loc["slug"]}
    hour = gs.get("kalender", {}).get("stunde", 12)
    present = []
    for slug, e in wiki_index.get_index()["entries"].items():
        if e["type"] != "character":
            continue
        entry = read_world_entry(slug)
        if entry is None:
            continue
        for shift in entry[0].get("zeitplan") or []:
            ort = shift.get("ort") or shift.get("scene_id", "")
            von, bis = shift.get("von", 0), shift.get("bis", 24)
            in_shift = von <= hour < bis if von <= bis else (hour >= von or hour < bis)
            if ort in here and in_shift:
                present.append(slug)
                break
    return present


def gamestate_summary(gs: dict) -> str:
    lines = [
        f"PC: {gs['name']} ({gs.get('klasse', '?')}) — Level {gs['level']}, "
        f"{gs.get('skill_ups', 0)} Skill-Ups",
        f"Zeit: {format_kalender(gs.get('kalender') or {'jahr': 743, 'monat': 4, 'tag': 12, 'stunde': 9, 'minute': 0})}",
        f"HP: {gs['hp']}/{gs['hp_max']} ({hp_status_tag(gs['hp'], gs['hp_max'])})"
        + (" — STERBEND, blutet!" if gs["hp"] <= 0 and not gs.get("stabilisiert") else ""),
        f"VW: {rules.verteidigungswert(gs)}",
        f"Boerse: {format_coins(gs['coins'])} (1 gm = 10 sm = 100 kp)",
    ]
    attr = gs.get("attribute") or {}
    if attr:
        lines.append("Attribute: " + ", ".join(
            f"{k} {v} ({rules.attr_mod(v):+d})" for k, v in attr.items()))
    skills = {n: s["wert"] for n, s in (gs.get("skills") or {}).items() if s["wert"] > 0}
    if skills:
        lines.append("Skills: " + ", ".join(
            f"{n} {w}" for n, w in sorted(skills.items(), key=lambda x: -x[1])[:15]))
    if gs.get("verletzungen"):
        lines.append("Verletzungen: " + ", ".join(
            f"{v['name']} ({v.get('modifikator', 0):+d})" for v in gs["verletzungen"]))
    if gs.get("status_effekte"):
        lines.append("Status-Effekte: " + ", ".join(gs["status_effekte"]))
    inv = gs.get("inventar") or []
    if inv:
        lines.append("Inventar: " + ", ".join(
            f"{i['name']} x{i.get('menge', 1)}" + (" [angelegt]" if i.get("equipped") else "")
            for i in inv[:20]))
    if gs.get("location"):
        lines.append(f"Aktueller Ort: {gs['location']['name']} ({gs['location']['slug']})")
    quests = [q for q in gs.get("quests", []) if q.get("status") != "abgeschlossen"]
    for q in quests[:6]:
        lines.append(f"Quest [{q.get('status', 'offen')}]: {q['titel']}")
    if gs.get("combat"):
        c = gs["combat"]
        enemies = ", ".join(f"{e['name']} ({e['hp']}/{e['hp_max']} HP)" for e in c["enemies"])
        lines.append(f"=== KAMPFZUSTAND === Runde {c['round']}, Phase {c['phase']}, Gegner: {enemies}")
    return "\n".join(lines)


def build_context(gs: dict) -> str:
    parts: list[str] = []
    flags = gs.get("world_flags") or {}

    canon = read_world_entry("canon")
    if canon:
        parts.append("## Welt-Canon (Layer A)\n" + _clip(canon[1].strip(), BUDGETS["canon"]))

    parts.append("## Spielstand\n" + _clip(gamestate_summary(gs), BUDGETS["gamestate"]))

    pinned = gs.get("pinned") or []
    if pinned:
        per = max(BUDGETS["pinned"] // len(pinned), 500)
        blocks = [_entry_block(s, per, flags) for s in pinned]
        parts.append("## Gepinnt\n" + "\n\n".join(blocks))

    stack = gs.get("location_stack") or []
    if gs.get("location") and gs["location"]["slug"] not in stack:
        stack = stack + [gs["location"]["slug"]]
    if stack:
        per = max(BUDGETS["locations"] // len(stack), 500)
        blocks = [_entry_block(s, per, flags) for s in stack]
        parts.append("## Ort & Umgebung (Layer B-D)\n" + "\n\n".join(blocks))

    # Anwesenheit: Zeitplan-NPCs (Schedule) + manuelle Overrides
    npcs = list(dict.fromkeys(scheduled_npcs(gs) + (gs.get("anwesende_npcs") or [])))
    if npcs:
        per = max(BUDGETS["npcs"] // len(npcs), 400)
        blocks = [_entry_block(s, per, flags) for s in npcs]
        parts.append("## Anwesende NPCs\n" + "\n\n".join(blocks))

    quest_slugs: list[str] = []
    for q in gs.get("quests", []):
        if q.get("status") != "abgeschlossen":
            quest_slugs.extend(q.get("entities") or [])
    # Status-Lore: Eintraege mit Tag 'lore' deren Status nicht normal ist
    idx = wiki_index.get_index()["entries"]
    lore_slugs = [s for s, e in idx.items()
                  if e["type"] == "lore" and e.get("status") in ("aktiv", "eskalierend")]
    combined = list(dict.fromkeys(quest_slugs + lore_slugs))
    seen = set(pinned) | set(stack) | set(npcs)
    combined = [s for s in combined if s not in seen]
    if combined:
        per = max(BUDGETS["quests_lore"] // len(combined), 400)
        blocks = [_entry_block(s, per) for s in combined[:10]]
        parts.append("## Quest-Wissen & aktive Lore\n" + "\n\n".join(blocks))

    events = read_journal_tail(gs["slug"], max_entries=4)
    if events:
        parts.append("## Letzte Ereignisse\n" + _clip(events, BUDGETS["events"]))

    return "\n\n".join(parts)
