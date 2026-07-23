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
    t = env["tools"]
    gs = _gs(env)
    gs["attribute"]["STR"] = 16  # +3, Klingenwaffen wird sicherer

    assert "FEHLER" in t.execute_tool(gs, "end_turn", {})
    r = json.loads(t.execute_tool(gs, "start_combat",
                                  {"gegner": [{"name": "Grubenwolf", "hp": 8}]}))
    assert r["phase"] == "pc_turn"
    assert "FEHLER" in t.execute_tool(gs, "start_combat", {"gegner": [{"name": "X"}]})
    assert "FEHLER" in t.execute_tool(gs, "npc_action", {"angreifer": "grubenwolf"})

    # Angriff = Skill-Probe mit Ziel
    res = t.execute_tool(gs, "request_skill_roll",
                         {"skill": "Klingenwaffen", "schwierigkeit": "Leicht",
                          "ziel": "Grubenwolf", "schaden": "1d4"})
    assert res == t.BLOCKING
    assert gs["combat"]["phase"] == "awaiting_roll"
    assert "FEHLER" in t.execute_tool(gs, "end_turn", {})

    outcome = t.resolve_player_roll(gs, 15)  # 15+3+0 = 18 >= 10
    assert outcome["erfolg"] is True
    assert 1 <= outcome["schaden"] <= 8  # 1d4, verdoppelt bei Crit
    wolf = gs["combat"]["enemies"][0]
    assert wolf["hp"] == 8 - outcome["schaden"]
    assert gs["combat"]["phase"] == "pc_turn"

    r = json.loads(t.execute_tool(gs, "end_turn", {}))
    assert r["phase"] == "npc_turn"

    # NPC-Angriff: Engine wuerfelt gegen den VW des PC
    hp_before = gs["hp"]
    r = json.loads(t.execute_tool(gs, "npc_action",
                                  {"angreifer": "Grubenwolf", "angriffsbonus": 30,
                                   "schaden": "1d4"}))
    assert r["treffer"] is True and gs["hp"] < hp_before

    r = json.loads(t.execute_tool(gs, "end_turn", {}))
    assert r["phase"] == "pc_turn" and gs["combat"]["round"] == 2

    r = json.loads(t.execute_tool(gs, "end_combat", {"ausgang": "sieg"}))
    assert r["ausgang"] == "sieg" and gs["combat"] is None


def test_bleeding_in_combat(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Wolf", "hp": 5}]})
    gs["hp"] = 0
    t.execute_tool(gs, "end_turn", {})   # -> npc_turn
    r = json.loads(t.execute_tool(gs, "end_turn", {}))  # -> Runde 2, Blutung
    assert gs["hp"] == -1
    assert r.get("pc_sterbend") is True
    # Heilung stabilisiert
    t.execute_tool(gs, "adjust_hp", {"delta": 3, "grund": "Erste Hilfe"})
    assert gs["stabilisiert"] is True


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
