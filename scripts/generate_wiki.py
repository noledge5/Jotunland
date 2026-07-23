"""4-Stufen-City-Pass: geography -> people -> politics -> institutions.

Pro Stadt und Stufe ein LLM-Call mit striktem JSON-Schema. Ergebnisse
werden dedupliziert (kanonische Slugs, Aehnlichkeitscheck) und als
Wiki-Eintraege geschrieben. Resume ueber wiki/world/_generation_log.json.
Provider-Fallback: openrouter -> google -> anthropic (je nach Keys).

Aufruf:
  python3 -m scripts.generate_wiki --city hartfeld
  python3 -m scripts.generate_wiki --all
  python3 -m scripts.generate_wiki --city hartfeld --dry-run   (ohne LLM)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import wiki_index  # noqa: E402
from app.gamestate import atomic_write_json, read_json, slugify  # noqa: E402
from app.llm_adapter import api_key_for  # noqa: E402
from app.tools import auto_coords  # noqa: E402
from app.wiki_io import WORLD_DIR, canonical_slug, read_world_entry, write_world_entry  # noqa: E402

LOG_PATH = WORLD_DIR / "_generation_log.json"
STAGES = ("geography", "people", "politics", "institutions")

STAGE_PROMPTS = {
    "geography": "Erzeuge 3-5 markante Orte INNERHALB der Stadt (Viertel, Plaetze, Bauwerke).",
    "people": "Erzeuge 4-6 Charaktere der Stadt (Handwerker, Haendler, Randfiguren, eine Autoritaet).",
    "politics": "Erzeuge 2-3 Machtstrukturen: Adelshaus, Rat oder Fraktion mit konkreten Interessen.",
    "institutions": "Erzeuge 2-4 Institutionen (Wache, Tempel, Gilde, Gericht) mit Wirtschaftsbezug (produces/imports).",
}

STAGE_TYPES = {
    "geography": "location",
    "people": "character",
    "politics": "faction",
    "institutions": "faction",
}

JSON_SCHEMA_HINT = """Antworte NUR mit JSON, keinem anderen Text:
{"entries": [{"name": str, "type": "location|character|faction|noble_house",
  "status": str, "body": str (2-4 Saetze, grimdark, konkret),
  "tags": [str], "produces": [str], "imports": [str]}]}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("Keine JSON-Struktur in der Antwort")
    return json.loads(m.group(0))


def _call_llm(prompt: str, provider: str, model: str | None = None) -> str:
    """Synchroner Call (Scripts brauchen kein Streaming)."""
    key = api_key_for(provider)
    if not key:
        raise RuntimeError(f"Kein Key fuer {provider}")
    if provider == "openrouter":
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model or "anthropic/claude-sonnet-4.5",
                             "messages": [{"role": "user", "content": prompt}],
                             "max_tokens": 3000},
                       timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    if provider == "google":
        m = model or "gemini-2.5-flash"
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                       headers={"x-goog-api-key": key},
                       json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
                       timeout=120)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                       json={"model": model or "claude-sonnet-4-5",
                             "max_tokens": 3000,
                             "messages": [{"role": "user", "content": prompt}]},
                       timeout=120)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])
    raise ValueError(provider)


def call_with_fallback(prompt: str) -> str:
    errors = []
    for provider in ("openrouter", "google", "anthropic"):
        if not api_key_for(provider):
            continue
        try:
            return _call_llm(prompt, provider)
        except Exception as e:
            errors.append(f"{provider}: {e}")
    raise RuntimeError("Alle Provider fehlgeschlagen: " + "; ".join(errors or ["keine Keys gesetzt"]))


DRY_RUN_SAMPLES = {
    "geography": [{"name": "Schlackenmarkt", "type": "location", "status": "aktiv",
                   "body": "Der Markt am alten Schmelzofen. Asche im Brot, Blei im Bier.",
                   "tags": ["viertel"]}],
    "people": [{"name": "Greta Eisenhand", "type": "character", "status": "lebendig",
                "body": "Schmiedemeisterin mit Soeldnervergangenheit. Verkauft an beide Seiten.",
                "tags": []}],
    "politics": [{"name": "Rat der Essen", "type": "faction", "status": "aktiv",
                  "body": "Zunftrat der Schmieden. Stimmen werden in Erz gewogen.",
                  "tags": []}],
    "institutions": [{"name": "Stadtwache", "type": "faction", "status": "aktiv",
                      "body": "Unterbesetzt, ueberbestochen. Haelt die Tore, nicht das Recht.",
                      "tags": [], "imports": ["getreide"], "produces": []}],
}


def generate_stage(city_slug: str, stage: str, dry_run: bool = False) -> dict:
    city = read_world_entry(city_slug)
    if city is None:
        raise ValueError(f"Stadt '{city_slug}' existiert nicht im Wiki")
    city_meta, city_body = city
    region = city_meta.get("region", "")

    if dry_run:
        data = {"entries": DRY_RUN_SAMPLES[stage]}
    else:
        prompt = (f"Grimdark Low-Fantasy. Stadt: {city_meta['name']} (Region {region}).\n"
                  f"Beschreibung: {city_body.strip()}\n\n"
                  f"{STAGE_PROMPTS[stage]}\n\n{JSON_SCHEMA_HINT}")
        data = _extract_json(call_with_fallback(prompt))

    written, skipped = [], []
    for entry in data.get("entries", []):
        name = entry.get("name", "").strip()
        if not name:
            continue
        etype = entry.get("type") or STAGE_TYPES[stage]
        slug = canonical_slug(name, etype, city=city_meta["name"])
        # Dedup: exakter Slug oder Aehnlichkeitstreffer gleichen Typs
        if read_world_entry(slug) is not None:
            skipped.append(slug)
            continue
        similar = [s for s in wiki_index.find_similar_slugs(slug)
                   if wiki_index.get_entry_meta(s)["type"] == etype]
        if similar:
            skipped.append(f"{slug} (aehnlich: {','.join(similar)})")
            continue
        meta = {"type": etype, "name": name, "region": region,
                "links": [city_slug], "tags": entry.get("tags") or []}
        if entry.get("status"):
            meta["status"] = entry["status"]
        for k in ("produces", "imports"):
            if entry.get(k):
                meta[k] = entry[k]
        if etype == "location":
            meta["koordinaten"] = auto_coords(slug, region)
        write_world_entry(slug, meta, entry.get("body", ""))
        written.append(slug)

    # Backlinks: die Stadt verankert ihre neuen Eintraege (sonst Orphans)
    if written:
        from app.wiki_io import update_entry_meta
        links = sorted(set(city_meta.get("links") or []) | set(written))
        update_entry_meta(city_slug, {"links": links})

    return {"written": written, "skipped": skipped}


def generate_city(city_slug: str, dry_run: bool = False) -> None:
    log = read_json(LOG_PATH, {})
    city_log = log.setdefault(city_slug, {})
    for stage in STAGES:
        if city_log.get(stage) == "done":
            print(f"  {stage}: bereits erledigt (resume)")
            continue
        result = generate_stage(city_slug, stage, dry_run=dry_run)
        city_log[stage] = "done"
        atomic_write_json(LOG_PATH, log)
        print(f"  {stage}: {len(result['written'])} neu, {len(result['skipped'])} dedupliziert")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help="Stadt-Slug (z.B. hartfeld)")
    ap.add_argument("--all", action="store_true", help="Alle Staedte (tags: stadt)")
    ap.add_argument("--dry-run", action="store_true", help="Ohne LLM, mit Beispieldaten")
    args = ap.parse_args()

    if args.all:
        cities = [s for s, e in wiki_index.get_index(force=True)["entries"].items()
                  if "stadt" in (e.get("tags") or [])]
    elif args.city:
        cities = [slugify(args.city)]
    else:
        ap.error("--city oder --all angeben")

    for c in cities:
        print(f"Stadt: {c}")
        generate_city(c, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
