"""Wiki-IO: atomare Markdown-Writes mit YAML-Frontmatter.

Alle Welt-Eintraege liegen flach unter wiki/world/<slug>.md mit
Frontmatter (slug, type, name, region, status, tags, koordinaten, ...).
Pro PC gibt es wiki/pc/<slug>/journal.md und events/.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml

from .gamestate import PC_DIR, WIKI_DIR, now_iso, slugify

WORLD_DIR = WIKI_DIR / "world"

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

# Slugs, die als "generische Institution einer Stadt" gelten, muessen dem
# Muster <institution>-<stadt> folgen (Pinpoint-Slug-Regel gegen Duplikate
# wie hartfeld-wache vs stadtwache-hartfeld). Keyword -> kanonischer Name.
INSTITUTION_KEYWORDS = {
    "wache": "stadtwache", "stadtwache": "stadtwache", "garnison": "garnison",
    "tempel": "tempel", "gilde": "gilde", "rat": "rat", "markt": "markt",
    "hafen": "hafen", "gericht": "gericht", "kerker": "kerker",
}


def canonical_slug(name: str, entry_type: str = "", city: str | None = None) -> str:
    """Slug-Erzeugung mit Pinpoint-Regel fuer Stadt-Institutionen.

    Eine Stadtwache von Hartfeld wird immer 'stadtwache-hartfeld',
    egal ob der Name 'Hartfelder Wache' oder 'Wache von Hartfeld' lautet.
    """
    base = slugify(name)
    if city:
        city_slug = slugify(city)
        for word in base.split("-"):
            inst = INSTITUTION_KEYWORDS.get(word)
            if inst:
                return f"{inst}-{city_slug}"
    return base


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, text[m.end():]


def render_entry(meta: dict, body: str) -> str:
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body.strip()}\n"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def entry_path(slug: str) -> Path:
    return WORLD_DIR / f"{slug}.md"


def read_world_entry(slug: str) -> tuple[dict, str] | None:
    p = entry_path(slug)
    if not p.exists():
        return None
    return parse_frontmatter(p.read_text(encoding="utf-8"))


def write_world_entry(slug: str, meta: dict, body: str,
                      write_if_absent: bool = False) -> bool:
    """Schreibt einen Welt-Eintrag. True wenn geschrieben.

    write_if_absent=True ueberspringt existierende Eintraege (idempotentes
    Seeding). Invalidiert den Index-Cache.
    """
    p = entry_path(slug)
    if write_if_absent and p.exists():
        return False
    meta = {"slug": slug, **meta}
    meta.setdefault("aktualisiert", now_iso())
    _atomic_write_text(p, render_entry(meta, body))
    from . import wiki_index
    wiki_index.invalidate()
    return True


def append_world_entry(slug: str, addition: str) -> bool:
    existing = read_world_entry(slug)
    if existing is None:
        return False
    meta, body = existing
    meta["aktualisiert"] = now_iso()
    _atomic_write_text(entry_path(slug), render_entry(meta, body + "\n\n" + addition.strip()))
    from . import wiki_index
    wiki_index.invalidate()
    return True


def update_entry_meta(slug: str, patch: dict) -> bool:
    existing = read_world_entry(slug)
    if existing is None:
        return False
    meta, body = existing
    meta.update(patch)
    meta["aktualisiert"] = now_iso()
    _atomic_write_text(entry_path(slug), render_entry(meta, body))
    from . import wiki_index
    wiki_index.invalidate()
    return True


# --- PC-Journal & Events -----------------------------------------------

def journal_path(pc_slug: str) -> Path:
    return PC_DIR / pc_slug / "journal.md"


def append_pc_journal(pc_slug: str, text: str) -> None:
    p = journal_path(pc_slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_iso()
    block = f"\n## {stamp}\n\n{text.strip()}\n"
    existing = p.read_text(encoding="utf-8") if p.exists() else f"# Journal\n"
    _atomic_write_text(p, existing + block)


def read_journal_tail(pc_slug: str, max_entries: int = 5) -> str:
    p = journal_path(pc_slug)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", text)
    tail = sections[-max_entries:] if len(sections) > 1 else []
    return "\n".join("## " + s.strip() for s in tail if s.strip() and not s.startswith("# "))


def write_pc_event(pc_slug: str, title: str, text: str) -> Path:
    events = PC_DIR / pc_slug / "events"
    events.mkdir(parents=True, exist_ok=True)
    fname = f"{now_iso().replace(':', '-')}-{slugify(title)}.md"
    p = events / fname
    _atomic_write_text(p, f"# {title}\n\n{text.strip()}\n")
    return p
