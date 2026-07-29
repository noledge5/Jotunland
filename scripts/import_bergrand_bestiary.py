"""
Import Bergrand Bestiary — lädt Kreaturen aus world/data/bergrand_bestiary.json in die npcs-Tabelle.
Idempotent (INSERT OR REPLACE). Läuft standalone: python3 -m scripts.import_bergrand_bestiary
"""
import json
import os
import sys

# Ensure rpg_engine is on the path when run as a module from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rpg_engine'))

from db import get_db, init_db

BESTIARY_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'world', 'data', 'bergrand_bestiary.json'
)
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'rpg_engine', 'rpg.db')


def import_bestiary(db_path=DB_PATH):
    if not os.path.exists(BESTIARY_PATH):
        print(f"[Bestiary] Datei nicht gefunden: {BESTIARY_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(BESTIARY_PATH, encoding='utf-8') as f:
        data = json.load(f)

    creatures = data.get('creatures', [])
    if not creatures:
        print("[Bestiary] Keine Einträge in 'creatures'.")
        return

    # Ensure DB and tables exist
    init_db(db_path)
    conn = get_db(db_path)

    inserted = 0
    updated = 0
    for c in creatures:
        cid = c.get('id')
        if not cid:
            print(f"[Bestiary] Übersprungen — kein 'id': {c}", file=sys.stderr)
            continue

        existing = conn.execute("SELECT id FROM npcs WHERE id=?", (cid,)).fetchone()

        conn.execute(
            """INSERT OR REPLACE INTO npcs
               (id, name, role, description, personality, faction, tier, knowledge,
                relation_score_default, stats)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                cid,
                c.get('name', cid),
                c.get('role', 'Kreatur'),
                c.get('description', ''),
                c.get('personality', ''),
                c.get('faction', 'wildnis'),
                c.get('tier', 'creature'),
                c.get('knowledge', ''),
                0,
                json.dumps(c.get('stats', {})),
            )
        )
        if existing:
            updated += 1
        else:
            inserted += 1

    conn.commit()
    conn.close()
    print(f"[Bestiary] Bergrand — {inserted} neu importiert, {updated} aktualisiert. DB: {db_path}")


if __name__ == '__main__':
    import_bestiary()
