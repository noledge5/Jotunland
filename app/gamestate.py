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

# --- XP / Level ---------------------------------------------------------
# Schwelle fuer Level n (Index n-1). Level 1 startet bei 0.
XP_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500,
                 5500, 6600, 7800, 9100, 10500]
MAX_LEVEL = len(XP_THRESHOLDS)

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


# --- Level --------------------------------------------------------------

def level_for_xp(xp: int) -> int:
    level = 1
    for i, threshold in enumerate(XP_THRESHOLDS, start=1):
        if xp >= threshold:
            level = i
    return min(level, MAX_LEVEL)


def xp_to_next(xp: int) -> int | None:
    lvl = level_for_xp(xp)
    if lvl >= MAX_LEVEL:
        return None
    return XP_THRESHOLDS[lvl] - xp


# --- PC-Gamestate -------------------------------------------------------

def default_gamestate(name: str, slug: str) -> dict:
    return {
        "slug": slug,
        "name": name,
        "level": 1,
        "xp": 0,
        "hp": 12,
        "hp_max": 12,
        "attribute": {"staerke": 0, "geschick": 0, "verstand": 0, "wille": 0},
        "inventar": [],
        "coins": {"gm": 0, "sm": 2, "kp": 5},
        "status_effekte": [],
        "location": None,           # {"slug": ..., "name": ...}
        "location_stack": [],       # Pfad von Region bis aktueller Ort
        "anwesende_npcs": [],       # Slugs
        "quests": [],               # {id, titel, status, entities}
        "pinned": [],               # Wiki-Slugs, immer im Kontext
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


def create_pc(name: str) -> dict:
    slug = slugify(name)
    if load_pc(slug) is not None:
        raise ValueError(f"PC '{slug}' existiert bereits")
    gs = default_gamestate(name, slug)
    save_pc(gs)
    return gs


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


def add_xp(gs: dict, amount: int) -> dict:
    """XP gutschreiben. Liefert {neue_xp, level, level_up: bool, hp_bonus}."""
    if amount < 0:
        raise ValueError("Negatives XP")
    old_level = gs["level"]
    gs["xp"] += amount
    new_level = level_for_xp(gs["xp"])
    hp_bonus = 0
    if new_level > old_level:
        hp_bonus = 3 * (new_level - old_level)
        gs["hp_max"] += hp_bonus
        gs["hp"] = gs["hp_max"]  # Level-Up heilt voll
        gs["level"] = new_level
    return {"xp": gs["xp"], "level": gs["level"],
            "level_up": new_level > old_level, "hp_bonus": hp_bonus,
            "bis_naechstes_level": xp_to_next(gs["xp"])}


def adjust_hp(gs: dict, delta: int) -> dict:
    gs["hp"] = max(min(gs["hp"] + delta, gs["hp_max"]), -10)
    return {"hp": gs["hp"], "hp_max": gs["hp_max"],
            "status": hp_status_tag(gs["hp"], gs["hp_max"])}


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
