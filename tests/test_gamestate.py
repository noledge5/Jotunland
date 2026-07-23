import pytest


def test_coin_total_and_consolidate(env):
    g = env["gsm"]
    assert g.total_copper({"gm": 2, "sm": 3, "kp": 7}) == 237
    assert g.consolidate_coins(237) == {"gm": 2, "sm": 3, "kp": 7}
    assert g.consolidate_coins(0) == {"gm": 0, "sm": 0, "kp": 0}


def test_pay_copper_makes_change_from_total(env):
    """Der alte Currency-Bug: 5 kp zahlen mit nur Gold in der Boerse
    darf NICHT einfach Gold abziehen — Wechselgeld ueber Gesamtwert."""
    g = env["gsm"]
    coins = {"gm": 1, "sm": 0, "kp": 0}
    result = g.pay_copper(coins, 5)
    assert g.total_copper(result) == 95
    assert result == {"gm": 0, "sm": 9, "kp": 5}


def test_pay_copper_insufficient(env):
    g = env["gsm"]
    with pytest.raises(ValueError):
        g.pay_copper({"gm": 0, "sm": 0, "kp": 3}, 10)
    with pytest.raises(ValueError):
        g.pay_copper({"gm": 1, "sm": 0, "kp": 0}, -1)


def test_add_coins_and_format(env):
    g = env["gsm"]
    coins = g.add_coins({"gm": 0, "sm": 9, "kp": 8}, kp=5)
    assert coins == {"gm": 1, "sm": 0, "kp": 3}
    assert g.format_coins(coins) == "1 gm 3 kp"
    assert g.format_coins({"gm": 0, "sm": 0, "kp": 0}) == "0 kp"
    with pytest.raises(ValueError):
        g.add_coins(coins, kp=-5)


def test_xp_thresholds_and_levelup(env):
    g = env["gsm"]
    assert g.level_for_xp(0) == 1
    assert g.level_for_xp(99) == 1
    assert g.level_for_xp(100) == 2
    assert g.level_for_xp(300) == 3
    gs = g.default_gamestate("Test", "test")
    info = g.add_xp(gs, 150)
    assert info["level_up"] is True
    assert gs["level"] == 2
    assert gs["hp"] == gs["hp_max"] == 15  # +3 HP, voll geheilt
    info = g.add_xp(gs, 10)
    assert info["level_up"] is False
    assert info["bis_naechstes_level"] == 300 - 160


def test_hp_status_tags(env):
    g = env["gsm"]
    assert g.hp_status_tag(12, 12) == "unversehrt"
    assert g.hp_status_tag(8, 12) == "angeschlagen"
    assert g.hp_status_tag(4, 12) == "verwundet"
    assert g.hp_status_tag(1, 12) == "schwer verwundet"
    assert g.hp_status_tag(0, 12) == "todgeweiht"


def test_pc_roundtrip_atomic(env):
    g = env["gsm"]
    gs = g.create_pc("Marek")
    assert gs["slug"] == "marek"
    loaded = g.load_pc("marek")
    assert loaded["name"] == "Marek"
    assert loaded["hp_status"] == "unversehrt"
    with pytest.raises(ValueError):
        g.create_pc("Marek")
    assert [p["slug"] for p in g.list_pcs()] == ["marek"]


def test_slugify_umlauts(env):
    g = env["gsm"]
    assert g.slugify("Käthe von Öl-Straße") == "kaethe-von-oel-strasse"
    assert g.slugify("  Grauwall  ") == "grauwall"


def test_settings_always_from_disk(env):
    """Settings-Race-Fix: Aenderung ist sofort in jedem load sichtbar."""
    g = env["gsm"]
    s1 = g.load_settings()
    assert s1["active_pc_slug"] is None
    g.set_active_pc_slug("marek")
    assert g.load_settings()["active_pc_slug"] == "marek"
    g.save_settings({"model": "gemini-2.5-flash"})
    s = g.load_settings()
    assert s["model"] == "gemini-2.5-flash"
    assert s["active_pc_slug"] == "marek"  # nicht ueberschrieben
