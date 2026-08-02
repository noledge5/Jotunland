import json


def _gs(env):
    return env["gsm"].create_pc("Marek")


def test_skill_roll_outside_combat(env):
    """request_skill_roll ist der Pflichtweg fuer jede Probe (ADR-0001)."""
    t = env["tools"]
    gs = _gs(env)
    res = t.execute_tool(gs, "request_skill_roll",
                         {"skill": "Schleichen", "schwierigkeit": "Schwer",
                          "beschreibung": "an der Wache vorbei"})
    assert res == t.BLOCKING
    assert gs["pending_roll"]["sg"] == 14
    outcome = t.resolve_player_roll(gs, 15)
    assert outcome["erfolg"] is (15 + outcome["attribut_mod"] + outcome["skill_bonus"] >= 14)
    assert gs["pending_roll"] is None
    assert gs["skills"]["Schleichen"]["ticks"] == 1  # Tick trotz allem


def test_skill_roll_validation(env):
    t = env["tools"]
    gs = _gs(env)
    assert "FEHLER" in t.execute_tool(gs, "request_skill_roll",
                                      {"skill": "Zaubern", "schwierigkeit": "Leicht"})
    assert "FEHLER" in t.execute_tool(gs, "request_skill_roll",
                                      {"skill": "Athletik", "schwierigkeit": "Episch"})
    # ziel ausserhalb Kampf -> Fehler
    assert "FEHLER" in t.execute_tool(gs, "request_skill_roll",
                                      {"skill": "Klingenwaffen", "schwierigkeit": "Leicht",
                                       "ziel": "wolf"})


def test_full_combat_cycle(env):
    """Runden schaltet die Engine selbst (ADR-0003) — es gibt kein end_turn."""
    t = env["tools"]
    gs = _gs(env)
    gs["attribute"]["STR"] = 16  # +3, Klingenwaffen wird sicherer

    r = json.loads(t.execute_tool(gs, "start_combat",
                                  {"gegner": [{"name": "Grubenwolf", "hp": 8,
                                               "angriffsbonus": 30, "schaden": "1d4"}]}))
    assert r["runde"] == 1
    assert "FEHLER" in t.execute_tool(gs, "start_combat", {"gegner": [{"name": "X"}]})
    # Gegnerwerte sind ab jetzt gebunden
    wolf = gs["combat"]["enemies"][0]
    assert wolf["angriffsbonus"] == 30 and wolf["schaden"] == "1d4"

    # Angriff = Skill-Probe mit Ziel; Schaden kommt aus der Skill-Tabelle
    res = t.execute_tool(gs, "request_skill_roll",
                         {"skill": "Klingenwaffen", "schwierigkeit": "Leicht",
                          "ziel": "Grubenwolf"})
    assert res == t.BLOCKING
    assert gs["combat"]["pending_roll"]["schaden"] == "1d6"  # nicht vom LLM

    outcome = t.resolve_player_roll(gs, 15)  # 15+3+0 = 18 >= 10
    assert outcome["erfolg"] is True
    assert wolf["hp"] == 8 - outcome["schaden"]
    assert gs["combat"]["pc_gehandelt"] is True

    # Zweiter Angriff in derselben Runde wird abgewiesen
    assert "bereits gehandelt" in t.execute_tool(
        gs, "request_skill_roll", {"skill": "Klingenwaffen",
                                   "schwierigkeit": "Leicht", "ziel": "Grubenwolf"})

    # NPC-Angriff: Werte aus dem Stat-Block, danach automatisch neue Runde
    hp_before = gs["hp"]
    r = json.loads(t.execute_tool(gs, "npc_action", {"angreifer": "Grubenwolf"}))
    assert r["treffer"] is True and gs["hp"] < hp_before
    assert r["neue_runde"] == 2 and gs["combat"]["round"] == 2
    assert gs["combat"]["pc_gehandelt"] is False

    # Derselbe Gegner darf in der neuen Runde wieder
    r2 = json.loads(t.execute_tool(gs, "npc_action", {"angreifer": "Grubenwolf"}))
    assert r2["treffer"] is True
    assert "bereits gehandelt" in t.execute_tool(gs, "npc_action",
                                                 {"angreifer": "Grubenwolf"})

    r = json.loads(t.execute_tool(gs, "end_combat", {"ausgang": "sieg"}))
    assert r["ausgang"] == "sieg" and gs["combat"] is None


def test_enemy_stats_are_bound_at_start(env):
    """npc_action ignoriert Werte in den Argumenten — sie kommen aus dem
    Stat-Block. Das war die groesste Halluzinationsflaeche im Playtest."""
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [
        {"name": "Ratte", "hp": 4, "angriffsbonus": 30, "schaden": "1d4"}]})
    gs["combat"]["pc_gehandelt"] = True
    hp_before = gs["hp"]
    # Versuch, mit 2d6+10 zuzuschlagen — muss ignoriert werden
    r = json.loads(t.execute_tool(gs, "npc_action",
                                  {"angreifer": "Ratte", "schaden": "2d6+10",
                                   "angriffsbonus": 99}))
    assert r["treffer"] is True
    assert 1 <= (hp_before - gs["hp"]) <= 4  # 1d4 aus dem Stat-Block


def test_zonenmodell_reichweite(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [
        {"name": "Schuetze", "hp": 40, "distanz": 2, "schaden": "1d6"}]})
    # Nahkampf gegen einen entfernten Gegner geht nicht
    assert "nicht erreichbar" in t.execute_tool(
        gs, "request_skill_roll", {"skill": "Klingenwaffen",
                                   "schwierigkeit": "Leicht", "ziel": "Schuetze"})
    # Fernkampf schon
    assert t.execute_tool(gs, "request_skill_roll",
                          {"skill": "Bogen", "schwierigkeit": "Leicht",
                           "ziel": "Schuetze"}) == t.BLOCKING
    t.resolve_player_roll(gs, 10)
    # Gegner ist noch nicht heran und kann nicht angreifen
    assert "entfernt" in t.execute_tool(gs, "npc_action", {"angreifer": "Schuetze"})


def test_aktive_verteidigung(env):
    t = env["tools"]
    gs = _gs(env)
    gs["attribute"]["GES"] = 16
    t.execute_tool(gs, "start_combat", {"gegner": [
        {"name": "Wolf", "hp": 6, "angriffsbonus": 0, "schaden": "1d4"}]})
    assert t.execute_tool(gs, "request_defense_roll", {"art": "ausweichen"}) == t.BLOCKING
    out = t.resolve_player_roll(gs, 20)   # Nat 20 = kritischer Erfolg
    assert out["kritisch"] == "erfolg"
    assert gs["combat"]["aktive_verteidigung"]["runde"] == 1
    assert gs["skills"]["Akrobatik"]["ticks"] == 1   # Tick auch fuers Verteidigen
    # Kritischer Verteidigungs-Erfolg: nichts trifft in dieser Runde
    r = json.loads(t.execute_tool(gs, "npc_action", {"angreifer": "Wolf"}))
    assert r["treffer"] is False and r["gegen"].startswith("aktive Verteidigung")


def test_bleeding_in_combat(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [
        {"name": "Wolf", "hp": 5, "angriffsbonus": 0, "schaden": "1d4"}]})
    gs["hp"] = 0
    gs["combat"]["pc_gehandelt"] = True
    # Gegnerangriff schliesst die Runde -> Blutung beim Rundenwechsel
    r = json.loads(t.execute_tool(gs, "npc_action", {"angreifer": "Wolf"}))
    assert gs["combat"]["round"] == 2
    assert gs["hp"] < 0            # Blutung (ggf. plus Treffer)
    assert r.get("pc_sterbend") is True
    # Heilung stabilisiert
    t.execute_tool(gs, "adjust_hp", {"delta": 3, "grund": "Erste Hilfe"})
    assert gs["stabilisiert"] is True


def test_roll_dice_im_kampf_gesperrt(env):
    t = env["tools"]
    gs = _gs(env)
    assert "total" in t.execute_tool(gs, "roll_dice", {"ausdruck": "1d6"})
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Wolf", "hp": 5}]})
    res = t.execute_tool(gs, "roll_dice", {"ausdruck": "1d6"})
    assert "FEHLER" in res and "npc_action" in res


def test_enemy_status_entfernt_aus_dem_kampf(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [
        {"name": "Wolf", "hp": 5}, {"name": "Rabe", "hp": 3}]})
    r = json.loads(t.execute_tool(gs, "set_enemy_status",
                                  {"gegner": "Rabe", "status": "fled"}))
    assert r["kampffaehig"] == ["Wolf"]
    assert "FEHLER" in t.execute_tool(gs, "npc_action", {"angreifer": "Rabe"})


def test_time_and_flags_and_rest(env):
    t = env["tools"]
    gs = _gs(env)
    r = json.loads(t.execute_tool(gs, "advance_time", {"minuten": 90}))
    assert "10:30" in r["zeit"]
    assert "FEHLER" in t.execute_tool(gs, "advance_time", {"minuten": 99999})

    env["wio"].write_world_entry("taverne-x", {"type": "scene", "name": "Taverne X"}, "x")
    r = json.loads(t.execute_tool(gs, "set_world_flag",
                                  {"slug": "taverne-x", "feld": "abgebrannt", "wert": True}))
    assert gs["world_flags"]["taverne-x"]["abgebrannt"] is True
    assert "FEHLER" in t.execute_tool(gs, "set_world_flag", {"slug": "fehlt", "feld": "x"})

    gs["hp"] = 1
    json.loads(t.execute_tool(gs, "rest", {"naechte": 1}))
    assert gs["hp"] > 1


def test_roll_expr_bounds(env):
    t = env["tools"]
    assert 3 <= t.roll_expr("2d6+1")["total"] <= 13
    assert 1 <= t.roll_expr("1w6")["total"] <= 6
    import pytest
    with pytest.raises(ValueError):
        t.roll_expr("kaese")


def test_alter_kampf_aus_dem_spielstand_laeuft_weiter(env):
    """Bestandsschutz: ein Kampf, der vor ADR-0003 begonnen wurde, kennt die
    neuen Felder nicht. Ohne Migration bricht npc_action mit KeyError ab und
    der laufende Spielstand haengt fest."""
    t = env["tools"]
    gs = _gs(env)
    gs["combat"] = {
        "round": 3, "phase": "npc_turn", "pending_roll": None,
        "enemies": [{"slug": "kontakt-hammer", "name": "Kontakt Hammer",
                     "hp": 8, "hp_max": 8, "notiz": ""}],
        "log": [],
    }
    r = t.execute_tool(gs, "npc_action", {"angreifer": "Kontakt Hammer"})
    assert "FEHLER" not in r, r
    assert json.loads(r)["angreifer"] == "Kontakt Hammer"
    # Angriff des PC funktioniert ebenfalls
    assert t.execute_tool(gs, "request_skill_roll",
                          {"skill": "Klingenwaffen", "schwierigkeit": "Leicht",
                           "ziel": "Kontakt Hammer"}) == t.BLOCKING
    out = t.resolve_player_roll(gs, 15)
    assert "schaden" in out or out["erfolg"] is False
