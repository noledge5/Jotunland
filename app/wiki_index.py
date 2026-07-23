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
from .wiki_io import WORLD_DIR, parse_frontmatter

INDEX_PATH = WORLD_DIR / "_index.json"
LINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")

_mem_cache: dict | None = None


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
                "status": meta.get("status"),
                "tags": meta.get("tags") or [],
                "koordinaten": meta.get("koordinaten"),
                "links": links,
                "path": str(p.relative_to(WORLD_DIR)),
            }
            for good in meta.get("produces") or []:
                produced_by.setdefault(good, []).append(slug)
            for good in meta.get("imports") or []:
                imported_by.setdefault(good, []).append(slug)
    return {"entries": entries, "produced_by": produced_by, "imported_by": imported_by}


def get_index(force: bool = False) -> dict:
    global _mem_cache
    if _mem_cache is not None and not force:
        return _mem_cache
    if not force:
        cached = read_json(INDEX_PATH)
        if cached:
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


def find_similar_slugs(slug: str) -> list[str]:
    """Findet potentielle Duplikate: gleiche Wortmenge in anderer Reihenfolge
    oder Teilmengen-Ueberlappung (hartfeld-wache vs stadtwache-hartfeld)."""
    words = set(slug.split("-"))
    hits = []
    for other in get_index()["entries"]:
        if other == slug:
            continue
        ow = set(other.split("-"))
        shared = words & ow
        # Ueberlappung von mind. 2 Woertern oder identische Wortmenge
        if words == ow or (len(shared) >= 2 and shared != {"der", "die", "das", "von"}):
            hits.append(other)
    return hits
