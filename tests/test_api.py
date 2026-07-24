import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(env):
    import app.main as main
    importlib.reload(main)
    main._pending_responses.clear()
    return TestClient(main.app)


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "JOTUNLAND" in r.text


def test_state_and_settings_roundtrip(client):
    r = client.get("/api/state").json()
    assert r["pc"] is None
    client.post("/api/settings", json={"model": "gemini-2.5-flash"})
    assert client.get("/api/settings").json()["model"] == "gemini-2.5-flash"


def test_pc_lifecycle(client):
    r = client.post("/api/pcs", json={"name": "Marek"})
    assert r.status_code == 200
    assert r.json()["slug"] == "marek"
    assert r.json()["attribute"]["STR"] == 13  # Default-Verteilung
    # Duplikat -> 409
    assert client.post("/api/pcs", json={"name": "Marek"}).status_code == 409
    # Wizard mit Punktepools
    r = client.post("/api/pcs", json={
        "name": "Vela", "klasse": "Schurke",
        "attribute": {"STR": 15, "GES": 14, "KON": 13, "INT": 12, "WEI": 12, "CHA": 12},
        "skills": {"Schleichen": 30}})
    assert r.status_code == 200
    # Pool-Fehler -> 400
    r = client.post("/api/pcs", json={
        "name": "Kaputt",
        "attribute": {"STR": 18, "GES": 18, "KON": 18, "INT": 18, "WEI": 18, "CHA": 18},
        "skills": {}})
    assert r.status_code == 400
    client.post("/api/pcs/marek/activate")
    assert client.get("/api/state").json()["pc"]["slug"] == "marek"
    assert client.post("/api/pcs/gibtsnicht/activate").status_code == 404


def test_rules_endpoint(client):
    r = client.get("/api/rules").json()
    assert r["attr_pool"] == 78 and r["skill_pool"] == 80
    assert len(r["skills"]) == 32 and "Krieger" in r["classes"]


def test_history_restore_endpoint(client, env):
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    hist = [
        {"role": "user", "content": "Ich schaue mich um."},
        {"role": "assistant", "content": "Die Halle ist leer.", "tool_calls": []},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "name": "advance_time", "args": {}}]},
        {"role": "tool", "tool_call_id": "x", "name": "advance_time", "content": "{}"},
    ]
    main.save_history("bjorn", hist)
    msgs = client.get("/api/history").json()["messages"]
    # Nur User + Erzaehler mit Text, keine Tool-/Leer-Turns
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Die Halle ist leer."


def test_classifier_error_surfaces(client, env, monkeypatch):
    """Ungueltige Classifier-Modell-ID -> sichtbarer Hinweis, kein stiller
    Ausfall; Erzaehler uebernimmt (streamt hier mangels Key einen Fehler)."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Bjorn"})
    client.post("/api/settings", json={"classifier_model": "haiku"})
    for v in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    r = client.post("/api/chat", json={"message": "Ich drohe ihm", "mode": "handeln"})
    assert '"hinweis"' in r.text and "haiku" in r.text


def test_chat_requires_pc(client):
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 400


def test_chat_without_key_streams_error(client, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    client.post("/api/pcs", json={"name": "Marek"})
    r = client.post("/api/chat", json={"message": "hallo"})
    assert r.status_code == 200
    assert '"error"' in r.text and "API-Key" in r.text


def test_roll_without_pending(client):
    client.post("/api/pcs", json={"name": "Marek"})
    assert client.post("/api/roll", json={"wurf": 12}).status_code == 409


def test_map_and_wiki_endpoints(client, env):
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    entries = client.get("/api/map").json()
    assert any(e["slug"] == "salzhaven" for e in entries)
    assert all(e.get("koordinaten") for e in entries)
    r = client.get("/api/wiki/salzhaven").json()
    assert r["meta"]["type"] == "city"
    assert client.get("/api/wiki/fehlt").status_code == 404
    npcs = client.get("/api/wiki", params={"type": "character"}).json()
    assert len(npcs) >= 8  # Salzhaven-NPCs + Provinz-NPCs


def test_wiki_edit_and_graph(client, env):
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()

    # Editieren: Status + Body + Koordinaten
    r = client.put("/api/wiki/marta-velde",
                   json={"status": "verschollen", "body": "Neuer Text."})
    assert r.status_code == 200
    assert r.json()["meta"]["status"] == "verschollen"
    r = client.put("/api/wiki/salzhaven", json={"koordinaten": [2381000, 1201000], "gesperrt": False})
    assert r.json()["meta"]["koordinaten"] == [2381000, 1201000]
    assert client.put("/api/wiki/salzhaven",
                      json={"links": ["gibtsnicht"]}).status_code == 400
    assert client.put("/api/wiki/fehlt", json={"body": "x"}).status_code == 404

    # Klick-to-Add: neuer Eintrag mit Koordinaten (z.B. Fauna)
    r = client.post("/api/wiki", json={"type": "fauna", "name": "Binnenmeer-Schlange",
                                       "body": "Serpentiner Jaeger der tiefen Routen.",
                                       "koordinaten": [2200000, 1100000]})
    assert r.status_code == 200
    assert client.get("/api/wiki/binnenmeer-schlange").json()["meta"]["koordinaten"] == [2200000, 1100000]
    # Duplikat -> 400
    assert client.post("/api/wiki", json={"type": "city", "name": "Salzhaven",
                                          "body": "x"}).status_code == 400

    # Graph: Knoten + implizite parent-Kanten
    g = client.get("/api/graph").json()
    slugs = {n["slug"] for n in g["nodes"]}
    assert "salzhaven" in slugs and "salzhaven-goldenes-schiff" in slugs
    assert ["salzhaven", "suedkueste"] in [sorted(e) for e in g["edges"]]


def test_canon_locked_against_move(client, env):
    """Kanon-Orte sind gesperrt: Koordinaten nur nach Entsperren aenderbar."""
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    node = next(n for n in client.get("/api/graph").json()["nodes"] if n["slug"] == "salzhaven")
    assert node["gesperrt"] is True
    # Verschieben abgelehnt
    r = client.put("/api/wiki/salzhaven", json={"koordinaten": [2400000, 1300000]})
    assert r.status_code == 409
    # Entsperren + verschieben in einem Request klappt
    r = client.put("/api/wiki/salzhaven", json={"koordinaten": [2400000, 1300000], "gesperrt": False})
    assert r.status_code == 200
    assert r.json()["meta"]["koordinaten"] == [2400000, 1300000]


def test_scope_promote_and_demote(client, env):
    """Scope-Workflow: charaktergebunden -> Kanon und zurueck."""
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    client.post("/api/pcs", json={"name": "Bjorn"})  # aktiver PC
    # Charaktergebundenen Eintrag anlegen (wie im Spiel generiert)
    client.post("/api/wiki", json={"type": "character", "name": "Dunkler Fremder",
                                   "body": "Beobachtet.", "scope": "charakter"})
    assert client.get("/api/wiki/dunkler-fremder").json()["meta"]["scope"] == "charakter"
    # In den Kanon uebernehmen
    r = client.post("/api/wiki/dunkler-fremder/scope", json={"scope": "welt"})
    assert r.status_code == 200
    assert client.get("/api/wiki/dunkler-fremder").json()["meta"]["scope"] == "welt"
    # Wieder an Charakter binden
    r = client.post("/api/wiki/dunkler-fremder/scope", json={"scope": "charakter"})
    assert r.status_code == 200
    assert client.get("/api/wiki/dunkler-fremder").json()["meta"]["pc"] == "bjorn"
    # Gesperrten Kanon kann man nicht an einen Charakter binden
    assert client.post("/api/wiki/salzhaven/scope", json={"scope": "charakter"}).status_code == 409


def test_history_bounded_persistence(env):
    import app.main as main
    importlib.reload(main)
    hist = [{"role": "user", "content": f"msg {i}"} for i in range(main.HISTORY_ACTIVE_LIMIT + 10)]
    main.save_history("marek", hist)
    active = main.load_history("marek")
    assert len(active) == main.HISTORY_ACTIVE_LIMIT + 10 - main.HISTORY_ARCHIVE_CHUNK
    archive = main.archive_path("marek")
    assert archive.exists()
    assert len(archive.read_text().strip().splitlines()) == main.HISTORY_ARCHIVE_CHUNK
    # Fenster schneidet keine tool-Results am Anfang ab
    hist2 = [{"role": "tool", "content": "x"}, {"role": "user", "content": "y"}]
    assert main.llm_window(hist2, 2)[0]["role"] == "user"
