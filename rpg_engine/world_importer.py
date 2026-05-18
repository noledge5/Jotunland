import json
import sqlite3
import os

WORLD_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'world', 'data')


def _get_coord(obj, key='coordinate_anchor'):
    c = obj.get(key, {})
    return c.get('x', 0), c.get('y', 0)


def _get_bbox(obj):
    bb = obj.get('bounding_box', {})
    return (
        bb.get('x_min', 0), bb.get('y_min', 0),
        bb.get('x_max', 0), bb.get('y_max', 0)
    )


def import_scenes_for_zone(conn, zone_id, scenes):
    """Import scenes and sub_scenes for a zone."""
    for scene in scenes:
        x, y = _get_coord(scene)
        conn.execute(
            "INSERT OR IGNORE INTO scenes (id, zone_id, parent_scene_id, name, type, layer_d_text, x, y) "
            "VALUES (?,?,NULL,?,?,?,?,?)",
            (scene['id'], zone_id, scene.get('name', ''), scene.get('type', ''),
             scene.get('layer_d_text', ''), x, y)
        )
        # Group entries
        for ge in scene.get('group_entries', []):
            conn.execute(
                "INSERT INTO group_entries (scene_id, label, description) VALUES (?,?,?)",
                (scene['id'], ge.get('label', ''), ge.get('description', ''))
            )
        # Sub-scenes
        for sub in scene.get('sub_scenes', []):
            sx, sy = _get_coord(sub)
            conn.execute(
                "INSERT OR IGNORE INTO scenes (id, zone_id, parent_scene_id, name, type, layer_d_text, x, y) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (sub['id'], zone_id, scene['id'], sub.get('name', ''), sub.get('type', ''),
                 sub.get('layer_d_text', ''), sx, sy)
            )
            for ge in sub.get('group_entries', []):
                conn.execute(
                    "INSERT INTO group_entries (scene_id, label, description) VALUES (?,?,?)",
                    (sub['id'], ge.get('label', ''), ge.get('description', ''))
                )


def import_npcs(conn, npcs, realm_id=None):
    """Import static NPCs and their schedules."""
    for npc in npcs:
        stats_json = json.dumps(npc.get('stats', {}))
        conn.execute(
            "INSERT OR IGNORE INTO npcs (id, name, role, description, personality, faction, "
            "tier, knowledge, relation_score_default, stats) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                npc['id'], npc.get('name', ''), npc.get('role', ''),
                npc.get('description', ''), npc.get('personality', ''),
                npc.get('faction', ''), 'static',
                npc.get('knowledge', ''), npc.get('relation_score_default', 0),
                stats_json
            )
        )
        for sched in npc.get('schedule', []):
            conn.execute(
                "INSERT INTO npc_schedules (npc_id, hour_start, hour_end, scene_id) VALUES (?,?,?,?)",
                (npc['id'], sched['hour_start'], sched['hour_end'], sched['scene_id'])
            )


def import_salzhaven(conn, data):
    """Import Salzhaven city area and all its zones, scenes, group entries, npcs."""
    realm_id = data.get('realm_id', 'ostimperium')

    # Ensure realm exists
    conn.execute(
        "INSERT OR IGNORE INTO realms (id, name, government_type) VALUES (?,?,?)",
        (realm_id, 'Ostimperium', 'imperial')
    )

    region = data['region']
    rx, ry = _get_coord(region)
    rx_min, ry_min, rx_max, ry_max = _get_bbox(region)
    conn.execute(
        "INSERT OR IGNORE INTO regions (id, realm_id, name, climate, layer_b_text, x, y, "
        "x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (region['id'], realm_id, region['name'], region.get('climate', ''),
         region.get('layer_b_text', ''), rx, ry, rx_min, ry_min, rx_max, ry_max)
    )

    ca = data['city_area']
    cax, cay = _get_coord(ca)
    ca_min_x, ca_min_y, ca_max_x, ca_max_y = _get_bbox(ca)
    conn.execute(
        "INSERT OR IGNORE INTO city_areas (id, region_id, name, size, population, x, y, "
        "x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ca['id'], region['id'], ca['name'], ca.get('size', ''),
         ca.get('population', 0), cax, cay, ca_min_x, ca_min_y, ca_max_x, ca_max_y)
    )

    for zone in ca.get('zones', []):
        zx, zy = _get_coord(zone)
        zx_min, zy_min, zx_max, zy_max = _get_bbox(zone)
        conn.execute(
            "INSERT OR IGNORE INTO zones (id, city_area_id, region_id, name, type, layer_c_text, "
            "x, y, x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (zone['id'], ca['id'], region['id'], zone['name'], zone.get('type', ''),
             zone.get('layer_c_text', ''), zx, zy, zx_min, zy_min, zx_max, zy_max)
        )
        import_scenes_for_zone(conn, zone['id'], zone.get('scenes', []))

    import_npcs(conn, data.get('static_npcs', []), realm_id)


def import_delta_province(conn, data):
    """Import Ostimperium Delta Province."""
    realm_id = data.get('realm_id', 'ostimperium')

    conn.execute(
        "INSERT OR IGNORE INTO realms (id, name, government_type) VALUES (?,?,?)",
        (realm_id, 'Ostimperium', 'imperial')
    )

    region = data['region']
    rx, ry = _get_coord(region)
    rx_min, ry_min, rx_max, ry_max = _get_bbox(region)
    conn.execute(
        "INSERT OR IGNORE INTO regions (id, realm_id, name, climate, layer_b_text, x, y, "
        "x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (region['id'], realm_id, region['name'], region.get('climate', ''),
         region.get('layer_b_text', ''), rx, ry, rx_min, ry_min, rx_max, ry_max)
    )

    if data.get('city_area'):
        ca = data['city_area']
        cax, cay = _get_coord(ca)
        ca_min_x, ca_min_y, ca_max_x, ca_max_y = _get_bbox(ca)
        conn.execute(
            "INSERT OR IGNORE INTO city_areas (id, region_id, name, size, population, x, y, "
            "x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ca['id'], region['id'], ca['name'], ca.get('size', ''),
             ca.get('population', 0), cax, cay, ca_min_x, ca_min_y, ca_max_x, ca_max_y)
        )
        for zone in ca.get('zones', []):
            zx, zy = _get_coord(zone)
            zx_min, zy_min, zx_max, zy_max = _get_bbox(zone)
            conn.execute(
                "INSERT OR IGNORE INTO zones (id, city_area_id, region_id, name, type, layer_c_text, "
                "x, y, x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (zone['id'], ca['id'], region['id'], zone['name'], zone.get('type', ''),
                 zone.get('layer_c_text', ''), zx, zy, zx_min, zy_min, zx_max, zy_max)
            )
            import_scenes_for_zone(conn, zone['id'], zone.get('scenes', []))

    for settlement in data.get('secondary_settlements', []):
        sid = settlement.get('id', '')
        sx, sy = _get_coord(settlement)
        sx_min, sy_min, sx_max, sy_max = _get_bbox(settlement)
        conn.execute(
            "INSERT OR IGNORE INTO zones (id, city_area_id, region_id, name, type, layer_c_text, "
            "x, y, x_min, y_min, x_max, y_max) VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?)",
            (sid, region['id'], settlement.get('name', ''), 'settlement',
             settlement.get('layer_c_text', ''), sx, sy, sx_min, sy_min, sx_max, sy_max)
        )
        import_scenes_for_zone(conn, sid, settlement.get('scenes', []))

    import_npcs(conn, data.get('static_npcs', []), realm_id)


def import_remaining_provinces(conn, data):
    """Import remaining Ostimperium provinces (region-level data only)."""
    realm_id = data.get('realm_id', 'ostimperium')

    conn.execute(
        "INSERT OR IGNORE INTO realms (id, name, government_type) VALUES (?,?,?)",
        (realm_id, 'Ostimperium', 'imperial')
    )

    for province in data.get('provinces', []):
        px, py = _get_coord(province)
        px_min, py_min, px_max, py_max = _get_bbox(province)
        conn.execute(
            "INSERT OR IGNORE INTO regions (id, realm_id, name, climate, layer_b_text, x, y, "
            "x_min, y_min, x_max, y_max) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (province['id'], realm_id, province['name'], province.get('climate', ''),
             province.get('layer_b_text', ''), px, py, px_min, py_min, px_max, py_max)
        )

        for settlement in province.get('settlements', []):
            sid = settlement.get('id', '')
            sx, sy = _get_coord(settlement)
            sx_min, sy_min, sx_max, sy_max = _get_bbox(settlement)
            conn.execute(
                "INSERT OR IGNORE INTO zones (id, city_area_id, region_id, name, type, layer_c_text, "
                "x, y, x_min, y_min, x_max, y_max) VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?)",
                (sid, province['id'], settlement.get('name', ''), 'settlement',
                 settlement.get('layer_c_text', ''), sx, sy, sx_min, sy_min, sx_max, sy_max)
            )
            import_scenes_for_zone(conn, sid, settlement.get('scenes', []))

        import_npcs(conn, province.get('static_npcs', []), realm_id)


def import_world(db_path):
    """Import all world JSON files into the database. Idempotent."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Import salzhaven
    salzhaven_path = os.path.join(WORLD_DATA_DIR, 'salzhaven.json')
    if os.path.exists(salzhaven_path):
        with open(salzhaven_path) as f:
            salzhaven_data = json.load(f)
        import_salzhaven(conn, salzhaven_data)
        print("[Importer] Salzhaven imported.")

    # Import delta province
    delta_path = os.path.join(WORLD_DATA_DIR, 'ostimperium_deltaprovince.json')
    if os.path.exists(delta_path):
        with open(delta_path) as f:
            delta_data = json.load(f)
        import_delta_province(conn, delta_data)
        print("[Importer] Delta Province imported.")

    # Import remaining provinces
    remaining_path = os.path.join(WORLD_DATA_DIR, 'ostimperium_remaining_provinces.json')
    if os.path.exists(remaining_path):
        with open(remaining_path) as f:
            remaining_data = json.load(f)
        import_remaining_provinces(conn, remaining_data)
        print("[Importer] Remaining provinces imported.")

    conn.commit()
    conn.close()
    print("[Importer] World import complete.")
