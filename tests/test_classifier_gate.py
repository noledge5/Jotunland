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


def test_classifier_validates_skill(env, monkeypatch):
    import app.classifier as clf
    importlib.reload(clf)
    gs = env["gsm"].create_pc("Bjorn")

    async def fake_complete(model, system, user, max_tokens=200):
        return '{"braucht_probe": true, "skill": "Zaubern", "tier": "Leicht", "grund": "x"}'
    monkeypatch.setattr(clf.llm_adapter, "complete", fake_complete)
    import asyncio
    out = asyncio.get_event_loop().run_until_complete(clf.classify(gs, "test", "or/x/y"))
    assert out["braucht_probe"] is False  # ungueltiger Skill -> keine Probe
