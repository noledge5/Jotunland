"""Seed: importiert die Avarr-Weltdaten (world/data/*.json + Realm-Tabelle
aus world/CONTEXT.md) ins Markdown-Wiki. Idempotent (write_if_absent);
Backlinks (Stadt -> Personen) werden immer nachgezogen.

Hierarchie: realm -> region -> city -> zone -> scene (parent-Kette,
Meter-Koordinaten). NPCs bekommen ihren Zeitplan als Frontmatter.

Aufruf:  python3 -m scripts.seed_world
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gamestate import slugify  # noqa: E402
from app.wiki_io import read_world_entry, update_entry_meta, write_world_entry  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "world" / "data"

REALMS = {
    "nordklans": ("Nordklans", "Clan-Konfoederation der noerdlichen Fjorde. Lange Winter, kurze Vertraege, lange Erinnerungen.", (1100000, 2750000), (400000, 2500000, 1800000, 3000000)),
    "gebirgsstaaten": ("Gebirgsstaaten", "Militaerische Handelsstaaten um die Kristallminen. Horten Essenz und trauen niemandem.", (2200000, 2450000), (1800000, 2000000, 2600000, 2900000)),
    "ostimperium": ("Ostimperium", "Das dominante Reich Avarrs: riesig, reich, von innen faulend. Ein alternder Kaiser in Vareth, neun Governors wie Geier.", (2400000, 1700000), (2000000, 1200000, 2800000, 2200000)),
    "steppenvoelker": ("Steppenvoelker", "Nomadische Clans der Suedoststeppe. Ihre oestlichen Weiden vertrocknen; ihre Raids reichen jedes Jahr tiefer.", (2300000, 700000), (1800000, 400000, 2800000, 1000000)),
    "binnenhandelsliga": ("Binnenhandelsliga", "Liga der Stadtstaaten am inneren Binnenmeer. Alles ist verhandelbar, auch die Mitgliedschaft.", (1000000, 1150000), (400000, 800000, 1600000, 1500000)),
    "waldreiche": ("Waldreiche", "Kleine Feudalkoenigreiche des Westens. Alt, stolz, zersplittert.", (550000, 1100000), (200000, 400000, 900000, 1800000)),
    "vhaelor": ("Vhaelor", "Vulkanische Regenwaldinsel im Zentrum des Binnenmeers. Evolutionaere Druckkammer, Essenz-Stuerme, unkontrollierbar.", (1500000, 1350000), None),
}


class Seeder:
    def __init__(self):
        self.written = 0
        self.skipped = 0
        self.anchors: dict[str, set] = {}

    def w(self, slug, meta, body):
        if write_world_entry(slug, meta, body, write_if_absent=True):
            self.written += 1
        else:
            self.skipped += 1

    def anchor(self, host, child):
        self.anchors.setdefault(host, set()).add(child)

    def link_pass(self):
        for host, children in self.anchors.items():
            entry = read_world_entry(host)
            if entry is None:
                continue
            meta, _ = entry
            merged = sorted(set(meta.get("links") or []) | children)
            if merged != sorted(meta.get("links") or []):
                update_entry_meta(host, {"links": merged})


def _bbox(d: dict | None) -> list[int] | None:
    if not d:
        return None
    return [d["x_min"], d["y_min"], d["x_max"], d["y_max"]]


def _coord(d: dict | None) -> list[int] | None:
    if not d:
        return None
    return [d["x"], d["y"]]


def _npc(s: Seeder, npc: dict, host_slug: str, region_name: str):
    slug = slugify(npc["id"])
    body_parts = [npc.get("description", "").strip()]
    if npc.get("personality"):
        body_parts.append("PERSOENLICHKEIT: " + npc["personality"].strip())
    if npc.get("knowledge"):
        body_parts.append("WISSEN: " + json.dumps(npc["knowledge"], ensure_ascii=False))
    if npc.get("schedule_summary"):
        body_parts.append("TAGESABLAUF: " + npc["schedule_summary"])
    meta = {"type": "character", "name": npc["name"], "region": region_name,
            "status": "lebendig", "tags": ["static-npc"], "links": [host_slug]}
    if npc.get("role"):
        meta["rolle"] = npc["role"]
    if npc.get("faction"):
        meta["faction"] = npc["faction"]
    if npc.get("stats"):
        meta["stats"] = npc["stats"]
    if npc.get("schedule"):
        meta["zeitplan"] = [{"ort": slugify(sh["scene_id"]),
                             "von": sh["hour_start"], "bis": sh["hour_end"]}
                            for sh in npc["schedule"]]
    s.w(slug, meta, "\n\n".join(p for p in body_parts if p))
    s.anchor(host_slug, slug)


def _city_area(s: Seeder, ca: dict, region_slug: str, region_name: str):
    city_slug = slugify(ca["id"])
    s.w(city_slug, {"type": "city", "name": ca["name"], "region": region_name,
                    "parent": region_slug, "tags": ["stadt"],
                    "einwohner": ca.get("population"),
                    "koordinaten": _coord(ca.get("coordinate_anchor")),
                    "bounding_box": _bbox(ca.get("bounding_box"))},
        f"{ca.get('size', 'city').capitalize()} in der Region {region_name}.")
    for zone in ca.get("zones", []):
        zslug = slugify(zone["id"])
        s.w(zslug, {"type": "zone", "name": zone["name"], "region": region_name,
                    "parent": city_slug, "tags": [zone.get("type", "zone")],
                    "koordinaten": _coord(zone.get("coordinate_anchor")),
                    "bounding_box": _bbox(zone.get("bounding_box"))},
            zone.get("layer_c_text", ""))
        for scene in zone.get("scenes", []):
            body = scene.get("layer_d_text", "")
            for g in scene.get("group_entries", []) or []:
                body += f"\n\nGRUPPE: {g.get('name', g) if isinstance(g, dict) else g}"
            for sub in scene.get("sub_scenes", []) or []:
                if isinstance(sub, dict):
                    body += f"\n\nNEBENRAUM {sub.get('name', sub.get('id', ''))}: {sub.get('text', '')}"
            s.w(slugify(scene["id"]),
                {"type": "scene", "name": scene["name"], "region": region_name,
                 "parent": zslug, "tags": [scene.get("type", "scene")],
                 "koordinaten": _coord(scene.get("coordinate_anchor"))},
                body)
    return city_slug


def seed() -> dict:
    s = Seeder()
    wc = json.loads((DATA / "world_constants.json").read_text(encoding="utf-8"))
    s.w("canon", {"type": "canon", "name": "Avarr — Weltkonstanten"},
        wc["world"]["constants"]["layer_a_text"]
        + "\n\nStartjahr: 743 IC. Muenzen: 1 Goldmark (gm) = 10 Silbermark (sm) "
          "= 100 Kupferpfennig (kp). Es gibt keine Magie — nur Essenz.")

    for slug, (name, desc, anchor, bbox) in REALMS.items():
        meta = {"type": "realm", "name": name, "koordinaten": list(anchor)}
        if bbox:
            meta["bounding_box"] = list(bbox)
        s.w(slug, meta, desc)

    # Suedkueste + Salzhaven (voll ausgebaut)
    sh = json.loads((DATA / "salzhaven.json").read_text(encoding="utf-8"))
    reg = sh["region"]
    reg_slug = slugify(reg["id"])
    s.w(reg_slug, {"type": "region", "name": reg["name"], "parent": "ostimperium",
                   "klima": reg.get("climate"),
                   "koordinaten": _coord(reg.get("coordinate_anchor")),
                   "bounding_box": _bbox(reg.get("bounding_box"))},
        reg.get("layer_b_text", ""))
    _city_area(s, sh["city_area"], reg_slug, reg["name"])
    for npc in sh.get("static_npcs", []):
        _npc(s, npc, slugify(sh["city_area"]["id"]), reg["name"])

    # Deltaprovince + Vareth
    dl = json.loads((DATA / "ostimperium_deltaprovince.json").read_text(encoding="utf-8"))
    dreg = dl["region"]
    dreg_slug = slugify(dreg["id"])
    s.w(dreg_slug, {"type": "region", "name": dreg["name"], "parent": "ostimperium",
                    "klima": dreg.get("climate"),
                    "koordinaten": _coord(dreg.get("coordinate_anchor")),
                    "bounding_box": _bbox(dreg.get("bounding_box"))},
        dreg.get("layer_b_text", ""))
    _city_area(s, dl["city_area"], dreg_slug, dreg["name"])
    for st in dl.get("secondary_settlements", []):
        s.w(slugify(st["id"]),
            {"type": "city" if st.get("size") == "city" else "location",
             "name": st["name"], "region": dreg["name"], "parent": dreg_slug,
             "tags": ["stadt"] if st.get("size") == "city" else ["siedlung"],
             "einwohner": st.get("population"),
             "koordinaten": _coord(st.get("coordinate_anchor"))},
            st.get("layer_c_text") or st.get("description", ""))

    # Restliche 7 Provinzen mit Siedlungen und NPCs
    rp = json.loads((DATA / "ostimperium_remaining_provinces.json").read_text(encoding="utf-8"))
    for prov in rp["provinces"]:
        pslug = slugify(prov["id"])
        s.w(pslug, {"type": "region", "name": prov["name"], "parent": "ostimperium",
                    "koordinaten": _coord(prov.get("coordinate_anchor")),
                    "bounding_box": _bbox(prov.get("bounding_box"))},
            prov.get("layer_b_text", ""))
        for st in prov.get("settlements", []):
            sslug = slugify(st["id"])
            s.w(sslug, {"type": "city" if st.get("size") == "city" else "location",
                        "name": st["name"], "region": prov["name"], "parent": pslug,
                        "tags": ["stadt"] if st.get("size") == "city" else ["siedlung"],
                        "einwohner": st.get("population"),
                        "koordinaten": _coord(st.get("coordinate"))},
                st.get("note", ""))
        for npc in prov.get("static_npcs", []):
            host = slugify(prov["settlements"][0]["id"]) if prov.get("settlements") else pslug
            _npc(s, npc, host, prov["name"])

    s.link_pass()
    return {"written": s.written, "skipped": s.skipped}


if __name__ == "__main__":
    result = seed()
    print(f"Seed fertig: {result['written']} geschrieben, {result['skipped']} uebersprungen (existierten).")
