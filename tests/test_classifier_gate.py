"""Tests fuer den Proben-Gate-Flow und den geschaerften Validator.
Der Classifier selbst braucht einen LLM-Key; hier wird die Verdrahtung
(synthetischer Roll, Validator) ohne Netz geprueft."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(env):
    import app.main as main
    importlib.reload(main)
    main._pending_responses.clear()
    return TestClient(main.app)


def test_validator_flags_mechanics_and_money(env):
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    # Erfundene Ticks/XP
    p = main.validate_narration("Du hast jetzt 1/3 Ticks in Einschuechtern.", ["advance_time"], gs)
    assert any("Mechanik" in x for x in p)
    # Geld wechselt die Hand ohne pay
    p = main.validate_narration("Du bezahlst sechs Silber und nimmst den Beutel.", ["advance_time"], gs)
    assert any("Geld" in x for x in p)
    # Reine Preisnennung eines NPC ist ok
    p = main.validate_narration("\"Das Bier kostet einen Kupferpfennig\", sagt sie.", ["advance_time", "pay"], gs)
    assert not any("Geld" in x for x in p)
    # Zeitfortschritt fehlt
    p = main.validate_narration("Du schaust dich um.", [], gs)
    assert any("Zeitfortschritt" in x for x in p)
    # Mit request_skill_roll zaehlt der Zug als Aktion (kein Zeit-Flag)
    p = main.validate_narration("Du versuchst es.", ["request_skill_roll"], gs)
    assert not any("Zeitfortschritt" in x for x in p)


def test_gate_creates_pending_and_roll_resolves(client, env, monkeypatch):
    """Simuliert einen positiven Classifier-Entscheid: der Gate legt eine
    ausstehende Probe an, /api/roll loest sie auf (mit echtem Tick)."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})

    async def fake_classify(gs, msg, model):
        return {"braucht_probe": True, "skill": "Einschüchtern",
                "tier": "Durchschnitt", "grund": "Drohung gegen NPC"}
    monkeypatch.setattr(main.classifier, "classify", fake_classify)
    # Kein echter Erzaehler-Call noetig: Gate blockt vor der Narration.
    r = client.post("/api/chat", json={"message": "Ich drohe ihm", "mode": "handeln"})
    assert r.status_code == 200
    assert '"gate"' in r.text and '"awaiting_roll"' in r.text
    # Jetzt steht eine Probe aus
    state = client.get("/api/state").json()
    assert state["awaiting_roll"]["skill"] == "Einschüchtern"


def test_classifier_off_skips_gate(client, env, monkeypatch):
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": False})
    called = {"n": 0}

    async def fake_classify(gs, msg, model):
        called["n"] += 1
        return {"braucht_probe": True, "skill": "Einschüchtern", "tier": "Leicht"}
    monkeypatch.setattr(main.classifier, "classify", fake_classify)
    # Ohne Key streamt der Erzaehler einen Fehler — aber der Classifier
    # darf gar nicht erst aufgerufen werden.
    for v in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    client.post("/api/chat", json={"message": "Ich drohe ihm", "mode": "handeln"})
    assert called["n"] == 0


def test_blocking_tool_not_last_pairs_results(client, env, monkeypatch):
    """Regression: emittiert das LLM [request_skill_roll, advance_time] in
    einem Batch, darf advance_time nicht ohne tool_result verwaisen — sonst
    weist die LLM-API die Fortsetzung nach dem Wurf ab."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": False})
    cap = {"n": 0, "resume_msgs": None}

    async def fake_stream(model, system, messages, tools_):
        cap["n"] += 1
        if cap["n"] == 1:
            yield {"type": "tool_call", "id": "r", "name": "request_skill_roll",
                   "args": {"skill": "Schleichen", "schwierigkeit": "Leicht"}}
            yield {"type": "tool_call", "id": "a", "name": "advance_time", "args": {"minuten": 5}}
            yield {"type": "stop", "reason": "tool_use"}
        else:
            cap["resume_msgs"] = messages
            yield {"type": "text", "text": "Du schleichst weiter."}
            yield {"type": "stop", "reason": "end"}
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", fake_stream)

    r = client.post("/api/chat", json={"message": "Ich schleiche", "mode": "handeln"})
    assert '"awaiting_roll"' in r.text
    hist = main.load_history("bjorn")
    assert "a" in [m["tool_call_id"] for m in hist if m["role"] == "tool"]  # Skip-Result da

    r2 = client.post("/api/roll", json={"wurf": 12})
    assert r2.status_code == 200
    results = {m["tool_call_id"] for m in cap["resume_msgs"] if m.get("role") == "tool"}
    assert {"r", "a"} <= results  # beide tool_uses gepaart -> keine API-Ablehnung


def test_classifier_validates_skill(env, monkeypatch):
    import app.classifier as clf
    importlib.reload(clf)
    gs = env["gsm"].create_pc("Bjorn")

    async def fake_complete(model, system, user, max_tokens=200, timeout=None):
        return '{"braucht_probe": true, "skill": "Zaubern", "tier": "Leicht", "grund": "x"}'
    monkeypatch.setattr(clf.llm_adapter, "complete", fake_complete)
    import asyncio
    out = asyncio.get_event_loop().run_until_complete(clf.classify(gs, "test", "or/x/y"))
    assert out["braucht_probe"] is False  # ungueltiger Skill -> keine Probe


def test_validator_flags_combat_bypass_outside_combat(env):
    """Rule-Bypass-Heuristik (ADR-0001-Hauptbug): Kampf-Ausgang in Prosa
    ohne jede Kampf-Mechanik wird geflaggt; mit request_skill_roll oder
    waehrend eines laufenden Kampfs nicht (dort gilt die eigene Rundenlogik)."""
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    p = main.validate_narration("Du triffst den Waechter hart am Arm.", ["advance_time"], gs)
    assert any("Regelverstoss" in x for x in p)
    p = main.validate_narration("Du triffst den Waechter hart am Arm.",
                                ["advance_time", "request_skill_roll"], gs)
    assert not any("Regelverstoss" in x for x in p)
    gs["combat"] = {"round": 1, "phase": "npc_turn", "enemies": [], "pending_roll": None, "log": []}
    p = main.validate_narration("Du triffst den Waechter hart am Arm.", [], gs)
    assert not any("Regelverstoss" in x for x in p)


def test_validator_no_time_flag_during_combat(env):
    """end_turn/npc_action zaehlen im Kampf als Zeit-Handlung — advance_time
    waere dort fachlich falsch (Runden sind Sekunden, keine Minuten)."""
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    gs["combat"] = {"round": 2, "phase": "pc_turn", "enemies": [], "pending_roll": None, "log": []}
    p = main.validate_narration("Der Wolf faellt.", ["npc_action", "end_turn"], gs)
    assert not any("Zeitfortschritt" in x for x in p)


def test_agent_stream_auto_advances_missing_time(client, env, monkeypatch):
    """P0-Fix: advance_time-Meldung war reine Detection, keine Korrektur.
    Vergisst das Modell den Tool-Call, holt die Engine ihn jetzt selbst
    nach, statt nur zu warnen und die Uhr stehen zu lassen."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": False})

    async def fake_stream(model, system, messages, tools_):
        yield {"type": "text", "text": "Du schaust dich um."}
        yield {"type": "stop", "reason": "end"}
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", fake_stream)

    kal_before = dict(env["gsm"].load_pc("bjorn")["kalender"])
    r = client.post("/api/chat", json={"message": "Ich schaue mich um", "mode": "handeln"})
    assert '"hinweis"' in r.text
    assert "Kein Zeitfortschritt" not in r.text
    gs_after = env["gsm"].load_pc("bjorn")
    assert gs_after["kalender"] != kal_before
    assert gs_after["turn_count"] == 1


def test_agent_stream_no_auto_advance_in_combat(client, env, monkeypatch):
    """Kein Auto-Vorschub waehrend eines laufenden Kampfs (eigene
    Rundenlogik, keine Minuten-Zeit pro npc_action/end_turn)."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": False})
    gs = env["gsm"].load_pc("bjorn")
    gs["combat"] = {"round": 1, "phase": "pc_turn",
                    "enemies": [{"slug": "wolf", "name": "Wolf", "hp": 3, "hp_max": 3}],
                    "pending_roll": None, "log": []}
    env["gsm"].save_pc(gs)
    kal_before = dict(gs["kalender"])

    async def fake_stream(model, system, messages, tools_):
        yield {"type": "text", "text": "Der Wolf knurrt dich an."}
        yield {"type": "stop", "reason": "end"}
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", fake_stream)

    r = client.post("/api/chat", json={"message": "Ich beobachte", "mode": "handeln"})
    assert '"hinweis"' not in r.text
    assert env["gsm"].load_pc("bjorn")["kalender"] == kal_before


def test_synopsis_written_and_included_in_context(env, monkeypatch):
    """Synopsen-Feature (rulebook.synopsis_every_n_turns): bei Faelligkeit
    wird eine Zusammenfassung geschrieben und taucht im naechsten
    Context-Build als eigene Schicht auf."""
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    monkeypatch.setattr(main.llm_adapter, "available_providers", lambda: ["openrouter"])
    monkeypatch.setitem(main.rules.RULEBOOK, "synopsis_every_n_turns", 2)

    async def fake_complete(model, system, user, max_tokens=400):
        return "Bjorn erkundet den Hafen und trifft einen misstrauischen Schmuggler."
    monkeypatch.setattr(main.llm_adapter, "complete", fake_complete)

    gs["turn_count"] = 2  # Vielfaches von every=2 -> faellig
    history = [{"role": "user", "content": "Ich gehe zum Hafen"},
              {"role": "assistant", "content": "Du erreichst den Hafen."}]
    import asyncio
    asyncio.get_event_loop().run_until_complete(main._maybe_write_synopsis("bjorn", history, gs))

    synopses = env["wio"].read_recent_synopses("bjorn", max_n=2)
    assert len(synopses) == 1 and "Schmuggler" in synopses[0]
    ctx = env["wctx"].build_context(gs)
    assert "Bisherige Kapitel" in ctx and "Schmuggler" in ctx


def test_synopsis_skipped_when_not_due(env, monkeypatch):
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    monkeypatch.setattr(main.llm_adapter, "available_providers", lambda: ["openrouter"])
    monkeypatch.setitem(main.rules.RULEBOOK, "synopsis_every_n_turns", 2)
    called = {"n": 0}

    async def fake_complete(model, system, user, max_tokens=400):
        called["n"] += 1
        return "x"
    monkeypatch.setattr(main.llm_adapter, "complete", fake_complete)

    gs["turn_count"] = 3  # kein Vielfaches von every=2
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        main._maybe_write_synopsis("bjorn", [{"role": "user", "content": "x"}], gs))
    assert called["n"] == 0


def test_test_classifier_endpoint(client, monkeypatch):
    """/api/models/test-classifier: Fehlkonfiguration soll beim Einstellen
    auffallen, nicht erst mitten in der Szene (P1-Review-Fund)."""
    import app.main as main

    async def fake_ok(model, system, user, max_tokens=200, timeout=None):
        return '{"braucht_probe": false, "skill": null, "tier": null, "grund": "x"}'
    monkeypatch.setattr(main.classifier.llm_adapter, "complete", fake_ok)
    r = client.post("/api/models/test-classifier", json={"model": "or/x/y"})
    assert r.status_code == 200 and r.json()["ok"] is True

    async def fake_bad(model, system, user, max_tokens=200, timeout=None):
        return "Ich denke, keine Probe noetig."  # kein JSON
    monkeypatch.setattr(main.classifier.llm_adapter, "complete", fake_bad)
    r = client.post("/api/models/test-classifier", json={"model": "or/broken/model"})
    assert r.status_code == 200 and r.json()["ok"] is False


def test_classifier_failure_streak_escalates(client, env, monkeypatch):
    """Wiederholte Gate-Ausfaelle in Folge eskalieren die Meldung, statt bei
    jedem Zug identisch (und uebersehbar) zu bleiben."""
    import app.main as main
    importlib.reload(main)
    main._classifier_state["fail_streak"] = 0
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": True, "classifier_model": "or/broken/model"})

    async def fake_stream(model, system, messages, tools_):
        yield {"type": "text", "text": "x"}
        yield {"type": "stop", "reason": "end"}
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", fake_stream)

    async def broken_classify(gs, msg, model):
        raise RuntimeError("kein JSON")
    monkeypatch.setattr(main.classifier, "classify", broken_classify)

    texts = [client.post("/api/chat", json={"message": "test", "mode": "handeln"}).text
            for _ in range(main.CLASSIFIER_ESCALATE_AFTER)]
    assert all("Testen" not in t for t in texts[:-1])
    assert "Testen" in texts[-1]
    assert main._classifier_state["fail_streak"] == main.CLASSIFIER_ESCALATE_AFTER


def test_context_budgets_from_rulebook(env):
    """BUDGETS darf nicht mehr im Python hartkodiert sein, sonst driftet es
    unbemerkt vom Rulebook weg (P2-Review-Fund: war 5x ueber dem alten,
    toten Ziel-Wert)."""
    import app.wiki_context as wctx
    import app.rules as rules
    importlib.reload(rules)
    importlib.reload(wctx)
    assert wctx.BUDGETS is rules.RULEBOOK["context_char_budgets"]
    assert "synopses" in wctx.BUDGETS


# --- ADR-0003: Retry, Undo, Korrektur-Enforcement -----------------------

def test_korrektur_ohne_zustandsaenderung_wird_geflaggt(env):
    """Playtest-Fund: drei [KORREKTUR]-Zuege aenderten nur den Text, nie den
    Spielstand — danach liefen Prosa und Zahlen dauerhaft auseinander."""
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    p = main.validate_narration("Du hast recht, entschuldige.", [],
                                gs, mode="korrektur")
    assert any("Spielstand" in x for x in p)
    p = main.validate_narration("Korrigiert.", ["set_location"], gs, mode="korrektur")
    assert p == []


def test_validator_flaggt_fehlenden_ortswechsel(env):
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    gate = {"ortswechsel": True}
    p = main.validate_narration("Du folgst ihnen zum Leuchtturm.",
                                ["advance_time"], gs, gate=gate)
    assert any("set_location" in x for x in p)
    p = main.validate_narration("Du folgst ihnen zum Leuchtturm.",
                                ["advance_time", "set_location"], gs, gate=gate)
    assert not any("set_location" in x for x in p)


def test_validator_flaggt_roll_dice_im_kampf(env):
    import app.main as main
    importlib.reload(main)
    gs = env["gsm"].create_pc("Bjorn")
    gs["combat"] = {"round": 1, "enemies": [], "pending_roll": None, "log": []}
    p = main.validate_narration("Der Hammer saust herab.", ["roll_dice"], gs)
    assert any("roll_dice" in x for x in p)


def test_retry_bei_regelverstoss_im_kampf(client, env, monkeypatch):
    """Gepufferter Kampfzug: ein regelwidriger erster Versuch wird verworfen
    und nicht angezeigt; der zweite Versuch geht durch."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": False})
    gs = env["gsm"].load_pc("bjorn")
    gs["combat"] = {"round": 1, "enemies": [], "pending_roll": None,
                    "pc_gehandelt": False, "aktive_verteidigung": None, "log": []}
    env["gsm"].save_pc(gs)
    cap = {"n": 0}

    async def fake_stream(model, system, messages, tools_):
        cap["n"] += 1
        if cap["n"] == 1:
            # Genau der Playtest-Fehler: erzaehlte HP, die nicht zum
            # Spielstand passen (dort 1/10, waehrend die Engine 0 fuehrte).
            yield {"type": "text", "text": "Du hast nur noch 3 LP."}
        else:
            yield {"type": "text", "text": "Zweiter, sauberer Versuch."}
        yield {"type": "stop", "reason": "end"}
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", fake_stream)

    r = client.post("/api/chat", json={"message": "Ich schlage zu", "mode": "handeln"})
    assert cap["n"] == 2                      # es gab genau einen Retry
    assert "nur noch 3 LP" not in r.text      # verworfener Text bleibt unsichtbar
    assert "Zweiter, sauberer Versuch" in r.text


def test_undo_stellt_zustand_wieder_her(client, env, monkeypatch):
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"use_classifier": False})

    runs = {"n": 0}

    async def fake_stream(model, system, messages, tools_):
        runs["n"] += 1
        if runs["n"] == 1:
            yield {"type": "tool_call", "id": "h", "name": "adjust_hp",
                   "args": {"delta": -5, "grund": "Falle"}}
            yield {"type": "stop", "reason": "tool_use"}
        else:
            yield {"type": "text", "text": "Die Falle schnappt zu."}
            yield {"type": "stop", "reason": "end"}
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", fake_stream)

    hp_vorher = env["gsm"].load_pc("bjorn")["hp"]
    client.post("/api/chat", json={"message": "Ich gehe weiter", "mode": "handeln"})
    assert env["gsm"].load_pc("bjorn")["hp"] == hp_vorher - 5
    assert client.get("/api/undo").json()["verfuegbar"] == 1

    r = client.post("/api/undo")
    assert r.status_code == 200
    assert env["gsm"].load_pc("bjorn")["hp"] == hp_vorher
    assert client.get("/api/undo").json()["verfuegbar"] == 0
    assert client.post("/api/undo").status_code == 409


def test_trivial_skip_spart_den_gate_call(env, monkeypatch):
    import app.classifier as clf
    importlib.reload(clf)
    called = {"n": 0}

    async def fake_complete(model, system, user, max_tokens=200, timeout=None):
        called["n"] += 1
        return '{"braucht_probe": false}'
    monkeypatch.setattr(clf.llm_adapter, "complete", fake_complete)
    import asyncio
    out = asyncio.get_event_loop().run_until_complete(
        clf.classify({}, "Ich schaue mich um", "or/x/y"))
    assert out["braucht_probe"] is False and called["n"] == 0


def test_rule_bypass_greift_jetzt_auch_im_kampf(env):
    """Die Pruefung war mit `not gs.get("combat")` genau dort abgeschaltet, wo
    sie im Playtest gebraucht worden waere. Jetzt entscheidet der Delta."""
    import app.main as main
    importlib.reload(main)
    from app import session
    gs = env["gsm"].create_pc("Bjorn")
    main.tools.execute_tool(gs, "start_combat", {"gegner": [{"name": "Schmuggler", "hp": 10}]})
    text = "Du triffst den Schmuggler hart. Er geht zu Boden."

    vorher = session.state_fingerprint(gs)
    # a) Erzaehlung ohne jede Bewegung im Spielstand -> Verstoss
    p = session.validate_narration(text, [], gs, vorher=vorher)
    assert any("Rule Bypass" in x for x in p), p

    # b) Derselbe Text, nachdem wirklich ein Treffer gelandet ist -> sauber
    gs["combat"]["enemies"][0]["hp"] = 4
    gs["combat"]["log"].append("PC-Angriff: 6 Schaden")
    p = session.validate_narration(text, [], gs, vorher=vorher)
    assert not any("Rule Bypass" in x for x in p), p


def test_gescheitertes_tool_deckt_keine_behauptung(env):
    """turn_tools wird im Server VOR der Ausfuehrung gefuellt. Ein an
    'Nicht genug Muenzen' gescheitertes pay stand also im Protokoll und
    befriedigte die Muenz-Regel — der Delta kennt diesen Unterschied."""
    import app.main as main
    importlib.reload(main)
    from app import session
    gs = env["gsm"].create_pc("Bjorn")
    text = "Du zahlst dem Wirt drei Silber."
    vorher = session.state_fingerprint(gs)

    gescheitert = main.tools.execute_tool(gs, "pay", {"betrag_kp": 99999})
    assert "FEHLER" in gescheitert
    p = session.validate_narration(text, ["pay", "advance_time"], gs, vorher=vorher)
    assert any("Boerse" in x for x in p), p

    main.tools.execute_tool(gs, "pay", {"betrag_kp": 30})
    p = session.validate_narration(text, ["pay", "advance_time"], gs, vorher=vorher)
    assert not any("Boerse" in x for x in p), p
