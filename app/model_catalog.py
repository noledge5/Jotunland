"""Modell-Katalog: kuratierte Liste (config/models.json) plus optionaler
Live-Abgleich mit dem OpenRouter-Modellverzeichnis.

Der Katalog fuellt das Modell-Dropdown im Frontend vor. Es tauchen NUR
tool-faehige Modelle auf: die Engine ruft bei jeder unsicheren Aktion
request_skill_roll auf (ADR-0001) — ein Modell ohne Function-Calling wuerde
die Mechanik aushebeln.

Analog zu load_settings wird der Katalog immer frisch von Disk gelesen, damit
Aenderungen an models.json ohne Neustart greifen.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

CONFIG_DIR = Path(__file__).parent / "config"
CATALOG_PATH = CONFIG_DIR / "models.json"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_FETCH_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def load_catalog() -> dict:
    """Kuratierten Katalog frisch von Disk lesen."""
    with open(CATALOG_PATH, encoding="utf-8") as f:
        cat = json.load(f)
    cat.setdefault("default", "or/anthropic/claude-sonnet-5")
    cat.setdefault("models", [])
    return cat


def _is_free(pricing: dict) -> bool:
    """Ein Modell gilt als gratis, wenn Prompt- und Completion-Preis 0 sind."""
    def zero(v) -> bool:
        try:
            return float(v) == 0.0
        except (TypeError, ValueError):
            return False
    return zero(pricing.get("prompt")) and zero(pricing.get("completion"))


def _normalise_openrouter(raw: list[dict], only_tools: bool) -> list[dict]:
    """OpenRouter-Verzeichnis auf unser Katalog-Format bringen und filtern.

    Rueckgabe: [{id (mit or/-Prefix), label, tag, free, note}], gratis zuerst,
    dann alphabetisch. Getrennt gehalten von fetch_openrouter, damit ohne Netz
    testbar."""
    out: list[dict] = []
    for m in raw:
        mid = m.get("id") or ""
        if not mid:
            continue
        params = m.get("supported_parameters") or []
        if only_tools and "tools" not in params:
            continue
        free = _is_free(m.get("pricing") or {})
        out.append({
            "id": f"or/{mid}",
            "label": m.get("name") or mid,
            "tag": "gratis" if free else "bezahlt",
            "free": free,
            "note": "",
        })
    out.sort(key=lambda x: (not x["free"], x["label"].lower()))
    return out


async def fetch_openrouter(only_tools: bool = True) -> list[dict]:
    """Live-Verzeichnis von OpenRouter, gefiltert auf tool-faehige Modelle.

    Das Verzeichnis ist oeffentlich — kein API-Key noetig. Wirft bei Netz- oder
    HTTP-Fehlern (der Aufrufer faengt das ab und faellt auf den Katalog zurueck).
    """
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
        r = await client.get(OPENROUTER_MODELS_URL)
        r.raise_for_status()
        raw = r.json().get("data", [])
    return _normalise_openrouter(raw, only_tools)
