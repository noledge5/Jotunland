import random
import json
import os
from db import get_db

_rulebook = None

def _load_rulebook():
    global _rulebook
    if _rulebook is None:
        rb_path = os.path.join(os.path.dirname(__file__), 'config', 'rulebook.json')
        with open(rb_path) as f:
            _rulebook = json.load(f)
    return _rulebook

def roll_d20():
    return random.randint(1, 20)

def get_injury_modifiers(playthrough_id, skill_name):
    """Return total modifier from injuries affecting this skill."""
    conn = get_db()
    rows = conn.execute(
        "SELECT modifier FROM injuries WHERE playthrough_id=? AND entity_type='player' AND affected_skill=?",
        (playthrough_id, skill_name)
    ).fetchall()
    conn.close()
    return sum(r['modifier'] for r in rows)

def resolve_skill_check(playthrough_id, skill_name, difficulty_tier):
    """Roll d20 + skill modifier vs DC. Returns result dict."""
    rb = _load_rulebook()
    dc = rb['difficulty_tiers'].get(difficulty_tier, 12)

    conn = get_db()
    row = conn.execute(
        "SELECT level FROM player_skills WHERE playthrough_id=? AND skill_name=?",
        (playthrough_id, skill_name)
    ).fetchone()
    conn.close()

    skill_level = row['level'] if row else 0
    injury_mod = get_injury_modifiers(playthrough_id, skill_name)
    modifier = skill_level + injury_mod

    raw_roll = roll_d20()
    total = raw_roll + modifier

    if raw_roll == rb['critical_success_roll']:
        outcome = 'CRITICAL_SUCCESS'
        xp_gained = rb['xp_per_critical']
    elif raw_roll == rb['critical_failure_roll']:
        outcome = 'CRITICAL_FAILURE'
        xp_gained = rb['xp_per_action']
    elif total >= dc + 5:
        outcome = 'SUCCESS'
        xp_gained = rb['xp_per_success']
    elif total >= dc:
        outcome = 'SUCCESS'
        xp_gained = rb['xp_per_success']
    elif total >= dc - 4:
        outcome = 'PARTIAL'
        xp_gained = rb['xp_per_action']
    else:
        outcome = 'FAILURE'
        xp_gained = rb['xp_per_action']

    # Award XP to skill and player
    _award_xp(playthrough_id, skill_name, xp_gained)

    return {
        'roll': raw_roll,
        'modifier': modifier,
        'total': total,
        'dc': dc,
        'outcome': outcome,
        'skill': skill_name,
        'difficulty_tier': difficulty_tier,
        'xp_gained': xp_gained
    }

def _award_xp(playthrough_id, skill_name, xp_gained):
    conn = get_db()
    # Award to skill
    conn.execute(
        "INSERT INTO player_skills (playthrough_id, skill_name, level, xp) VALUES (?,?,0,?) "
        "ON CONFLICT(playthrough_id, skill_name) DO UPDATE SET xp=xp+?",
        (playthrough_id, skill_name, xp_gained, xp_gained)
    )
    # Award to player total xp
    conn.execute(
        "UPDATE player SET xp=xp+? WHERE playthrough_id=?",
        (xp_gained, playthrough_id)
    )
    # Check skill level up
    rb = _load_rulebook()
    thresholds = rb['level_thresholds']
    row = conn.execute(
        "SELECT level, xp FROM player_skills WHERE playthrough_id=? AND skill_name=?",
        (playthrough_id, skill_name)
    ).fetchone()
    if row:
        current_level = row['level']
        current_xp = row['xp']
        next_level = current_level + 1
        if next_level < len(thresholds) and current_xp >= thresholds[next_level]:
            conn.execute(
                "UPDATE player_skills SET level=? WHERE playthrough_id=? AND skill_name=?",
                (next_level, playthrough_id, skill_name)
            )
    conn.commit()
    conn.close()

def apply_engine_result(playthrough_id, classifier_output, skill_result):
    """After classifier and dice, update any immediate state. Returns engine_result dict."""
    result = {
        'needs_roll': classifier_output.get('needs_roll', False),
        'skill_result': skill_result,
        'target': classifier_output.get('target'),
        'status': 'resolved'
    }

    # If in combat, update combat state based on skill result
    conn = get_db()
    player = conn.execute(
        "SELECT in_combat FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    conn.close()

    if player and player['in_combat']:
        result['in_combat'] = True
        if skill_result:
            result['combat_action'] = True

    check_level_up(playthrough_id)
    return result

def get_current_scene_npcs(playthrough_id):
    """Get NPCs present at player's current scene given current in-game time."""
    conn = get_db()
    player = conn.execute(
        "SELECT current_scene_id, in_game_hour FROM player WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchone()

    if not player:
        conn.close()
        return []

    scene_id = player['current_scene_id']
    hour = player['in_game_hour']

    # NPCs scheduled to this scene at this hour
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

    npcs = []
    for row in scheduled:
        npc = dict(row)
        npcs.append(npc)

    conn.close()
    return npcs

def advance_time(playthrough_id, delta_minutes):
    """Advance in-game clock by delta_minutes. Max 4320."""
    rb = _load_rulebook()
    delta_minutes = min(delta_minutes, rb['max_time_delta_minutes'])
    if delta_minutes <= 0:
        return

    conn = get_db()
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

    # Simple 30-day months, 12 months per year
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

def apply_narrator_output(playthrough_id, narrator_json):
    """Apply the structured Narrator Output to the DB."""
    conn = get_db()

    # Apply world_state_changes
    for change in narrator_json.get('world_state_changes', []):
        conn.execute(
            "INSERT INTO world_state_flags (playthrough_id, entity_type, entity_id, flag_name, flag_value) "
            "VALUES (?,?,?,?,?) ON CONFLICT(playthrough_id, entity_type, entity_id, flag_name) "
            "DO UPDATE SET flag_value=?",
            (playthrough_id, change.get('entity_type', 'scene'), change.get('entity_id', ''),
             change.get('flag_name', ''), change.get('flag_value', ''), change.get('flag_value', ''))
        )

    # Insert generated NPCs
    for npc in narrator_json.get('generated_npcs', []):
        conn.execute(
            "INSERT OR IGNORE INTO npcs (id, name, role, description, personality, home_scene_id, stats, tier) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (npc.get('id', ''), npc.get('name', ''), npc.get('role', ''),
             npc.get('description', ''), npc.get('personality', ''),
             npc.get('home_scene_id', ''), json.dumps(npc.get('stats', {})), 'generated')
        )

    # Insert generated locations
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

    # Insert generated groups
    for group in narrator_json.get('generated_groups', []):
        conn.execute(
            "INSERT INTO group_entries (scene_id, label, description) VALUES (?,?,?)",
            (group.get('scene_id', ''), group.get('label', ''), group.get('description', ''))
        )

    conn.commit()
    conn.close()

    # Advance time
    delta = narrator_json.get('time_delta_minutes', 5)
    if isinstance(delta, (int, float)) and delta > 0:
        advance_time(playthrough_id, int(delta))

def get_combat_state(playthrough_id):
    """Return current combat combatants and their status."""
    conn = get_db()
    combatants = conn.execute(
        "SELECT * FROM combat_combatants WHERE playthrough_id=? AND combat_status='active'",
        (playthrough_id,)
    ).fetchall()
    conn.close()
    return [dict(c) for c in combatants]

def resolve_combat_turn(playthrough_id, player_action, target_npc_id):
    """Resolve one combat round: player action + enemy counter-action."""
    conn = get_db()

    # Determine combat skill from action
    action_lower = player_action.lower()
    if any(word in action_lower for word in ['shoot', 'arrow', 'bow', 'throw']):
        combat_skill = 'Ranged'
    else:
        combat_skill = 'Melee'

    # Get target combatant
    target = conn.execute(
        "SELECT * FROM combat_combatants WHERE playthrough_id=? AND entity_id=? AND combat_status='active'",
        (playthrough_id, target_npc_id)
    ).fetchone()

    # Get player combatant
    player_combatant = conn.execute(
        "SELECT * FROM combat_combatants WHERE playthrough_id=? AND is_player=1",
        (playthrough_id,)
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
        'combat_end_reason': None
    }

    # Player attacks
    if target:
        skill_result = resolve_skill_check(playthrough_id, combat_skill, 'Medium')
        result['player_attack'] = skill_result

        if skill_result['outcome'] in ('SUCCESS', 'CRITICAL_SUCCESS'):
            damage = roll_d20() // 4 + 1
            if skill_result['outcome'] == 'CRITICAL_SUCCESS':
                damage *= 2
            new_hp = max(0, target['hp_current'] - damage)
            result['player_attack']['damage'] = damage
            result['player_attack']['target_new_hp'] = new_hp

            conn.execute(
                "UPDATE combat_combatants SET hp_current=? WHERE playthrough_id=? AND entity_id=?",
                (new_hp, playthrough_id, target_npc_id)
            )

            if new_hp <= 0:
                conn.execute(
                    "UPDATE combat_combatants SET combat_status='dead' WHERE playthrough_id=? AND entity_id=?",
                    (playthrough_id, target_npc_id)
                )
                result['combat_ended'] = True
                result['combat_end_reason'] = f"{target_npc_id} is dead"

    # Enemy counter-attack (if combat not ended)
    if not result['combat_ended'] and target and player_hp:
        enemy_roll = roll_d20()
        npc_row = conn.execute("SELECT stats FROM npcs WHERE id=?", (target_npc_id,)).fetchone()
        npc_combat = 8
        if npc_row:
            try:
                stats = json.loads(npc_row['stats'] or '{}')
                npc_combat = stats.get('combat_skill', 8)
            except Exception:
                pass

        enemy_total = enemy_roll + (npc_combat // 3)
        player_defense_dc = 12

        enemy_result = {
            'roll': enemy_roll,
            'total': enemy_total,
            'dc': player_defense_dc
        }

        if enemy_roll == 20:
            enemy_damage = 8
            enemy_result['outcome'] = 'CRITICAL_SUCCESS'
        elif enemy_roll == 1:
            enemy_damage = 0
            enemy_result['outcome'] = 'CRITICAL_FAILURE'
        elif enemy_total >= player_defense_dc:
            enemy_damage = roll_d20() // 4 + 1
            enemy_result['outcome'] = 'SUCCESS'
        else:
            enemy_damage = 0
            enemy_result['outcome'] = 'FAILURE'

        if enemy_damage > 0:
            new_player_hp = max(0, player_hp['hp_current'] - enemy_damage)
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
                result['combat_ended'] = True
                result['combat_end_reason'] = 'player_defeated'

        result['enemy_attack'] = enemy_result

    # Check if all enemies defeated
    active_enemies = conn.execute(
        "SELECT COUNT(*) as cnt FROM combat_combatants "
        "WHERE playthrough_id=? AND is_player=0 AND combat_status='active'",
        (playthrough_id,)
    ).fetchone()

    if active_enemies and active_enemies['cnt'] == 0:
        result['combat_ended'] = True
        result['combat_end_reason'] = 'all_enemies_defeated'
        conn.execute("UPDATE player SET in_combat=0 WHERE playthrough_id=?", (playthrough_id,))

    if result['combat_ended'] and result['combat_end_reason'] in ('all_enemies_defeated', 'player_defeated'):
        conn.execute("UPDATE player SET in_combat=0 WHERE playthrough_id=?", (playthrough_id,))

    conn.commit()
    conn.close()
    return result

def check_level_up(playthrough_id):
    """Check if player XP exceeds threshold for next level."""
    rb = _load_rulebook()
    thresholds = rb['level_thresholds']

    conn = get_db()
    player = conn.execute(
        "SELECT level, xp FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()

    if player:
        current_level = player['level']
        current_xp = player['xp']
        next_level = current_level + 1

        if next_level < len(thresholds) and current_xp >= thresholds[next_level]:
            new_hp_max = 20 + (next_level * 5)
            conn.execute(
                "UPDATE player SET level=?, hp_max=?, hp_current=MIN(hp_current+5, ?) "
                "WHERE playthrough_id=?",
                (next_level, new_hp_max, new_hp_max, playthrough_id)
            )
            conn.commit()

    conn.close()
