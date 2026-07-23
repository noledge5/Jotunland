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


def test_lint_bad_slug(env):
    w = env["wio"]
    # bewusst kaputten Slug direkt schreiben
    p = w.WORLD_DIR / "Böser_Slug.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nslug: Böser_Slug\ntype: lore\nname: X\n---\n\nx\n", encoding="utf-8")
    problems = _lint(env)
    assert any(p["check"] == "bad-slug" for p in problems)


def test_lint_duplicate_class(env):
    """Die Duplikat-Klasse aus dem Handoff: hartfeld-wache vs wache-hartfeld."""
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


def test_seed_idempotent_and_lint_clean(env):
    import scripts.seed_world as sw
    importlib.reload(sw)
    r1 = sw.seed()
    assert r1["written"] > 50
    r2 = sw.seed()
    assert r2["written"] == 0
    assert r2["skipped"] == r1["written"]
    # Seed-Welt darf keine Lint-Errors haben
    problems = _lint(env)
    errors = [p for p in problems if p["level"] == "error"]
    assert errors == [], errors


def test_generate_wiki_dry_run(env):
    import scripts.seed_world as sw
    import scripts.generate_wiki as gw
    importlib.reload(sw)
    importlib.reload(gw)
    sw.seed()
    gw.generate_city("hartfeld", dry_run=True)
    # Resume: zweiter Lauf ueberspringt alles
    gw.generate_city("hartfeld", dry_run=True)
    meta = env["widx"].get_entry_meta("stadtwache-hartfeld")
    assert meta is not None  # kanonischer Slug trotz Name 'Stadtwache'
    assert meta["type"] == "faction"
