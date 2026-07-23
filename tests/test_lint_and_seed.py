import importlib


def _lint(env):
    import scripts.wiki_lint as wl
    importlib.reload(wl)
    return wl.run_lint()


def test_lint_dead_link_and_orphan(env):
    w = env["wio"]
    w.write_world_entry("a-ort", {"type": "location", "name": "A",
                                  "links": ["fehlt-komplett"]}, "x")
    w.write_world_entry("jarn", {"type": "character", "name": "Jarn"}, "verwaist")
    problems = _lint(env)
    checks = {(p["check"], p["level"]) for p in problems}
    assert ("dead-link", "error") in checks
    assert ("orphan", "error") in checks  # character ist NEVER_ORPHAN


def test_lint_parent_counts_as_link(env):
    w = env["wio"]
    w.write_world_entry("stadt-a", {"type": "city", "name": "Stadt A"}, "x")
    w.write_world_entry("gasse-b", {"type": "scene", "name": "Gasse B",
                                    "parent": "stadt-a"}, "y")
    problems = _lint(env)
    assert not any(p["check"] == "orphan" and "gasse-b" in p["msg"] for p in problems)


def test_lint_duplicate_class(env):
    w = env["wio"]
    w.write_world_entry("hartfeld-wache", {"type": "faction", "name": "W1"}, "x")
    w.write_world_entry("wache-hartfeld", {"type": "faction", "name": "W2"}, "y")
    problems = _lint(env)
    dupes = [p for p in problems if p["check"] == "duplicate"]
    assert dupes and "hartfeld-wache" in dupes[0]["msg"]


def test_lint_status_conflict(env):
    w = env["wio"]
    w.write_world_entry("toter-mann", {"type": "character", "name": "Toter",
                                       "status": "tot"}, "x")
    w.write_world_entry("schenke", {"type": "location", "name": "Schenke",
                                    "tags": ["anwesend"], "links": ["toter-mann"]}, "y")
    problems = _lint(env)
    assert any(p["check"] == "status-conflict" for p in problems)


def test_lint_economy_gap(env):
    w = env["wio"]
    w.write_world_entry("markt", {"type": "economy", "name": "Markt",
                                  "imports": ["seide"]}, "x")
    problems = _lint(env)
    gaps = [p for p in problems if p["check"] == "economy-gap"]
    assert gaps and "seide" in gaps[0]["msg"]


def test_seed_avarr_idempotent_and_lint_clean(env):
    import scripts.seed_world as sw
    importlib.reload(sw)
    r1 = sw.seed()
    assert r1["written"] >= 80  # Realms, 9 Provinzen, Salzhaven voll, NPCs
    r2 = sw.seed()
    assert r2["written"] == 0
    assert r2["skipped"] == r1["written"]
    # Kernbestand
    assert env["widx"].get_entry_meta("salzhaven")["type"] == "city"
    assert env["widx"].get_entry_meta("ostimperium")["type"] == "realm"
    npc = env["widx"].get_entry_meta("marta-velde")
    assert npc["type"] == "character"
    # Zeitplan importiert (Frontmatter)
    meta, _ = env["wio"].read_world_entry("marta-velde")
    assert meta["zeitplan"][0]["ort"] == "salzhaven-goldenes-schiff"
    # Avarr-Seed ist lint-sauber
    problems = _lint(env)
    errors = [p for p in problems if p["level"] == "error"]
    assert errors == [], errors


def test_new_pc_starts_in_authored_salzhaven(env):
    """Live-Playtest-Fund: PC muss in der ausgearbeiteten Startszene
    beginnen, nicht dass der DM einen Ort erfindet."""
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    gs = env["gsm"].create_pc("Bjorn")
    assert gs["location"]["slug"] == "salzhaven-goldenes-schiff"
    assert "salzhaven" in gs["location_stack"]
    assert "ostimperium" in gs["location_stack"]


def test_generated_npc_anchored_to_location(env):
    """Live-Playtest-Fund: im Spiel erschaffene NPCs haengen nicht als
    Orphan, sondern werden an den aktuellen Ort verlinkt."""
    import scripts.seed_world as sw
    importlib.reload(sw)
    sw.seed()
    t, gsm = env["tools"], env["gsm"]
    gs = gsm.create_pc("Bjorn")  # startet in salzhaven-goldenes-schiff
    t.execute_tool(gs, "add_wiki_entry", {"type": "character", "name": "Zwielichtiger Gast",
                                          "scope": "charakter", "body": "Beobachtet die Tuer."})
    meta = env["widx"].get_entry_meta("zwielichtiger-gast")
    assert "salzhaven-goldenes-schiff" in meta["links"]


def test_generate_wiki_dry_run(env):
    import scripts.seed_world as sw
    import scripts.generate_wiki as gw
    importlib.reload(sw)
    importlib.reload(gw)
    sw.seed()
    gw.generate_city("salzhaven", dry_run=True)
    gw.generate_city("salzhaven", dry_run=True)  # Resume ueberspringt
    meta = env["widx"].get_entry_meta("stadtwache-salzhaven")
    assert meta is not None and meta["type"] == "faction"
