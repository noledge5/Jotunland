import os
import json
from flask import Flask, request, jsonify, render_template, session
from db import get_db, init_db
from engine import (
    resolve_skill_check, apply_engine_result, apply_narrator_output,
    advance_time, get_combat_state, resolve_combat_turn, check_level_up
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
        "SELECT skill_name, level, xp FROM player_skills WHERE playthrough_id=?",
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

    # Get current scene/zone names
    scene_name = player['current_scene_id'] or "Unknown"
    if player['current_scene_id']:
        scene_row = conn.execute(
            "SELECT name FROM scenes WHERE id=?", (player['current_scene_id'],)
        ).fetchone()
        if scene_row:
            scene_name = scene_row['name']

    conn.close()

    return {
        "playthrough_id": playthrough_id,
        "name": player['name'],
        "class": player['class'],
        "level": player['level'],
        "xp": player['xp'],
        "hp_current": player['hp_current'],
        "hp_max": player['hp_max'],
        "gold": player['gold'],
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
        "skills": [dict(s) for s in skills],
        "inventory": [dict(i) for i in inventory],
        "quests": [dict(q) for q in quests],
        "injuries": [dict(i) for i in injuries]
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/new_game', methods=['POST'])
def new_game():
    """Create new playthrough. Body: {"name": str, "class": str}"""
    data = request.get_json()
    if not data or not data.get('name') or not data.get('class'):
        return jsonify({"error": "name and class required"}), 400

    char_name = data['name'].strip()
    char_class = data['class'].strip()
    api_key = data.get('api_key') or None
    model = data.get('model') or None
    provider = data.get('provider', 'anthropic')

    skills_data = _load_skills()
    valid_classes = list(skills_data['class_starting_skills'].keys())
    if char_class not in valid_classes:
        return jsonify({"error": f"Invalid class. Choose: {', '.join(valid_classes)}"}), 400

    conn = get_db(DB_PATH)

    # Create playthrough
    cursor = conn.execute(
        "INSERT INTO playthroughs (character_name, character_class) VALUES (?,?)",
        (char_name, char_class)
    )
    playthrough_id = cursor.lastrowid

    # Create player record
    conn.execute(
        "INSERT INTO player (playthrough_id, name, class, current_scene_id) VALUES (?,?,?,?)",
        (playthrough_id, char_name, char_class, 'salzhaven_goldenes_schiff')
    )

    # Initialize skills from class config
    starting_skills = skills_data['class_starting_skills'].get(char_class, {})
    for skill_obj in skills_data['skills']:
        skill_name = skill_obj['name']
        skill_level = starting_skills.get(skill_name, 0)
        conn.execute(
            "INSERT OR IGNORE INTO player_skills (playthrough_id, skill_name, level, xp) VALUES (?,?,?,0)",
            (playthrough_id, skill_name, skill_level)
        )

    # Give starting equipment based on class
    starting_items = {
        "Krieger": [("Sword", 1, 1, '{"damage": "1d6+2"}'), ("Leather Armor", 1, 1, '{"defense": 2}')],
        "Schurke": [("Dagger", 1, 1, '{"damage": "1d4"}'), ("Lockpicks", 1, 0, '{}')],
        "Händler": [("Merchant Ledger", 1, 0, '{}'), ("Fine Clothes", 1, 1, '{}')],
        "Essenzkundiger": [("Essenz Focus Crystal", 1, 1, '{"essenz_bonus": 1}'), ("Scholar Robes", 1, 1, '{}')],
        "Waldläufer": [("Hunting Bow", 1, 1, '{"damage": "1d6"}'), ("Quiver (20 arrows)", 1, 0, '{}'), ("Hunting Knife", 1, 0, '{"damage": "1d4"}')]
    }
    for item_name, qty, equipped, props in starting_items.get(char_class, []):
        conn.execute(
            "INSERT INTO inventory (playthrough_id, item_name, quantity, equipped, properties) VALUES (?,?,?,?,?)",
            (playthrough_id, item_name, qty, equipped, props)
        )

    # Create initial session log entry
    cursor2 = conn.execute(
        "INSERT INTO session_log (playthrough_id, summary) VALUES (?,?)",
        (playthrough_id, f"{char_name} the {char_class} begins their story in Salzhaven, at the Goldenes Schiff inn.")
    )
    session_id = cursor2.lastrowid

    conn.commit()
    conn.close()

    # Generate opening narration
    initial_engine_result = {"needs_roll": False, "skill_result": None, "status": "new_game"}
    context_prompt = build_context(playthrough_id, "I arrive at the Goldenes Schiff and look around.", initial_engine_result)
    narrator_output = generate_narration(context_prompt, api_key=api_key, model=model, provider=provider)
    narration = narrator_output.get("narration", "You stand in the Goldenes Schiff, a familiar crossroads of travelers and secrets.")

    # Log the opening turn
    ts = "743-04-12 09:00"
    conn2 = get_db(DB_PATH)
    turn_count = conn2.execute(
        "SELECT COUNT(*) as cnt FROM turn_log WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()['cnt']
    conn2.execute(
        "INSERT INTO turn_log (playthrough_id, session_id, turn_number, player_input, "
        "engine_result, narration, time_delta_minutes, in_game_timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (playthrough_id, session_id, turn_count + 1, "[Game Start]",
         json.dumps(initial_engine_result), narration, 0, ts)
    )
    conn2.commit()
    conn2.close()

    state = _get_player_state(playthrough_id)
    return jsonify({
        "playthrough_id": playthrough_id,
        "narration": narration,
        "game_state": state
    })


@app.route('/api/turn', methods=['POST'])
def take_turn():
    """Process one player turn."""
    data = request.get_json()
    if not data or not data.get('playthrough_id') or not data.get('input'):
        return jsonify({"error": "playthrough_id and input required"}), 400

    playthrough_id = int(data['playthrough_id'])
    player_input = data['input'].strip()

    if not player_input:
        return jsonify({"error": "input cannot be empty"}), 400

    conn = get_db(DB_PATH)
    player = conn.execute(
        "SELECT * FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    if not player:
        conn.close()
        return jsonify({"error": "Playthrough not found"}), 404

    in_combat = bool(player['in_combat'])
    current_scene_id = player['current_scene_id'] or 'unknown'

    # Get session id
    session_row = conn.execute(
        "SELECT id FROM session_log WHERE playthrough_id=? ORDER BY id DESC LIMIT 1",
        (playthrough_id,)
    ).fetchone()
    session_id = session_row['id'] if session_row else None

    # Turn count
    turn_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM turn_log WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()['cnt']

    conn.close()

    # 1. Build skill list
    skills_data = _load_skills()
    skill_list = [s['name'] for s in skills_data['skills']]

    # Get scene name for classifier context
    conn2 = get_db(DB_PATH)
    scene_row = conn2.execute("SELECT name FROM scenes WHERE id=?", (current_scene_id,)).fetchone()
    scene_name = scene_row['name'] if scene_row else current_scene_id
    conn2.close()

    api_key = data.get('api_key') or None
    model = data.get('model') or None
    provider = data.get('provider', 'anthropic')

    # 2. Classify action (LLM Call #1)
    classifier_output = classify_action(player_input, skill_list, scene_name, in_combat,
                                        api_key=api_key, model=model, provider=provider)

    # 3. Resolve mechanics
    skill_result = None
    if classifier_output.get('needs_roll') and classifier_output.get('skill'):
        skill_name = classifier_output['skill']
        difficulty_tier = classifier_output.get('difficulty_tier', 'Medium')
        if in_combat and classifier_output.get('target'):
            # Route through combat resolution
            combat_result = resolve_combat_turn(playthrough_id, player_input, classifier_output['target'])
            engine_result = {
                "needs_roll": True,
                "skill_result": combat_result.get('player_attack'),
                "combat_result": combat_result,
                "status": "combat_resolved"
            }
        else:
            skill_result = resolve_skill_check(playthrough_id, skill_name, difficulty_tier)
            engine_result = apply_engine_result(playthrough_id, classifier_output, skill_result)
    else:
        engine_result = apply_engine_result(playthrough_id, classifier_output, None)

    # 4. Build context
    context_prompt = build_context(playthrough_id, player_input, engine_result)

    # 5. Generate narration (LLM Call #2)
    narrator_output = generate_narration(context_prompt, api_key=api_key, model=model, provider=provider)
    narration = narrator_output.get("narration", "The moment passes.")

    # 6. Apply narrator output to DB
    apply_narrator_output(playthrough_id, narrator_output)

    # 7. Log the turn
    conn3 = get_db(DB_PATH)
    p_time = conn3.execute(
        "SELECT in_game_year, in_game_month, in_game_day, in_game_hour, in_game_minute "
        "FROM player WHERE playthrough_id=?", (playthrough_id,)
    ).fetchone()
    ts = f"{p_time['in_game_year']}-{p_time['in_game_month']:02d}-{p_time['in_game_day']:02d} {p_time['in_game_hour']:02d}:{p_time['in_game_minute']:02d}"

    conn3.execute(
        "INSERT INTO turn_log (playthrough_id, session_id, turn_number, player_input, "
        "engine_result, narration, time_delta_minutes, in_game_timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (playthrough_id, session_id, turn_count + 1, player_input,
         json.dumps(engine_result), narration,
         narrator_output.get('time_delta_minutes', 5), ts)
    )

    # 8. Check synopsis trigger
    rb = _load_rulebook()
    synopsis_every = rb.get('synopsis_every_n_turns', 20)
    if (turn_count + 1) % synopsis_every == 0:
        recent_turns = conn3.execute(
            "SELECT narration FROM turn_log WHERE playthrough_id=? ORDER BY turn_number DESC LIMIT ?",
            (playthrough_id, synopsis_every)
        ).fetchall()
        recent_narrations = [t['narration'] for t in reversed(recent_turns)]
        p = conn3.execute("SELECT name, class, level FROM player WHERE playthrough_id=?", (playthrough_id,)).fetchone()
        player_summary = f"{p['name']} the {p['class']} (Level {p['level']})"
        synopsis = generate_session_synopsis(recent_narrations, player_summary,
                                              api_key=api_key, model=model, provider=provider)
        conn3.execute(
            "INSERT INTO session_log (playthrough_id, summary) VALUES (?,?)",
            (playthrough_id, synopsis)
        )

    conn3.commit()
    conn3.close()

    check_level_up(playthrough_id)
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
        return jsonify({"error": "playthrough_id required"}), 400
    try:
        playthrough_id = int(playthrough_id)
    except ValueError:
        return jsonify({"error": "invalid playthrough_id"}), 400

    state = _get_player_state(playthrough_id)
    if not state:
        return jsonify({"error": "Playthrough not found"}), 404
    return jsonify(state)


@app.route('/api/playthroughs', methods=['GET'])
def list_playthroughs():
    """List all active playthroughs."""
    conn = get_db(DB_PATH)
    rows = conn.execute(
        "SELECT p.id, p.character_name, p.character_class, p.created_at, "
        "pl.level, pl.hp_current, pl.hp_max "
        "FROM playthroughs p LEFT JOIN player pl ON pl.playthrough_id = p.id "
        "WHERE p.status='active' ORDER BY p.id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/classes', methods=['GET'])
def list_classes():
    """Return available character classes."""
    skills_data = _load_skills()
    classes = []
    for cls_name, starting_skills in skills_data['class_starting_skills'].items():
        classes.append({
            "name": cls_name,
            "starting_skills": starting_skills
        })
    return jsonify(classes)


if __name__ == '__main__':
    init_db(DB_PATH)
    import_world(DB_PATH)
    app.run(debug=True, port=5000)
