import json
import os
import math
from db import get_db

_world_constants = None


def _load_world_constants():
    global _world_constants
    if _world_constants is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'world', 'data', 'world_constants.json')
        try:
            with open(path) as f:
                data = json.load(f)
            _world_constants = data['world']['constants']['layer_a_text']
        except Exception:
            _world_constants = (
                "Avarr ist eine düstere Low-Fantasy-Welt unter dem Ostimperium. "
                "Essenz ist real, aber selten. Die Götter schweigen. Es ist das Jahr 743 IC."
            )
    return _world_constants


def get_layer_a():
    return _load_world_constants()


def _get_scene_flags(conn, playthrough_id, scene_id, entity_type='scene'):
    rows = conn.execute(
        "SELECT flag_name, flag_value FROM world_state_flags "
        "WHERE playthrough_id=? AND entity_type=? AND entity_id=?",
        (playthrough_id, entity_type, scene_id)
    ).fetchall()
    return {r['flag_name']: r['flag_value'] for r in rows}


def _append_flags(text, flags):
    if not flags:
        return text
    flag_lines = "; ".join(f"{k}={v}" for k, v in flags.items())
    return text + f" [Zustand: {flag_lines}]"


def _attr_mod(value: int) -> int:
    return math.floor((value - 10) / 2)


def _format_mod(m: int) -> str:
    return f"+{m}" if m >= 0 else str(m)


def get_active_context(playthrough_id, engine_result):
    """Build Layer E: NPCs present, player stats, recent turns, engine result."""
    conn = get_db()

    player = conn.execute(
        "SELECT * FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return "Kein Spieler gefunden."

    # Attributes
    attrs_rows = conn.execute(
        "SELECT attr_name, value FROM player_attributes WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchall()
    attrs = {r['attr_name']: r['value'] for r in attrs_rows}
    attr_order = ['STR', 'GES', 'KON', 'INT', 'WEI', 'CHA']
    attrs_compact = " ".join(
        f"{a}:{attrs.get(a, 10)}({_format_mod(_attr_mod(attrs.get(a, 10)))})"
        for a in attr_order
    )

    # Skills with tick progress
    skills = conn.execute(
        "SELECT skill_name, level, ticks FROM player_skills WHERE playthrough_id=? AND level > 0 ORDER BY skill_name",
        (playthrough_id,)
    ).fetchall()

    def tick_threshold(skill_value):
        thresholds = [(0, 3), (21, 5), (41, 8), (61, 12), (81, 20)]
        result = 3
        for low, th in thresholds:
            if skill_value >= low:
                result = th
        return result

    skills_text = ", ".join(
        f"{s['skill_name']} {s['level']} [{s['ticks']}/{tick_threshold(s['level'])} Ticks]"
        for s in skills
    ) or "keine"

    # Equipped items
    equipped = conn.execute(
        "SELECT item_name FROM inventory WHERE playthrough_id=? AND equipped=1",
        (playthrough_id,)
    ).fetchall()
    equipped_text = ", ".join(e['item_name'] for e in equipped) or "nichts ausgerüstet"

    # Inventory
    inv = conn.execute(
        "SELECT item_name, quantity FROM inventory WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchall()
    inv_text = ", ".join(f"{i['item_name']}x{i['quantity']}" for i in inv) or "leer"

    # Injuries
    injuries = conn.execute(
        "SELECT injury_name, affected_skill, modifier FROM injuries "
        "WHERE playthrough_id=? AND entity_type='player'",
        (playthrough_id,)
    ).fetchall()
    injuries_text = "; ".join(
        f"{i['injury_name']} ({i['affected_skill']} {i['modifier']:+d})" for i in injuries
    ) or "keine"

    # NPCs in scene
    from engine import get_current_scene_npcs
    npcs = get_current_scene_npcs(playthrough_id)
    npc_lines = []
    for npc in npcs:
        rel_score = npc.get('relation_score', npc.get('relation_score_default', 0)) or 0
        met = npc.get('met', 0)
        rel_text = f"rel={rel_score:+d}" if met else "Fremder"
        npc_lines.append(f"  - {npc['name']} ({npc['role']}): {rel_text}. {npc.get('description', '')[:80]}")
    npcs_text = "\n".join(npc_lines) if npc_lines else "  (keine bemerkenswerten NSCs anwesend)"

    # Recent turns (last 4)
    turns = conn.execute(
        "SELECT turn_number, player_input, narration, in_game_timestamp FROM turn_log "
        "WHERE playthrough_id=? AND narration != '' ORDER BY turn_number DESC LIMIT 4",
        (playthrough_id,)
    ).fetchall()
    turns_text_parts = []
    for t in reversed(turns):
        turns_text_parts.append(f"[{t['in_game_timestamp']}] Spieler: {t['player_input']}\nErzähler: {t['narration']}")
    turns_text = "\n---\n".join(turns_text_parts) if turns_text_parts else "(Spielbeginn)"

    # Session synopses
    rb_path = os.path.join(os.path.dirname(__file__), 'config', 'rulebook.json')
    max_synopses = 2
    try:
        with open(rb_path) as f:
            rb = json.load(f)
        max_synopses = rb.get('max_synopses_in_context', 2)
    except Exception:
        pass

    synopses = conn.execute(
        "SELECT summary FROM session_log WHERE playthrough_id=? ORDER BY id DESC LIMIT ?",
        (playthrough_id, max_synopses)
    ).fetchall()
    synopses_text = "\n".join(s['summary'] for s in reversed(synopses)) if synopses else ""

    # Active quests
    quests = conn.execute(
        "SELECT title, description FROM quests WHERE playthrough_id=? AND status='active'",
        (playthrough_id,)
    ).fetchall()
    quests_text = "; ".join(q['title'] for q in quests) or "keine"

    conn.close()

    # Format engine result (exclude pending_roll info)
    engine_text = ""
    if engine_result:
        sr = engine_result.get('skill_result')
        if sr:
            outcome_de = sr.get('outcome', '?')
            dice = sr.get('dice_result', '?')
            mod = sr.get('modifier', 0)
            total = sr.get('total', '?')
            sg = sr.get('sg', sr.get('dc', '?'))
            engine_text = (
                f"Fertigkeitsprobe: {sr.get('skill', '?')} (SG {sg}, Stufe {sr.get('difficulty_tier', '?')})\n"
                f"Wurf: {dice} + {mod} = {total} → {outcome_de}"
            )
            tick = engine_result.get('tick_result')
            if tick:
                if tick.get('skill_up'):
                    engine_text += f"\nSkill-Up! {sr.get('skill', '?')} → {tick['new_value']}"
                else:
                    engine_text += f"\nTick: {tick['ticks']}/{tick['ticks_needed']}"
            if engine_result.get('leveled_up'):
                engine_text += "\nCHARACTER LEVEL UP!"
        elif engine_result.get('needs_roll') is False:
            engine_text = "Keine Fertigkeitsprobe erforderlich."
        else:
            # Don't expose pending_roll internals to narrator
            safe = {k: v for k, v in engine_result.items() if k != 'pending_roll'}
            engine_text = json.dumps(safe)

    ts = f"{player['in_game_year']}-{player['in_game_month']:02d}-{player['in_game_day']:02d} {player['in_game_hour']:02d}:{player['in_game_minute']:02d}"

    player_summary = (
        f"Name: {player['name']}, Klasse: {player['class']}, Level: {player['level']}, "
        f"LP: {player['hp_current']}/{player['hp_max']}, Gold: {player['gold']}\n"
        f"Attribute: {attrs_compact}\n"
        f"Fertigkeiten: {skills_text}\n"
        f"Ausgerüstet: {equipped_text}\n"
        f"Inventar: {inv_text}\n"
        f"Verletzungen: {injuries_text}\n"
        f"Aktive Quests: {quests_text}\n"
        f"Im Kampf: {'ja' if player['in_combat'] else 'nein'}\n"
        f"Aktuelle Zeit: {ts}"
    )

    layer_e = f"""=== SPIELER ===
{player_summary}

=== ANWESENDE NSCs ===
{npcs_text}

=== JÜNGSTE EREIGNISSE ===
{synopses_text + chr(10) if synopses_text else ""}{turns_text}

=== MECHANISCHES ERGEBNIS ===
{engine_text}"""

    return layer_e


def build_context(playthrough_id, player_input, engine_result):
    """Assemble the full context dict for the Narrator prompt."""
    conn = get_db()

    player = conn.execute(
        "SELECT current_scene_id FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    if not player or not player['current_scene_id']:
        conn.close()
        return _build_fallback_prompt(player_input, engine_result)

    scene_id = player['current_scene_id']

    # Layer D: scene
    scene = conn.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()

    layer_d_text = ""
    zone_id = None

    if scene:
        zone_id = scene['zone_id']
        layer_d_text = scene['layer_d_text'] or ""
        flags = _get_scene_flags(conn, playthrough_id, scene_id, 'scene')
        layer_d_text = _append_flags(layer_d_text, flags)

        groups = conn.execute(
            "SELECT label, description FROM group_entries WHERE scene_id=?", (scene_id,)
        ).fetchall()
        if groups:
            group_lines = "\n".join(f"  [{g['label']}]: {g['description']}" for g in groups)
            layer_d_text += f"\n\nAnwesende Gruppen:\n{group_lines}"

    # Layer C: zone
    layer_c_text = ""
    city_area_id = None

    if zone_id:
        zone = conn.execute("SELECT * FROM zones WHERE id=?", (zone_id,)).fetchone()
        if zone:
            layer_c_text = zone['layer_c_text'] or ""
            city_area_id = zone['city_area_id']
            zone_flags = _get_scene_flags(conn, playthrough_id, zone_id, 'zone')
            layer_c_text = _append_flags(layer_c_text, zone_flags)

    # Layer B: region
    layer_b_text = ""
    region_id = None

    if city_area_id:
        city_area = conn.execute("SELECT region_id FROM city_areas WHERE id=?", (city_area_id,)).fetchone()
        if city_area:
            region_id = city_area['region_id']
    elif zone_id:
        zone = conn.execute("SELECT region_id FROM zones WHERE id=?", (zone_id,)).fetchone()
        if zone:
            region_id = zone['region_id']

    if region_id:
        region = conn.execute("SELECT layer_b_text FROM regions WHERE id=?", (region_id,)).fetchone()
        if region:
            layer_b_text = region['layer_b_text'] or ""

    conn.close()

    layer_a = get_layer_a()
    layer_e = get_active_context(playthrough_id, engine_result)

    narrator_system = f"""Du bist der Erzähler einer düsteren Low-Fantasy-Welt namens Avarr. Du entscheidest NICHT über Ergebnisse — diese werden bereits durch die Spielengine bestimmt. Deine einzige Aufgabe ist lebendiges Erzählen und die Verwaltung des Weltzustands.

WELT:
{layer_a}

REGION:
{layer_b_text or "(keine Regionsdaten)"}

ZONE:
{layer_c_text or "(keine Zonendaten)"}

SCHAUPLATZ:
{layer_d_text or "(keine Schauplatzdaten)"}

{layer_e}

Spielereingabe: "{player_input}"

Antworte NUR mit gültigem JSON:
{{
  "narration": "2-4 Sätze lebendiger Erzählung in der Gegenwartsform. Bleib dem düsteren Ton der Welt treu. Webe Sinnesdetails ein.",
  "time_delta_minutes": <ganzzahl, wie viele Spielminuten diese Handlung dauerte, max 4320>,
  "gold_delta": <ganzzahl, positiv = Spieler erhält Gold/Münzen, negativ = Spieler gibt Gold aus. 0 wenn kein Handel>,
  "inventory_changes": [],
  "generated_locations": [],
  "generated_npcs": [],
  "generated_groups": [],
  "world_state_changes": []
}}

inventory_changes Format: {{"op": "add" oder "remove", "item_name": str, "quantity": int, "equipped": false, "properties": {{}}}}
generated_npcs Format: {{"id": "eindeutiger_slug", "name": str, "role": str, "description": str, "personality": str, "home_scene_id": str, "stats": {{}}}}
generated_locations Format: {{"id": str, "name": str, "type": str, "layer_d_text": str, "parent_scene_id": str oder "zone_id": str, "x": int, "y": int}}
generated_groups Format: {{"scene_id": str, "label": str, "description": str}}
world_state_changes Format: {{"entity_type": str, "entity_id": str, "flag_name": str, "flag_value": str}}

Generiere Orte/NSCs/Gruppen nur, wenn der Spieler direkt auf etwas Neues trifft oder es entdeckt. Halte generierte Inhalte konsistent mit dem Ton der Welt und dem Schauplatzkontext.
Wenn der Spieler etwas kauft, verkauft, erhält oder verliert: setze gold_delta und inventory_changes entsprechend. Vergiss nie gold_delta wenn Münzen wechseln."""

    return narrator_system


def _build_fallback_prompt(player_input, engine_result):
    layer_a = get_layer_a()
    safe_result = {k: v for k, v in (engine_result or {}).items() if k != 'pending_roll'}
    engine_text = json.dumps(safe_result) if safe_result else "keines"
    return f"""Du bist der Erzähler von Avarr. Erzähle lebendig.

WELT: {layer_a}

MECHANISCHES ERGEBNIS: {engine_text}
Spielereingabe: "{player_input}"

Antworte NUR mit gültigem JSON:
{{"narration": "...", "time_delta_minutes": 5, "gold_delta": 0, "inventory_changes": [], "generated_locations": [], "generated_npcs": [], "generated_groups": [], "world_state_changes": []}}"""
