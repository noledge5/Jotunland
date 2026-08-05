"""Globaler Slug-Index ueber wiki/world/ mit Disk-Cache.

Der Index kennt zu jedem Slug Typ, Name, Region, Status, Tags und Links,
plus produced_by/imported_by-Maps fuer Economy-Eintraege. Cache liegt
unter wiki/world/_index.json und wird bei jedem Write invalidiert.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .gamestate import atomic_write_json, read_json
from .wiki_io import INSTITUTION_KEYWORDS, WORLD_DIR, parse_frontmatter

INDEX_PATH = WORLD_DIR / "_index.json"
LINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")

# Hochzaehlen, wenn _scan neue Felder schreibt — sonst liefert der Disk-Cache
# eines laufenden Servers weiter die alte Struktur und das neue Feld fehlt still.
INDEX_VERSION = 3

_mem_cache: dict | None = None


def _kurzfassung(body: str) -> str:
    """Erste inhaltliche Zeile eines Eintrags — Rollen-/Zweckzeile fuer das
    Namensregister im Prompt. Wird beim Index-Scan einmal berechnet und
    mitgecacht, kostet zur Laufzeit also keinen Datei-Read."""
    for raw in body.splitlines():
        line = raw.strip().lstrip("#*->").strip()
        if len(line) < 8 or line.startswith(("|", "```", "[[", "!")):
            continue
        if len(line) <= 90:
            return line
        return line[:90].rsplit(" ", 1)[0] + " ..."
    return ""


def _dateistand() -> float:
    """Juengste Aenderungszeit im Wiki. Der Cache wird invalidiert, wenn die
    Engine schreibt — aber nicht, wenn jemand von aussen editiert (Obsidian,
    Editor, Sync). Ohne diesen Vergleich liest ein laufender Server nach einer
    externen Aenderung still die alte Fassung weiter."""
    if not WORLD_DIR.exists():
        return 0.0
    return max((p.stat().st_mtime for p in WORLD_DIR.glob("*.md")), default=0.0)


def invalidate() -> None:
    global _mem_cache
    _mem_cache = None
    if INDEX_PATH.exists():
        INDEX_PATH.unlink()


def _scan() -> dict:
    entries: dict[str, dict] = {}
    produced_by: dict[str, list] = {}
    imported_by: dict[str, list] = {}
    if WORLD_DIR.exists():
        for p in sorted(WORLD_DIR.glob("*.md")):
            meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
            slug = meta.get("slug") or p.stem
            links = sorted(set(LINK_RE.findall(body)) | set(meta.get("links") or []))
            entries[slug] = {
                "slug": slug,
                "type": meta.get("type", "unbekannt"),
                "name": meta.get("name", slug),
                "region": meta.get("region"),
                "parent": meta.get("parent"),
                "status": meta.get("status"),
                # Rolle/Fraktion sind die driftanfaelligsten Fakten einer Figur
                # und stehen im Frontmatter — sie gehoeren ins Namensregister.
                "rolle": meta.get("rolle"),
                "faction": meta.get("faction"),
                # Biologie (Flora/Fauna): Abstammung und Nahrungsnetz. 'gattung'
                # ist die Taxonomie-Achse, getrennt von 'parent' (Geografie).
                "rang": meta.get("rang"),
                "gattung": meta.get("gattung"),
                "frisst": meta.get("frisst") or [],
                "biom": meta.get("biom") or [],
                "essenz": meta.get("essenz"),
                "scope": meta.get("scope", "welt"),
                "gesperrt": bool(meta.get("gesperrt", False)),
                "pc": meta.get("pc"),
                "tags": meta.get("tags") or [],
                "koordinaten": meta.get("koordinaten"),
                "bild": meta.get("bild"),
                "zeitplan": meta.get("zeitplan") or [],
                "bounding_box": meta.get("bounding_box"),
                "links": links,
                "kurz": _kurzfassung(body),
                "path": str(p.relative_to(WORLD_DIR)),
            }
            for good in meta.get("produces") or []:
                produced_by.setdefault(good, []).append(slug)
            for good in meta.get("imports") or []:
                imported_by.setdefault(good, []).append(slug)
    return {"version": INDEX_VERSION, "stand": _dateistand(), "entries": entries,
            "produced_by": produced_by, "imported_by": imported_by}


def get_index(force: bool = False) -> dict:
    global _mem_cache
    stand = _dateistand()

    def frisch(idx: dict | None) -> bool:
        return bool(idx) and idx.get("version") == INDEX_VERSION \
            and idx.get("stand", -1) >= stand

    if not force and frisch(_mem_cache):
        return _mem_cache
    if not force:
        cached = read_json(INDEX_PATH)
        if frisch(cached):
            _mem_cache = cached
            return cached
    idx = _scan()
    atomic_write_json(INDEX_PATH, idx)
    _mem_cache = idx
    return idx


def get_entry_meta(slug: str) -> dict | None:
    return get_index()["entries"].get(slug)


def slugs_of_type(entry_type: str) -> list[str]:
    return [s for s, e in get_index()["entries"].items() if e["type"] == entry_type]


_STOPWORDS = {"der", "die", "das", "des", "von", "vom", "im", "zur", "zum"}


def _word_set(slug: str) -> frozenset:
    """Wortmenge eines Slugs, normalisiert: Stoppwoerter raus,
    Institutions-Aliasse vereinheitlicht (wache -> stadtwache)."""
    return frozenset(INSTITUTION_KEYWORDS.get(w, w)
                     for w in slug.split("-") if w not in _STOPWORDS)


def find_similar_slugs(slug: str) -> list[str]:
    """Findet potentielle Duplikate: gleiche normalisierte Wortmenge
    (hartfeld-wache vs stadtwache-hartfeld) oder echte Teilmenge."""
    words = _word_set(slug)
    hits = []
    for other in get_index()["entries"]:
        if other == slug:
            continue
        ow = _word_set(other)
        if words == ow or (len(words) > 1 and words < ow) or (len(ow) > 1 and ow < words):
            hits.append(other)
    return hits
