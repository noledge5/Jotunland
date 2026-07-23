"""Seed: Basis-Welt (Canon, Regionen, Subregionen, Staedte, Factions,
Lore) plus dichte Vorkonstruktion aus scripts/world_data.py —
alle 11 Staedte ausgebaut, Adelshaeuser, Recht, Wirtschaft, Chroniken.
Idempotent (write_if_absent); Backlinks werden immer nachgezogen.

Aufruf:  python3 -m scripts.seed_world
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gamestate import slugify  # noqa: E402
from app.tools import auto_coords  # noqa: E402
from app.wiki_io import read_world_entry, update_entry_meta, write_world_entry  # noqa: E402
from scripts import world_data  # noqa: E402

CANON = """Die Welt ist alt, kalt und verschuldet. Drei Generationen nach dem
Aschekrieg halten fuenf Regionen ein bruechiges Buendnis: Velara im Westen,
die Eisenmark im Zentrum, die Frostmark im Norden, Rastberg im Osten und
der Schilfgrund im Sueden.

GESETZE DER WELT:
- Magie existiert, ist aber selten, koerperlich teuer und gesellschaftlich
  gefuerchtet. Kein Feuerball loest ein Problem, das ein Messer loesen kann.
- Muenzen: 1 Goldmark (gm) = 10 Silbermark (sm) = 100 Kupferpfennig (kp).
  Ein Tagelohn liegt bei 8-12 kp. Gold sieht ein einfacher Mann selten.
- Der Tod ist endgueltig. Heilung ist Handwerk (Wundnaht, Kraeuter), kein Wunder.
- Institutionen sind korrupt, aber nicht karikaturhaft: jede Wache, jede
  Gilde, jeder Tempel hat Interessen und einen Preis.
- Das Buendnis der fuenf Regionen haelt nur, weil der Krieg teurer waere."""

REGIONS = {
    "Velara": "Weinbau, Fluesse, alte Handelsstrassen. Reich, dekadent, verschuldet bei den eigenen Banken.",
    "Eisenmark": "Erzminen, Schmieden, Soeldnerwesen. Das militaerische Rueckgrat des Buendnisses.",
    "Frostmark": "Karger Norden, Fischfang, Walfang, Kloester. Menschen, die Kaelte fuer eine Tugend halten.",
    "Rastberg": "Hochland, Schafzucht, Silberminen, Blutfehden zwischen Talschaften.",
    "Schilfgrund": "Suempfe und Flussdeltas. Schmuggel, Aale, Fieber. Wer hier lebt, hat einen Grund.",
}

SUBREGION_STEMS = {
    "Velara": ["Goldene Huegel", "Weinsteig", "Unterlauf", "Alte Furt", "Herzland",
               "Westkueste", "Graue Doerfer", "Muendungsland"],
    "Eisenmark": ["Erzkamm", "Schlackental", "Hammerwald", "Ostschanze", "Kohlgrund",
                  "Rauchheide", "Zwingfeld", "Grenzmark"],
    "Frostmark": ["Eishornkueste", "Walfjorde", "Nebelhoehen", "Steinoedland", "Klosterland",
                  "Treibeisbucht", "Rentierweiden", "Schwarzfels"],
    "Rastberg": ["Silbertal", "Hochweiden", "Fehdenland", "Passland", "Steinerne Stufen",
                 "Windkar", "Talschaft Grau", "Talschaft Rot"],
    "Schilfgrund": ["Aalgraeben", "Binsenmeer", "Fieberland", "Delta", "Torfstiche",
                    "Schwarzwasser", "Reusenkueste", "Treibholzufer"],
}

CAPITALS = {
    "Hartfeld": ("Eisenmark", "Hauptstadt der Eisenmark. Schmiedefeuer, Soeldnerboersen, der groesste Waffenmarkt des Buendnisses."),
    "Velara-Stadt": ("Velara", "Hauptstadt Velaras. Banken, Weinhaeuser, Intrigen. Die Stadt lebt auf Kredit."),
    "Eisentor": ("Eisenmark", "Festungsstadt am Ostpass. Wer das Tor haelt, haelt die Grenze."),
    "Frostburg": ("Frostmark", "Hauptstadt der Frostmark. Walspeck, Klosterpolitik, ewiger Wind."),
}

TOWNS = {
    "Goldhausen": ("Velara", "Minenstadt, deren Goldadern duenn werden. Die Fassaden sind praechtiger als die Kassen."),
    "Bergerz": ("Eisenmark", "Grubenstadt am Erzkamm. Halb Stadt, halb Stollen."),
    "Rastberg-Stadt": ("Rastberg", "Marktflecken des Hochlands. Neutraler Boden fuer verfeindete Talschaften."),
    "Salzhafen": ("Frostmark", "Fischerhafen mit Salzsiederei. Riecht nach Tran und Geld."),
    "Eishorn-Kloster": ("Frostmark", "Bergkloster ueber der Eishornkueste. Bibliothek, Brauerei, Beichtgeheimnisse."),
    "Schilfgrund-Dorf": ("Schilfgrund", "Pfahldorf im Delta. Offiziell Fischerei, faktisch Schmuggelboerse."),
    "Grauwall": ("Rastberg", "Grenzstadt an der alten Mauer. Zollstation und Schmugglernest zugleich."),
}

FACTIONS = {
    "Buendnisrat": "Der gemeinsame Rat der fuenf Regionen. Traege, zerstritten, unverzichtbar.",
    "Eiserne Rechnung": "Soeldnerbank der Eisenmark: verleiht Truppen wie Kredite — mit Zins.",
    "Orden vom Eishorn": "Kloesterlicher Orden der Frostmark. Bewahrt Wissen, verkauft Absolution.",
    "Aalbruderschaft": "Schmuggelnetz des Schilfgrunds. Jeder kennt einen Bruder, niemand kennt zwei.",
    "Velarische Bankhaeuser": "Kartell der Geldhaeuser Velaras. Haelt halbe Regionen ueber Schulden im Griff.",
}

LORE = {
    "Der Aschekrieg": "Der Krieg vor drei Generationen, der die alten Reiche brach. Niemand nennt einen Sieger.",
    "Die Duennung": "Leises Schwinden der Magie seit dem Aschekrieg. Zauberwirker altern schneller.",
    "Das Buendnis der Fuenf": "Der Vertrag, der die Regionen bindet. Jede Klausel wurde mit Blut bezahlt.",
    "Die Zinslast": "Velarische Kredite finanzierten den Wiederaufbau. Die Rueckzahlung formt bis heute jede Politik.",
}


def seed() -> dict:
    written = 0
    skipped = 0

    def w(slug, meta, body):
        nonlocal written, skipped
        if write_world_entry(slug, meta, body, write_if_absent=True):
            written += 1
        else:
            skipped += 1

    w("canon", {"type": "canon", "name": "Welt-Canon"}, CANON)

    for name, desc in REGIONS.items():
        slug = slugify(name)
        w(slug, {"type": "region", "name": name,
                 "koordinaten": auto_coords(slug, name)}, desc)

    for region, stems in SUBREGION_STEMS.items():
        for stem in stems:
            slug = slugify(f"{stem}")
            w(slug, {"type": "subregion", "name": stem, "region": region,
                     "koordinaten": auto_coords(slug, region)},
              f"Subregion von {region}.")

    for name, (region, desc) in CAPITALS.items():
        slug = slugify(name)
        w(slug, {"type": "location", "name": name, "region": region,
                 "tags": ["stadt", "hauptstadt"],
                 "koordinaten": auto_coords(slug, region),
                 "links": [slugify(region)]}, desc)

    for name, (region, desc) in TOWNS.items():
        slug = slugify(name)
        w(slug, {"type": "location", "name": name, "region": region,
                 "tags": ["stadt"],
                 "koordinaten": auto_coords(slug, region),
                 "links": [slugify(region)]}, desc)

    for name, desc in FACTIONS.items():
        w(slugify(name), {"type": "faction", "name": name}, desc)

    for name, desc in LORE.items():
        w(slugify(name), {"type": "lore", "name": name, "status": "ruhend"}, desc)

    dense = seed_dense(w)
    _link(dense)

    return {"written": written, "skipped": skipped}


def seed_dense(w) -> dict:
    """Schreibt die dichte Welt aus world_data.py. Liefert die Link-Map
    {host_slug: [kind_slugs]} fuer den Backlink-Pass."""
    links: dict[str, set] = {}

    def anchor(host: str, child: str) -> None:
        links.setdefault(host, set()).add(child)

    for city_slug, data in world_data.CITIES.items():
        city_meta = (read_world_entry(city_slug) or ({}, ""))[0]
        region = city_meta.get("region", "")
        city_name = city_meta.get("name", city_slug.capitalize())
        for name, body in data["locations"]:
            slug = slugify(name)
            w(slug, {"type": "location", "name": name, "region": region,
                     "tags": ["viertel"], "links": [city_slug]}, body)
            anchor(city_slug, slug)
        for name, status, body in data["characters"]:
            slug = slugify(name)
            w(slug, {"type": "character", "name": name, "region": region,
                     "status": status, "links": [city_slug]}, body)
            anchor(city_slug, slug)
        for inst in data["institutions"]:
            key, body = inst[0], inst[1]
            produces = inst[2] if len(inst) > 2 else []
            imports = inst[3] if len(inst) > 3 else []
            slug = f"{key}-{city_slug}"
            meta = {"type": "faction", "name": f"{key.capitalize()} {city_name}",
                    "region": region, "links": [city_slug]}
            if produces:
                meta["produces"] = produces
            if imports:
                meta["imports"] = imports
            w(slug, meta, body)
            anchor(city_slug, slug)

    for region, houses in world_data.NOBLE_HOUSES.items():
        rslug = slugify(region)
        for name, status, seat, body in houses:
            slug = slugify(name)
            w(slug, {"type": "noble_house", "name": name, "region": region,
                     "status": status, "links": [seat]}, body)
            anchor(rslug, slug)
            anchor(seat, slug)

    name, status, body = world_data.FALLEN_HOUSE
    slug = slugify(name)
    w(slug, {"type": "noble_house", "name": name, "region": "Eisenmark",
             "status": status, "links": ["der-aschekrieg"]}, body)
    anchor(slugify("Eisenmark"), slug)

    for region, (name, body) in world_data.LAWS.items():
        slug = slugify(name)
        w(slug, {"type": "law", "name": name, "region": region}, body)
        anchor(slugify(region), slug)

    for region, (name, produces, imports, body) in world_data.ECONOMY.items():
        slug = slugify(name)
        w(slug, {"type": "economy", "name": name, "region": region,
                 "produces": produces, "imports": imports}, body)
        anchor(slugify(region), slug)

    for name, body in world_data.CHRONICLES:
        w(slugify(name), {"type": "chronicle", "name": name}, body)

    for name, status, body in world_data.LORE_EXTRA:
        w(slugify(name), {"type": "lore", "name": name, "status": status}, body)

    for name, host, body in world_data.WANDERERS:
        slug = slugify(name)
        w(slug, {"type": "character", "name": name, "status": "lebendig",
                 "links": [host]}, body)
        anchor(host, slug)

    for faction_slug, host in world_data.FACTION_ANCHORS.items():
        anchor(host, faction_slug)

    return links


def _link(link_map: dict[str, set]) -> None:
    """Backlink-Pass: Hosts (Staedte/Regionen) verlinken ihre Kinder.
    Laeuft auch bei Re-Seed, damit Links vollstaendig bleiben."""
    for host, children in link_map.items():
        entry = read_world_entry(host)
        if entry is None:
            continue
        meta, _ = entry
        merged = sorted(set(meta.get("links") or []) | children)
        if merged != sorted(meta.get("links") or []):
            update_entry_meta(host, {"links": merged})


if __name__ == "__main__":
    result = seed()
    print(f"Seed fertig: {result['written']} geschrieben, {result['skipped']} uebersprungen (existierten).")
