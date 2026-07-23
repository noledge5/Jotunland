"""Regel-Engine: laedt rulebook.json + skills.json und rechnet Proben.

Kanonische Regelquelle ist CONTEXT.md (Glossar) + DM.md. Diese Datei
implementiert: Attributsmodifikatoren, Skill-Boni, Probenaufloesung mit
Crits, Tick-Steigerung (Learning-by-Doing), Level-Ups ueber Skill-Ups,
Verteidigungswert und Sterberegeln.
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"

with open(CONFIG_DIR / "rulebook.json", encoding="utf-8") as f:
    RULEBOOK = json.load(f)
with open(CONFIG_DIR / "skills.json", encoding="utf-8") as f:
    _SKILLS_RAW = json.load(f)

SKILLS = {s["name"]: s for s in _SKILLS_RAW["skills"]}
CLASSES = _SKILLS_RAW["classes"]
ATTRS = ("STR", "GES", "KON", "INT", "WEI", "CHA")
TIERS = RULEBOOK["difficulty_tiers"]


def attr_mod(value: int) -> int:
    return (value - 10) // 2


def skill_bonus(wert: int) -> int:
    return wert // 10


def tick_threshold(wert: int) -> int:
    """Noetige Ticks fuer +1 Skillpunkt, abhaengig vom Niveau."""
    best = 3
    for lo, ticks in sorted((int(k), v) for k, v in RULEBOOK["tick_thresholds"].items()):
        if wert >= lo:
            best = ticks
    return best


def leit_mod(gs: dict, skill_name: str) -> int:
    """Hoeherer Modifikator der Leit-Attribute des Skills."""
    sdef = SKILLS.get(skill_name)
    if not sdef:
        return 0
    return max(attr_mod(gs["attribute"].get(a, 10)) for a in sdef["attrs"])


def sg_for_tier(tier: str) -> int | None:
    return TIERS.get(tier)


def get_skill(gs: dict, skill_name: str) -> dict:
    return gs["skills"].setdefault(skill_name, {"wert": 0, "ticks": 0})


def award_tick(gs: dict, skill_name: str) -> dict:
    """Tick vergeben (bei jeder Probe, egal ob Erfolg). Liefert
    {skill_up: bool, neuer_wert, level_up: bool, level}."""
    sk = get_skill(gs, skill_name)
    sk["ticks"] += RULEBOOK["ticks_per_action"]
    result = {"skill_up": False, "neuer_wert": sk["wert"], "level_up": False,
              "level": gs["level"]}
    if sk["ticks"] >= tick_threshold(sk["wert"]) and sk["wert"] < 100:
        sk["ticks"] = 0
        sk["wert"] += 1
        gs["skill_ups"] = gs.get("skill_ups", 0) + 1
        result.update({"skill_up": True, "neuer_wert": sk["wert"]})
        new_level = 1 + gs["skill_ups"] // RULEBOOK["skill_ups_for_char_level"]
        if new_level > gs["level"]:
            gs["level"] = new_level
            gs["hp_max"] += RULEBOOK["hp_per_level"]
            gs["hp"] = min(gs["hp"] + RULEBOOK["hp_per_level"], gs["hp_max"])
            gs["attr_punkte_frei"] = gs.get("attr_punkte_frei", 0) + RULEBOOK["attr_point_per_char_level"]
            result.update({"level_up": True, "level": new_level})
    return result


def resolve_probe(gs: dict, skill_name: str, tier: str, roll: int) -> dict:
    """Probenaufloesung: W20 + Leit-Attributsmod + Skill-Bonus vs SG.
    Nat 20 = krit. Erfolg, Nat 1 = krit. Fehlschlag. Tick immer."""
    sg = sg_for_tier(tier)
    if sg is None:
        raise ValueError(f"Unbekannter Difficulty Tier: {tier}")
    sk = get_skill(gs, skill_name)
    mod = leit_mod(gs, skill_name)
    bonus = skill_bonus(sk["wert"])
    total = roll + mod + bonus
    if roll >= RULEBOOK["critical_success_roll"]:
        success, crit = True, "erfolg"
    elif roll <= RULEBOOK["critical_failure_roll"]:
        success, crit = False, "fehlschlag"
    else:
        success, crit = total >= sg, None
    tick = award_tick(gs, skill_name)
    return {"skill": skill_name, "tier": tier, "sg": sg, "wurf": roll,
            "attribut_mod": mod, "skill_bonus": bonus, "gesamt": total,
            "erfolg": success, "kritisch": crit, "tick": tick}


def verteidigungswert(gs: dict) -> int:
    """VW = 10 + GES-Mod + Schild-Bonus (equipped Schild-Item)."""
    vw = RULEBOOK["vw_base"] + attr_mod(gs["attribute"].get("GES", 10))
    for item in gs.get("inventar", []):
        if item.get("equipped") and "schild" in item["name"].lower():
            vw += 2
    for verl in gs.get("verletzungen", []):
        vw += min(verl.get("modifikator", 0), 0)
    return vw


def max_hp_for(attribute: dict, level: int) -> int:
    return (RULEBOOK["hp_base"] + attr_mod(attribute.get("KON", 10))
            + RULEBOOK["hp_per_level"] * (level - 1))


# --- Charaktererstellung -----------------------------------------------

def validate_creation(attribute: dict, skills: dict) -> list[str]:
    """Punktepool-Validierung. Liefert Fehlerliste (leer = ok)."""
    errors = []
    if set(attribute) != set(ATTRS):
        errors.append(f"Attribute muessen genau {', '.join(ATTRS)} sein")
        return errors
    for a, v in attribute.items():
        if not (RULEBOOK["attr_start_min"] <= v <= RULEBOOK["attr_start_max"]):
            errors.append(f"{a}={v} ausserhalb {RULEBOOK['attr_start_min']}-{RULEBOOK['attr_start_max']}")
    if sum(attribute.values()) != RULEBOOK["attr_start_pool"]:
        errors.append(f"Attributpunkte: {sum(attribute.values())} statt {RULEBOOK['attr_start_pool']}")
    for name, wert in skills.items():
        if name not in SKILLS:
            errors.append(f"Unbekannter Skill: {name}")
        elif not (0 <= wert <= RULEBOOK["skill_start_max"]):
            errors.append(f"Skill {name}={wert} ausserhalb 0-{RULEBOOK['skill_start_max']}")
    if sum(skills.values()) > RULEBOOK["skill_start_pool"]:
        errors.append(f"Skillpunkte: {sum(skills.values())} > {RULEBOOK['skill_start_pool']}")
    return errors


# --- Sterben / Heilung --------------------------------------------------

def is_dying(gs: dict) -> bool:
    return gs["hp"] <= RULEBOOK["dying"]["ko_threshold"]


def is_dead(gs: dict) -> bool:
    return gs["hp"] <= RULEBOOK["dying"]["death_threshold"]


def bleed(gs: dict) -> int:
    """Blutung pro Kampfrunde wenn sterbend. Liefert neue HP."""
    if is_dying(gs) and not gs.get("stabilisiert"):
        gs["hp"] -= RULEBOOK["dying"]["bleed_per_round"]
    return gs["hp"]


def natural_rest_heal(gs: dict) -> int:
    """LP pro Nacht natuerlicher Rast: KON-Mod + Level, min 1."""
    return max(attr_mod(gs["attribute"].get("KON", 10)) + gs["level"],
               RULEBOOK["healing"]["natural_rest_min"])
