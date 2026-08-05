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
ORPHAN_OK = {"canon", "realm", "region", "lore", "chronicle", "law"}


def run_lint() -> list[dict]:
    idx = wiki_index.get_index(force=True)
    entries = idx["entries"]
    problems: list[dict] = []

    def add(level, check, msg):
        problems.append({"level": level, "check": check, "msg": msg})

    from app.gamestate import slugify

    all_slugs = set(entries)
    # Regionen sind ueber Slug ODER Namen referenzierbar (id vs name)
    name_to_slug = {slugify(e["name"]): slug for slug, e in entries.items()}

    def resolve(ref: str | None) -> str | None:
        if not ref:
            return None
        r = slugify(ref)
        return r if r in all_slugs else name_to_slug.get(r)

    linked_from: dict[str, list[str]] = {}
    for slug, e in entries.items():
        for target in e["links"]:
            linked_from.setdefault(target, []).append(slug)
        # region-/parent-Zugehoerigkeit zaehlt als impliziter Link
        for ref in (e.get("region"), e.get("parent")):
            resolved = resolve(ref)
            if resolved:
                linked_from.setdefault(slug, []).append(resolved)

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

        # orphan — charakter-gebundene Eintraege sind situativ, nie hart
        if slug not in linked_from and e["type"] not in ORPHAN_OK and slug != "canon":
            hard = e["type"] in NEVER_ORPHAN and e.get("scope", "welt") == "welt"
            level = "error" if hard else "warning"
            add(level, "orphan", f"'{slug}' ({e['type']}) wird nirgends verlinkt")

        # region-/parent-referenz
        region = e.get("region")
        if region and resolve(region) is None:
            add("warning", "dead-link", f"'{slug}' referenziert unbekannte Region '{region}'")
        parent = e.get("parent")
        if parent and resolve(parent) is None:
            add("warning", "dead-link", f"'{slug}' referenziert unbekannten Parent '{parent}'")

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

    problems += _oekologie_checks(entries)
    return problems


def _oekologie_checks(entries: dict) -> list[dict]:
    """Prueft das Bestiarium auf biologische Stimmigkeit statt auf Formalien.

    Eine erfundene Welt hat keine Quellen, aber sehr wohl Ableitungsautoritaet:
    eine Art folgt aus ihrer Gattung, ein Raubtier setzt Beute in seinem Biom
    voraus, ein Biom ohne Primaerproduzenten traegt keine Pflanzenfresser.
    Genau das laesst sich pruefen — und nur was hier geprueft wird, bleibt bei
    500 Eintraegen stimmig.
    """
    p: list[dict] = []

    def add(level, check, msg):
        p.append({"level": level, "check": check, "msg": msg})

    arten = {s: e for s, e in entries.items() if e["type"] in ("fauna", "flora")}
    if not arten:
        return p

    # --- Taxonomie: 'gattung' muss existieren, vom selben Reich sein, ein
    #     hoeherer Rang, und darf keinen Zyklus bilden.
    RANG_ORDNUNG = {"art": 0, "gattung": 1, "familie": 2}
    for slug, e in arten.items():
        g = e.get("gattung")
        if not g:
            continue
        ziel = arten.get(g)
        if ziel is None:
            add("error", "taxonomie",
                f"'{slug}' leitet sich von '{g}' ab, das es nicht als Art/Gattung gibt")
            continue
        if ziel["type"] != e["type"]:
            add("error", "taxonomie",
                f"'{slug}' ({e['type']}) haengt an '{g}' ({ziel['type']}) — "
                f"Flora und Fauna teilen keine Abstammung")
        r_kind, r_eltern = (RANG_ORDNUNG.get(x.get("rang") or "art", 0)
                            for x in (e, ziel))
        if r_eltern <= r_kind:
            add("error", "taxonomie",
                f"'{slug}' (Rang {e.get('rang') or 'art'}) haengt an '{g}' "
                f"(Rang {ziel.get('rang') or 'art'}) — die Gattung muss hoeher stehen")
    for slug in arten:
        gesehen, cur = {slug}, arten[slug].get("gattung")
        while cur and cur in arten:
            if cur in gesehen:
                add("error", "taxonomie", f"Abstammungs-Zyklus bei '{slug}'")
                break
            gesehen.add(cur)
            cur = arten[cur].get("gattung")

    # --- Nahrungsnetz: Beute muss existieren und ein Biom mit dem Jaeger teilen.
    for slug, e in arten.items():
        biome = set(e.get("biom") or [])
        for beute in e.get("frisst") or []:
            ziel = arten.get(beute)
            if ziel is None:
                add("error", "nahrungsnetz",
                    f"'{slug}' frisst '{beute}', das im Bestiarium fehlt")
                continue
            if (ziel.get("rang") or "art") != "art":
                add("warning", "nahrungsnetz",
                    f"'{slug}' frisst '{beute}', eine {ziel.get('rang')} statt einer Art — "
                    f"Nahrungsnetze verbinden Arten, nicht Taxa")
            gemeinsam = biome & set(ziel.get("biom") or [])
            if biome and ziel.get("biom") and not gemeinsam:
                add("error", "nahrungsnetz",
                    f"'{slug}' ({', '.join(sorted(biome))}) frisst '{beute}' "
                    f"({', '.join(sorted(ziel.get('biom')))}) — kein gemeinsames Biom")

    # --- Trophie pro Biom: jedes Biom braucht Produzenten, und jeder
    #     Konsument braucht eine Nahrungsquelle.
    biome: dict[str, dict] = {}
    for slug, e in arten.items():
        for b in e.get("biom") or []:
            eintrag = biome.setdefault(b, {"produzenten": [], "konsumenten": [], "alle": []})
            eintrag["alle"].append(slug)
            if e["type"] == "flora":
                eintrag["produzenten"].append(slug)
            elif (e.get("rang") or "art") == "art":
                eintrag["konsumenten"].append(slug)
    for b, x in sorted(biome.items()):
        if not x["produzenten"]:
            add("error", "trophie",
                f"Biom '{b}' hat keine Primaerproduzenten, traegt aber "
                f"{len(x['konsumenten'])} Tierarten")
        elif len(x["konsumenten"]) > len(x["produzenten"]) * 3:
            add("warning", "trophie",
                f"Biom '{b}': {len(x['konsumenten'])} Tierarten auf "
                f"{len(x['produzenten'])} Pflanzenarten — die Pyramide steht auf dem Kopf")

    for slug, e in arten.items():
        if e["type"] != "fauna" or (e.get("rang") or "art") != "art":
            continue
        if not (e.get("frisst") or []):
            add("warning", "trophie",
                f"'{slug}' hat keine Nahrungsquelle — 'frisst' fehlt")

    return p


if __name__ == "__main__":
    problems = run_lint()
    errors = [p for p in problems if p["level"] == "error"]
    for p in problems:
        print(f"[{p['level'].upper():7}] {p['check']:15} {p['msg']}")
    print(f"\n{len(errors)} Errors, {len(problems) - len(errors)} Warnings")
    sys.exit(1 if errors else 0)
