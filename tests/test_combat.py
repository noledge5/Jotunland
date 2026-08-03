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


def test_kampf_endet_automatisch_ohne_gegner(env):
    """Der Kampf blieb nach dem letzten Toten im Spielstand stehen, weil
    end_combat freiwillig war. start_combat verweigerte darum jeden neuen
    Kampf — daher der Gegner-Wirrwarr im zweiten Playtest."""
    t = env["tools"]
    gs = _gs(env)
    gs["attribute"]["STR"] = 18
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Saebelmann", "hp": 1}]})
    t.execute_tool(gs, "request_skill_roll", {"skill": "Klingenwaffen",
                                              "schwierigkeit": "Leicht",
                                              "ziel": "Saebelmann"})
    out = t.resolve_player_roll(gs, 20)
    assert out["kampf_ende"]["kampf_beendet"] is True
    assert gs["combat"] is None
    # Ein neuer Kampf laesst sich sofort starten
    r = json.loads(t.execute_tool(gs, "start_combat",
                                  {"gegner": [{"name": "Neuer Gegner", "hp": 8}]}))
    assert r["status"] == "kampf_gestartet" and r["runde"] == 1


def test_flucht_des_letzten_gegners_beendet_den_kampf(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Rabe", "hp": 3}]})
    r = json.loads(t.execute_tool(gs, "set_enemy_status",
                                  {"gegner": "Rabe", "status": "fled"}))
    assert r["kampf_ende"]["kampf_beendet"] is True
    assert gs["combat"] is None


def test_runde_schliesst_auch_ohne_npc_action(env):
    """Deadlock aus dem Playtest: ein lebender Gegner, fuer den der Erzaehler
    kein npc_action aufrief, blockierte den Rundenwechsel dauerhaft — jede
    weitere Spieleraktion lief in 'bereits gehandelt'."""
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Saebelmann", "hp": 10}]})
    c = gs["combat"]
    for erwartete_runde in (2, 3, 4):
        c["pc_gehandelt"] = True
        t.close_combat_round(gs)
        assert c["round"] == erwartete_runde
        assert c["pc_gehandelt"] is False
        assert t.execute_tool(gs, "request_skill_roll",
                              {"skill": "Klingenwaffen", "schwierigkeit": "Leicht",
                               "ziel": "Saebelmann"}) == t.BLOCKING
        c["pending_roll"] = None
    assert "ohne Aktion von: Saebelmann" in " ".join(c["log"])


def test_close_combat_round_wartet_auf_ausstehenden_wurf(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Wolf", "hp": 10}]})
    t.execute_tool(gs, "request_skill_roll", {"skill": "Klingenwaffen",
                                              "schwierigkeit": "Leicht", "ziel": "Wolf"})
    t.close_combat_round(gs)
    assert gs["combat"]["round"] == 1
    assert gs["combat"]["pending_roll"] is not None


def test_verstaerkung_im_laufenden_kampf(env):
    t = env["tools"]
    gs = _gs(env)
    t.execute_tool(gs, "start_combat", {"gegner": [{"name": "Wolf", "hp": 10}]})
    r = json.loads(t.execute_tool(gs, "start_combat", {
        "gegner": [{"name": "Wolf", "hp": 4},        # zweiter Wolf, eigene Identitaet
                   {"name": "Zweiter Wolf", "hp": 6, "distanz": 2}]}))
    assert r["status"] == "verstaerkung_hinzugefuegt"
    assert gs["combat"]["round"] == 1               # Runde laeuft weiter
    assert [e["name"] for e in gs["combat"]["enemies"]] == [
        "Wolf", "Wolf 2", "Zweiter Wolf"]
    assert gs["combat"]["enemies"][0]["hp"] == 10    # der erste bleibt unangetastet
    assert gs["combat"]["enemies"][1]["hp"] == 4


def test_gleichnamige_gegner_haben_eigene_identitaeten(env):
    """Drei 'Wache' teilten sich den Slug 'wache': EIN Treffer schaedigte alle
    drei, npc_action erwischte immer nur die erste, und alle fielen gemeinsam
    auf 0. Der Kanon-Slug bleibt fuer den Wiki-Bezug erhalten."""
    t = env["tools"]
    gs = _gs(env)
    gs["attribute"]["STR"] = 18
    r = json.loads(t.execute_tool(gs, "start_combat", {"gegner": [
        {"name": "Wache", "hp": 30}, {"name": "Wache", "hp": 30},
        {"name": "Wache", "hp": 30}]}))
    e = gs["combat"]["enemies"]
    assert [x["slug"] for x in e] == ["wache", "wache-2", "wache-3"]
    assert [x["name"] for x in e] == ["Wache", "Wache 2", "Wache 3"]
    assert all(x["kanon_slug"] == "wache" for x in e)
    assert [g["name"] for g in r["gegner"]] == ["Wache", "Wache 2", "Wache 3"]

    # Ein Treffer trifft genau eine Wache
    t.execute_tool(gs, "request_skill_roll", {"skill": "Klingenwaffen",
                                              "schwierigkeit": "Leicht",
                                              "ziel": "Wache 2"})
    out = t.resolve_player_roll(gs, 20)
    assert out["ziel"] == "Wache 2"
    assert e[0]["hp"] == 30 and e[2]["hp"] == 30    # die anderen unberuehrt
    assert e[1]["hp"] == 30 - out["schaden"]

    # Und jede Wache handelt einzeln
    for name in ("Wache", "Wache 2", "Wache 3"):
        res = t.execute_tool(gs, "npc_action", {"angreifer": name})
        assert "FEHLER" not in res, res
        assert json.loads(res)["angreifer"] == name
    assert gs["combat"]["round"] == 2          # Runde schaltet erst danach
