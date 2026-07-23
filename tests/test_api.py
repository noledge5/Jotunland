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
    assert "NOVATERRUM" in r.text


def test_state_and_settings_roundtrip(client):
    r = client.get("/api/state").json()
    assert r["pc"] is None
    client.post("/api/settings", json={"model": "gemini-2.5-flash"})
    assert client.get("/api/settings").json()["model"] == "gemini-2.5-flash"


def test_pc_lifecycle(client):
    r = client.post("/api/pcs", json={"name": "Marek"})
    assert r.status_code == 200
    assert r.json()["slug"] == "marek"
    # Duplikat -> 409
    assert client.post("/api/pcs", json={"name": "Marek"}).status_code == 409
    # Auto-aktiviert
    state = client.get("/api/state").json()
    assert state["pc"]["name"] == "Marek"
    # Zweiter PC + Wechsel
    client.post("/api/pcs", json={"name": "Leian"})
    client.post("/api/pcs/marek/activate")
    assert client.get("/api/state").json()["pc"]["slug"] == "marek"
    assert client.post("/api/pcs/gibtsnicht/activate").status_code == 404


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
    assert any(e["slug"] == "hartfeld" for e in entries)
    assert all(e.get("koordinaten") for e in entries)
    r = client.get("/api/wiki/hartfeld").json()
    assert r["meta"]["type"] == "location"
    assert client.get("/api/wiki/fehlt").status_code == 404
    factions = client.get("/api/wiki", params={"type": "faction"}).json()
    assert len(factions) == 5


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
