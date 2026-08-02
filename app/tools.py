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
from . import rules, wiki_index
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


def auto_coords(slug: str, parent: str | None) -> list[int]:
    """Deterministische Meter-Koordinaten nahe dem Eltern-Eintrag
    (Region/Stadt/Zone). Fallback: Zentrum des Ostimperiums."""
    base = (2380000, 1200000)
    if parent:
        meta = wiki_index.get_entry_meta(gsm.slugify(parent))
        if meta and meta.get("koordinaten"):
            base = tuple(meta["koordinaten"])
    h = int(hashlib.sha256(slug.encode()).hexdigest(), 16)
    return [base[0] + (h % 4000) - 2000, base[1] + ((h // 4000) % 4000) - 2000]


# --- Kampf-State-Machine ------------------------------------------------
# Die Engine schaltet die Runden selbst (ADR-0003): Es gibt kein end_turn-Tool
# mehr. Statt einer Phasensperre traegt jeder Handelnde ein Flag, dass er in
# dieser Runde dran war; sind PC und alle kampffaehigen Gegner durch, beginnt
# automatisch die naechste Runde. 'phase' bleibt als reine Anzeige erhalten.

def _combat_required(gs: dict) -> dict | str:
    c = gs.get("combat")
    if not c:
        return "FEHLER: Kein Kampf aktiv. Erst start_combat aufrufen."
    return c


def _aktive_gegner(c: dict) -> list[dict]:
    return [e for e in c["enemies"] if e["hp"] > 0 and e.get("status", "active") == "active"]


def _set_phase(gs: dict, c: dict) -> None:
    """Anzeige-Phase aus dem tatsaechlichen Zustand ableiten."""
    if c.get("pending_roll"):
        c["phase"] = "awaiting_roll"
    elif c.get("pc_gehandelt"):
        c["phase"] = "npc_turn"
    else:
        c["phase"] = "pc_turn"


def _kann_handeln(e: dict) -> bool:
    """Ein Nahkaempfer auf Distanz verbringt seine Runde mit Aufschliessen —
    er zaehlt als beschaeftigt, sonst blockiert er den Rundenwechsel und der
    Spieler kaeme nie zu einem zweiten Fernkampfschuss."""
    return e.get("distanz", 0) == 0 or e.get("fernkampf", False)


def _maybe_next_round(gs: dict, c: dict) -> bool:
    """Neue Runde, sobald der PC und alle handlungsfaehigen Gegner dran waren.
    Schliesst dabei Nahkaempfer auf, laesst Sterbende bluten und loescht die
    aktive Verteidigung (sie gilt immer nur fuer eine Runde)."""
    aktive = _aktive_gegner(c)
    if not c.get("pc_gehandelt"):
        return False
    if any(e.get("gehandelt_runde") != c["round"]
           for e in aktive if _kann_handeln(e)):
        return False
    c["round"] += 1
    c["pc_gehandelt"] = False
    c["aktive_verteidigung"] = None
    schritt = rules.RULEBOOK["kampf_zone_pro_runde"]
    for e in aktive:
        if not e.get("fernkampf") and e.get("distanz", 0) > 0:
            e["distanz"] = max(e["distanz"] - schritt, 0)
    if rules.is_dying(gs):
        rules.bleed(gs)
        c["log"].append(f"PC blutet: {gs['hp']} HP")
    return True


def start_combat(gs: dict, args: dict) -> str:
    if gs.get("combat"):
        return "FEHLER: Kampf laeuft bereits. end_combat zuerst."
    max_dist = rules.RULEBOOK["kampf_distanz_max"]
    enemies = []
    for e in args.get("gegner", []):
        slug = gsm.slugify(e["name"])
        hp = int(e.get("hp", 6))
        dist = max(0, min(int(e.get("distanz", 0)), max_dist))
        enemies.append({
            "slug": slug, "name": e["name"], "hp": hp, "hp_max": hp,
            # Kampfwerte werden EINMAL hier festgelegt und sind danach
            # gebunden — npc_action liest nur noch von hier (ADR-0003).
            "angriffsbonus": int(e.get("angriffsbonus", 0)),
            "schaden": e.get("schaden", "1d6"),
            "status": "active",
            "distanz": dist,
            "fernkampf": bool(e.get("fernkampf", False)),
            "gehandelt_runde": 0,
            "notiz": e.get("notiz", ""),
        })
    if not enemies:
        return "FEHLER: start_combat braucht mindestens einen Gegner."
    for e in enemies:
        try:
            roll_expr(e["schaden"])
        except ValueError:
            return (f"FEHLER: Ungueltiger Schadenswuerfel '{e['schaden']}' fuer "
                    f"'{e['name']}'. Format z.B. 1d6, 2d4+1.")
    gs["combat"] = {
        "round": 1,
        "phase": "pc_turn",
        "enemies": enemies,
        "pending_roll": None,
        "pc_gehandelt": False,
        "aktive_verteidigung": None,
        "log": [f"Kampf beginnt: {', '.join(e['name'] for e in enemies)}"],
    }
    return json.dumps({"status": "kampf_gestartet", "runde": 1,
                       "gegner": [{"name": e["name"], "hp": e["hp"],
                                   "distanz": e["distanz"]} for e in enemies]},
                      ensure_ascii=False)


def set_enemy_status(gs: dict, args: dict) -> str:
    """Flucht, Aufgabe oder Kampfunfaehigkeit eines Gegners. Nur so verlaesst
    ein Gegner den Kampf, ohne dass seine HP auf 0 fallen muessen."""
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    slug = gsm.slugify(args.get("gegner", ""))
    status = args.get("status", "")
    erlaubt = rules.RULEBOOK["combat_status_values"]
    if status not in erlaubt:
        return f"FEHLER: Status muss einer von {', '.join(erlaubt)} sein."
    for e in c["enemies"]:
        if e["slug"] == slug:
            e["status"] = status
            c["log"].append(f"{e['name']}: {status}")
            _maybe_next_round(gs, c)
            _set_phase(gs, c)
            return json.dumps({"gegner": e["name"], "status": status,
                               "kampffaehig": [x["name"] for x in _aktive_gegner(c)]},
                              ensure_ascii=False)
    return f"FEHLER: '{slug}' ist kein Gegner in diesem Kampf."


def request_skill_roll(gs: dict, args: dict) -> str:
    """Pflichtweg fuer JEDE Probe (ADR-0001). Blockiert bis zum W20 des
    Spielers. Im Kampf mit 'ziel' ist es ein Angriff (Schaden bei Erfolg)."""
    skill = args.get("skill", "")
    if skill not in rules.SKILLS:
        return (f"FEHLER: Unbekannter Skill '{skill}'. "
                f"Gueltig: {', '.join(sorted(rules.SKILLS))}")
    tier = args.get("schwierigkeit", "Durchschnitt")
    if rules.sg_for_tier(tier) is None:
        return f"FEHLER: Unbekannter Tier '{tier}'. Gueltig: {', '.join(rules.TIERS)}"
    pending = {
        "typ": "probe",
        "skill": skill,
        "tier": tier,
        "sg": rules.sg_for_tier(tier),
        "beschreibung": args.get("beschreibung", ""),
        "ziel": None,
        "schaden": None,
    }
    c = gs.get("combat")
    target = gsm.slugify(args.get("ziel", "")) if args.get("ziel") else None
    if target:
        if not c:
            return "FEHLER: 'ziel' nur im Kampf. Erst start_combat."
        if c.get("pc_gehandelt"):
            return "FEHLER: Der PC hat in dieser Runde bereits gehandelt."
        gegner = next((e for e in _aktive_gegner(c) if e["slug"] == target), None)
        if gegner is None:
            return f"FEHLER: '{target}' ist kein kampffaehiger Gegner."
        # Zonenmodell: Reichweite muss zur Entfernung passen (ADR-0003)
        dist = gegner.get("distanz", 0)
        if rules.ist_fernkampf(skill) and dist == 0:
            return (f"FEHLER: {skill} geht nicht im Nahkampf — '{gegner['name']}' "
                    f"steht direkt bei dir. Nahkampfwaffe waehlen.")
        if not rules.ist_fernkampf(skill) and dist > 0:
            return (f"FEHLER: '{gegner['name']}' ist {dist} Zone(n) entfernt — "
                    f"mit {skill} nicht erreichbar. Fernkampf nutzen oder warten.")
        pending["typ"] = "angriff"
        pending["ziel"] = target
        # Schaden kommt aus der Skill-Tabelle, nie vom LLM (ADR-0003)
        pending["schaden"] = rules.schaden_fuer_skill(skill)
    if c:
        if c.get("pending_roll"):
            return "FEHLER: Es steht bereits ein Wurf aus."
        c["pending_roll"] = pending
        _set_phase(gs, c)
    else:
        gs["pending_roll"] = pending
    return BLOCKING


def request_defense_roll(gs: dict, args: dict) -> str:
    """Aktive Verteidigung: ersetzt den Angriff des PC in dieser Runde. Ein
    Wurf gilt gegen ALLE Angriffe der folgenden Gegnerrunde (ADR-0003)."""
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    art = str(args.get("art", "")).lower()
    if art not in rules.RULEBOOK["verteidigung_arten"]:
        arten = ", ".join(rules.RULEBOOK["verteidigung_arten"])
        return f"FEHLER: art muss eine von {arten} sein."
    if c.get("pending_roll"):
        return "FEHLER: Es steht bereits ein Wurf aus."
    if c.get("pc_gehandelt"):
        return "FEHLER: Der PC hat in dieser Runde bereits gehandelt."
    c["pending_roll"] = {"typ": "verteidigung", "art": art,
                         "skill": rules.RULEBOOK["verteidigung_arten"][art]["skill"],
                         "beschreibung": args.get("beschreibung", "")}
    _set_phase(gs, c)
    return BLOCKING


def resolve_player_roll(gs: dict, roll: int) -> dict:
    """Spieler hat physisch gewuerfelt: Engine rechnet Probe, Ticks,
    Level-Ups und (bei Angriff) Schaden. Liefert das Tool-Result."""
    c = gs.get("combat")
    if c and c.get("pending_roll"):
        pr = c["pending_roll"]
    elif gs.get("pending_roll"):
        pr = gs["pending_roll"]
    else:
        raise ValueError("Kein ausstehender Wurf")

    # --- Aktive Verteidigung: ersetzt Angriff und passiven VW dieser Runde
    if pr.get("typ") == "verteidigung" and c:
        result = rules.resolve_defense(gs, pr["art"], roll)
        result["beschreibung"] = pr.get("beschreibung", "")
        c["aktive_verteidigung"] = {"wert": result["gesamt"], "runde": c["round"],
                                    "art": pr["art"], "kritisch": result["kritisch"]}
        c["pc_gehandelt"] = True
        c["pending_roll"] = None
        c["log"].append(f"PC verteidigt aktiv ({pr['art']}): {result['gesamt']}")
        _maybe_next_round(gs, c)
        _set_phase(gs, c)
        return result

    result = rules.resolve_probe(gs, pr["skill"], pr["tier"], roll)
    result["beschreibung"] = pr.get("beschreibung", "")

    if pr.get("ziel") and c:
        if result["erfolg"]:
            dmg = roll_expr(pr["schaden"] or "1d6")
            total_dmg = dmg["total"] * (2 if result["kritisch"] == "erfolg" else 1)
            result["schaden"] = total_dmg
            for e in c["enemies"]:
                if e["slug"] == pr["ziel"]:
                    e["hp"] = max(e["hp"] - total_dmg, 0)
                    result["ziel"] = e["name"]
                    result["ziel_hp"] = f"{e['hp']}/{e['hp_max']}"
                    if e["hp"] == 0:
                        e["status"] = "incapacitated"
                        result["ziel_kampfunfaehig"] = True
            c["log"].append(f"PC-Angriff auf {pr['ziel']}: {result['gesamt']} vs SG {result['sg']}, {total_dmg} Schaden")
        else:
            c["log"].append(f"PC verfehlt {pr['ziel']} ({result['gesamt']} vs SG {result['sg']})")
        c["pc_gehandelt"] = True

    if c:
        c["pending_roll"] = None
        if _maybe_next_round(gs, c):
            result["neue_runde"] = c["round"]
        _set_phase(gs, c)
        result["kampf"] = {"runde": c["round"],
                           "gegner": [{"name": e["name"], "hp": f"{e['hp']}/{e['hp_max']}",
                                       "distanz": e.get("distanz", 0)}
                                      for e in _aktive_gegner(c)]}
    else:
        gs["pending_roll"] = None
    return result


def npc_action(gs: dict, args: dict) -> str:
    """NPC-Angriff. Angriffsbonus und Schaden kommen aus dem bei start_combat
    festgelegten Stat-Block, nie aus den Argumenten (ADR-0003). Die Engine
    wuerfelt gegen den passiven VW — oder gegen die aktive Verteidigung."""
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    attacker = gsm.slugify(args.get("angreifer", ""))
    gegner = next((e for e in _aktive_gegner(c) if e["slug"] == attacker), None)
    if gegner is None:
        return f"FEHLER: '{attacker}' ist kein kampffaehiger Gegner."
    if gegner.get("gehandelt_runde") == c["round"]:
        return (f"FEHLER: {gegner['name']} hat in Runde {c['round']} bereits "
                f"gehandelt.")
    if gegner.get("distanz", 0) > 0 and not gegner.get("fernkampf"):
        return (f"FEHLER: {gegner['name']} ist noch {gegner['distanz']} Zone(n) "
                f"entfernt und kann nicht angreifen.")

    atk = roll_expr("1d20")
    atk_total = atk["total"] + gegner["angriffsbonus"]
    av = c.get("aktive_verteidigung")
    if av and av.get("runde") == c["round"]:
        ziel_wert, quelle = av["wert"], f"aktive Verteidigung ({av['art']})"
        if av.get("kritisch") == "erfolg":
            treffer = False
        elif av.get("kritisch") == "fehlschlag":
            treffer = True
        else:
            treffer = atk_total >= ziel_wert
    else:
        ziel_wert, quelle = rules.verteidigungswert(gs), "VW"
        treffer = atk_total >= ziel_wert

    gegner["gehandelt_runde"] = c["round"]
    result: dict = {"angreifer": gegner["name"], "wurf": atk_total,
                    "ziel_wert": ziel_wert, "gegen": quelle}
    if treffer:
        dmg = roll_expr(gegner["schaden"])
        hp_info = gsm.adjust_hp(gs, -dmg["total"])
        result.update({"treffer": True, "schaden": dmg["total"], **hp_info})
        c["log"].append(f"{gegner['name']} trifft PC: {dmg['total']} Schaden -> {hp_info['hp']} HP")
    else:
        result["treffer"] = False
        c["log"].append(f"{gegner['name']} verfehlt den PC ({atk_total} vs {ziel_wert})")

    if _maybe_next_round(gs, c):
        result["neue_runde"] = c["round"]
        result["gegner_stand"] = [{"name": e["name"], "distanz": e.get("distanz", 0)}
                                  for e in _aktive_gegner(c)]
    if rules.is_dead(gs):
        result["pc_tot"] = True
    elif rules.is_dying(gs):
        result["pc_sterbend"] = True
    _set_phase(gs, c)
    return json.dumps(result, ensure_ascii=False)


def end_combat(gs: dict, args: dict) -> str:
    c = _combat_required(gs)
    if isinstance(c, str):
        return c
    outcome = args.get("ausgang", "unentschieden")
    summary = {"ausgang": outcome, "runden": c["round"], "log": c["log"][-10:]}
    gs["combat"] = None
    return json.dumps(summary, ensure_ascii=False)


# --- Zeit & Flags -------------------------------------------------------

def advance_time(gs: dict, args: dict) -> str:
    minuten = int(args.get("minuten", 0))
    if not (0 < minuten <= rules.RULEBOOK["max_time_delta_minutes"]):
        return f"FEHLER: minuten muss 1-{rules.RULEBOOK['max_time_delta_minutes']} sein."
    gsm.advance_kalender(gs["kalender"], minuten)
    return json.dumps({"zeit": gsm.format_kalender(gs["kalender"])}, ensure_ascii=False)


def set_world_flag(gs: dict, args: dict) -> str:
    """Character-Scope-Aenderung an einem bestehenden Welt-Eintrag
    (ADR-0002): 'taverne_abgebrannt=true' statt Wiki-Edit im Spiel."""
    slug = args.get("slug", "")
    if wiki_index.get_entry_meta(slug) is None:
        return f"FEHLER: Welt-Eintrag '{slug}' existiert nicht."
    feld = args.get("feld", "").strip()
    if not feld:
        return "FEHLER: feld fehlt."
    gs.setdefault("world_flags", {}).setdefault(slug, {})[feld] = args.get("wert", True)
    return json.dumps({"flag": f"{slug}.{feld}", "wert": args.get("wert", True)},
                      ensure_ascii=False)


def rest(gs: dict, args: dict) -> str:
    """Natuerliche Rast: KON-Mod + Level LP pro Nacht (min 1),
    laengere Rast (>=3 Tage ohne Kampf) doppelt."""
    naechte = max(int(args.get("naechte", 1)), 1)
    heal_per_night = rules.natural_rest_heal(gs)
    if naechte >= rules.RULEBOOK["healing"]["extended_rest_days"]:
        heal_per_night *= rules.RULEBOOK["healing"]["extended_rest_multiplier"]
    info = gsm.adjust_hp(gs, heal_per_night * naechte)
    gs["stabilisiert"] = True
    gsm.advance_kalender(gs["kalender"], naechte * 24 * 60)
    return json.dumps({**info, "naechte": naechte,
                       "zeit": gsm.format_kalender(gs["kalender"])}, ensure_ascii=False)


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

VALID_TYPES = ("realm", "region", "city", "zone", "scene", "location",
               "character", "faction", "noble_house", "lore", "economy",
               "law", "chronicle", "flora", "fauna")
COORD_TYPES = ("realm", "region", "city", "zone", "scene", "location",
               "flora", "fauna")


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
    for key in ("region", "parent", "status", "tags", "produces", "imports",
                "zeitplan", "bounding_box"):
        if args.get(key):
            meta[key] = args[key]
    # Waehrend des Spiels erschaffene NPCs/Orte an den aktuellen Ort
    # ankern, damit sie nicht als Orphan im Netz haengen.
    if not args.get("links") and not meta.get("parent") and gs.get("location"):
        loc = gs["location"]["slug"]
        if loc != slug and wiki_index.get_entry_meta(loc):
            meta["links"] = [loc]
    elif args.get("links"):
        meta["links"] = args["links"]
    if etype in COORD_TYPES:
        meta["koordinaten"] = args.get("koordinaten") or auto_coords(
            slug, args.get("parent") or args.get("stadt") or args.get("region"))
    # Kleine, situative NPCs sind Character-Scope (ADR-0002); Promotion
    # macht sie bei Bedarf permanent. Alles andere ist sofort Weltkanon.
    if args.get("scope") == "charakter" and gs.get("slug"):
        meta["scope"] = "charakter"
        meta["pc"] = gs["slug"]
    write_world_entry(slug, meta, args.get("body", ""))
    return json.dumps({"angelegt": slug, "type": etype,
                       "scope": meta.get("scope", "welt")}, ensure_ascii=False)


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
    if meta is None and args.get("body"):
        # Unbekannter Ort mit Beschreibung: Eintrag miterzeugen statt zwei
        # Aufrufe zu verlangen (ADR-0003). Im Playtest wurde der Ortswechsel
        # genau deshalb uebersprungen — und der Kontext blieb auf der alten
        # Szene stehen, samt der dort anwesenden NPCs.
        parent = args.get("parent") or (gs.get("location") or {}).get("slug")
        neu = add_wiki_entry(gs, {"type": args.get("type", "location"), "name": name,
                                  "slug": slug, "body": args["body"],
                                  "parent": parent})
        if neu.startswith(("FEHLER", "WARNUNG")):
            return neu
        meta = wiki_index.get_entry_meta(slug)
    if meta is None:
        return (f"FEHLER: Ort '{slug}' hat keinen Wiki-Eintrag. Entweder 'body' "
                f"mitgeben (dann wird er angelegt) oder erst add_wiki_entry.")
    gs["location"] = {"slug": slug, "name": meta.get("name", name)}
    # Stack ueber die parent-Kette: Szene -> Zone -> Stadt -> Region -> Realm
    stack, cur, seen = [slug], meta, {slug}
    while True:
        parent = cur.get("parent") or (gsm.slugify(cur["region"]) if cur.get("region") else None)
        if not parent or parent in seen:
            break
        pmeta = wiki_index.get_entry_meta(parent)
        if pmeta is None:
            break
        stack.insert(0, parent)
        seen.add(parent)
        cur = pmeta
    gs["location_stack"] = stack
    if meta.get("koordinaten"):
        gs["position"] = {"x": meta["koordinaten"][0], "y": meta["koordinaten"][1]}
    gs["anwesende_npcs"] = []  # Ortswechsel leert manuelle Overrides
    return json.dumps({"ort": gs["location"]["name"], "stack": stack}, ensure_ascii=False)


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
    delta = int(args.get("delta", 0))
    was_dying = rules.is_dying(gs)
    info = gsm.adjust_hp(gs, delta)
    if delta > 0 and was_dying:
        gs["stabilisiert"] = True  # Heilung am Sterbenden stabilisiert
        info["stabilisiert"] = True
    return json.dumps({**info, "grund": args.get("grund", "")}, ensure_ascii=False)


def promote_entry(gs: dict, args: dict) -> str:
    """Character-Scope-Eintrag zum Weltkanon befoerdern (ADR-0002)."""
    slug = args.get("slug", "")
    entry = read_world_entry(slug)
    if entry is None:
        return f"FEHLER: '{slug}' existiert nicht."
    meta, _ = entry
    if meta.get("scope") != "charakter":
        return f"FEHLER: '{slug}' ist bereits Weltkanon."
    update_entry_meta(slug, {"scope": "welt", "pc": None})
    return json.dumps({"befoerdert": slug}, ensure_ascii=False)


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
    ruestung = args.get("ruestung")
    if ruestung is not None:
        ruestung = str(ruestung).lower()
        if ruestung not in rules.RULEBOOK["ruestung"]:
            typen = ", ".join(rules.RULEBOOK["ruestung"])
            return f"FEHLER: Unbekannter Ruestungstyp '{ruestung}'. Gueltig: {typen}"
    if existing:
        existing["menge"] = existing.get("menge", 1) + menge
        if ruestung is not None:
            existing["ruestung"] = ruestung
        if args.get("equipped") is not None:
            existing["equipped"] = bool(args["equipped"])
    else:
        item = {"name": name, "menge": menge, "notiz": args.get("notiz", "")}
        if ruestung is not None:
            item["ruestung"] = ruestung
        if args.get("equipped") is not None:
            item["equipped"] = bool(args["equipped"])
        inv.append(item)
    return json.dumps({"inventar": [f"{i['name']} x{i.get('menge', 1)}" for i in inv],
                       "vw": rules.verteidigungswert(gs)}, ensure_ascii=False)


def set_injury(gs: dict, args: dict) -> str:
    """Verletzung setzen oder heilen. Der DM benennt die Schwere, die Zahl
    kommt aus dem Rulebook (ADR-0003) — wie bei den Difficulty Tiers."""
    name = args.get("name", "").strip()
    if not name:
        return "FEHLER: name fehlt."
    verletzungen = gs.setdefault("verletzungen", [])
    if args.get("geheilt"):
        vorher = len(verletzungen)
        gs["verletzungen"] = [v for v in verletzungen if v["name"].lower() != name.lower()]
        if len(gs["verletzungen"]) == vorher:
            return f"FEHLER: Verletzung '{name}' nicht gefunden."
        return json.dumps({"geheilt": name, "vw": rules.verteidigungswert(gs)},
                          ensure_ascii=False)
    stufe = str(args.get("stufe", "")).lower()
    if stufe not in rules.RULEBOOK["verletzungsstufen"]:
        stufen = ", ".join(rules.RULEBOOK["verletzungsstufen"])
        return f"FEHLER: stufe muss eine von {stufen} sein."
    for v in verletzungen:
        if v["name"].lower() == name.lower():
            v["stufe"] = stufe
            break
    else:
        verletzungen.append({"name": name, "stufe": stufe})
    return json.dumps({"verletzung": name, "stufe": stufe,
                       "vw": rules.verteidigungswert(gs)}, ensure_ascii=False)


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
    # Im Kampf gesperrt (ADR-0003): freie Wuerfe waren der Weg, auf dem im
    # Playtest die gesamte Kampfmechanik umgangen wurde — Angriffe und Schaden
    # wurden gewuerfelt und in Prosa verrechnet, ohne je im Spielstand zu landen.
    if gs.get("combat"):
        return ("FEHLER: Im Kampf keine freien Wuerfe. Angriffe des PC ueber "
                "request_skill_roll (mit 'ziel'), Angriffe der Gegner ueber "
                "npc_action, aktive Verteidigung ueber request_defense_roll.")
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
    {"name": "roll_dice", "description": "Serverseitiger Wuerfelwurf fuer Weltereignisse ausserhalb des Kampfes (z.B. '2d6+1'). IM KAMPF GESPERRT — dort laufen PC-Angriffe ueber request_skill_roll (mit 'ziel'), Gegner-Angriffe ueber npc_action, Verteidigung ueber request_defense_roll.",
     "input_schema": _schema({"ausdruck": S}, ["ausdruck"])},
    {"name": "pay", "description": "PC bezahlt einen Betrag in Kupfer (kp). Backend macht das Wechselgeld ueber den Boersen-Gesamtwert. 1 gm = 10 sm = 100 kp.",
     "input_schema": _schema({"betrag_kp": I, "empfaenger": S}, ["betrag_kp"])},
    {"name": "receive_coins", "description": "PC erhaelt Muenzen (gm/sm/kp, jeweils >= 0).",
     "input_schema": _schema({"gm": I, "sm": I, "kp": I, "quelle": S})},
    {"name": "adjust_hp", "description": "HP des PC aendern (delta negativ = Schaden, positiv = Heilung). Heilung an einem Sterbenden stabilisiert ihn.",
     "input_schema": _schema({"delta": I, "grund": S}, ["delta"])},
    {"name": "advance_time", "description": "In-Game-Zeit voranschreiten lassen. Nach JEDER erzaehlten Aktion aufrufen (Gespraech 5-15 min, Fussweg je Distanz, Rast via rest).",
     "input_schema": _schema({"minuten": I}, ["minuten"])},
    {"name": "rest", "description": "Rast: heilt KON-Mod+Level LP pro Nacht (ab 3 Naechten doppelt), stellt die Zeit vor, stabilisiert.",
     "input_schema": _schema({"naechte": I})},
    {"name": "set_world_flag", "description": "Aenderung an einem BESTEHENDEN Welt-Eintrag in diesem Durchlauf (z.B. feld=abgebrannt, wert=true; feld=besitzer, wert='vex'). Nie update_wiki_entry fuer Spielfolgen nutzen.",
     "input_schema": _schema({"slug": S, "feld": S, "wert": {}}, ["slug", "feld"])},
    {"name": "promote_entry", "description": "Charakter-gebundenen Eintrag dauerhaft zum Weltkanon befoerdern.",
     "input_schema": _schema({"slug": S}, ["slug"])},
    {"name": "manage_inventory", "description": "Item ins Inventar legen oder entfernen (entfernen=true). Bei Ruestung/Schild 'ruestung' auf einen Typ setzen (keine/gepolstert/leder/kettenhemd/platte/schild) und 'equipped' — die Engine rechnet VW und Handicap daraus.",
     "input_schema": _schema({"name": S, "menge": I, "notiz": S, "entfernen": B,
                              "ruestung": S, "equipped": B}, ["name"])},
    {"name": "set_injury", "description": "Verletzung setzen (name + stufe: leicht/schwer/kritisch) oder heilen (geheilt=true). Gibt Wurf-Mali auf koerperliche Proben und den VW — die Zahl kennt die Engine, nenne nur die Stufe.",
     "input_schema": _schema({"name": S, "stufe": S, "geheilt": B}, ["name"])},
    {"name": "status_effect", "description": "Status-Effekt setzen oder entfernen (z.B. 'vergiftet', 'erschoepft').",
     "input_schema": _schema({"effekt": S, "entfernen": B}, ["effekt"])},
    {"name": "add_wiki_entry", "description": "Neuen Eintrag anlegen. Neue Orte sind sofort Weltkanon; situative Klein-NPCs mit scope=charakter anlegen. Bei Stadt-Institutionen 'stadt' angeben (kanonischer Slug). 'parent' = uebergeordneter Ort (Koordinaten werden daneben gesetzt).",
     "input_schema": _schema({"type": {"type": "string", "enum": list(VALID_TYPES)},
                              "name": S, "slug": S, "region": S, "stadt": S, "parent": S,
                              "status": S, "scope": {"type": "string", "enum": ["welt", "charakter"]},
                              "tags": ARR_S, "produces": ARR_S, "imports": ARR_S,
                              "koordinaten": {"type": "array", "items": I},
                              "body": S}, ["type", "name", "body"])},
    {"name": "update_wiki_entry", "description": "Bestehenden Welt-Eintrag erweitern (body_anhang) oder Status/Tags aendern.",
     "input_schema": _schema({"slug": S, "body_anhang": S, "status": S, "tags": ARR_S}, ["slug"])},
    {"name": "set_location", "description": "PC bewegt sich an einen Ort. PFLICHT bei jedem Ortswechsel, sonst bleibt der Kontext auf der alten Szene stehen (samt der dort anwesenden NPCs). Existiert der Ort noch nicht, 'body' mitgeben — dann wird er angelegt und sofort betreten.",
     "input_schema": _schema({"slug": S, "name": S, "body": S, "type": S, "parent": S}, ["name"])},
    {"name": "npc_present", "description": "NPC betritt (oder verlaesst, entfernen=true) die Szene.",
     "input_schema": _schema({"slug": S, "name": S, "entfernen": B})},
    {"name": "manage_quest", "description": "Quest anlegen (aktion=neu, titel) oder aktualisieren (aktion=update, id, status: offen/aktiv/abgeschlossen/gescheitert, entities: verknuepfte Wiki-Slugs).",
     "input_schema": _schema({"aktion": {"type": "string", "enum": ["neu", "update"]},
                              "titel": S, "id": S, "status": S, "entities": ARR_S}, ["aktion"])},
    {"name": "pin_entry", "description": "Wiki-Eintrag dauerhaft in den Kontext pinnen (oder entfernen=true).",
     "input_schema": _schema({"slug": S, "entfernen": B}, ["slug"])},
    {"name": "append_journal", "description": "Wichtiges Ereignis ins PC-Journal schreiben (Persistenz ueber Sessions).",
     "input_schema": _schema({"text": S}, ["text"])},
    {"name": "request_skill_roll", "description": "PFLICHT fuer jede Aktion mit unsicherem Ausgang: Skill + Tier (Sehr Leicht/Leicht/Durchschnitt/Schwer/Sehr Schwer/Heroisch/Extrem) benennen. BLOCKIERT bis der Spieler seinen W20 eingibt; Engine rechnet Ergebnis, Crits und Ticks. Im Kampf mit 'ziel' ist es ein Angriff — den Schadenswuerfel kennt die Engine aus dem Kampf-Skill, nenne ihn nicht.",
     "input_schema": _schema({"skill": S, "schwierigkeit": S, "beschreibung": S,
                              "ziel": S}, ["skill", "schwierigkeit"])},
    {"name": "request_defense_roll", "description": "Aktive Verteidigung des PC, wenn er sie ansagt: art=ausweichen (Akrobatik) oder parade (Parade, nutzt Ruestung). ERSETZT seinen Angriff in dieser Runde; der Wurf gilt gegen ALLE Gegnerangriffe der Runde statt des passiven VW. BLOCKIERT bis zum W20.",
     "input_schema": _schema({"art": S, "beschreibung": S}, ["art"])},
    {"name": "start_combat", "description": "Kampf starten. Pro Gegner: name, hp, angriffsbonus, schaden (Wuerfel, z.B. 1d6), distanz (0=Nahkampf, bis 3=weit weg), fernkampf (true bei Bogenschuetzen), notiz. Angriffswerte gelten fuer den ganzen Kampf und sind danach nicht mehr aenderbar.",
     "input_schema": _schema({"gegner": {"type": "array", "items": _schema(
         {"name": S, "hp": I, "angriffsbonus": I, "schaden": S, "distanz": I,
          "fernkampf": B, "notiz": S}, ["name"])}}, ["gegner"])},
    {"name": "npc_action", "description": "Angriff eines Gegners. Engine wuerfelt 1d20 plus seinen festgelegten Angriffsbonus gegen VW bzw. aktive Verteidigung und wendet seinen festgelegten Schaden an. Jeder Gegner einmal pro Runde; Nahkaempfer muessen erst aufschliessen (distanz 0). Die Runde schaltet die Engine selbst weiter.",
     "input_schema": _schema({"angreifer": S, "beschreibung": S}, ["angreifer"])},
    {"name": "set_enemy_status", "description": "Gegner verlaesst den Kampf oder aendert seinen Zustand: active/incapacitated/fled/surrendered/dead. Fuer Flucht und Aufgabe — nicht fuer Schaden (der laeuft ueber Angriffe).",
     "input_schema": _schema({"gegner": S, "status": S}, ["gegner", "status"])},
    {"name": "end_combat", "description": "Kampf beenden. ausgang: sieg/niederlage/flucht/uebergabe/verhandlung.",
     "input_schema": _schema({"ausgang": S}, ["ausgang"])},
]

HANDLERS = {
    "roll_dice": roll_dice_tool,
    "pay": pay,
    "receive_coins": receive_coins,
    "adjust_hp": adjust_hp_tool,
    "advance_time": advance_time,
    "rest": rest,
    "set_world_flag": set_world_flag,
    "promote_entry": promote_entry,
    "manage_inventory": manage_inventory,
    "set_injury": set_injury,
    "status_effect": status_effect,
    "add_wiki_entry": add_wiki_entry,
    "update_wiki_entry": update_wiki_entry,
    "set_location": set_location,
    "npc_present": npc_present,
    "manage_quest": manage_quest,
    "pin_entry": pin_entry,
    "append_journal": journal_tool,
    "request_skill_roll": request_skill_roll,
    "request_defense_roll": request_defense_roll,
    "start_combat": start_combat,
    "npc_action": npc_action,
    "set_enemy_status": set_enemy_status,
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
