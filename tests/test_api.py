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


_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
        "FcSJAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII=")


def test_image_upload_serve_and_bild(client, env):
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    r = client.post("/api/upload", json={"data_url": _PNG})
    assert r.status_code == 200
    path = r.json()["path"]
    assert path.startswith("/images/") and path.endswith(".png")
    assert client.get(path).status_code == 200
    assert client.post("/api/upload", json={"data_url": "kein bild"}).status_code == 400
    assert client.get("/images/../etc").status_code in (400, 404)
    # Bild an einen Ort haengen (Kanon entsperren fuer den Test)
    r = client.put("/api/wiki/salzhaven", json={"bild": path})
    assert r.json()["meta"]["bild"] == path
    node = next(n for n in client.get("/api/graph").json()["nodes"] if n["slug"] == "salzhaven")
    assert node["bild"] == path


def test_scene_prompt_validation(client, env):
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    assert client.post("/api/scene_prompt", json={}).status_code == 400          # kein Ort
    assert client.post("/api/scene_prompt", json={"slug": "gibtsnicht"}).status_code == 404


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


def _fake_llm(script):
    """Ersetzt llm_adapter.stream_with_tools durch ein Skript von Zuegen.
    Jeder Eintrag: (text, [(tool_name, args), ...])."""
    zuege = list(script)

    async def stream_with_tools(model, system, messages, tool_defs):
        text, calls = zuege.pop(0) if zuege else ("", [])
        yield {"type": "text", "text": text}
        for i, (name, args) in enumerate(calls):
            yield {"type": "tool_call", "id": f"tc{i}", "name": name, "args": args}
        yield {"type": "stop", "reason": "tool_use" if calls else "end"}

    return stream_with_tools


def test_verworfener_zug_wird_zurueckgerollt(client, env, monkeypatch):
    """Ein gepufferter Zug, den der Validator verwirft, darf weder seine
    Zustandsaenderungen noch seine Erzaehlung hinterlassen. Vorher lief der
    zweite Versuch auf den Wirkungen des ersten weiter — Schaden doppelt."""
    import app.main as main
    client.post("/api/pcs", json={"name": "Marek"})
    gs = env["gsm"].load_pc("marek")
    main.tools.execute_tool(gs, "start_combat",
                            {"gegner": [{"name": "Wolf", "hp": 9}]})
    env["gsm"].save_pc(gs)                       # Kampf -> Zug ist gepuffert
    hp_vorher = gs["hp"]

    # Je zwei Skript-Eintraege sind ein Zug: erst der Tool-Call (stop=tool_use),
    # dann eine Runde ohne Calls (stop=end). Zug 1 verletzt eine Regel und
    # zieht HP ab, Zug 2 ist sauber und zieht dieselben HP noch einmal ab.
    monkeypatch.setattr(main.llm_adapter, "stream_with_tools", _fake_llm([
        ("Der Wolf beisst zu. Dein Verteidigungswert sinkt.",
         [("adjust_hp", {"delta": -3, "grund": "Biss"})]),
        ("", []),
        ("Der Wolf beisst zu.", [("adjust_hp", {"delta": -3, "grund": "Biss"})]),
        ("", []),
    ]))
    r = client.post("/api/chat", json={"message": "Ich warte ab.", "mode": "handeln"})
    assert r.status_code == 200

    gs = env["gsm"].load_pc("marek")
    assert gs["hp"] == hp_vorher - 3, "Schaden wurde doppelt angewandt"

    inhalte = [str(m.get("content", "")) for m in main.load_history("marek")]
    assert not any("Verteidigungswert sinkt" in c for c in inhalte), \
        "verworfene Erzaehlung steht noch in der History"
    assert any("REGELVERSTOSS" in c for c in inhalte)
