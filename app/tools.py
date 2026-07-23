"""DM-Tool-Registry und Kampf-State-Machine.

Jedes Tool: JSON-Schema fuer das LLM + Handler. Handler bekommen den
Gamestate (dict, mutiert in place) und die Argumente, geben einen
Ergebnis-String (oder Dict) fuer das LLM zurueck. Fehler werden als
String zurueckgegeben, nie als Exception — das LLM soll korrigieren.

Blocking-Tools (Wuerfelwuerfe des Spielers) geben BLOCKING zurueck;
der Agent-Loop pausiert dann und wartet auf die Spieler-Eingabe.
"""
from __future__ import annotations

import hashlib
import json
import random
import re

from . import gamestate as gsm
from . import wiki_index
from .wiki_io import (append_pc_journal, append_world_entry, canonical_slug,
                      read_world_entry, update_entry_meta, write_world_entry)

BLOCKING = "__AWAITING_PLAYER_ROLL__"

DICE_RE = re.compile(r"^(\d*)[dw](\d+)([+-]\d+)?$", re.IGNORECASE)


def roll_expr(expr: str, rng: random.Random | None = None) -> dict:
    """Wuerfelt '2d6+1', 'd20', '1w6' etc. serverseitig (fuer NPC/Welt)."""
    rng = rng or random.Random()
    m = DICE_RE.match(expr.strip().replace(" ", ""))
    if not m:
        raise ValueError(f"Ungueltiger Wuerfelausdruck: {expr}")
    count = int(m.group(1) or 1)
    sides = int(m.group(2))
    mod = int(m.group(3) or 0)
    if not (1 <= count <= 20 and 2 <= sides <= 100):
        raise ValueError(f"Ausserhalb erlaubter Grenzen: {expr}")
    rolls = [rng.randint(1, sides) for _ in range(count)]
    return {"expr": expr, "rolls": rolls, "mod": mod, "total": sum(rolls) + mod}


def auto_coords(slug: str, region: str | None) -> list[int]:
    """Deterministische Kartenkoordinaten: Region bestimmt die Zelle,
    der Slug-Hash den Offset. Fix fuer 'Map leer bei Spielstart'."""
    region_cells = {
        "velara": (150, 420), "eisenmark": (450, 180), "frostmark": (620, 80),
        "rastberg": (520, 480), "schilfgrund": (250, 620),
    }
    base = region_cells.get(gsm.slugify(region or ""), (400, 350))
    h = int(hashlib.sha256(slug.encode()).hexdigest(), 16)
    return [base[0] + (h % 160) - 80, base[1] + ((h // 160) % 160) - 80]


# --- Kampf-State-Machine ------------------------------------------------
# Phasen: pc_turn -> (awaiting_roll) -> npc_turn -> pc_turn ... bis end_combat.
# Alle Kampf-Tools validieren die Phase und geben sonst einen Fehler-String.

def _combat_required(gs: dict) -> dict | str:
    c = gs.get("combat")
    if not c:
        return "FEHLER: Kein Kampf aktiv. Erst start_combat aufrufen."
    return c


def start_combat(gs: dict, args: dict) -> str:
    if gs.get("combat"):
        return "FEHLER: Kampf laeuft bereits. end_combat zuerst."
    enemies = []
    for e in args.get("gegner", []):
        slug = gsm.slugify(e["name"])
        hp = int(e.get("hp", 6))
        enemies.append({"slug": slug, "name": e["name"], "hp": hp, "hp_max": hp,
                        "notiz": e.get("notiz", "")})
    if not enemies:
        return "FEHLER: start_combat braucht mindestens einen Gegner."
    gs["combat"] = {
        "round": 1,
        "phase": "pc_turn",
        "enemies": enemies,
        "pending_roll": None,
        "log": [f"Kampf beginnt: {', '.join(e['name'] for e in enemies)}"],
    }
    return json.dumps({"status": "kampf_gestartet", "runde": 1, "phase": "pc_turn",
                       "gegner": enemies}, ensure_ascii=False)


def request_attack_roll(gs: dict, args: dict) -> str:
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    if c["phase"] != "pc_turn":
        return f"FEHLER: request_attack_roll nur in Phase pc_turn (aktuell: {c['phase']})."
    target = gsm.slugify(args.get("ziel", ""))
    if not any(e["slug"] == target for e in c["enemies"]):
        return f"FEHLER: Ziel '{target}' ist kein Gegner in diesem Kampf."
    c["pending_roll"] = {
        "art": "angriff",
        "ziel": target,
        "modifikator": int(args.get("modifikator", 0)),
        "schwierigkeit": int(args.get("schwierigkeit", 10)),
        "schaden": args.get("schaden", "1d6"),
        "beschreibung": args.get("beschreibung", ""),
    }
    c["phase"] = "awaiting_roll"
    return BLOCKING


def resolve_player_roll(gs: dict, roll: int) -> dict:
    """Wird vom Backend aufgerufen wenn der Spieler gewuerfelt hat.
    Liefert das Tool-Result fuer die LLM-Continuation."""
    c = gs.get("combat")
    if not c or c["phase"] != "awaiting_roll" or not c.get("pending_roll"):
        raise ValueError("Kein ausstehender Wurf")
    pr = c["pending_roll"]
    total = roll + pr["modifikator"]
    hit = total >= pr["schwierigkeit"]
    result = {"wurf": roll, "modifikator": pr["modifikator"], "gesamt": total,
              "schwierigkeit": pr["schwierigkeit"], "treffer": hit}
    if hit:
        dmg = roll_expr(pr["schaden"])
        result["schaden"] = dmg["total"]
        for e in c["enemies"]:
            if e["slug"] == pr["ziel"]:
                e["hp"] = max(e["hp"] - dmg["total"], 0)
                result["ziel"] = e["name"]
                result["ziel_hp"] = f"{e['hp']}/{e['hp_max']}"
                if e["hp"] == 0:
                    result["ziel_kampfunfaehig"] = True
        c["log"].append(f"PC trifft {pr['ziel']} ({total} vs {pr['schwierigkeit']}), {dmg['total']} Schaden")
    else:
        c["log"].append(f"PC verfehlt {pr['ziel']} ({total} vs {pr['schwierigkeit']})")
    c["pending_roll"] = None
    c["phase"] = "pc_turn"  # LLM entscheidet: weitere Aktion oder end_turn
    return result


def npc_action(gs: dict, args: dict) -> str:
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    if c["phase"] != "npc_turn":
        return f"FEHLER: npc_action nur in Phase npc_turn (aktuell: {c['phase']}). Erst end_turn."
    attacker = gsm.slugify(args.get("angreifer", ""))
    living = [e for e in c["enemies"] if e["hp"] > 0]
    if not any(e["slug"] == attacker for e in living):
        return f"FEHLER: '{attacker}' ist kein kampffaehiger Gegner."
    atk = roll_expr(args.get("angriffswurf", "1d20"))
    difficulty = int(args.get("schwierigkeit", 10))
    result: dict = {"angreifer": attacker, "wurf": atk["total"], "schwierigkeit": difficulty}
    if atk["total"] >= difficulty:
        dmg = roll_expr(args.get("schaden", "1d6"))
        hp_info = gsm.adjust_hp(gs, -dmg["total"])
        result.update({"treffer": True, "schaden": dmg["total"], **hp_info})
        c["log"].append(f"{attacker} trifft PC: {dmg['total']} Schaden -> {hp_info['hp']} HP")
    else:
        result["treffer"] = False
        c["log"].append(f"{attacker} verfehlt den PC")
    return json.dumps(result, ensure_ascii=False)


def end_turn(gs: dict, args: dict) -> str:
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    if c["phase"] == "awaiting_roll":
        return "FEHLER: Es steht noch ein Spieler-Wurf aus."
    if c["phase"] == "pc_turn":
        c["phase"] = "npc_turn"
    else:
        c["phase"] = "pc_turn"
        c["round"] += 1
    return json.dumps({"runde": c["round"], "phase": c["phase"],
                       "gegner_kampffaehig": [e["name"] for e in c["enemies"] if e["hp"] > 0]},
                      ensure_ascii=False)


def end_combat(gs: dict, args: dict) -> str:
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    outcome = args.get("ausgang", "unentschieden")
    xp = int(args.get("xp", 0))
    summary = {"ausgang": outcome, "runden": c["round"], "log": c["log"][-10:]}
    if xp > 0:
        summary["xp"] = gsm.add_xp(gs, xp)
    gs["combat"] = None
    return json.dumps(summary, ensure_ascii=False)


# --- Wirtschaft ---------------------------------------------------------

def pay(gs: dict, args: dict) -> str:
    amount = int(args.get("betrag_kp", 0))
    try:
        gs["coins"] = gsm.pay_copper(gs["coins"], amount)
    except ValueError as e:
        return f"FEHLER: {e}"
    return json.dumps({"bezahlt_kp": amount,
                       "empfaenger": args.get("empfaenger", ""),
                       "boerse": gsm.format_coins(gs["coins"])}, ensure_ascii=False)


def receive_coins(gs: dict, args: dict) -> str:
    try:
        gs["coins"] = gsm.add_coins(gs["coins"], int(args.get("gm", 0)),
                                    int(args.get("sm", 0)), int(args.get("kp", 0)))
    except ValueError as e:
        return f"FEHLER: {e}"
    return json.dumps({"quelle": args.get("quelle", ""),
                       "boerse": gsm.format_coins(gs["coins"])}, ensure_ascii=False)


# --- Wiki / Welt --------------------------------------------------------

VALID_TYPES = ("location", "character", "faction", "noble_house", "lore",
               "economy", "law", "chronicle", "region", "subregion")


def add_wiki_entry(gs: dict, args: dict) -> str:
    etype = args.get("type", "lore")
    if etype not in VALID_TYPES:
        return f"FEHLER: Ungueltiger Typ '{etype}'. Erlaubt: {', '.join(VALID_TYPES)}"
    name = args.get("name", "").strip()
    if not name:
        return "FEHLER: name fehlt."
    city = args.get("stadt")
    slug = args.get("slug") or canonical_slug(name, etype, city)
    similar = wiki_index.find_similar_slugs(slug)
    if read_world_entry(slug) is not None:
        return f"FEHLER: '{slug}' existiert bereits. update_wiki_entry nutzen."
    if similar:
        return (f"WARNUNG: '{slug}' aehnelt existierenden Eintraegen: {', '.join(similar)}. "
                f"Wenn identisch: update_wiki_entry auf den bestehenden Slug. "
                f"Wenn wirklich neu: erneut mit explizitem slug-Parameter aufrufen.")
    meta = {"type": etype, "name": name}
    for key in ("region", "status", "tags", "produces", "imports"):
        if args.get(key):
            meta[key] = args[key]
    if etype in ("location", "region", "subregion"):
        meta["koordinaten"] = args.get("koordinaten") or auto_coords(slug, args.get("region"))
    write_world_entry(slug, meta, args.get("body", ""))
    return json.dumps({"angelegt": slug, "type": etype}, ensure_ascii=False)


def update_wiki_entry(gs: dict, args: dict) -> str:
    slug = args.get("slug", "")
    if read_world_entry(slug) is None:
        return f"FEHLER: '{slug}' existiert nicht."
    did = []
    if args.get("body_anhang"):
        append_world_entry(slug, args["body_anhang"])
        did.append("body erweitert")
    patch = {k: args[k] for k in ("status", "tags") if args.get(k)}
    if patch:
        update_entry_meta(slug, patch)
        did.append("meta aktualisiert")
    if not did:
        return "FEHLER: Nichts zu aendern (body_anhang oder status/tags angeben)."
    return json.dumps({"slug": slug, "aenderungen": did}, ensure_ascii=False)


def set_location(gs: dict, args: dict) -> str:
    slug = args.get("slug") or gsm.slugify(args.get("name", ""))
    name = args.get("name", slug)
    meta = wiki_index.get_entry_meta(slug)
    if meta is None:
        return (f"FEHLER: Ort '{slug}' hat keinen Wiki-Eintrag. "
                f"Erst add_wiki_entry mit type=location.")
    gs["location"] = {"slug": slug, "name": name}
    stack = []
    region = meta.get("region")
    if region:
        rslug = gsm.slugify(region)
        if wiki_index.get_entry_meta(rslug):
            stack.append(rslug)
    stack.append(slug)
    gs["location_stack"] = stack
    gs["anwesende_npcs"] = []  # Ortswechsel leert die Anwesenheitsliste
    return json.dumps({"ort": name, "stack": stack}, ensure_ascii=False)


def npc_present(gs: dict, args: dict) -> str:
    slug = args.get("slug") or gsm.slugify(args.get("name", ""))
    if args.get("entfernen"):
        gs["anwesende_npcs"] = [n for n in gs["anwesende_npcs"] if n != slug]
        return json.dumps({"entfernt": slug}, ensure_ascii=False)
    if wiki_index.get_entry_meta(slug) is None:
        return f"FEHLER: NPC '{slug}' hat keinen Wiki-Eintrag. Erst add_wiki_entry mit type=character."
    if slug not in gs["anwesende_npcs"]:
        gs["anwesende_npcs"].append(slug)
    return json.dumps({"anwesend": gs["anwesende_npcs"]}, ensure_ascii=False)


def manage_quest(gs: dict, args: dict) -> str:
    action = args.get("aktion", "neu")
    if action == "neu":
        qid = gsm.slugify(args.get("titel", ""))
        if any(q["id"] == qid for q in gs["quests"]):
            return f"FEHLER: Quest '{qid}' existiert bereits."
        gs["quests"].append({"id": qid, "titel": args.get("titel", qid),
                             "status": "offen", "entities": args.get("entities") or []})
        return json.dumps({"quest_angelegt": qid}, ensure_ascii=False)
    qid = args.get("id", "")
    for q in gs["quests"]:
        if q["id"] == qid:
            if args.get("status"):
                q["status"] = args["status"]
            for e in args.get("entities") or []:
                if e not in q["entities"]:
                    q["entities"].append(e)
            return json.dumps({"quest": qid, "status": q["status"]}, ensure_ascii=False)
    return f"FEHLER: Quest '{qid}' nicht gefunden."


def pin_entry(gs: dict, args: dict) -> str:
    slug = args.get("slug", "")
    if args.get("entfernen"):
        gs["pinned"] = [p for p in gs["pinned"] if p != slug]
        return json.dumps({"pinned": gs["pinned"]}, ensure_ascii=False)
    if wiki_index.get_entry_meta(slug) is None:
        return f"FEHLER: '{slug}' existiert nicht im Wiki."
    if slug not in gs["pinned"]:
        gs["pinned"].append(slug)
    return json.dumps({"pinned": gs["pinned"]}, ensure_ascii=False)


# --- PC-Verwaltung ------------------------------------------------------

def adjust_hp_tool(gs: dict, args: dict) -> str:
    info = gsm.adjust_hp(gs, int(args.get("delta", 0)))
    return json.dumps({**info, "grund": args.get("grund", "")}, ensure_ascii=False)


def add_xp_tool(gs: dict, args: dict) -> str:
    try:
        info = gsm.add_xp(gs, int(args.get("menge", 0)))
    except ValueError as e:
        return f"FEHLER: {e}"
    return json.dumps({**info, "grund": args.get("grund", "")}, ensure_ascii=False)


def manage_inventory(gs: dict, args: dict) -> str:
    name = args.get("name", "").strip()
    menge = int(args.get("menge", 1))
    if not name:
        return "FEHLER: name fehlt."
    inv = gs["inventar"]
    existing = next((i for i in inv if i["name"].lower() == name.lower()), None)
    if args.get("entfernen"):
        if not existing:
            return f"FEHLER: '{name}' nicht im Inventar."
        existing["menge"] = existing.get("menge", 1) - menge
        if existing["menge"] <= 0:
            inv.remove(existing)
        return json.dumps({"entfernt": name, "menge": menge}, ensure_ascii=False)
    if existing:
        existing["menge"] = existing.get("menge", 1) + menge
    else:
        inv.append({"name": name, "menge": menge, "notiz": args.get("notiz", "")})
    return json.dumps({"inventar": [f"{i['name']} x{i.get('menge', 1)}" for i in inv]},
                      ensure_ascii=False)


def status_effect(gs: dict, args: dict) -> str:
    eff = args.get("effekt", "").strip()
    if not eff:
        return "FEHLER: effekt fehlt."
    if args.get("entfernen"):
        gs["status_effekte"] = [e for e in gs["status_effekte"] if e != eff]
    elif eff not in gs["status_effekte"]:
        gs["status_effekte"].append(eff)
    return json.dumps({"status_effekte": gs["status_effekte"]}, ensure_ascii=False)


def journal_tool(gs: dict, args: dict) -> str:
    text = args.get("text", "").strip()
    if not text:
        return "FEHLER: text fehlt."
    append_pc_journal(gs["slug"], text)
    return json.dumps({"journal": "eingetragen"}, ensure_ascii=False)


def roll_dice_tool(gs: dict, args: dict) -> str:
    try:
        return json.dumps(roll_expr(args.get("ausdruck", "1d20")), ensure_ascii=False)
    except ValueError as e:
        return f"FEHLER: {e}"


# --- Registry -----------------------------------------------------------

def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}

S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}
ARR_S = {"type": "array", "items": {"type": "string"}}

TOOLS: list[dict] = [
    {"name": "roll_dice", "description": "Serverseitiger Wuerfelwurf fuer NPCs und Weltereignisse (z.B. '2d6+1'). Spieler-Angriffe laufen ueber request_attack_roll.",
     "input_schema": _schema({"ausdruck": S}, ["ausdruck"])},
    {"name": "pay", "description": "PC bezahlt einen Betrag in Kupfer (kp). Backend macht das Wechselgeld ueber den Boersen-Gesamtwert. 1 gm = 10 sm = 100 kp.",
     "input_schema": _schema({"betrag_kp": I, "empfaenger": S}, ["betrag_kp"])},
    {"name": "receive_coins", "description": "PC erhaelt Muenzen (gm/sm/kp, jeweils >= 0).",
     "input_schema": _schema({"gm": I, "sm": I, "kp": I, "quelle": S})},
    {"name": "adjust_hp", "description": "HP des PC aendern (delta negativ = Schaden, positiv = Heilung).",
     "input_schema": _schema({"delta": I, "grund": S}, ["delta"])},
    {"name": "add_xp", "description": "XP vergeben. Level-Up passiert automatisch.",
     "input_schema": _schema({"menge": I, "grund": S}, ["menge"])},
    {"name": "manage_inventory", "description": "Item ins Inventar legen oder entfernen (entfernen=true).",
     "input_schema": _schema({"name": S, "menge": I, "notiz": S, "entfernen": B}, ["name"])},
    {"name": "status_effect", "description": "Status-Effekt setzen oder entfernen (z.B. 'vergiftet', 'erschoepft').",
     "input_schema": _schema({"effekt": S, "entfernen": B}, ["effekt"])},
    {"name": "add_wiki_entry", "description": "Neuen Welt-Eintrag anlegen. Bei Stadt-Institutionen (Wache, Tempel, Gilde...) 'stadt' angeben — der Slug wird kanonisch. Locations bekommen automatisch Kartenkoordinaten.",
     "input_schema": _schema({"type": {"type": "string", "enum": list(VALID_TYPES)},
                              "name": S, "slug": S, "region": S, "stadt": S, "status": S,
                              "tags": ARR_S, "produces": ARR_S, "imports": ARR_S,
                              "body": S}, ["type", "name", "body"])},
    {"name": "update_wiki_entry", "description": "Bestehenden Welt-Eintrag erweitern (body_anhang) oder Status/Tags aendern.",
     "input_schema": _schema({"slug": S, "body_anhang": S, "status": S, "tags": ARR_S}, ["slug"])},
    {"name": "set_location", "description": "PC bewegt sich an einen Ort (muss als Wiki-Eintrag existieren). Setzt den Location-Stack und leert die NPC-Anwesenheit.",
     "input_schema": _schema({"slug": S, "name": S}, ["name"])},
    {"name": "npc_present", "description": "NPC betritt (oder verlaesst, entfernen=true) die Szene.",
     "input_schema": _schema({"slug": S, "name": S, "entfernen": B})},
    {"name": "manage_quest", "description": "Quest anlegen (aktion=neu, titel) oder aktualisieren (aktion=update, id, status: offen/aktiv/abgeschlossen/gescheitert, entities: verknuepfte Wiki-Slugs).",
     "input_schema": _schema({"aktion": {"type": "string", "enum": ["neu", "update"]},
                              "titel": S, "id": S, "status": S, "entities": ARR_S}, ["aktion"])},
    {"name": "pin_entry", "description": "Wiki-Eintrag dauerhaft in den Kontext pinnen (oder entfernen=true).",
     "input_schema": _schema({"slug": S, "entfernen": B}, ["slug"])},
    {"name": "append_journal", "description": "Wichtiges Ereignis ins PC-Journal schreiben (Persistenz ueber Sessions).",
     "input_schema": _schema({"text": S}, ["text"])},
    {"name": "start_combat", "description": "Kampf starten. gegner: Liste mit name, hp, notiz.",
     "input_schema": _schema({"gegner": {"type": "array", "items": _schema(
         {"name": S, "hp": I, "notiz": S}, ["name"])}}, ["gegner"])},
    {"name": "request_attack_roll", "description": "Spieler um einen Angriffswurf (d20) bitten. BLOCKIERT bis der Spieler wuerfelt. Nur in Phase pc_turn.",
     "input_schema": _schema({"ziel": S, "modifikator": I, "schwierigkeit": I,
                              "schaden": S, "beschreibung": S}, ["ziel", "schwierigkeit"])},
    {"name": "npc_action", "description": "NPC-Aktion im Kampf (nur Phase npc_turn). Wuerfe macht das Backend.",
     "input_schema": _schema({"angreifer": S, "angriffswurf": S, "schwierigkeit": I,
                              "schaden": S, "beschreibung": S}, ["angreifer"])},
    {"name": "end_turn", "description": "Zug beenden: pc_turn -> npc_turn -> naechste Runde.",
     "input_schema": _schema({})},
    {"name": "end_combat", "description": "Kampf beenden. ausgang: sieg/niederlage/flucht/verhandlung. Optional xp.",
     "input_schema": _schema({"ausgang": S, "xp": I}, ["ausgang"])},
]

HANDLERS = {
    "roll_dice": roll_dice_tool,
    "pay": pay,
    "receive_coins": receive_coins,
    "adjust_hp": adjust_hp_tool,
    "add_xp": add_xp_tool,
    "manage_inventory": manage_inventory,
    "status_effect": status_effect,
    "add_wiki_entry": add_wiki_entry,
    "update_wiki_entry": update_wiki_entry,
    "set_location": set_location,
    "npc_present": npc_present,
    "manage_quest": manage_quest,
    "pin_entry": pin_entry,
    "append_journal": journal_tool,
    "start_combat": start_combat,
    "request_attack_roll": request_attack_roll,
    "npc_action": npc_action,
    "end_turn": end_turn,
    "end_combat": end_combat,
}


def execute_tool(gs: dict, name: str, args: dict) -> str:
    handler = HANDLERS.get(name)
    if handler is None:
        return f"FEHLER: Unbekanntes Tool '{name}'."
    try:
        return handler(gs, args or {})
    except Exception as e:  # Handler-Bugs nie zum LLM durchschlagen lassen
        return f"FEHLER: {type(e).__name__}: {e}"
