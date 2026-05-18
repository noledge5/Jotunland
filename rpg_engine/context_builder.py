import json
import os
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
                "Avarr is a dark low-fantasy world dominated by the Ostimperium. "
                "Essenz is real but rare. Gods are silent. It is the year 743 IC."
            )
    return _world_constants


def get_layer_a():
    """Return world constants text."""
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
    return text + f" [State: {flag_lines}]"


def get_active_context(playthrough_id, engine_result):
    """Build Layer E: NPCs present, player stats, recent turns, engine result."""
    conn = get_db()

    # Player stats
    player = conn.execute(
        "SELECT * FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return "No player found."

    # Skills
    skills = conn.execute(
        "SELECT skill_name, level, xp FROM player_skills WHERE playthrough_id=? ORDER BY skill_name",
        (playthrough_id,)
    ).fetchall()
    skills_text = ", ".join(f"{s['skill_name']} Lv{s['level']}" for s in skills) or "none"

    # Equipped items
    equipped = conn.execute(
        "SELECT item_name, properties FROM inventory WHERE playthrough_id=? AND equipped=1",
        (playthrough_id,)
    ).fetchall()
    equipped_text = ", ".join(e['item_name'] for e in equipped) or "nothing equipped"

    # Inventory
    inv = conn.execute(
        "SELECT item_name, quantity FROM inventory WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchall()
    inv_text = ", ".join(f"{i['item_name']}x{i['quantity']}" for i in inv) or "empty"

    # Injuries
    injuries = conn.execute(
        "SELECT injury_name, affected_skill, modifier FROM injuries "
        "WHERE playthrough_id=? AND entity_type='player'",
        (playthrough_id,)
    ).fetchall()
    injuries_text = "; ".join(f"{i['injury_name']} ({i['affected_skill']} {i['modifier']:+d})" for i in injuries) or "none"

    # NPC relations in current scene
    from engine import get_current_scene_npcs
    npcs = get_current_scene_npcs(playthrough_id)
    npc_lines = []
    for npc in npcs:
        rel_score = npc.get('relation_score', npc.get('relation_score_default', 0)) or 0
        met = npc.get('met', 0)
        rel_text = f"rel={rel_score:+d}" if met else "stranger"
        npc_lines.append(f"  - {npc['name']} ({npc['role']}): {rel_text}. {npc.get('description', '')[:80]}")
    npcs_text = "\n".join(npc_lines) if npc_lines else "  (no notable NPCs present)"

    # Recent turns (last 4)
    turns = conn.execute(
        "SELECT turn_number, player_input, narration, in_game_timestamp FROM turn_log "
        "WHERE playthrough_id=? ORDER BY turn_number DESC LIMIT 4",
        (playthrough_id,)
    ).fetchall()
    turns_text_parts = []
    for t in reversed(turns):
        turns_text_parts.append(f"[{t['in_game_timestamp']}] Player: {t['player_input']}\nNarrator: {t['narration']}")
    turns_text = "\n---\n".join(turns_text_parts) if turns_text_parts else "(start of session)"

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
    quests_text = "; ".join(q['title'] for q in quests) or "none"

    conn.close()

    # Format engine result
    engine_text = ""
    if engine_result:
        sr = engine_result.get('skill_result')
        if sr:
            engine_text = (
                f"Skill check: {sr['skill']} (DC {sr['dc']}, tier {sr['difficulty_tier']})\n"
                f"Roll: {sr['roll']} + {sr['modifier']} = {sr['total']} → {sr['outcome']}\n"
                f"XP gained: {sr['xp_gained']}"
            )
        elif engine_result.get('needs_roll') is False:
            engine_text = "No skill check required."
        else:
            engine_text = json.dumps(engine_result)

    ts = f"{player['in_game_year']}-{player['in_game_month']:02d}-{player['in_game_day']:02d} {player['in_game_hour']:02d}:{player['in_game_minute']:02d}"

    player_summary = (
        f"Name: {player['name']}, Class: {player['class']}, Level: {player['level']}, "
        f"XP: {player['xp']}, HP: {player['hp_current']}/{player['hp_max']}, "
        f"Gold: {player['gold']}\n"
        f"Skills: {skills_text}\n"
        f"Equipped: {equipped_text}\n"
        f"Inventory: {inv_text}\n"
        f"Injuries: {injuries_text}\n"
        f"Active quests: {quests_text}\n"
        f"In combat: {'yes' if player['in_combat'] else 'no'}\n"
        f"Current time: {ts}"
    )

    layer_e = f"""=== PLAYER ===
{player_summary}

=== NPCs PRESENT ===
{npcs_text}

=== RECENT EVENTS ===
{synopses_text + chr(10) if synopses_text else ""}{turns_text}

=== MECHANICAL OUTCOME ===
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
    scene = conn.execute(
        "SELECT * FROM scenes WHERE id=?", (scene_id,)
    ).fetchone()

    layer_d_text = ""
    zone_id = None
    scene_name = scene_id

    if scene:
        scene_name = scene['name']
        zone_id = scene['zone_id']
        layer_d_text = scene['layer_d_text'] or ""
        # Append flags
        flags = _get_scene_flags(conn, playthrough_id, scene_id, 'scene')
        layer_d_text = _append_flags(layer_d_text, flags)

        # Group entries
        groups = conn.execute(
            "SELECT label, description FROM group_entries WHERE scene_id=?", (scene_id,)
        ).fetchall()
        if groups:
            group_lines = "\n".join(f"  [{g['label']}]: {g['description']}" for g in groups)
            layer_d_text += f"\n\nPresent groups:\n{group_lines}"

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

    narrator_system = f"""You are the narrator of a dark low-fantasy world called Avarr. You do NOT decide outcomes — those are already determined by the game engine. Your only job is to narrate vividly and manage world state.

WORLD:
{layer_a}

REGION:
{layer_b_text or "(no region data)"}

ZONE:
{layer_c_text or "(no zone data)"}

SCENE:
{layer_d_text or "(no scene data)"}

{layer_e}

Player input: "{player_input}"

Respond with ONLY valid JSON:
{{
  "narration": "2-4 sentences of vivid narration in present tense. Stay true to the world's dark tone. Weave in sensory detail.",
  "time_delta_minutes": <integer, how many in-game minutes this action took, max 4320>,
  "generated_locations": [],
  "generated_npcs": [],
  "generated_groups": [],
  "world_state_changes": []
}}

generated_npcs format: {{"id": "unique_slug", "name": str, "role": str, "description": str, "personality": str, "home_scene_id": str, "stats": {{}}}}
generated_locations format: {{"id": str, "name": str, "type": str, "layer_d_text": str, "parent_scene_id": str or "zone_id": str, "x": int, "y": int}}
generated_groups format: {{"scene_id": str, "label": str, "description": str}}
world_state_changes format: {{"entity_type": str, "entity_id": str, "flag_name": str, "flag_value": str}}

Only generate locations/npcs/groups when the player directly encounters or discovers something new. Keep generated content consistent with the world's tone and the scene context."""

    return narrator_system


def _build_fallback_prompt(player_input, engine_result):
    layer_a = get_layer_a()
    engine_text = json.dumps(engine_result) if engine_result else "none"
    return f"""You are the narrator of Avarr. Narrate vividly.

WORLD: {layer_a}

MECHANICAL OUTCOME: {engine_text}
Player input: "{player_input}"

Respond with ONLY valid JSON:
{{"narration": "...", "time_delta_minutes": 5, "generated_locations": [], "generated_npcs": [], "generated_groups": [], "world_state_changes": []}}"""
