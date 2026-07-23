"""Gamestate: per-PC JSON-Spielstand mit atomaren Writes.

Enthaelt XP-Schwellen, Level-Up, HP-Status-Tags und die komplette
Coin-Math (1 gm = 10 sm = 100 kp). Zahlungen laufen immer ueber
Kupfer-Gesamtwert mit Backend-Wechselgeld — nie direkte Abzuege von
einzelnen Muenzsorten (das war der alte Currency-Bug).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(os.environ.get("NOVATERRUM_DATA", Path(__file__).resolve().parent.parent))
WIKI_DIR = BASE_DIR / "wiki"
PC_DIR = WIKI_DIR / "pc"
SETTINGS_PATH = BASE_DIR / "data" / "settings.json"

# --- Muenzen ------------------------------------------------------------
KP_PER_SM = 10
KP_PER_GM = 100


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    """Kanonischer Slug: Umlaute transkribiert, lowercase, Bindestriche."""
    s = name.strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unbenannt"


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- Coin-Math ----------------------------------------------------------

def total_copper(coins: dict) -> int:
    return coins.get("gm", 0) * KP_PER_GM + coins.get("sm", 0) * KP_PER_SM + coins.get("kp", 0)


def consolidate_coins(total_kp: int) -> dict:
    """Gesamt-Kupfer in die kompakteste Stueckelung umrechnen."""
    if total_kp < 0:
        raise ValueError("Negativer Muenzwert")
    return {
        "gm": total_kp // KP_PER_GM,
        "sm": (total_kp % KP_PER_GM) // KP_PER_SM,
        "kp": total_kp % KP_PER_SM,
    }


def pay_copper(coins: dict, amount_kp: int) -> dict:
    """Zahlt amount_kp aus dem Boersen-Gesamtwert. Wirft bei Unterdeckung.

    Wechselgeld macht das Backend: Restwert wird neu gestueckelt.
    """
    if amount_kp < 0:
        raise ValueError("Negativer Zahlbetrag")
    have = total_copper(coins)
    if amount_kp > have:
        raise ValueError(f"Nicht genug Muenzen: habe {have} kp, brauche {amount_kp} kp")
    return consolidate_coins(have - amount_kp)


def add_coins(coins: dict, gm: int = 0, sm: int = 0, kp: int = 0) -> dict:
    if min(gm, sm, kp) < 0:
        raise ValueError("Negative Muenzmengen — zum Zahlen pay_copper nutzen")
    return consolidate_coins(total_copper(coins) + gm * KP_PER_GM + sm * KP_PER_SM + kp)


def format_coins(coins: dict) -> str:
    parts = []
    for key, label in (("gm", "gm"), ("sm", "sm"), ("kp", "kp")):
        v = coins.get(key, 0)
        if v:
            parts.append(f"{v} {label}")
    return " ".join(parts) if parts else "0 kp"


# --- HP-Status ----------------------------------------------------------

def hp_status_tag(hp: int, hp_max: int) -> str:
    if hp <= 0:
        return "todgeweiht"
    ratio = hp / max(hp_max, 1)
    if ratio >= 0.9:
        return "unversehrt"
    if ratio >= 0.6:
        return "angeschlagen"
    if ratio >= 0.3:
        return "verwundet"
    return "schwer verwundet"


# --- Kalender (12 Monate x 30 Tage, Imperialer Kalender) ----------------

def default_kalender() -> dict:
    return {"jahr": 743, "monat": 4, "tag": 12, "stunde": 9, "minute": 0}


def advance_kalender(kal: dict, minuten: int) -> dict:
    total = kal["minute"] + minuten
    kal["minute"] = total % 60
    total_h = kal["stunde"] + total // 60
    kal["stunde"] = total_h % 24
    total_d = kal["tag"] + total_h // 24
    kal["tag"] = (total_d - 1) % 30 + 1
    total_m = kal["monat"] + (total_d - 1) // 30
    kal["monat"] = (total_m - 1) % 12 + 1
    kal["jahr"] += (total_m - 1) // 12
    return kal


def format_kalender(kal: dict) -> str:
    return (f"{kal['tag']:02d}.{kal['monat']:02d}.{kal['jahr']} IC, "
            f"{kal['stunde']:02d}:{kal['minute']:02d}")


# --- PC-Gamestate -------------------------------------------------------

def default_gamestate(name: str, slug: str) -> dict:
    from . import rules
    attribute = {a: 13 for a in rules.ATTRS}  # 6x13 = 78 (voller Pool)
    hp = rules.max_hp_for(attribute, 1)
    return {
        "slug": slug,
        "name": name,
        "klasse": "Krieger",
        "hintergrund": "",
        "level": 1,
        "skill_ups": 0,
        "attr_punkte_frei": 0,
        "hp": hp,
        "hp_max": hp,
        "attribute": attribute,          # STR/GES/KON/INT/WEI/CHA, 1-20
        "skills": {},                    # {name: {wert, ticks}}
        "inventar": [],
        "coins": consolidate_coins(500),  # rulebook starting_gold (Kupfer)
        "status_effekte": [],
        "verletzungen": [],              # [{name, modifikator}]
        "stabilisiert": False,
        "location": None,                # {"slug": ..., "name": ...}
        "location_stack": [],            # Realm -> Region -> Stadt -> Zone -> Szene
        "position": {"x": 2380000, "y": 1200000},
        "kalender": default_kalender(),
        "anwesende_npcs": [],            # Slugs (manuelle Overrides)
        "quests": [],
        "pinned": [],
        "world_flags": {},               # {entity_slug: {feld: wert}} — Character-Scope
        "combat": None,
        "erstellt": now_iso(),
        "aktualisiert": now_iso(),
    }


def pc_path(slug: str) -> Path:
    return PC_DIR / slug / "gamestate.json"


def load_pc(slug: str) -> dict | None:
    return read_json(pc_path(slug))


def save_pc(gs: dict) -> None:
    gs["aktualisiert"] = now_iso()
    gs["hp_status"] = hp_status_tag(gs["hp"], gs["hp_max"])
    atomic_write_json(pc_path(gs["slug"]), gs)


def create_pc(name: str, klasse: str | None = None, hintergrund: str = "",
              attribute: dict | None = None, skills: dict | None = None) -> dict:
    """PC anlegen. Mit attribute/skills laeuft die Punktepool-Validierung
    (78 Attributpunkte, 80 Skillpunkte); ohne gibt es Standardwerte."""
    from . import rules
    slug = slugify(name)
    if load_pc(slug) is not None:
        raise ValueError(f"PC '{slug}' existiert bereits")
    gs = default_gamestate(name, slug)
    if klasse:
        if klasse not in rules.CLASSES:
            raise ValueError(f"Unbekannte Klasse: {klasse}")
        gs["klasse"] = klasse
    gs["hintergrund"] = hintergrund
    if attribute is not None or skills is not None:
        errors = rules.validate_creation(attribute or {}, skills or {})
        if errors:
            raise ValueError("; ".join(errors))
        gs["attribute"] = attribute
        gs["skills"] = {n: {"wert": w, "ticks": 0} for n, w in (skills or {}).items() if w > 0}
        gs["hp"] = gs["hp_max"] = rules.max_hp_for(attribute, 1)
    for item in rules.CLASSES[gs["klasse"]]["starting_items"]:
        gs["inventar"].append({"name": item, "menge": 1, "equipped": True})
    set_starting_location(gs)
    save_pc(gs)
    return gs


def set_starting_location(gs: dict) -> None:
    """Setzt den Startort aus world/data/world_constants.json, sofern der
    zugehoerige Wiki-Eintrag existiert (Seed gelaufen). Sonst location=None
    und der DM waehlt selbst. Baut den location_stack ueber die parent-Kette."""
    from . import wiki_index
    # Autorenwelt liegt versioniert im Repo (nicht im Laufzeit-BASE_DIR).
    repo_root = Path(__file__).resolve().parent.parent
    constants = read_json(repo_root / "world" / "data" / "world_constants.json", {})
    start = (((constants.get("world") or {}).get("starting_state")) or {})
    scene_id = start.get("location_scene_id")
    if not scene_id:
        return
    slug = slugify(scene_id)
    meta = wiki_index.get_entry_meta(slug)
    if meta is None:
        return
    gs["location"] = {"slug": slug, "name": meta.get("name", slug)}
    stack, cur, seen = [slug], meta, {slug}
    while True:
        parent = cur.get("parent") or (slugify(cur["region"]) if cur.get("region") else None)
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
    coord = start.get("coordinate")
    if coord:
        gs["position"] = {"x": coord["x"], "y": coord["y"]}


def list_pcs() -> list[dict]:
    if not PC_DIR.exists():
        return []
    result = []
    for d in sorted(PC_DIR.iterdir()):
        gs = read_json(d / "gamestate.json")
        if gs:
            result.append({"slug": gs["slug"], "name": gs["name"],
                           "level": gs["level"], "hp": gs["hp"], "hp_max": gs["hp_max"]})
    return result


def adjust_hp(gs: dict, delta: int) -> dict:
    """HP aendern. Bei Schaden faellt die Stabilisierung weg; unter 0
    ist der PC sterbend (Blutung), bei -10 tot (rules.is_dead)."""
    gs["hp"] = max(min(gs["hp"] + delta, gs["hp_max"]), -10)
    if delta < 0:
        gs["stabilisiert"] = False
    return {"hp": gs["hp"], "hp_max": gs["hp_max"],
            "status": hp_status_tag(gs["hp"], gs["hp_max"]),
            "sterbend": gs["hp"] <= 0}


# --- Settings (always-read-from-disk gegen Settings-Race) ---------------

DEFAULT_SETTINGS = {
    "model": "or/anthropic/claude-sonnet-4.5",
    "active_pc_slug": None,
    "history_window": 30,
}


def load_settings() -> dict:
    """Immer frisch von Disk lesen — kein Modul-Cache (alter Race-Bug)."""
    s = read_json(SETTINGS_PATH, {})
    merged = {**DEFAULT_SETTINGS, **(s or {})}
    return merged


def save_settings(patch: dict) -> dict:
    current = load_settings()
    current.update({k: v for k, v in patch.items() if k in DEFAULT_SETTINGS})
    atomic_write_json(SETTINGS_PATH, current)
    return current


def set_active_pc_slug(slug: str | None) -> dict:
    return save_settings({"active_pc_slug": slug})
