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


def test_import_bergrand_bestiary_idempotent_and_lint_clean(env):
    """Handautorierter Import (Bergrand + Welt-Bestiarium Batch 1) auf dem
    Seed: idempotent (zweiter Lauf schreibt nichts) und lint-sauber."""
    import scripts.seed_world as sw
    import scripts.import_bergrand_bestiary as imp
    importlib.reload(sw)
    importlib.reload(imp)
    sw.seed()
    r1 = imp.run()
    assert r1["written"] == 48
    r2 = imp.run()
    assert r2["written"] == 0
    problems = _lint(env)
    errors = [p for p in problems if p["level"] == "error"]
    assert errors == [], errors
    idx = env["widx"].get_index(force=True)["entries"]
    assert idx["haus-kelbrandt"]["type"] == "noble_house"
    assert idx["urwyrm"]["type"] == "fauna"
    fauna_flora = sum(1 for e in idx.values() if e["type"] in ("fauna", "flora"))
    assert fauna_flora == 36


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


def _art(wio, slug, typ="fauna", **meta):
    wio.write_world_entry(slug, {"type": typ, "name": slug.title(), **meta},
                          f"Beschreibung von {slug}.")


def _checks(env, name):
    from scripts.wiki_lint import run_lint
    env["widx"].invalidate()
    return [p for p in run_lint() if p["check"] == name]


def test_taxonomie_prueft_abstammung(env):
    """Eine erfundene Welt hat keine Quellen, aber Ableitungsautoritaet: eine
    Art folgt aus ihrer Gattung. Genau das ist pruefbar."""
    wio = env["wio"]
    _art(wio, "woelfe", rang="gattung", biom=["biom-nordwald"])
    _art(wio, "kammwolf", rang="art", gattung="woelfe", biom=["biom-nordwald"])
    assert _checks(env, "taxonomie") == []

    _art(wio, "geistwolf", rang="art", gattung="fehlt-im-wiki", biom=["biom-nordwald"])
    _art(wio, "moosart", typ="flora", rang="art", gattung="woelfe", biom=["biom-nordwald"])
    _art(wio, "falschrang", rang="gattung", gattung="woelfe", biom=["biom-nordwald"])
    msgs = " ".join(p["msg"] for p in _checks(env, "taxonomie"))
    assert "fehlt-im-wiki" in msgs                     # Gattung existiert nicht
    assert "teilen keine Abstammung" in msgs           # Flora haengt an Fauna
    assert "muss hoeher stehen" in msgs                # Gattung unter Gattung


def test_nahrungsnetz_braucht_gemeinsames_biom(env):
    wio = env["wio"]
    _art(wio, "seegras", typ="flora", biom=["biom-binnenmeer"])
    _art(wio, "bergkraut", typ="flora", biom=["biom-hochgebirge"])
    _art(wio, "silberfisch", biom=["biom-binnenmeer"], frisst=["seegras"])
    assert _checks(env, "nahrungsnetz") == []

    _art(wio, "gratvogel", biom=["biom-hochgebirge"], frisst=["silberfisch", "phantom"])
    msgs = " ".join(p["msg"] for p in _checks(env, "nahrungsnetz"))
    assert "kein gemeinsames Biom" in msgs
    assert "phantom" in msgs


def test_trophie_pyramide_steht_richtig_herum(env):
    """Ein Biom ohne Primaerproduzenten traegt keine Pflanzenfresser."""
    wio = env["wio"]
    _art(wio, "raubtier-a", biom=["biom-steppe"], frisst=[])
    fehler = [p for p in _checks(env, "trophie") if p["level"] == "error"]
    assert any("keine Primaerproduzenten" in p["msg"] for p in fehler)

    _art(wio, "steppengras", typ="flora", biom=["biom-steppe"])
    _art(wio, "grasfresser", biom=["biom-steppe"], frisst=["steppengras"])
    assert [p for p in _checks(env, "trophie") if p["level"] == "error"] == []
    # Raubtier ohne 'frisst' bleibt eine Warnung
    assert any("keine Nahrungsquelle" in p["msg"] for p in _checks(env, "trophie"))
