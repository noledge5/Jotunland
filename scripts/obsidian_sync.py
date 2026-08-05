"""Bruecke zwischen Engine-Wiki und einem Obsidian-Vault — in beide Richtungen.

Das Engine-Wiki ist auf Maschinen optimiert: eine flache Ablage, Dateinamen
sind Slugs, Verweise im Text sind `[[slug]]`. Ein Vault, in dem man auf dem
Handy arbeiten will, braucht das Gegenteil: sprechende Titel, Ordner nach
Typ, und einen Graph, dessen Knoten Namen tragen statt Kennungen.

    python3 -m scripts.obsidian_sync export ~/Avarr-Vault
    python3 -m scripts.obsidian_sync import ~/Avarr-Vault [--trocken]

Der Anker der Rueckrichtung ist IMMER das Feld `slug` im Frontmatter, nie der
Dateiname. Nur so ueberlebt der Rundlauf ein Umbenennen in Obsidian — und
umbenennen wird man wollen, sobald der Graph lesbar ist.

Was NICHT synchronisiert wird: der Spielstand. Er wird als lesbare Notiz
exportiert und beim Import ignoriert. Spielstand aendert man ueber die
Engine, nie ueber einen Texteditor (ADR-0001) — ein Vault, aus dem man HP
zurueckschreiben koennte, waere genau die Tuer, die dieses Projekt zuhaelt.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gamestate as gsm  # noqa: E402
from app import wiki_index  # noqa: E402
from app.wiki_io import (WORLD_DIR, parse_frontmatter, write_world_entry)  # noqa: E402

LINK_RE = re.compile(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]")

# Ordner im Vault. Alles, was hier nicht steht, landet in "Sonstiges".
ORDNER = {
    "realm": "01 Reiche", "region": "02 Regionen", "city": "03 Staedte",
    "zone": "04 Zonen", "scene": "05 Orte", "location": "05 Orte",
    "character": "06 Figuren", "faction": "07 Fraktionen",
    "noble_house": "07 Fraktionen", "fauna": "08 Fauna", "flora": "09 Flora",
    "lore": "10 Lore", "law": "10 Lore", "chronicle": "10 Lore",
    "economy": "11 Wirtschaft",
}
SONSTIGES = "12 Sonstiges"

VERBOTEN = r'\/:*?"<>|'


def _dateiname(name: str, slug: str) -> str:
    """Sprechender Dateiname. Faellt auf den Slug zurueck, wenn der Name im
    Dateisystem nicht darstellbar ist."""
    sauber = "".join(c for c in (name or "") if c not in VERBOTEN).strip().rstrip(".")
    return sauber or slug


def _frontmatter(meta: dict) -> str:
    import yaml
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n"


# --- Export ---------------------------------------------------------------

def export(ziel: Path) -> dict:
    idx = wiki_index.get_index(force=True)["entries"]
    if not idx:
        raise SystemExit("FEHLER: Kein Wiki gefunden. Erst 'python3 -m scripts.seed_world'.")

    # slug -> Anzeigename, damit [[slug]] im Text zu [[Name]] wird
    name_von = {slug: _dateiname(e.get("name") or slug, slug) for slug, e in idx.items()}
    # Kollisionen aufloesen, sonst zeigen zwei Links auf dieselbe Datei
    gesehen: dict[str, str] = {}
    for slug in sorted(name_von):
        n = name_von[slug]
        if n in gesehen:
            name_von[slug] = f"{n} ({slug})"
        else:
            gesehen[n] = slug

    def links_uebersetzen(text: str) -> str:
        return LINK_RE.sub(
            lambda m: f"[[{name_von.get(m.group(1), m.group(1))}]]", text)

    ziel.mkdir(parents=True, exist_ok=True)
    geschrieben = 0
    for slug, e in sorted(idx.items()):
        quelle = WORLD_DIR / e["path"]
        if not quelle.exists():
            continue
        meta, body = parse_frontmatter(quelle.read_text(encoding="utf-8"))
        meta["slug"] = slug                      # Anker der Rueckrichtung
        # Beziehungsfelder ebenfalls auf Namen umstellen: so zeichnet Obsidian
        # die Hierarchie und die Abstammung als echte Kanten im Graph.
        zeilen = []
        for feld, label in (("parent", "Liegt in"), ("gattung", "Gattung")):
            wert = meta.get(feld)
            if wert and wert in name_von:
                zeilen.append(f"**{label}:** [[{name_von[wert]}]]")
        for feld, label in (("frisst", "Frisst"), ("links", "Verbunden mit")):
            werte = [w for w in (meta.get(feld) or []) if w in name_von]
            if werte:
                zeilen.append(f"**{label}:** "
                              + ", ".join(f"[[{name_von[w]}]]" for w in werte))
        kopf = ("\n".join(zeilen) + "\n\n") if zeilen else ""

        ordner = ziel / ORDNER.get(e["type"], SONSTIGES)
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / f"{name_von[slug]}.md").write_text(
            _frontmatter(meta) + kopf + links_uebersetzen(body).strip() + "\n",
            encoding="utf-8")
        geschrieben += 1

    _spielstand_notiz(ziel)
    _leseanleitung(ziel, geschrieben)
    return {"eintraege": geschrieben, "ziel": str(ziel)}


def _spielstand_notiz(ziel: Path) -> None:
    """Der Spielstand kommt als Momentaufnahme mit, aber nur lesend."""
    from app import session
    aktiv = gsm.load_settings().get("active_pc_slug")
    gs = gsm.load_pc(aktiv) if aktiv else None
    if gs is None:
        return
    text = ("---\ntyp: spielstand\nnur_lesen: true\n---\n\n"
            "# Spielstand (Momentaufnahme)\n\n"
            "> Nicht bearbeiten. Diese Notiz wird bei jedem Export ueberschrieben\n"
            "> und beim Import ignoriert. Der Spielstand gehoert der Engine.\n\n"
            "```\n" + session.state_panel(gs) + "\n```\n")
    (ziel / "Spielstand.md").write_text(text, encoding="utf-8")


def _leseanleitung(ziel: Path, n: int) -> None:
    (ziel / "README Vault.md").write_text(
        "---\ntyp: anleitung\n---\n\n"
        "# Avarr — Vault\n\n"
        f"{n} Eintraege, exportiert aus dem Engine-Wiki.\n\n"
        "## Was du hier tun kannst\n\n"
        "- Lesen, suchen, im Graph navigieren.\n"
        "- Eintraege bearbeiten: Fliesstext frei, Properties mit Bedacht.\n"
        "- Neue Eintraege anlegen: Ordner egal, aber `type:` im Frontmatter\n"
        "  setzen. Einen `slug:` brauchst du nicht — der Import vergibt ihn.\n\n"
        "## Was du hier NICHT tun solltest\n\n"
        "- `slug:` aendern. Das ist der Anker, an dem der Rueckweg haengt.\n"
        "  Dateien umbenennen ist dagegen gefahrlos.\n"
        "- `Spielstand.md` bearbeiten. Wird beim Export ueberschrieben.\n"
        "- Waehrend einer laufenden Spielsitzung schreiben — Sync und Engine\n"
        "  auf denselben Dateien geben Konfliktkopien.\n\n"
        "## Zurueck in die Engine\n\n"
        "```\npython3 -m scripts.obsidian_sync import <dieser-Ordner> --trocken\n"
        "python3 -m scripts.obsidian_sync import <dieser-Ordner>\n"
        "python3 -m scripts.wiki_lint\n```\n",
        encoding="utf-8")


# --- Import ---------------------------------------------------------------

def importieren(quelle: Path, trocken: bool = False) -> dict:
    if not quelle.exists():
        raise SystemExit(f"FEHLER: '{quelle}' gibt es nicht.")
    idx = wiki_index.get_index(force=True)["entries"]
    name_zu_slug = {(e.get("name") or slug): slug for slug, e in idx.items()}

    # Erster Durchgang: Dateinamen im Vault auf Slugs abbilden. Obsidian
    # schreibt beim Umbenennen einer Datei alle Links auf sie mit um — ohne
    # diese Karte zeigt danach jeder Verweis auf einen Slug, den es nicht
    # gibt. Der Dateiname gewinnt, weil er der ist, der im Link steht.
    dateien = sorted(quelle.rglob("*.md"))
    for datei in dateien:
        m, _ = parse_frontmatter(datei.read_text(encoding="utf-8"))
        if m.get("typ") in ("spielstand", "anleitung") or not m.get("type"):
            continue
        s = m.get("slug") or gsm.slugify(m.get("name") or datei.stem)
        name_zu_slug[datei.stem] = s
        if m.get("name"):
            name_zu_slug.setdefault(m["name"], s)

    bericht = {"geaendert": [], "neu": [], "unveraendert": 0, "uebersprungen": []}
    for datei in dateien:
        meta, body = parse_frontmatter(datei.read_text(encoding="utf-8"))
        if meta.get("typ") in ("spielstand", "anleitung"):
            continue
        if not meta.get("type"):
            bericht["uebersprungen"].append(f"{datei.name} (kein 'type')")
            continue

        slug = meta.get("slug") or gsm.slugify(meta.get("name") or datei.stem)
        meta["slug"] = slug
        meta.setdefault("name", datei.stem)
        # Namen in Verweisen wieder auf Slugs zurueckdrehen
        rueck = LINK_RE.sub(
            lambda m: f"[[{name_zu_slug.get(m.group(1), gsm.slugify(m.group(1)))}]]",
            body)
        # Die Beziehungs-Kopfzeilen aus dem Export sind abgeleitete Anzeige,
        # kein Inhalt — sie duerfen nicht als Text zurueckwandern.
        rueck = "\n".join(z for z in rueck.splitlines()
                          if not re.match(r"^\*\*(Liegt in|Gattung|Frisst|Verbunden mit):\*\*", z))
        for feld in ("parent", "gattung"):
            if meta.get(feld) in name_zu_slug:
                meta[feld] = name_zu_slug[meta[feld]]
        for feld in ("frisst", "links"):
            if meta.get(feld):
                meta[feld] = [name_zu_slug.get(w, gsm.slugify(w)) for w in meta[feld]]
        rueck = rueck.strip() + "\n"

        alt = idx.get(slug)
        if alt is None:
            bericht["neu"].append(slug)
        else:
            a_meta, a_body = parse_frontmatter(
                (WORLD_DIR / alt["path"]).read_text(encoding="utf-8"))
            if a_body.strip() == rueck.strip() and {k: v for k, v in a_meta.items()} == meta:
                bericht["unveraendert"] += 1
                continue
            bericht["geaendert"].append(slug)
        if not trocken:
            write_world_entry(slug, meta, rueck)

    if not trocken:
        wiki_index.invalidate()
    return bericht


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="obsidian_sync", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export", help="Engine-Wiki -> Obsidian-Vault")
    p.add_argument("ziel", type=Path)
    p.add_argument("--frisch", action="store_true",
                   help="Zielordner vorher leeren")
    p = sub.add_parser("import", help="Obsidian-Vault -> Engine-Wiki")
    p.add_argument("quelle", type=Path)
    p.add_argument("--trocken", action="store_true",
                   help="nur zeigen, was sich aendern wuerde")
    args = ap.parse_args(argv)

    if args.cmd == "export":
        if args.frisch and args.ziel.exists():
            shutil.rmtree(args.ziel)
        r = export(args.ziel)
        print(f"{r['eintraege']} Eintraege nach {r['ziel']} exportiert.")
    else:
        r = importieren(args.quelle, args.trocken)
        vorsatz = "[Trockenlauf] " if args.trocken else ""
        print(f"{vorsatz}{len(r['neu'])} neu, {len(r['geaendert'])} geaendert, "
              f"{r['unveraendert']} unveraendert.")
        for s in r["neu"]:
            print(f"  + {s}")
        for s in r["geaendert"]:
            print(f"  ~ {s}")
        for s in r["uebersprungen"]:
            print(f"  ? uebersprungen: {s}")


if __name__ == "__main__":
    main()
