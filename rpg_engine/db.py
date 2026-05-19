import sqlite3
import os

def get_db(db_path=None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), 'rpg.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(db_path=None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), 'rpg.db')
    conn = get_db(db_path)
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS realms (
      id TEXT PRIMARY KEY, name TEXT, government_type TEXT,
      description TEXT, x INTEGER, y INTEGER,
      x_min INTEGER, y_min INTEGER, x_max INTEGER, y_max INTEGER
    );

    CREATE TABLE IF NOT EXISTS regions (
      id TEXT PRIMARY KEY, realm_id TEXT, name TEXT, climate TEXT,
      layer_b_text TEXT, x INTEGER, y INTEGER,
      x_min INTEGER, y_min INTEGER, x_max INTEGER, y_max INTEGER
    );

    CREATE TABLE IF NOT EXISTS city_areas (
      id TEXT PRIMARY KEY, region_id TEXT, name TEXT, size TEXT,
      population INTEGER, x INTEGER, y INTEGER,
      x_min INTEGER, y_min INTEGER, x_max INTEGER, y_max INTEGER
    );

    CREATE TABLE IF NOT EXISTS zones (
      id TEXT PRIMARY KEY,
      city_area_id TEXT,
      region_id TEXT,
      name TEXT, type TEXT, layer_c_text TEXT,
      x INTEGER, y INTEGER,
      x_min INTEGER, y_min INTEGER, x_max INTEGER, y_max INTEGER
    );

    CREATE TABLE IF NOT EXISTS scenes (
      id TEXT PRIMARY KEY, zone_id TEXT, parent_scene_id TEXT,
      name TEXT, type TEXT, layer_d_text TEXT,
      x INTEGER, y INTEGER
    );

    CREATE TABLE IF NOT EXISTS group_entries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scene_id TEXT, label TEXT, description TEXT
    );

    CREATE TABLE IF NOT EXISTS npcs (
      id TEXT PRIMARY KEY, name TEXT, role TEXT,
      description TEXT, personality TEXT, faction TEXT,
      tier TEXT DEFAULT 'generated',
      knowledge TEXT, relation_score_default INTEGER DEFAULT 0,
      home_scene_id TEXT, stats TEXT
    );

    CREATE TABLE IF NOT EXISTS npc_schedules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      npc_id TEXT, hour_start INTEGER, hour_end INTEGER, scene_id TEXT
    );

    CREATE TABLE IF NOT EXISTS playthroughs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      character_name TEXT, character_class TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      status TEXT DEFAULT 'active'
    );

    CREATE TABLE IF NOT EXISTS player (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER UNIQUE,
      name TEXT, class TEXT,
      level INTEGER DEFAULT 1,
      xp INTEGER DEFAULT 0,
      hp_current INTEGER DEFAULT 20,
      hp_max INTEGER DEFAULT 20,
      gold INTEGER DEFAULT 50,
      current_scene_id TEXT,
      x INTEGER DEFAULT 2380000, y INTEGER DEFAULT 1200000,
      in_game_year INTEGER DEFAULT 743,
      in_game_month INTEGER DEFAULT 4,
      in_game_day INTEGER DEFAULT 12,
      in_game_hour INTEGER DEFAULT 9,
      in_game_minute INTEGER DEFAULT 0,
      in_combat INTEGER DEFAULT 0,
      background TEXT DEFAULT '',
      pending_roll TEXT DEFAULT NULL,
      skill_ups_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS player_attributes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER,
      attr_name TEXT,
      value INTEGER DEFAULT 10,
      UNIQUE(playthrough_id, attr_name)
    );

    CREATE TABLE IF NOT EXISTS player_skills (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, skill_name TEXT,
      level INTEGER DEFAULT 0, xp INTEGER DEFAULT 0,
      ticks INTEGER DEFAULT 0,
      UNIQUE(playthrough_id, skill_name)
    );

    CREATE TABLE IF NOT EXISTS inventory (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, item_name TEXT,
      quantity INTEGER DEFAULT 1, equipped INTEGER DEFAULT 0,
      properties TEXT
    );

    CREATE TABLE IF NOT EXISTS npc_relations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, npc_id TEXT,
      met INTEGER DEFAULT 0, relation_score INTEGER DEFAULT 0,
      player_knows TEXT DEFAULT '', npc_knows TEXT DEFAULT '',
      shared_history TEXT DEFAULT '',
      UNIQUE(playthrough_id, npc_id)
    );

    CREATE TABLE IF NOT EXISTS world_state_flags (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, entity_type TEXT, entity_id TEXT,
      flag_name TEXT, flag_value TEXT,
      UNIQUE(playthrough_id, entity_type, entity_id, flag_name)
    );

    CREATE TABLE IF NOT EXISTS combat_combatants (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, entity_type TEXT, entity_id TEXT,
      combat_status TEXT DEFAULT 'active',
      initiative INTEGER DEFAULT 0,
      hp_current INTEGER, hp_max INTEGER,
      is_player INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS injuries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, entity_type TEXT, entity_id TEXT,
      injury_name TEXT, affected_skill TEXT, modifier INTEGER
    );

    CREATE TABLE IF NOT EXISTS session_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
      summary TEXT
    );

    CREATE TABLE IF NOT EXISTS turn_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, session_id INTEGER,
      turn_number INTEGER, player_input TEXT,
      engine_result TEXT, narration TEXT,
      time_delta_minutes INTEGER DEFAULT 5,
      in_game_timestamp TEXT
    );

    CREATE TABLE IF NOT EXISTS quests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playthrough_id INTEGER, title TEXT,
      status TEXT DEFAULT 'active',
      description TEXT, related_npc_id TEXT
    );
    """)

    conn.commit()

    # Idempotent column additions for existing DBs (catch exception if column exists)
    _add_column_if_missing(conn, 'player', 'background', "TEXT DEFAULT ''")
    _add_column_if_missing(conn, 'player', 'pending_roll', "TEXT DEFAULT NULL")
    _add_column_if_missing(conn, 'player', 'skill_ups_count', "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, 'player_skills', 'ticks', "INTEGER DEFAULT 0")

    conn.commit()
    conn.close()
    print(f"[DB] Initialized: {db_path}")


def _add_column_if_missing(conn, table, column, col_def):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        conn.commit()
    except Exception:
        pass  # Column already exists
