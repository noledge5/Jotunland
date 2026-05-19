import random
import json
import os
import math
from db import get_db
import trace as _trace

_rulebook = None
_skills_data = None
_DB_PATH = os.path.join(os.path.dirname(__file__), 'rpg.db')


def _db():
    return get_db(_DB_PATH)


def _load_rulebook():
    global _rulebook
    if _rulebook is None:
        rb_path = os.path.join(os.path.dirname(__file__), 'config', 'rulebook.json')
        with open(rb_path) as f:
            _rulebook = json.load(f)
    return _rulebook


def _load_skills_data():
    global _skills_data
    if _skills_data is None:
        sk_path = os.path.join(os.path.dirname(__file__), 'config', 'skills.json')
        with open(sk_path) as f:
            _skills_data = json.load(f)
    return _skills_data


def roll_d20():
    return random.randint(1, 20)


# ── Attribute & Skill Helpers ───────────────────────────────────────────────

def attr_mod(value: int) -> int:
    """floor((value - 10) / 2)"""
    return math.floor((value - 10) / 2)


def skill_bonus(skill_value: int) -> int:
    """floor(skill_value / 10)"""
    return math.floor(skill_value / 10)


def get_attr(playthrough_id, attr_name) -> int:
    """Read attribute value from player_attributes."""
    conn = _db()
    row = conn.execute(
        "SELECT value FROM player_attributes WHERE playthrough_id=? AND attr_name=?",
        (playthrough_id, attr_name)
    ).fetchone()
    conn.close()
    return row['value'] if row else 10


def get_best_attr_mod(playthrough_id, attrs: list) -> int:
    """For two attributes: take the higher modifier."""
    mods = [attr_mod(get_attr(playthrough_id, a)) for a in attrs]
    return max(mods) if mods else 0


def get_player_vw(playthrough_id) -> int:
    """10 + GES-MOD + shield bonus (shield from inventory equipped)."""
    ges = get_attr(playthrough_id, 'GES')
    base = 10 + attr_mod(ges)
    # Check for shield in equipped inventory
    conn = _db()
    shields = conn.execute(
        "SELECT item_name, properties FROM inventory "
        "WHERE playthrough_id=? AND equipped=1",
        (playthrough_id,)
    ).fetchall()
    conn.close()
    shield_bonus = 0
    for item in shields:
        try:
            props = json.loads(item['properties'] or '{}')
            shield_bonus += props.get('shield_bonus', 0)
        except Exception:
            pass
    return base + shield_bonus


def get_skill_value(playthrough_id, skill_name) -> int:
    """Read skill value (level column) from player_skills, 0 if not found."""
    conn = _db()
    row = conn.execute(
        "SELECT level FROM player_skills WHERE playthrough_id=? AND skill_name=?",
        (playthrough_id, skill_name)
    ).fetchone()
    conn.close()
    return row['level'] if row else 0


def get_skill_attrs(skill_name) -> list:
    """Read attrs for a skill from skills.json."""
    sk = _load_skills_data()
    for s in sk['skills']:
        if s['name'] == skill_name:
            return s['attrs']
    return []


def get_injury_modifiers(playthrough_id, skill_name):
    """Return total modifier from injuries affecting this skill."""
    conn = _db()
    rows = conn.execute(
        "SELECT modifier FROM injuries WHERE playthrough_id=? AND entity_type='player' AND affected_skill=?",
        (playthrough_id, skill_name)
    ).fetchall()
    conn.close()
    return sum(r['modifier'] for r in rows)


# ── Tick & Level System ─────────────────────────────────────────────────────

def _tick_threshold_for_value(skill_value: int) -> int:
    """Return ticks needed to level up given current skill value."""
    rb = _load_rulebook()
    thresholds = rb['tick_thresholds']
    # thresholds keys are strings of lower bounds: "0", "21", "41", "61", "81"
    result = 3
    for key in sorted(thresholds.keys(), key=lambda k: int(k)):
        if skill_value >= int(key):
            result = thresholds[key]
    return result


def award_tick(playthrough_id, skill_name) -> dict:
    """
    Give +1 tick for the skill.
    If ticks >= threshold: skill_value += 1, ticks = 0, skill_ups_count += 1.
    Returns: {"skill_up": bool, "new_value": int, "ticks": int, "ticks_needed": int}
    """
    conn = _db()
    row = conn.execute(
        "SELECT level, ticks FROM player_skills WHERE playthrough_id=? AND skill_name=?",
        (playthrough_id, skill_name)
    ).fetchone()

    if not row:
        # Insert skill with 0 if missing
        conn.execute(
            "INSERT OR IGNORE INTO player_skills (playthrough_id, skill_name, level, ticks) VALUES (?,?,0,0)",
            (playthrough_id, skill_name)
        )
        conn.commit()
        row = conn.execute(
            "SELECT level, ticks FROM player_skills WHERE playthrough_id=? AND skill_name=?",
            (playthrough_id, skill_name)
        ).fetchone()

    current_value = row['level']
    current_ticks = row['ticks'] + 1
    threshold = _tick_threshold_for_value(current_value)

    skill_up = False
    if current_ticks >= threshold:
        current_value += 1
        current_ticks = 0
        skill_up = True
        conn.execute(
            "UPDATE player_skills SET level=?, ticks=? WHERE playthrough_id=? AND skill_name=?",
            (current_value, current_ticks, playthrough_id, skill_name)
        )
        conn.execute(
            "UPDATE player SET skill_ups_count = skill_ups_count + 1 WHERE playthrough_id=?",
            (playthrough_id,)
        )
    else:
        conn.execute(
            "UPDATE player_skills SET ticks=? WHERE playthrough_id=? AND skill_name=?",
            (current_ticks, playthrough_id, skill_name)
        )

    conn.commit()
    conn.close()

    _trace.log_tick(skill_name, current_ticks, threshold, skill_up, current_value)
    return {
        "skill_up": skill_up,
        "new_value": current_value,
        "ticks": current_ticks,
        "ticks_needed": _tick_threshold_for_value(current_value)
    }


def check_char_level_up(playthrough_id) -> bool:
    """
    Check if skill_ups_count >= (level * 10).
    If so: level += 1, hp_max += 2, return True.
    """
    conn = _db()
    player = conn.execute(
        "SELECT level, skill_ups_count, hp_max FROM player WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return False

    leveled_up = False
    if player['skill_ups_count'] >= player['level'] * 10:
        new_level = player['level'] + 1
        new_hp_max = player['hp_max'] + 2
        conn.execute(
            "UPDATE player SET level=?, hp_max=? WHERE playthrough_id=?",
            (new_level, new_hp_max, playthrough_id)
        )
        conn.commit()
        leveled_up = True
        _trace.log_state_change("player.level", player['level'], new_level, "skill_ups threshold reached")
        _trace.log_db_write("player", "UPDATE", {"level": new_level, "hp_max": new_hp_max})

    conn.close()
    return leveled_up


def calculate_max_hp(kon_value: int, level: int) -> int:
    """KON + 10 + (level * 2)"""
    return kon_value + 10 + (level * 2)


def process_dying(playthrough_id):
    """
    If player hp_current <= 0 and hp_current > -10: hp_current -= 1 (bleeding).
    If hp_current <= -10: player dies.
    """
    conn = _db()
    player = conn.execute(
        "SELECT hp_current FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return

    hp = player['hp_current']
    if hp <= 0 and hp > -10:
        new_hp = hp - 1
        conn.execute(
            "UPDATE player SET hp_current=? WHERE playthrough_id=?",
            (new_hp, playthrough_id)
        )
        if new_hp <= -10:
            # Player dies — mark in world_state_flags
            conn.execute(
                "INSERT OR REPLACE INTO world_state_flags "
                "(playthrough_id, entity_type, entity_id, flag_name, flag_value) "
                "VALUES (?, 'player', 'player', 'status', 'dead')",
                (playthrough_id,)
            )
        conn.commit()

    conn.close()


# ── External Roll System ────────────────────────────────────────────────────

def request_roll(playthrough_id, skill_name, difficulty_tier) -> dict:
    """
    Calculate modifier (ATTR-MOD + Skill-Bonus),
    save pending_roll in DB as JSON.
    Returns dict with needs_player_roll=True and roll info.
    """
    rb = _load_rulebook()
    sg = rb['difficulty_tiers'].get(difficulty_tier, 12)

    skill_value = get_skill_value(playthrough_id, skill_name)
    attrs = get_skill_attrs(skill_name)
    injury_mod = get_injury_modifiers(playthrough_id, skill_name)

    if attrs:
        best_mod = get_best_attr_mod(playthrough_id, attrs)
    else:
        best_mod = 0

    modifier = best_mod + skill_bonus(skill_value) + injury_mod

    pending = {
        "skill_name": skill_name,
        "sg": sg,
        "modifier": modifier,
        "difficulty_tier": difficulty_tier
    }

    conn = _db()
    cursor = conn.execute(
        "UPDATE player SET pending_roll=? WHERE playthrough_id=?",
        (json.dumps(pending), playthrough_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()

    # Verify write
    verify = conn.execute(
        "SELECT pending_roll FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    conn.close()

    print(f"[request_roll] rows_affected={rows_affected} verify={verify['pending_roll'] if verify else 'NO ROW'}")

    sign = "+" if modifier >= 0 else ""
    formula = f"W20 {sign}{modifier}"
    _trace.log_roll_requested(skill_name, sg, modifier, formula)
    _trace.log_db_write("player", "UPDATE", {"pending_roll": pending})
    return {
        "needs_player_roll": True,
        "skill_name": skill_name,
        "sg": sg,
        "modifier": modifier,
        "difficulty_tier": difficulty_tier,
        "formula": f"W20 {sign}{modifier}"
    }


def resolve_player_roll(playthrough_id, dice_result: int) -> dict:
    """
    Read pending_roll from DB.
    Calculate: total = dice_result + modifier.
    Compare with SG, determine outcome.
    Award tick, check skill-up.
    Clear pending_roll.
    Return full engine_result dict.
    """
    conn = _db()
    player = conn.execute(
        "SELECT pending_roll FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    conn.close()

    print(f"[resolve_player_roll] playthrough_id={playthrough_id} pending_roll={player['pending_roll'] if player else 'NO ROW'}")

    if not player or not player['pending_roll']:
        return {"error": "Kein ausstehender Wurf gefunden."}

    pending = json.loads(player['pending_roll'])
    skill_name = pending['skill_name']
    sg = pending['sg']
    modifier = pending['modifier']
    difficulty_tier = pending['difficulty_tier']

    total = dice_result + modifier

    # Determine outcome
    rb = _load_rulebook()
    crit_success = rb['critical_success_roll']
    crit_fail = rb['critical_failure_roll']

    if dice_result == crit_success:
        outcome = 'KRITISCHER_ERFOLG'
    elif dice_result == crit_fail:
        outcome = 'KRITISCHER_FEHLSCHLAG'
    elif total >= sg:
        outcome = 'ERFOLG'
    elif total >= sg - 3:
        outcome = 'TEILERFOLG'
    else:
        outcome = 'FEHLSCHLAG'

    _trace.log_roll_resolved(dice_result, modifier, total, sg, outcome)

    # Award tick and check skill-up
    tick_result = award_tick(playthrough_id, skill_name)

    # Check character level-up
    leveled_up = check_char_level_up(playthrough_id)

    # Clear pending_roll
    conn = _db()
    conn.execute(
        "UPDATE player SET pending_roll=NULL WHERE playthrough_id=?",
        (playthrough_id,)
    )
    conn.commit()
    conn.close()
    _trace.log_db_write("player", "UPDATE", {"pending_roll": None})

    return {
        "needs_roll": True,
        "skill_result": {
            "skill": skill_name,
            "sg": sg,
            "difficulty_tier": difficulty_tier,
            "dice_result": dice_result,
            "modifier": modifier,
            "total": total,
            "outcome": outcome
        },
        "tick_result": tick_result,
        "leveled_up": leveled_up,
        "status": "resolved"
    }


# ── Scene NPCs ──────────────────────────────────────────────────────────────

def get_current_scene_npcs(playthrough_id):
    """Get NPCs present at player's current scene given current in-game time."""
    conn = _db()
    player = conn.execute(
        "SELECT current_scene_id, in_game_hour FROM player WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return []

    scene_id = player['current_scene_id']
    hour = player['in_game_hour']

    scheduled = conn.execute("""
        SELECT n.*, ns.scene_id as sched_scene_id,
               nr.met, nr.relation_score, nr.player_knows, nr.npc_knows, nr.shared_history
        FROM npcs n
        JOIN npc_schedules ns ON n.id = ns.npc_id
        LEFT JOIN npc_relations nr ON nr.npc_id = n.id AND nr.playthrough_id = ?
        WHERE ns.scene_id = ?
          AND ns.hour_start <= ?
          AND (ns.hour_end > ? OR (ns.hour_start > ns.hour_end AND (? >= ns.hour_start OR ? < ns.hour_end)))
    """, (playthrough_id, scene_id, hour, hour, hour, hour)).fetchall()

    npcs = [dict(row) for row in scheduled]
    conn.close()
    return npcs


# ── Time ────────────────────────────────────────────────────────────────────

def advance_time(playthrough_id, delta_minutes):
    """Advance in-game clock by delta_minutes. Max 4320."""
    rb = _load_rulebook()
    delta_minutes = min(delta_minutes, rb['max_time_delta_minutes'])
    if delta_minutes <= 0:
        return

    conn = _db()
    player = conn.execute(
        "SELECT in_game_year, in_game_month, in_game_day, in_game_hour, in_game_minute "
        "FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return

    total_minutes = (
        player['in_game_hour'] * 60 +
        player['in_game_minute'] +
        delta_minutes
    )

    minute = total_minutes % 60
    total_hours = total_minutes // 60
    hour = total_hours % 24
    extra_days = total_hours // 24

    day = player['in_game_day'] + extra_days
    month = player['in_game_month']
    year = player['in_game_year']

    while day > 30:
        day -= 30
        month += 1
        if month > 12:
            month = 1
            year += 1

    conn.execute(
        "UPDATE player SET in_game_year=?, in_game_month=?, in_game_day=?, "
        "in_game_hour=?, in_game_minute=? WHERE playthrough_id=?",
        (year, month, day, hour, minute, playthrough_id)
    )
    conn.commit()
    conn.close()


# ── Narrator Output ─────────────────────────────────────────────────────────

def apply_narrator_output(playthrough_id, narrator_json):
    """Apply the structured Narrator Output to the DB."""
    conn = _db()

    for change in narrator_json.get('world_state_changes', []):
        conn.execute(
            "INSERT INTO world_state_flags (playthrough_id, entity_type, entity_id, flag_name, flag_value) "
            "VALUES (?,?,?,?,?) ON CONFLICT(playthrough_id, entity_type, entity_id, flag_name) "
            "DO UPDATE SET flag_value=?",
            (playthrough_id, change.get('entity_type', 'scene'), change.get('entity_id', ''),
             change.get('flag_name', ''), change.get('flag_value', ''), change.get('flag_value', ''))
        )
        _trace.log_db_write("world_state_flags", "UPSERT", {
            "entity": change.get('entity_id'), "flag": change.get('flag_name'), "value": change.get('flag_value')
        })

    for npc in narrator_json.get('generated_npcs', []):
        conn.execute(
            "INSERT OR IGNORE INTO npcs (id, name, role, description, personality, home_scene_id, stats, tier) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (npc.get('id', ''), npc.get('name', ''), npc.get('role', ''),
             npc.get('description', ''), npc.get('personality', ''),
             npc.get('home_scene_id', ''), json.dumps(npc.get('stats', {})), 'generated')
        )
        _trace.log_db_write("npcs", "INSERT", {"id": npc.get('id'), "name": npc.get('name'), "tier": "generated"})

    for loc in narrator_json.get('generated_locations', []):
        if 'parent_scene_id' in loc:
            conn.execute(
                "INSERT OR IGNORE INTO scenes (id, zone_id, parent_scene_id, name, type, layer_d_text, x, y) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (loc.get('id', ''), loc.get('zone_id', ''), loc.get('parent_scene_id'),
                 loc.get('name', ''), loc.get('type', ''), loc.get('layer_d_text', ''),
                 loc.get('x', 0), loc.get('y', 0))
            )
        elif 'zone_id' in loc:
            conn.execute(
                "INSERT OR IGNORE INTO scenes (id, zone_id, parent_scene_id, name, type, layer_d_text, x, y) "
                "VALUES (?,?,NULL,?,?,?,?,?)",
                (loc.get('id', ''), loc.get('zone_id', ''),
                 loc.get('name', ''), loc.get('type', ''), loc.get('layer_d_text', ''),
                 loc.get('x', 0), loc.get('y', 0))
            )
        _trace.log_db_write("scenes", "INSERT", {"id": loc.get('id'), "name": loc.get('name')})

    for group in narrator_json.get('generated_groups', []):
        conn.execute(
            "INSERT INTO group_entries (scene_id, label, description) VALUES (?,?,?)",
            (group.get('scene_id', ''), group.get('label', ''), group.get('description', ''))
        )
        _trace.log_db_write("group_entries", "INSERT", {"scene_id": group.get('scene_id'), "label": group.get('label')})

    conn.commit()
    conn.close()

    _trace.log_narrator_output(
        narrator_json.get('narration', ''),
        narrator_json.get('time_delta_minutes', 5),
        len(narrator_json.get('generated_npcs', [])),
        len(narrator_json.get('generated_locations', [])),
        len(narrator_json.get('generated_groups', [])),
        len(narrator_json.get('world_state_changes', []))
    )

    delta = narrator_json.get('time_delta_minutes', 5)
    if isinstance(delta, (int, float)) and delta > 0:
        advance_time(playthrough_id, int(delta))


# ── Combat ──────────────────────────────────────────────────────────────────

def resolve_combat_turn(playthrough_id, player_action, target_npc_id):
    """
    Resolve one combat round.
    Player attack: request_roll (external dice).
    NPC counter-attack: engine rolls internally.
    """
    conn = _db()

    # Determine combat skill from action
    action_lower = player_action.lower()
    if any(word in action_lower for word in ['schieß', 'pfeil', 'bogen', 'wurf', 'wirf', 'shoot', 'arrow', 'bow', 'throw']):
        if any(word in action_lower for word in ['wirf', 'wurf', 'throw']):
            combat_skill = 'Wurfwaffen'
        elif any(word in action_lower for word in ['bogen', 'pfeil', 'bow', 'arrow']):
            combat_skill = 'Bogen'
        else:
            combat_skill = 'Bogen'
    elif any(word in action_lower for word in ['armbrust', 'crossbow']):
        combat_skill = 'Armbrust'
    else:
        combat_skill = 'Klingenwaffen'

    # Get target combatant
    target = conn.execute(
        "SELECT * FROM combat_combatants WHERE playthrough_id=? AND entity_id=? AND combat_status='active'",
        (playthrough_id, target_npc_id)
    ).fetchone()

    player_hp = conn.execute(
        "SELECT hp_current, hp_max FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    result = {
        'player_action': player_action,
        'target_npc_id': target_npc_id,
        'combat_skill': combat_skill,
        'player_attack': None,
        'enemy_attack': None,
        'combat_ended': False,
        'combat_end_reason': None,
        'needs_player_roll': True
    }

    conn.close()

    # Player attack: use external roll system
    roll_request = request_roll(playthrough_id, combat_skill, 'Durchschnitt')
    result['player_attack'] = roll_request
    result['needs_player_roll'] = True

    return result


def resolve_combat_after_roll(playthrough_id, engine_result, target_npc_id):
    """
    After player's roll is resolved, apply combat damage and NPC counter-attack.
    Called after resolve_player_roll in combat context.
    """
    skill_result = engine_result.get('skill_result', {})
    outcome = skill_result.get('outcome', 'FEHLSCHLAG')

    conn = _db()

    target = conn.execute(
        "SELECT * FROM combat_combatants WHERE playthrough_id=? AND entity_id=? AND combat_status='active'",
        (playthrough_id, target_npc_id)
    ).fetchone()

    player_hp = conn.execute(
        "SELECT hp_current, hp_max FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    combat_result = dict(engine_result)
    combat_result['combat_ended'] = False
    combat_result['combat_end_reason'] = None

    # Apply player damage if successful
    if target and outcome in ('ERFOLG', 'KRITISCHER_ERFOLG'):
        damage = random.randint(1, 6) + 1
        if outcome == 'KRITISCHER_ERFOLG':
            damage *= 2
        new_hp = max(0, target['hp_current'] - damage)
        combat_result['player_damage'] = damage
        combat_result['target_new_hp'] = new_hp

        conn.execute(
            "UPDATE combat_combatants SET hp_current=? WHERE playthrough_id=? AND entity_id=?",
            (new_hp, playthrough_id, target_npc_id)
        )

        if new_hp <= 0:
            conn.execute(
                "UPDATE combat_combatants SET combat_status='dead' WHERE playthrough_id=? AND entity_id=?",
                (playthrough_id, target_npc_id)
            )
            combat_result['combat_ended'] = True
            combat_result['combat_end_reason'] = f"{target_npc_id} besiegt"

    # Enemy counter-attack (if combat not ended)
    if not combat_result['combat_ended'] and target and player_hp:
        enemy_roll = roll_d20()
        npc_row = conn.execute("SELECT stats FROM npcs WHERE id=?", (target_npc_id,)).fetchone()
        npc_combat = 8
        if npc_row:
            try:
                stats = json.loads(npc_row['stats'] or '{}')
                npc_combat = stats.get('combat_skill', 8)
            except Exception:
                pass

        player_vw = get_player_vw(playthrough_id)
        enemy_total = enemy_roll + (npc_combat // 3)
        enemy_result = {'roll': enemy_roll, 'total': enemy_total, 'vw': player_vw}

        if enemy_roll == 20:
            enemy_damage = 8
            enemy_result['outcome'] = 'KRITISCHER_ERFOLG'
        elif enemy_roll == 1:
            enemy_damage = 0
            enemy_result['outcome'] = 'KRITISCHER_FEHLSCHLAG'
        elif enemy_total >= player_vw:
            enemy_damage = random.randint(1, 6)
            enemy_result['outcome'] = 'ERFOLG'
        else:
            enemy_damage = 0
            enemy_result['outcome'] = 'FEHLSCHLAG'

        if enemy_damage > 0:
            new_player_hp = player_hp['hp_current'] - enemy_damage
            enemy_result['damage'] = enemy_damage
            enemy_result['player_new_hp'] = new_player_hp
            conn.execute(
                "UPDATE player SET hp_current=? WHERE playthrough_id=?",
                (new_player_hp, playthrough_id)
            )
            conn.execute(
                "UPDATE combat_combatants SET hp_current=? WHERE playthrough_id=? AND is_player=1",
                (new_player_hp, playthrough_id)
            )
            if new_player_hp <= 0:
                combat_result['combat_ended'] = True
                combat_result['combat_end_reason'] = 'spieler_besiegt'
                process_dying(playthrough_id)

        combat_result['enemy_attack'] = enemy_result

    # Check if all enemies defeated
    active_enemies = conn.execute(
        "SELECT COUNT(*) as cnt FROM combat_combatants "
        "WHERE playthrough_id=? AND is_player=0 AND combat_status='active'",
        (playthrough_id,)
    ).fetchone()

    if active_enemies and active_enemies['cnt'] == 0:
        combat_result['combat_ended'] = True
        combat_result['combat_end_reason'] = 'alle_feinde_besiegt'
        conn.execute("UPDATE player SET in_combat=0 WHERE playthrough_id=?", (playthrough_id,))

    if combat_result['combat_ended'] and combat_result['combat_end_reason'] in ('alle_feinde_besiegt', 'spieler_besiegt'):
        conn.execute("UPDATE player SET in_combat=0 WHERE playthrough_id=?", (playthrough_id,))

    conn.commit()
    conn.close()

    return combat_result


# ── Legacy compatibility ─────────────────────────────────────────────────────

def apply_engine_result(playthrough_id, classifier_output, skill_result):
    """After classifier, update immediate state. Returns engine_result dict."""
    result = {
        'needs_roll': classifier_output.get('needs_roll', False),
        'skill_result': skill_result,
        'target': classifier_output.get('target'),
        'status': 'resolved'
    }

    conn = _db()
    player = conn.execute(
        "SELECT in_combat FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    conn.close()

    if player and player['in_combat']:
        result['in_combat'] = True
        if skill_result:
            result['combat_action'] = True

    check_char_level_up(playthrough_id)
    return result


def check_level_up(playthrough_id):
    """Alias for check_char_level_up for backward compat."""
    return check_char_level_up(playthrough_id)
