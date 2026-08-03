"""7-Schichten-Context-Builder fuer den DM-Prompt.

Schichten (in Prioritaetsreihenfolge, je mit Zeichen-Budget aus
rulebook.json/context_char_budgets — Regel-Konstanten nur von dort,
keine hartkodierten Zweit-Zahlen im Python):
  1. Canon (Weltgesetze, immer vollstaendig)
  2. Gamestate-Zusammenfassung des aktiven PC
  3. Gepinnte Eintraege (volltext)
  4. Location-Stack (Region -> Subregion -> aktueller Ort)
  5. Anwesende NPCs
  6. Quest-Entities + Status-Lore + letzte Ereignisse (Journal-Tail)
  7. Bisherige Kapitel (Synopsen, siehe main._maybe_write_synopsis)
"""
from __future__ import annotations

from . import rules, wiki_index
from .gamestate import format_coins, format_kalender, hp_status_tag, slugify
from .wiki_io import read_journal_tail, read_recent_synopses, read_world_entry

BUDGETS = rules.RULEBOOK["context_char_budgets"]


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
    # Zeitplaene liegen im Index-Cache — kein Datei-Read pro Zug.
    for slug, e in wiki_index.get_index()["entries"].items():
        if e["type"] != "character":
            continue
        for shift in e.get("zeitplan") or []:
            ort = shift.get("ort") or shift.get("scene_id", "")
            von, bis = shift.get("von", 0), shift.get("bis", 24)
            in_shift = von <= hour < bis if von <= bis else (hour >= von or hour < bis)
            if ort in here and in_shift:
                present.append(slug)
                break
    return present


# Reihenfolge im Register: Figuren zuerst, weil ihre Rollen am schnellsten
# driften, danach Gruppen, dann Orte, dann der Rest.
_REGISTER_ORDER = {"character": 0, "faction": 1, "institution": 1, "organisation": 1,
                   "location": 2, "scene": 2, "zone": 2, "settlement": 2}


def _kette(idx: dict, slug: str, tiefe: int = 8) -> list[str]:
    """Eltern-Kette eines Slugs (ohne ihn selbst), robust gegen Zyklen."""
    kette, cur, seen = [], idx.get(slug), {slug}
    while cur is not None and len(kette) < tiefe:
        # 'region' im Frontmatter ist ein Klarname ("Suedkueste"), kein Slug —
        # ohne slugify bricht die Kette bei genau den Eintraegen ab, die nur
        # ueber die Region haengen (alle NPCs des Seeds).
        parent = cur.get("parent") or (slugify(cur["region"]) if cur.get("region") else None)
        if not parent or parent in seen:
            break
        kette.append(parent)
        seen.add(parent)
        cur = idx.get(parent)
    return kette


def entity_register(gs: dict) -> str:
    """Kompaktes Namensregister aller kanonischen Eigennamen im Umkreis des
    aktuellen Ortes — je eine Zeile mit Typ und Rolle.

    Ohne dieses Register enthielt der Prompt nur ANWESENDE NPCs. Sobald der
    Erzaehler ueber eine abwesende Figur sprach, hatte er keinerlei Kanon zu
    ihr im Kontext und erfand ihre Rolle neu (im Playtest wurde aus dem
    Stadtwache-Hauptmann Dura Fenk ein schuldengeplagter Hafenmeister).
    Volltext waere zu teuer — eine Zeile pro Name reicht, um Drift von
    Erfindung zu trennen: was hier steht, ist gesetzt; was fehlt, muss ueber
    add_wiki_entry entstehen."""
    idx = wiki_index.get_index()["entries"]
    flags = gs.get("world_flags") or {}
    stack = list(gs.get("location_stack") or [])
    if gs.get("location") and gs["location"]["slug"] not in stack:
        stack.append(gs["location"]["slug"])
    # Umkreis = Region abwaerts. Das Realm mitzuzaehlen wuerde jede Stadt des
    # Reiches ins Register holen — das sprengte im Test das Budget, und der
    # Erzaehler braucht keine Namen von der anderen Seite des Kontinents.
    umkreis = {s for s in stack if (idx.get(s) or {}).get("type") != "realm"}
    # Bereits als Volltext im Kontext — im Register waere das doppelt.
    volltext = set(gs.get("pinned") or []) | set(stack) | set(gs.get("anwesende_npcs") or [])

    treffer = []
    for slug, e in idx.items():
        if slug in volltext or slug == "canon":
            continue
        if e.get("scope") == "charakter" and e.get("pc") not in (None, gs["slug"]):
            continue
        # Realms und Regionen immer (es sind wenige, und sie verorten alles
        # andere), sonst nur, wenn die Eltern-Kette den Umkreis beruehrt.
        if e["type"] not in ("realm", "region") and not (umkreis & set(_kette(idx, slug))):
            continue
        treffer.append(e)

    if not treffer:
        return ""
    treffer.sort(key=lambda e: (_REGISTER_ORDER.get(e["type"], 3), e["name"]))
    zeilen = []
    for e in treffer:
        zeile = f"- {e['name']} [{e['type']}] ({e['slug']})"
        # Rolle schlaegt Fliesstext: bei Figuren ist die erste Body-Zeile eine
        # Beschreibung des Aussehens, driften tut aber das Amt.
        beschreibung = e.get("rolle") or e.get("kurz")
        if beschreibung:
            zeile += f" — {beschreibung}"
        if e.get("faction"):
            zeile += f" | Fraktion: {e['faction']}"
        if e.get("status") and e["status"] != "lebendig":
            zeile += f" | Status: {e['status']}"
        # Was dieser Durchlauf veraendert hat, gilt gegen den Welt-Text
        # (ADR-0002) — sonst steht ein im Spiel getoeteter NPC hier weiter
        # so da, als waere nichts gewesen.
        ef = flags.get(e["slug"])
        if ef:
            zeile += " | AKTUELL: " + ", ".join(f"{k}={v}" for k, v in ef.items())
        zeilen.append(zeile)
    return _clip("\n".join(zeilen), BUDGETS["register"])


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
            f"{v['name']} ({v.get('stufe', 'leicht')})" for v in gs["verletzungen"])
            + f" — Wurf-Malus gesamt {rules.verletzungs_mod(gs):+d}")
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
        teile = []
        for e in c.get("enemies", []):
            zustand = f"{e['name']} ({e['hp']}/{e['hp_max']} HP"
            if e.get("distanz"):
                zustand += f", {e['distanz']} Zone(n) entfernt"
            if e.get("status", "active") != "active":
                zustand += f", {e['status']}"
            elif e.get("gehandelt_runde") == c.get("round"):
                zustand += ", hat gehandelt"
            teile.append(zustand + ")")
        lines.append(f"=== KAMPFZUSTAND === Runde {c.get('round', 1)}, "
                     f"Phase {c.get('phase', 'pc_turn')}, Gegner: {', '.join(teile)}")
        if c.get("pc_gehandelt"):
            lines.append("Der PC hat in dieser Runde bereits gehandelt.")
        av = c.get("aktive_verteidigung")
        if av and av.get("runde") == c.get("round"):
            lines.append(f"PC verteidigt aktiv ({av['art']}) — Angriffe muessen "
                         f"{av['wert']} ueberbieten statt des VW.")
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

    max_synopses = rules.RULEBOOK.get("max_synopses_in_context", 2)
    synopses = read_recent_synopses(gs["slug"], max_n=max_synopses)
    if synopses:
        blocks = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(synopses))
        parts.append("## Bisherige Kapitel (Synopsen)\n" + _clip(blocks, BUDGETS["synopses"]))

    events = read_journal_tail(gs["slug"], max_entries=4)
    if events:
        parts.append("## Letzte Ereignisse\n" + _clip(events, BUDGETS["events"]))

    register = entity_register(gs)
    if register:
        parts.append("## Namensregister (kanonische Namen im Umkreis)\n"
                     "Diese Namen und Rollen sind gesetzt. Ein Name, der hier "
                     "oder oben nicht steht, existiert noch nicht — leg ihn "
                     "erst mit add_wiki_entry an.\n" + register)

    return "\n\n".join(parts)
