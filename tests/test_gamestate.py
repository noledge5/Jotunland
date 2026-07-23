import pytest

from app import rules


def test_coin_total_and_consolidate(env):
    g = env["gsm"]
    assert g.total_copper({"gm": 2, "sm": 3, "kp": 7}) == 237
    assert g.consolidate_coins(237) == {"gm": 2, "sm": 3, "kp": 7}


def test_pay_copper_makes_change_from_total(env):
    """Alter Currency-Bug: Wechselgeld ueber Gesamtwert, nie Sorten direkt."""
    g = env["gsm"]
    result = g.pay_copper({"gm": 1, "sm": 0, "kp": 0}, 5)
    assert result == {"gm": 0, "sm": 9, "kp": 5}
    with pytest.raises(ValueError):
        g.pay_copper({"gm": 0, "sm": 0, "kp": 3}, 10)


def test_attr_mod_and_skill_bonus():
    assert rules.attr_mod(10) == 0
    assert rules.attr_mod(18) == 4
    assert rules.attr_mod(6) == -2
    assert rules.skill_bonus(0) == 0
    assert rules.skill_bonus(29) == 2
    assert rules.skill_bonus(100) == 10


def test_tick_thresholds():
    assert rules.tick_threshold(0) == 3     # Novize
    assert rules.tick_threshold(20) == 3
    assert rules.tick_threshold(21) == 5    # Lehrling
    assert rules.tick_threshold(45) == 8    # Geselle
    assert rules.tick_threshold(70) == 12   # Experte
    assert rules.tick_threshold(90) == 20   # Meister


def test_probe_resolution_and_ticks(env):
    g = env["gsm"]
    gs = g.create_pc("Marek")
    gs["attribute"]["GES"] = 16  # Mod +3
    gs["skills"]["Schleichen"] = {"wert": 20, "ticks": 0}
    r = rules.resolve_probe(gs, "Schleichen", "Durchschnitt", 8)
    assert r["gesamt"] == 8 + 3 + 2 and r["erfolg"] is True  # 13 >= SG 12
    assert gs["skills"]["Schleichen"]["ticks"] == 1
    # Nat 1 / Nat 20 schlagen alles
    assert rules.resolve_probe(gs, "Schleichen", "Sehr Leicht", 1)["erfolg"] is False
    assert rules.resolve_probe(gs, "Schleichen", "Extrem", 20)["kritisch"] == "erfolg"
    with pytest.raises(ValueError):
        rules.resolve_probe(gs, "Schleichen", "Unmoeglich", 10)


def test_skill_up_and_level_up(env):
    g = env["gsm"]
    gs = g.create_pc("Marek")
    sk = rules.get_skill(gs, "Athletik")
    # Novize: 3 Ticks pro +1; 10 Skill-Ups = Level 2 (+2 HP, +1 Attributpunkt)
    hp_before = gs["hp_max"]
    for _ in range(30):
        rules.award_tick(gs, "Athletik")
    assert sk["wert"] == 10
    assert gs["skill_ups"] == 10
    assert gs["level"] == 2
    assert gs["hp_max"] == hp_before + 2
    assert gs["attr_punkte_frei"] == 1


def test_verteidigungswert(env):
    g = env["gsm"]
    gs = g.create_pc("Marek")
    gs["attribute"]["GES"] = 14  # +2
    gs["inventar"] = []
    assert rules.verteidigungswert(gs) == 12
    gs["inventar"].append({"name": "Holzschild", "menge": 1, "equipped": True})
    assert rules.verteidigungswert(gs) == 14


def test_dying_and_bleed(env):
    g = env["gsm"]
    gs = g.create_pc("Marek")
    g.adjust_hp(gs, -gs["hp"])
    assert rules.is_dying(gs) and not rules.is_dead(gs)
    rules.bleed(gs)
    assert gs["hp"] == -1
    gs["stabilisiert"] = True
    rules.bleed(gs)
    assert gs["hp"] == -1  # stabilisiert blutet nicht
    gs["hp"] = -10
    assert rules.is_dead(gs)


def test_creation_validation(env):
    g = env["gsm"]
    ok_attrs = {"STR": 15, "GES": 14, "KON": 13, "INT": 12, "WEI": 12, "CHA": 12}
    gs = g.create_pc("Vela", klasse="Schurke", attribute=ok_attrs,
                     skills={"Schleichen": 30, "Täuschen": 25, "Klingenwaffen": 25})
    assert gs["klasse"] == "Schurke"
    assert gs["skills"]["Schleichen"]["wert"] == 30
    assert any(i["name"] == "Dolch" for i in gs["inventar"])  # Startitems
    assert g.total_copper(gs["coins"]) == 500
    # Pool-Verletzungen
    with pytest.raises(ValueError):
        g.create_pc("X1", attribute={**ok_attrs, "STR": 16}, skills={})
    with pytest.raises(ValueError):
        g.create_pc("X2", attribute=ok_attrs, skills={"Schleichen": 31})
    with pytest.raises(ValueError):
        g.create_pc("X3", attribute=ok_attrs, skills={"Gibtsnicht": 5})
    with pytest.raises(ValueError):
        g.create_pc("X4", klasse="Nekromant")


def test_kalender(env):
    g = env["gsm"]
    kal = g.default_kalender()
    g.advance_kalender(kal, 75)
    assert (kal["stunde"], kal["minute"]) == (10, 15)
    g.advance_kalender(kal, 24 * 60 * 19)  # 19 Tage -> Monatswechsel
    assert (kal["monat"], kal["tag"]) == (5, 1)
    assert "IC" in g.format_kalender(kal)


def test_settings_always_from_disk(env):
    g = env["gsm"]
    g.set_active_pc_slug("marek")
    assert g.load_settings()["active_pc_slug"] == "marek"


def test_hp_status_tags(env):
    g = env["gsm"]
    assert g.hp_status_tag(12, 12) == "unversehrt"
    assert g.hp_status_tag(4, 12) == "verwundet"
    assert g.hp_status_tag(0, 12) == "todgeweiht"
