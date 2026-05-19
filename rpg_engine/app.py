import os
import json
from flask import Flask, request, jsonify, render_template
from db import get_db, init_db
import trace as _trace
from engine import (
    apply_narrator_output, advance_time,
    request_roll, resolve_player_roll,
    get_current_scene_npcs, check_char_level_up,
    calculate_max_hp, process_dying,
    resolve_combat_turn, resolve_combat_after_roll
)
from context_builder import build_context
from llm import classify_action, generate_narration, generate_session_synopsis
from world_importer import import_world

app = Flask(__name__)
app.secret_key = os.environ.get('RPG_SECRET_KEY', 'rpg-secret-key-change-in-prod')

DB_PATH = os.path.join(os.path.dirname(__file__), 'rpg.db')
SKILLS_PATH = os.path.join(os.path.dirname(__file__), 'config', 'skills.json')
RULEBOOK_PATH = os.path.join(os.path.dirname(__file__), 'config', 'rulebook.json')

_skills_data = None
_rulebook_data = None


def _load_skills():
    global _skills_data
    if _skills_data is None:
        with open(SKILLS_PATH) as f:
            _skills_data = json.load(f)
    return _skills_data


def _load_rulebook():
    global _rulebook_data
    if _rulebook_data is None:
        with open(RULEBOOK_PATH) as f:
            _rulebook_data = json.load(f)
    return _rulebook_data


def _get_player_state(playthrough_id):
    conn = get_db(DB_PATH)
    player = conn.execute(
        "SELECT * FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    if not player:
        conn.close()
        return None

    skills = conn.execute(
        "SELECT skill_name, level, ticks FROM player_skills WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchall()

    attributes = conn.execute(
        "SELECT attr_name, value FROM player_attributes WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchall()

    inventory = conn.execute(
        "SELECT item_name, quantity, equipped, properties FROM inventory WHERE playthrough_id=?",
        (playthrough_id,)
    ).fetchall()

    quests = conn.execute(
        "SELECT title, status, description FROM quests WHERE playthrough_id=? AND status='active'",
        (playthrough_id,)
    ).fetchall()

    injuries = conn.execute(
        "SELECT injury_name, affected_skill, modifier FROM injuries "
        "WHERE playthrough_id=? AND entity_type='player'",
        (playthrough_id,)
    ).fetchall()

    scene_name = player['current_scene_id'] or "Unbekannt"
    if player['current_scene_id']:
        scene_row = conn.execute(
            "SELECT name FROM scenes WHERE id=?", (player['current_scene_id'],)
        ).fetchone()
        if scene_row:
            scene_name = scene_row['name']

    # Pending roll
    pending_roll = None
    if player['pending_roll']:
        try:
            pending_roll = json.loads(player['pending_roll'])
        except Exception:
            pass

    conn.close()

    # Build skill tick info
    skills_with_ticks = []
    for s in skills:
        from engine import _tick_threshold_for_value
        ticks_needed = _tick_threshold_for_value(s['level'])
        skills_with_ticks.append({
            "skill_name": s['skill_name'],
            "level": s['level'],
            "ticks": s['ticks'],
            "ticks_needed": ticks_needed
        })

    return {
        "playthrough_id": playthrough_id,
        "name": player['name'],
        "class": player['class'],
        "level": player['level'],
        "hp_current": player['hp_current'],
        "hp_max": player['hp_max'],
        "gold": player['gold'],
        "skill_ups_count": player['skill_ups_count'] if 'skill_ups_count' in player.keys() else 0,
        "current_scene_id": player['current_scene_id'],
        "current_scene_name": scene_name,
        "in_combat": bool(player['in_combat']),
        "time": {
            "year": player['in_game_year'],
            "month": player['in_game_month'],
            "day": player['in_game_day'],
            "hour": player['in_game_hour'],
            "minute": player['in_game_minute']
        },
        "attributes": {r['attr_name']: r['value'] for r in attributes},
        "skills": skills_with_ticks,
        "inventory": [dict(i) for i in inventory],
        "quests": [dict(q) for q in quests],
        "injuries": [dict(i) for i in injuries],
        "pending_roll": pending_roll
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/character_options', methods=['GET'])
def character_options():
    """Return all skills, classes, and pool constants."""
    sk = _load_skills()
    rb = _load_rulebook()
    return jsonify({
        "skills": sk['skills'],
        "classes": [
            {
                "name": name,
                "description": data['description'],
                "starting_items": data['starting_items']
            }
            for name, data in sk['classes'].items()
        ],
        "attr_pool": rb['attr_start_pool'],
        "skill_pool": rb['skill_start_pool'],
        "attr_min": rb['attr_start_min'],
        "attr_max": rb['attr_start_max'],
        "skill_max": rb['skill_start_max']
    })


@app.route('/api/new_game', methods=['POST'])
def new_game():
    """
    Create new playthrough.
    Body: {
      "name": str, "class": str, "background": str,
      "attributes": {"STR":14,...}, "skills": {"Klingenwaffen":30,...},
      "api_key": str, "model": str, "provider": str
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    char_name = (data.get('name') or '').strip()
    char_class = (data.get('class') or '').strip()
    background = (data.get('background') or '').strip()
    api_key = data.get('api_key') or None
    model = data.get('model') or None
    provider = data.get('provider', 'anthropic')

    if not char_name:
        return jsonify({"error": "Name darf nicht leer sein."}), 400

    sk = _load_skills()
    rb = _load_rulebook()

    valid_classes = list(sk['classes'].keys())
    if char_class not in valid_classes:
        return jsonify({"error": f"Ungültige Klasse. Wähle: {', '.join(valid_classes)}"}), 400

    # Validate attributes
    attributes = data.get('attributes') or {}
    required_attrs = ['STR', 'GES', 'KON', 'INT', 'WEI', 'CHA']
    missing = [a for a in required_attrs if a not in attributes]
    if missing:
        return jsonify({"error": f"Fehlende Attribute: {', '.join(missing)}"}), 400

    attr_sum = sum(attributes[a] for a in required_attrs)
    if attr_sum != rb['attr_start_pool']:
        return jsonify({"error": f"Attribut-Summe muss {rb['attr_start_pool']} sein (aktuell: {attr_sum})."}), 400

    for a in required_attrs:
        v = attributes[a]
        if v < rb['attr_start_min'] or v > rb['attr_start_max']:
            return jsonify({"error": f"Attribut {a}={v} muss zwischen {rb['attr_start_min']} und {rb['attr_start_max']} liegen."}), 400

    # Validate skills
    skills_input = data.get('skills') or {}
    valid_skill_names = {s['name'] for s in sk['skills']}
    for sname in skills_input:
        if sname not in valid_skill_names:
            return jsonify({"error": f"Unbekannter Skill: {sname}"}), 400
        if skills_input[sname] > rb['skill_start_max']:
            return jsonify({"error": f"Skill {sname} darf maximal {rb['skill_start_max']} sein."}), 400

    skill_sum = sum(skills_input.values())
    if skill_sum > rb['skill_start_pool']:
        return jsonify({"error": f"Skill-Summe darf maximal {rb['skill_start_pool']} sein (aktuell: {skill_sum})."}), 400

    # Calculate HP
    kon_val = attributes['KON']
    hp_max = calculate_max_hp(kon_val, 1)

    conn = get_db(DB_PATH)

    # Create playthrough
    cursor = conn.execute(
        "INSERT INTO playthroughs (character_name, character_class) VALUES (?,?)",
        (char_name, char_class)
    )
    playthrough_id = cursor.lastrowid

    # Create player record
    conn.execute(
        "INSERT INTO player (playthrough_id, name, class, current_scene_id, hp_max, hp_current, background) "
        "VALUES (?,?,?,?,?,?,?)",
        (playthrough_id, char_name, char_class, 'salzhaven_goldenes_schiff', hp_max, hp_max, background)
    )

    # Store attributes
    for attr_name, val in attributes.items():
        conn.execute(
            "INSERT OR REPLACE INTO player_attributes (playthrough_id, attr_name, value) VALUES (?,?,?)",
            (playthrough_id, attr_name, val)
        )

    # Initialize all skills (only those with value > 0 get stored explicitly, others at 0)
    for skill_obj in sk['skills']:
        sname = skill_obj['name']
        sval = skills_input.get(sname, 0)
        conn.execute(
            "INSERT OR IGNORE INTO player_skills (playthrough_id, skill_name, level, ticks) VALUES (?,?,?,0)",
            (playthrough_id, sname, sval)
        )

    # Give starting equipment
    for item_name in sk['classes'][char_class]['starting_items']:
        conn.execute(
            "INSERT INTO inventory (playthrough_id, item_name, quantity, equipped, properties) VALUES (?,?,1,0,'{}' )",
            (playthrough_id, item_name)
        )

    # Create initial session log
    cursor2 = conn.execute(
        "INSERT INTO session_log (playthrough_id, summary) VALUES (?,?)",
        (playthrough_id, f"{char_name}, ein {char_class}, beginnt seine Geschichte in Salzhaven, im Goldenen Schiff.")
    )
    session_id = cursor2.lastrowid

    conn.commit()
    conn.close()

    # Generate opening narration
    initial_engine_result = {"needs_roll": False, "skill_result": None, "status": "new_game"}
    context_prompt = build_context(playthrough_id, "Ich betrete das Goldene Schiff und schaue mich um.", initial_engine_result)
    narrator_output = generate_narration(context_prompt, api_key=api_key, model=model, provider=provider)
    narration = narrator_output.get("narration", "Du stehst im Goldenen Schiff — ein vertrauter Knotenpunkt der Reisenden und Geheimnisse.")

    ts = "743-04-12 09:00"
    conn2 = get_db(DB_PATH)
    turn_count = conn2.execute(
        "SELECT COUNT(*) as cnt FROM turn_log WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()['cnt']
    conn2.execute(
        "INSERT INTO turn_log (playthrough_id, session_id, turn_number, player_input, "
        "engine_result, narration, time_delta_minutes, in_game_timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (playthrough_id, session_id, turn_count + 1, "[Spielbeginn]",
         json.dumps(initial_engine_result), narration, 0, ts)
    )
    conn2.commit()
    conn2.close()

    apply_narrator_output(playthrough_id, narrator_output)
    state = _get_player_state(playthrough_id)

    return jsonify({
        "playthrough_id": playthrough_id,
        "narration": narration,
        "game_state": state,
        "starting_items": sk['classes'][char_class]['starting_items']
    })


@app.route('/api/turn', methods=['POST'])
def take_turn():
    """Process one player turn."""
    data = request.get_json()
    if not data or not data.get('playthrough_id') or not data.get('input'):
        return jsonify({"error": "playthrough_id und input erforderlich"}), 400

    playthrough_id = int(data['playthrough_id'])
    player_input = data['input'].strip()
    _trace.new_turn(playthrough_id, player_input)

    if not player_input:
        return jsonify({"error": "input darf nicht leer sein"}), 400

    conn = get_db(DB_PATH)
    player = conn.execute(
        "SELECT * FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    if not player:
        conn.close()
        return jsonify({"error": "Playthrough nicht gefunden"}), 404

    # Check for pending roll
    if player['pending_roll']:
        try:
            pending = json.loads(player['pending_roll'])
        except Exception:
            pending = {}
        conn.close()
        return jsonify({
            "error": "Würfelwurf ausstehend",
            "pending_roll": pending
        }), 409

    in_combat = bool(player['in_combat'])
    current_scene_id = player['current_scene_id'] or 'unknown'

    session_row = conn.execute(
        "SELECT id FROM session_log WHERE playthrough_id=? ORDER BY id DESC LIMIT 1",
        (playthrough_id,)
    ).fetchone()
    session_id = session_row['id'] if session_row else None

    turn_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM turn_log WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()['cnt']

    conn.close()

    sk = _load_skills()
    skill_list = [s['name'] for s in sk['skills']]

    conn2 = get_db(DB_PATH)
    scene_row = conn2.execute("SELECT name FROM scenes WHERE id=?", (current_scene_id,)).fetchone()
    scene_name = scene_row['name'] if scene_row else current_scene_id
    conn2.close()

    api_key = data.get('api_key') or None
    model = data.get('model') or None
    provider = data.get('provider', 'anthropic')

    # 1. Classify action
    classifier_output = classify_action(player_input, skill_list, scene_name, in_combat,
                                        api_key=api_key, model=model, provider=provider)

    # 2. Check if roll needed
    if classifier_output.get('needs_roll') and classifier_output.get('skill'):
        skill_name = classifier_output['skill']
        difficulty_tier = classifier_output.get('difficulty_tier', 'Durchschnitt')

        # Request external roll
        roll_request = request_roll(playthrough_id, skill_name, difficulty_tier)

        # Log the input (no narration yet)
        conn3 = get_db(DB_PATH)
        conn3.execute(
            "INSERT INTO turn_log (playthrough_id, session_id, turn_number, player_input, "
            "engine_result, narration, time_delta_minutes, in_game_timestamp) VALUES (?,?,?,?,?,?,?,?)",
            (playthrough_id, session_id, turn_count + 1, player_input,
             json.dumps({"awaiting_roll": True, "roll_request": roll_request}),
             "", 0, "pending")
        )
        conn3.commit()
        conn3.close()

        state = _get_player_state(playthrough_id)
        return jsonify({
            "state": "awaiting_roll",
            "roll_request": roll_request,
            "game_state": state
        })

    # 3. No roll needed — direct narration
    engine_result = {
        "needs_roll": False,
        "skill_result": None,
        "target": classifier_output.get('target'),
        "status": "resolved"
    }

    context_prompt = build_context(playthrough_id, player_input, engine_result)
    narrator_output = generate_narration(context_prompt, api_key=api_key, model=model, provider=provider)
    narration = narrator_output.get("narration", "Der Moment vergeht.")

    apply_narrator_output(playthrough_id, narrator_output)

    conn4 = get_db(DB_PATH)
    p_time = conn4.execute(
        "SELECT in_game_year, in_game_month, in_game_day, in_game_hour, in_game_minute "
        "FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    ts = f"{p_time['in_game_year']}-{p_time['in_game_month']:02d}-{p_time['in_game_day']:02d} {p_time['in_game_hour']:02d}:{p_time['in_game_minute']:02d}"

    conn4.execute(
        "INSERT INTO turn_log (playthrough_id, session_id, turn_number, player_input, "
        "engine_result, narration, time_delta_minutes, in_game_timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (playthrough_id, session_id, turn_count + 1, player_input,
         json.dumps(engine_result), narration,
         narrator_output.get('time_delta_minutes', 5), ts)
    )

    # Synopsis check
    rb = _load_rulebook()
    synopsis_every = rb.get('synopsis_every_n_turns', 20)
    if (turn_count + 1) % synopsis_every == 0:
        recent_turns = conn4.execute(
            "SELECT narration FROM turn_log WHERE playthrough_id=? ORDER BY turn_number DESC LIMIT ?",
            (playthrough_id, synopsis_every)
        ).fetchall()
        recent_narrations = [t['narration'] for t in reversed(recent_turns)]
        p = conn4.execute("SELECT name, class, level FROM player WHERE playthrough_id=?", (playthrough_id,)).fetchone()
        player_summary = f"{p['name']} der {p['class']} (Level {p['level']})"
        synopsis = generate_session_synopsis(recent_narrations, player_summary,
                                             api_key=api_key, model=model, provider=provider)
        conn4.execute(
            "INSERT INTO session_log (playthrough_id, summary) VALUES (?,?)",
            (playthrough_id, synopsis)
        )

    conn4.commit()
    conn4.close()

    check_char_level_up(playthrough_id)
    state = _get_player_state(playthrough_id)

    return jsonify({
        "narration": narration,
        "engine_result": engine_result,
        "narrator_output": {
            "time_delta_minutes": narrator_output.get("time_delta_minutes", 5),
            "world_state_changes": narrator_output.get("world_state_changes", []),
            "generated_npcs": [n.get("name") for n in narrator_output.get("generated_npcs", [])],
            "generated_locations": [l.get("name") for l in narrator_output.get("generated_locations", [])]
        },
        "game_state": state
    })


@app.route('/api/roll', methods=['POST'])
def submit_roll():
    """Submit a player's physical dice roll result."""
    data = request.get_json()
    if not data or not data.get('playthrough_id') or data.get('dice_result') is None:
        return jsonify({"error": "playthrough_id und dice_result erforderlich"}), 400

    playthrough_id = int(data['playthrough_id'])
    dice_result = int(data['dice_result'])

    if dice_result < 1 or dice_result > 20:
        return jsonify({"error": "dice_result muss zwischen 1 und 20 liegen"}), 400

    api_key = data.get('api_key') or None
    model = data.get('model') or None
    provider = data.get('provider', 'anthropic')

    # Resolve the roll
    engine_result = resolve_player_roll(playthrough_id, dice_result)

    if 'error' in engine_result:
        return jsonify(engine_result), 400

    # Build context and narrate
    player_input_for_ctx = data.get('player_input', '[Würfelwurf]')
    context_prompt = build_context(playthrough_id, player_input_for_ctx, engine_result)
    narrator_output = generate_narration(context_prompt, api_key=api_key, model=model, provider=provider)
    narration = narrator_output.get("narration", "Der Moment vergeht.")

    apply_narrator_output(playthrough_id, narrator_output)

    # Update the pending turn_log entry (last one with no narration)
    conn = get_db(DB_PATH)
    p_time = conn.execute(
        "SELECT in_game_year, in_game_month, in_game_day, in_game_hour, in_game_minute "
        "FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    ts = f"{p_time['in_game_year']}-{p_time['in_game_month']:02d}-{p_time['in_game_day']:02d} {p_time['in_game_hour']:02d}:{p_time['in_game_minute']:02d}"

    # Update the last pending log entry (SQLite doesn't support ORDER BY in UPDATE)
    conn.execute(
        "UPDATE turn_log SET engine_result=?, narration=?, time_delta_minutes=?, in_game_timestamp=? "
        "WHERE id = ("
        "  SELECT id FROM turn_log "
        "  WHERE playthrough_id=? AND narration='' AND in_game_timestamp='pending' "
        "  ORDER BY id DESC LIMIT 1"
        ")",
        (json.dumps(engine_result), narration,
         narrator_output.get('time_delta_minutes', 5), ts, playthrough_id)
    )

    # Synopsis check
    rb = _load_rulebook()
    synopsis_every = rb.get('synopsis_every_n_turns', 20)
    turn_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM turn_log WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()['cnt']

    if turn_count % synopsis_every == 0:
        recent_turns = conn.execute(
            "SELECT narration FROM turn_log WHERE playthrough_id=? ORDER BY turn_number DESC LIMIT ?",
            (playthrough_id, synopsis_every)
        ).fetchall()
        recent_narrations = [t['narration'] for t in reversed(recent_turns) if t['narration']]
        p = conn.execute("SELECT name, class, level FROM player WHERE playthrough_id=?", (playthrough_id,)).fetchone()
        player_summary = f"{p['name']} der {p['class']} (Level {p['level']})"
        session_row = conn.execute(
            "SELECT id FROM session_log WHERE playthrough_id=? ORDER BY id DESC LIMIT 1",
            (playthrough_id,)
        ).fetchone()
        synopsis = generate_session_synopsis(recent_narrations, player_summary,
                                             api_key=api_key, model=model, provider=provider)
        conn.execute(
            "INSERT INTO session_log (playthrough_id, summary) VALUES (?,?)",
            (playthrough_id, synopsis)
        )

    conn.commit()
    conn.close()

    check_char_level_up(playthrough_id)
    state = _get_player_state(playthrough_id)

    return jsonify({
        "narration": narration,
        "engine_result": engine_result,
        "narrator_output": {
            "time_delta_minutes": narrator_output.get("time_delta_minutes", 5),
            "world_state_changes": narrator_output.get("world_state_changes", []),
            "generated_npcs": [n.get("name") for n in narrator_output.get("generated_npcs", [])],
            "generated_locations": [l.get("name") for l in narrator_output.get("generated_locations", [])]
        },
        "game_state": state
    })


@app.route('/api/game_state', methods=['GET'])
def game_state():
    """Return current game state for playthrough_id query param."""
    playthrough_id = request.args.get('playthrough_id')
    if not playthrough_id:
        return jsonify({"error": "playthrough_id erforderlich"}), 400
    try:
        playthrough_id = int(playthrough_id)
    except ValueError:
        return jsonify({"error": "Ungültige playthrough_id"}), 400

    state = _get_player_state(playthrough_id)
    if not state:
        return jsonify({"error": "Playthrough nicht gefunden"}), 404
    return jsonify(state)


@app.route('/api/playthroughs', methods=['GET'])
def list_playthroughs():
    """List all active playthroughs with last-played time and location."""
    conn = get_db(DB_PATH)
    rows = conn.execute(
        "SELECT p.id, p.character_name, p.character_class, p.created_at, "
        "pl.level, pl.hp_current, pl.hp_max, pl.current_scene_id, "
        "pl.in_game_year, pl.in_game_month, pl.in_game_day, pl.in_game_hour, pl.in_game_minute "
        "FROM playthroughs p LEFT JOIN player pl ON pl.playthrough_id = p.id "
        "WHERE p.status='active' ORDER BY p.id DESC"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # Last turn timestamp
        last_turn = conn.execute(
            "SELECT in_game_timestamp FROM turn_log WHERE playthrough_id=? "
            "AND in_game_timestamp != 'pending' ORDER BY id DESC LIMIT 1",
            (r['id'],)
        ).fetchone()
        d['last_played'] = last_turn['in_game_timestamp'] if last_turn else None
        # Scene name
        if r['current_scene_id']:
            scene = conn.execute(
                "SELECT name FROM scenes WHERE id=?", (r['current_scene_id'],)
            ).fetchone()
            d['location_name'] = scene['name'] if scene else r['current_scene_id']
        else:
            d['location_name'] = '—'
        result.append(d)
    conn.close()
    return jsonify(result)


@app.route('/api/delete_playthrough', methods=['POST'])
def delete_playthrough():
    """Hard-delete a playthrough and all its character-scoped data."""
    data = request.get_json()
    if not data or not data.get('playthrough_id'):
        return jsonify({"error": "playthrough_id erforderlich"}), 400
    pid = int(data['playthrough_id'])
    conn = get_db(DB_PATH)
    tables = [
        'player', 'player_attributes', 'player_skills', 'inventory',
        'npc_relations', 'world_state_flags', 'combat_combatants',
        'injuries', 'session_log', 'turn_log', 'quests'
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table} WHERE playthrough_id=?", (pid,))
    conn.execute("DELETE FROM playthroughs WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route('/api/turn_history', methods=['GET'])
def turn_history():
    """Return last N turns for a playthrough (for chat restore on continue)."""
    pid = request.args.get('playthrough_id')
    n = int(request.args.get('n', 10))
    if not pid:
        return jsonify({"error": "playthrough_id erforderlich"}), 400
    conn = get_db(DB_PATH)
    rows = conn.execute(
        "SELECT player_input, narration, engine_result FROM turn_log "
        "WHERE playthrough_id=? AND narration != '' AND in_game_timestamp != 'pending' "
        "ORDER BY id DESC LIMIT ?",
        (int(pid), n)
    ).fetchall()
    conn.close()
    turns = list(reversed([dict(r) for r in rows]))
    return jsonify(turns)


@app.route('/api/classes', methods=['GET'])
def list_classes():
    """Return available character classes (legacy endpoint)."""
    sk = _load_skills()
    classes = []
    for name, data in sk['classes'].items():
        classes.append({
            "name": name,
            "description": data['description'],
            "starting_items": data['starting_items']
        })
    return jsonify(classes)


@app.route('/api/debug/trace', methods=['GET'])
def debug_trace():
    """Return the trace log of the last turn (LLM calls, DB writes, state changes)."""
    return jsonify(_trace.get_trace())


if __name__ == '__main__':
    init_db(DB_PATH)
    import_world(DB_PATH)
    app.run(debug=True, port=5000)
