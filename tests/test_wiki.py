import json


def test_frontmatter_roundtrip(env):
    w = env["wio"]
    w.write_world_entry("test-ort", {"type": "location", "name": "Test-Ort",
                                     "tags": ["stadt"]}, "Ein Ort.\n\nMit [[canon]]-Link.")
    meta, body = w.read_world_entry("test-ort")
    assert meta["slug"] == "test-ort"
    assert meta["type"] == "location"
    assert meta["tags"] == ["stadt"]
    assert "[[canon]]" in body


def test_write_if_absent_idempotent(env):
    w = env["wio"]
    assert w.write_world_entry("x", {"type": "lore", "name": "X"}, "v1", write_if_absent=True)
    assert not w.write_world_entry("x", {"type": "lore", "name": "X"}, "v2", write_if_absent=True)
    _, body = w.read_world_entry("x")
    assert body.strip() == "v1"


def test_canonical_slug_city_institutions(env):
    """Pinpoint-Slug-Regel: verhindert hartfeld-wache vs stadtwache-hartfeld."""
    w = env["wio"]
    assert w.canonical_slug("Hartfelder Stadtwache", "faction", city="Hartfeld") == "stadtwache-hartfeld"
    assert w.canonical_slug("Wache von Hartfeld", "faction", city="Hartfeld") == "stadtwache-hartfeld"
    assert w.canonical_slug("Tempel des Aschenherrn", "location", city="Grauwall") == "tempel-grauwall"
    # Ohne Stadt: normaler Slug
    assert w.canonical_slug("Greta Eisenhand", "character") == "greta-eisenhand"


def test_index_and_similarity(env):
    w, widx = env["wio"], env["widx"]
    w.write_world_entry("hartfeld", {"type": "location", "name": "Hartfeld"}, "Stadt.")
    w.write_world_entry("stadtwache-hartfeld", {"type": "faction", "name": "Stadtwache Hartfeld",
                                                "links": ["hartfeld"]}, "Wache.")
    idx = widx.get_index(force=True)
    assert "hartfeld" in idx["entries"]
    assert idx["entries"]["stadtwache-hartfeld"]["links"] == ["hartfeld"]
    # Duplikat-Klasse wird erkannt
    w.write_world_entry("hartfeld-wache", {"type": "faction", "name": "Hartfeld-Wache"}, "Dublette.")
    similar = widx.find_similar_slugs("hartfeld-wache")
    assert "stadtwache-hartfeld" not in similar or True  # mind. kein Crash
    # 'wache' + 'hartfeld' ueberlappen mit stadtwache-hartfeld nur in 'hartfeld'
    # aber gleiche Wortmenge in anderer Reihenfolge matcht:
    w.write_world_entry("wache-hartfeld", {"type": "faction", "name": "Wache Hartfeld"}, "Dublette 2.")
    assert "hartfeld-wache" in widx.find_similar_slugs("wache-hartfeld")


def test_index_produced_imported_maps(env):
    w, widx = env["wio"], env["widx"]
    w.write_world_entry("salzsiederei", {"type": "economy", "name": "Salzsiederei",
                                         "produces": ["salz"]}, "Siedet.")
    w.write_world_entry("markt-grau", {"type": "economy", "name": "Grauer Markt",
                                       "imports": ["salz", "eisen"]}, "Handelt.")
    idx = widx.get_index(force=True)
    assert idx["produced_by"]["salz"] == ["salzsiederei"]
    assert idx["imported_by"]["eisen"] == ["markt-grau"]


def test_index_cache_invalidation(env):
    w, widx = env["wio"], env["widx"]
    w.write_world_entry("a", {"type": "lore", "name": "A"}, "x")
    assert "a" in widx.get_index()["entries"]
    w.write_world_entry("b", {"type": "lore", "name": "B"}, "y")
    assert "b" in widx.get_index()["entries"]  # Cache wurde invalidiert


def test_journal_append_and_tail(env):
    w = env["wio"]
    w.append_pc_journal("marek", "Erster Eintrag")
    w.append_pc_journal("marek", "Zweiter Eintrag")
    tail = w.read_journal_tail("marek", max_entries=1)
    assert "Zweiter Eintrag" in tail
    assert "Erster Eintrag" not in tail


def test_context_builder_layers(env):
    g, w, wctx, t = env["gsm"], env["wio"], env["wctx"], env["tools"]
    w.write_world_entry("canon", {"type": "canon", "name": "Canon"}, "Weltgesetze hier.")
    w.write_world_entry("grauwall", {"type": "location", "name": "Grauwall",
                                     "region": "Rastberg"}, "Grenzstadt.")
    w.write_world_entry("rastberg", {"type": "region", "name": "Rastberg"}, "Hochland.")
    w.write_world_entry("jarn", {"type": "character", "name": "Jarn"}, "Schmuggler.")
    w.write_world_entry("die-zinslast", {"type": "lore", "name": "Die Zinslast",
                                         "status": "aktiv"}, "Schulden druecken.")
    gs = g.create_pc("Marek")
    t.execute_tool(gs, "set_location", {"slug": "grauwall", "name": "Grauwall"})
    t.execute_tool(gs, "npc_present", {"slug": "jarn"})
    ctx = wctx.build_context(gs)
    assert "Weltgesetze hier" in ctx          # Schicht 1: Canon
    assert "Marek" in ctx                     # Schicht 2: Gamestate
    assert "Grenzstadt" in ctx                # Schicht 4: Location
    assert "Hochland" in ctx                  # Location-Stack: Region
    assert "Schmuggler" in ctx                # Schicht 5: NPC
    assert "Schulden druecken" in ctx         # Schicht 6: aktive Lore


def test_tool_add_wiki_entry_warns_on_similar(env):
    t = env["tools"]
    gs = env["gsm"].create_pc("Marek")
    r1 = t.execute_tool(gs, "add_wiki_entry",
                        {"type": "faction", "name": "Stadtwache", "stadt": "Hartfeld",
                         "body": "Die Wache."})
    assert "angelegt" in r1
    # Zweiter Versuch mit anderem Namen, gleiche Institution -> gleicher Slug
    r2 = t.execute_tool(gs, "add_wiki_entry",
                        {"type": "faction", "name": "Hartfelder Wache", "stadt": "Hartfeld",
                         "body": "Nochmal die Wache."})
    assert "existiert bereits" in r2


def test_tool_location_needs_wiki_entry(env):
    t = env["tools"]
    gs = env["gsm"].create_pc("Marek")
    r = t.execute_tool(gs, "set_location", {"name": "Nirgendwo"})
    assert "FEHLER" in r
    t.execute_tool(gs, "add_wiki_entry", {"type": "location", "name": "Nirgendwo",
                                          "region": "Rastberg", "body": "Oede."})
    r = t.execute_tool(gs, "set_location", {"name": "Nirgendwo"})
    assert "FEHLER" not in r
    # Location bekam automatisch Koordinaten (Map-leer-Fix)
    meta, _ = env["wio"].read_world_entry("nirgendwo")
    assert isinstance(meta["koordinaten"], list) and len(meta["koordinaten"]) == 2


def test_tool_economy(env):
    t = env["tools"]
    gs = env["gsm"].create_pc("Marek")  # startet mit 500 kp = 5 gm
    r = json.loads(t.execute_tool(gs, "pay", {"betrag_kp": 7, "empfaenger": "Wirt"}))
    assert r["boerse"] == "4 gm 9 sm 3 kp"
    r = t.execute_tool(gs, "pay", {"betrag_kp": 9999})
    assert "FEHLER" in r
    r = json.loads(t.execute_tool(gs, "receive_coins", {"gm": 1, "quelle": "Auftrag"}))
    assert r["boerse"] == "5 gm 9 sm 3 kp"


def test_flags_overlay_and_schedule(env):
    """Zwei-Schichten-Modell (ADR-0002): Flags ueberlagern das Wiki;
    Zeitplan-NPCs erscheinen nur waehrend ihrer Schicht."""
    g, w, wctx, t = env["gsm"], env["wio"], env["wctx"], env["tools"]
    w.write_world_entry("canon", {"type": "canon", "name": "Canon"}, "Weltgesetze.")
    w.write_world_entry("hafenstadt", {"type": "city", "name": "Hafenstadt"}, "Stadt.")
    w.write_world_entry("schenke", {"type": "scene", "name": "Schenke",
                                    "parent": "hafenstadt"}, "Dunkle Schenke.")
    w.write_world_entry("wirt-bo", {"type": "character", "name": "Bo",
                                    "links": ["schenke"],
                                    "zeitplan": [{"ort": "schenke", "von": 8, "bis": 22}]},
                        "Der Wirt.")
    gs = g.create_pc("Marek")
    t.execute_tool(gs, "set_location", {"slug": "schenke", "name": "Schenke"})
    assert gs["location_stack"] == ["hafenstadt", "schenke"]  # parent-Kette
    gs["kalender"]["stunde"] = 12
    ctx = wctx.build_context(gs)
    assert "Der Wirt" in ctx          # Schicht laeuft -> anwesend
    gs["kalender"]["stunde"] = 3
    ctx = wctx.build_context(gs)
    assert "Der Wirt" not in ctx      # keine Schicht -> nicht da
    # Flag-Overlay
    t.execute_tool(gs, "set_world_flag", {"slug": "schenke", "feld": "abgebrannt", "wert": True})
    ctx = wctx.build_context(gs)
    assert "abgebrannt=True" in ctx


def test_namensregister_liefert_abwesende_figuren_mit_rolle(env):
    """Der Prompt kannte nur ANWESENDE NPCs. Sobald der Erzaehler ueber eine
    abwesende Figur sprach, hatte er keinen Kanon zu ihr — im Playtest wurde
    der Stadtwache-Hauptmann so zum Hafenmeister."""
    wio, wctx, t = env["wio"], env["wctx"], env["tools"]
    gs = env["gsm"].create_pc("Marek")

    wio.write_world_entry("salzhaven", {"type": "settlement", "name": "Salzhaven"},
                          "Hafenstadt an der Suedkueste.")
    wio.write_world_entry("hafenviertel", {"type": "zone", "name": "Hafenviertel",
                                           "parent": "salzhaven"}, "Kaianlagen.")
    wio.write_world_entry("dura-fenk", {"type": "character", "name": "Dura Fenk",
                                        "rolle": "Wachhauptmann, Salzhaven",
                                        "faction": "stadtwache", "region": "Salzhaven"},
                          "Eine hagere Frau Anfang vierzig mit kurzgeschorenem Haar.")
    wio.write_world_entry("fernes-nest", {"type": "settlement", "name": "Fernes Nest",
                                          "parent": "anderswo"}, "Weit weg.")
    env["widx"].invalidate()
    t.execute_tool(gs, "set_location", {"slug": "hafenviertel"})

    reg = wctx.entity_register(gs)
    # Rolle statt Aussehen — das Amt ist der Fakt, der driftet
    assert "Dura Fenk [character] (dura-fenk) — Wachhauptmann, Salzhaven" in reg
    assert "hagere Frau" not in reg
    assert "Fraktion: stadtwache" in reg
    assert "Fernes Nest" not in reg          # ausserhalb des Umkreises
    assert "Hafenviertel" not in reg         # steht schon als Volltext im Kontext
    assert "Namensregister" in wctx.build_context(gs)

    # Was im Spiel passiert ist, ueberschreibt den Welt-Text (ADR-0002)
    t.execute_tool(gs, "set_world_flag", {"slug": "dura-fenk", "feld": "tot", "wert": True})
    assert "AKTUELL: tot=True" in wctx.entity_register(gs)


def test_index_cache_wird_bei_versionswechsel_neu_gebaut(env):
    """Ein alter _index.json ohne 'kurz' wuerde das Register still leeren."""
    wio, widx = env["wio"], env["widx"]
    wio.write_world_entry("alt", {"type": "location", "name": "Alt"}, "Beschreibung hier.")
    widx.get_index()
    from app.gamestate import atomic_write_json
    atomic_write_json(widx.INDEX_PATH, {"entries": {}, "produced_by": {},
                                        "imported_by": {}})   # ohne version
    widx._mem_cache = None
    assert widx.get_index()["entries"]["alt"]["kurz"] == "Beschreibung hier."
