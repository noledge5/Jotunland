"""Die DM-CLI ist der zweite Weg in dieselbe Engine (Claude Code statt API).

Wichtig ist nicht, dass die Befehle laufen, sondern dass sie GENAU dieselben
Regeln durchsetzen wie der Server — eine zweite, laxere Tuer in den Spielstand
waere schlimmer als gar keine.
"""
import json

import pytest


@pytest.fixture()
def cli(env, monkeypatch, capsys):
    import importlib
    import app.session as session
    importlib.reload(session)
    import scripts.dm_cli as dm
    importlib.reload(dm)
    gsm = env["gsm"]
    gs = gsm.create_pc("Marek")
    s = gsm.load_settings()
    s["active_pc_slug"] = gs["slug"]
    gsm.save_settings(s)

    def run(*argv):
        dm.main(list(argv))
        return capsys.readouterr().out

    return {"run": run, "dm": dm, "gsm": gsm, "slug": gs["slug"]}


def test_probe_blockiert_und_loest_auf(cli):
    out = cli["run"]("call", "request_skill_roll",
                     '{"skill":"Schleichen","schwierigkeit":"Schwer"}')
    assert "WARTET AUF WURF" in out and "Schleichen" in out
    # Zug darf nicht abgeschlossen werden, solange der Wurf offen ist
    with pytest.raises(SystemExit):
        cli["run"]("zugende", "--text", "Du schleichst vorbei.")
    with pytest.raises(SystemExit):
        cli["run"]("wurf", "21")
    res = json.loads(cli["run"]("wurf", "14"))
    assert res["skill"] == "Schleichen" and res["sg"] == 14


def test_zugende_validiert_wie_der_server(cli):
    """Derselbe Validator wie im Web — erfundene HP und Kampf ohne Probe."""
    bericht = json.loads(cli["run"](
        "zugende", "--spieler", "Ich greife an.",
        "--text", "Du toetest den Waechter. Du hast noch 99 HP."))
    probleme = " ".join(bericht["validator"])
    assert "99" in probleme                       # HP-Abgleich
    assert "Rule Bypass" in probleme              # Kampfausgang ohne Probe
    assert bericht["auto_zeit"] == 10             # Zeit nachgezogen


def test_tool_protokoll_zaehlt_den_blockierenden_wurf_mit(cli):
    """request_skill_roll ist eine Zeit-Handlung. Faellt es aus dem Protokoll,
    stellt die Automatik die Uhr ein zweites Mal vor."""
    cli["run"]("call", "advance_time", '{"minuten": 30}')
    cli["run"]("call", "request_skill_roll",
               '{"skill":"Schleichen","schwierigkeit":"Leicht"}')
    cli["run"]("wurf", "12")
    bericht = json.loads(cli["run"]("zugende", "--text", "Du kommst vorbei."))
    assert "request_skill_roll" in bericht["tools"]
    assert bericht["auto_zeit"] == 0


def test_fehlerhafter_call_landet_nicht_im_protokoll(cli):
    cli["run"]("call", "request_skill_roll", '{"skill":"Zaubern"}')
    bericht = json.loads(cli["run"]("zugende", "--text", "Nichts passiert."))
    assert bericht["tools"] == ["advance_time"]


def test_kampf_endet_auch_ueber_die_cli_von_selbst(cli):
    cli["run"]("call", "start_combat", '{"gegner":[{"name":"Ratte","hp":1}]}')
    cli["run"]("call", "request_skill_roll",
               '{"skill":"Klingenwaffen","schwierigkeit":"Leicht","ziel":"Ratte"}')
    res = json.loads(cli["run"]("wurf", "20"))
    assert res["kampf_ende"]["kampf_beendet"] is True
    assert cli["gsm"].load_pc(cli["slug"])["combat"] is None


def test_undo_nimmt_den_zug_zurueck(cli):
    cli["run"]("schnappschuss", "vor dem Schlag")
    cli["run"]("call", "adjust_hp", '{"delta": -5, "grund": "Test"}')
    assert cli["gsm"].load_pc(cli["slug"])["hp"] == 6
    cli["run"]("undo")
    assert cli["gsm"].load_pc(cli["slug"])["hp"] == 11
    with pytest.raises(SystemExit):
        cli["run"]("undo")


def test_ungueltiges_json_wird_abgewiesen(cli):
    with pytest.raises(SystemExit):
        cli["run"]("call", "adjust_hp", "{kaputt")
    with pytest.raises(SystemExit):
        cli["run"]("call", "adjust_hp", '[1,2]')
