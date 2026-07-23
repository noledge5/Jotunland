"""Wiki-Lint: dead-link / orphan / bad-slug / duplicate / status-conflict /
economy-gap Checks ueber wiki/world/.

Aufruf:  python3 -m scripts.wiki_lint
Exit-Code 1 bei Errors, 0 sonst (Warnings zaehlen nicht).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import wiki_index  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Typen, die nie verwaist sein duerfen (City-Anchor-Typen): sie existieren
# nur als Teil einer Stadt und muessen von dort verlinkt sein.
NEVER_ORPHAN = {"character", "noble_house"}
# Typen, die verwaist sein DUERFEN (Wurzeln der Hierarchie / Meta).
ORPHAN_OK = {"canon", "region", "lore", "chronicle", "law"}


def run_lint() -> list[dict]:
    idx = wiki_index.get_index(force=True)
    entries = idx["entries"]
    problems: list[dict] = []

    def add(level, check, msg):
        problems.append({"level": level, "check": check, "msg": msg})

    from app.gamestate import slugify

    all_slugs = set(entries)
    linked_from: dict[str, list[str]] = {}
    for slug, e in entries.items():
        for target in e["links"]:
            linked_from.setdefault(target, []).append(slug)
        # region-Zugehoerigkeit zaehlt als impliziter Link Region -> Eintrag
        region = e.get("region")
        if region and slugify(region) in all_slugs:
            linked_from.setdefault(slug, []).append(slugify(region))

    for slug, e in entries.items():
        # bad-slug
        if not SLUG_RE.match(slug):
            add("error", "bad-slug", f"'{slug}' verletzt das Slug-Schema [a-z0-9-]")
        if any(u in slug for u in "äöüß"):
            add("error", "bad-slug", f"'{slug}' enthaelt Umlaute")

        # dead-link
        for target in e["links"]:
            if target not in all_slugs:
                add("error", "dead-link", f"'{slug}' verlinkt auf fehlenden Eintrag '{target}'")

        # orphan
        if slug not in linked_from and e["type"] not in ORPHAN_OK and slug != "canon":
            level = "error" if e["type"] in NEVER_ORPHAN else "warning"
            add(level, "orphan", f"'{slug}' ({e['type']}) wird nirgends verlinkt")

        # region-referenz
        region = e.get("region")
        if region and slugify(region) not in all_slugs:
            add("warning", "dead-link", f"'{slug}' referenziert unbekannte Region '{region}'")

    # duplicate (Pinpoint-Slug-Klasse: hartfeld-wache vs stadtwache-hartfeld)
    reported = set()
    for slug in entries:
        for other in wiki_index.find_similar_slugs(slug):
            pair = tuple(sorted((slug, other)))
            if pair in reported:
                continue
            reported.add(pair)
            if entries[slug]["type"] == entries[other]["type"]:
                add("warning", "duplicate", f"Moegliches Duplikat: '{pair[0]}' vs '{pair[1]}'")

    # status-conflict: toter Charakter steht noch als anwesend/aktiv verlinkt
    for slug, e in entries.items():
        if e["type"] == "character" and e.get("status") in ("tot", "verschollen"):
            for src in linked_from.get(slug, []):
                src_e = entries[src]
                if "anwesend" in (src_e.get("tags") or []):
                    add("error", "status-conflict",
                        f"'{slug}' ist {e['status']}, aber in '{src}' als anwesend markiert")

    # economy-gap: importierte Gueter ohne Produzenten
    produced = set(idx["produced_by"])
    for good, importers in idx["imported_by"].items():
        if good not in produced:
            add("warning", "economy-gap",
                f"Gut '{good}' wird importiert ({', '.join(importers)}), aber nirgends produziert")

    return problems


if __name__ == "__main__":
    problems = run_lint()
    errors = [p for p in problems if p["level"] == "error"]
    for p in problems:
        print(f"[{p['level'].upper():7}] {p['check']:15} {p['msg']}")
    print(f"\n{len(errors)} Errors, {len(problems) - len(errors)} Warnings")
    sys.exit(1 if errors else 0)
