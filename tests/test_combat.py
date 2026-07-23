import json


def _gs(env):
    return env["gsm"].create_pc("Marek")


def test_full_combat_cycle(env):
    t = env["tools"]
    gs = _gs(env)

    # Kampf-Tools ohne aktiven Kampf -> Fehler
    assert "FEHLER" in t.execute_tool(gs, "end_turn", {})
    assert "FEHLER" in t.execute_tool(gs, "npc_action", {"angreifer": "wolf"})

    r = json.loads(t.execute_tool(gs, "start_combat",
                                  {"gegner": [{"name": "Grubenwolf", "hp": 8}]}))
    assert r["phase"] == "pc_turn"
    assert gs["combat"]["round"] == 1

    # Doppelter Kampfstart -> Fehler
    assert "FEHLER" in t.execute_tool(gs, "start_combat", {"gegner": [{"name": "X"}]})

    # npc_action in pc_turn -> Fehler
    assert "FEHLER" in t.execute_tool(gs, "npc_action", {"angreifer": "grubenwolf"})

    # Angriffswurf anfordern -> BLOCKING
    res = t.execute_tool(gs, "request_attack_roll",
                         {"ziel": "Grubenwolf", "modifikator": 2,
                          "schwierigkeit": 10, "schaden": "1d4"})
    assert res == t.BLOCKING
    assert gs["combat"]["phase"] == "awaiting_roll"

    # end_turn waehrend awaiting_roll -> Fehler
    assert "FEHLER" in t.execute_tool(gs, "end_turn", {})

    # Spieler wuerfelt 12 -> 14 vs 10 -> Treffer
    outcome = t.resolve_player_roll(gs, 12)
    assert outcome["treffer"] is True
    assert 1 <= outcome["schaden"] <= 4
    assert gs["combat"]["phase"] == "pc_turn"
    wolf = gs["combat"]["enemies"][0]
    assert wolf["hp"] == 8 - outcome["schaden"]

    # Zugwechsel -> npc_turn
    r = json.loads(t.execute_tool(gs, "end_turn", {}))
    assert r["phase"] == "npc_turn"

    # NPC greift an (deterministisch treffen: Schwierigkeit 0)
    hp_before = gs["hp"]
    r = json.loads(t.execute_tool(gs, "npc_action",
                                  {"angreifer": "Grubenwolf", "angriffswurf": "1d20",
                                   "schwierigkeit": 0, "schaden": "1d4"}))
    assert r["treffer"] is True
    assert gs["hp"] < hp_before

    # Zugwechsel -> neue Runde
    r = json.loads(t.execute_tool(gs, "end_turn", {}))
    assert r["phase"] == "pc_turn"
    assert gs["combat"]["round"] == 2

    # Kampf beenden mit XP
    r = json.loads(t.execute_tool(gs, "end_combat", {"ausgang": "sieg", "xp": 50}))
    assert r["ausgang"] == "sieg"
    assert gs["combat"] is None
    assert gs["xp"] == 50


def test_attack_roll_miss(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Wegelagerer", "hp": 6}]})
    t.execute_tool(gs, "request_attack_roll",
                   {"ziel": "wegelagerer", "modifikator": 0, "schwierigkeit": 15})
    outcome = t.resolve_player_roll(gs, 5)
    assert outcome["treffer"] is False
    assert gs["combat"]["enemies"][0]["hp"] == 6


def test_attack_invalid_target(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Wolf"}]})
    res = t.execute_tool(gs, "request_attack_roll",
                         {"ziel": "drache", "schwierigkeit": 10})
    assert "FEHLER" in res
    assert gs["combat"]["phase"] == "pc_turn"  # State unveraendert


def test_roll_expr_bounds(env):
    t = env["tools"]
    r = t.roll_expr("2d6+1")
    assert 3 <= r["total"] <= 13
    r = t.roll_expr("d20")
    assert 1 <= r["total"] <= 20
    r = t.roll_expr("1w6")  # deutsche Notation
    assert 1 <= r["total"] <= 6
    import pytest
    with pytest.raises(ValueError):
        t.roll_expr("100d100")
    with pytest.raises(ValueError):
        t.roll_expr("kaese")
