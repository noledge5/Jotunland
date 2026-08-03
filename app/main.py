"""NovaTerrum — FastAPI-Server: Agent-Loop, Routen, Blocking-Tool-Queue.

Start lokal:  python3 app/main.py   (Port 3111, oder PORT aus Env)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Direktstart (python3 app/main.py) ermoeglichen: Paketkontext herstellen
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import app  # noqa: F401
    __package__ = "app"

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import classifier
from . import gamestate as gsm
from . import llm_adapter, model_catalog, rules, tools, wiki_context, wiki_index
from .wiki_io import append_pc_journal, append_synopsis, read_journal_tail
from . import session
from .session import (  # noqa: F401  — Re-Export: Routen und Tests nutzen die alten Namen
    AUTO_ADVANCE_MINUTES, COMBAT_OUTCOME_RE, COMBAT_TOOLS, HISTORY_ACTIVE_LIMIT,
    HISTORY_ARCHIVE_CHUNK, STATE_CHANGING_TOOLS, SYSTEM_PROMPT, UNDO_DEPTH,
    _needs_time_tool, _quick_lint, archive_path, build_system_prompt,
    history_path, list_snapshots, llm_window, load_history, restore_last_snapshot,
    save_history, snapshot_turn, undo_dir, validate_narration)

app = FastAPI(title="NovaTerrum")

STATIC_DIR = Path(__file__).parent / "static"

MAX_CONTINUATIONS = 12          # Tool-Runden pro User-Nachricht

# Blocking-Tool-Queue: pro PC eine ausstehende Continuation (Spieler-Wurf).
# In-Memory-Cache fuers schnelle Popping; die Tool-Call-ID wird zusaetzlich
# in gs["pending_roll"]["tool_call_id"] gesichert (_stash_pending_call), denn
# der Auto-Deploy startet uvicorn per --reload bei jedem Commit neu — ohne
# den Disk-Fallback wuerde ein Neustart waehrend eines offenen Wurfs den Zug
# unaufloesbar machen: die UI zeigt (aus gamestate.json) weiter "wartet auf
# Wurf", aber /api/roll faende die zugehoerige Tool-Call-ID nirgends mehr.
_pending_responses: dict[str, dict] = {}


def _stash_pending_call(gs: dict, tool_call_id: str) -> None:
    """Haengt die Tool-Call-ID an den persistierten Pending-Roll, damit
    _resolve_pending_call sie nach einem Neustart von Disk wiederfindet."""
    pr = gsm.pending_roll(gs)
    if pr is not None:
        pr["tool_call_id"] = tool_call_id


def _resolve_pending_call(pc_slug: str, gs: dict | None) -> dict | None:
    """{tool_call_id, name} eines ausstehenden Wurfs. Bevorzugt den
    In-Memory-Cache; faellt auf die in gamestate.json gesicherte ID zurueck
    (Neustart-Fall). None heisst: wirklich kein Wurf offen."""
    cached = _pending_responses.get(pc_slug)
    if cached:
        return cached
    pr = gsm.pending_roll(gs) if gs else None
    if pr and pr.get("tool_call_id"):
        return {"tool_call_id": pr["tool_call_id"], "name": "request_skill_roll"}
    return None



# --- History (bounded persistence) --------------------------------------


# --- Modelle ------------------------------------------------------------

class ChatIn(BaseModel):
    message: str
    mode: str = "handeln"  # handeln | sprechen | dm | korrektur


class RollIn(BaseModel):
    wurf: int


class SettingsIn(BaseModel):
    model: str | None = None
    active_pc_slug: str | None = None
    history_window: int | None = None
    use_classifier: bool | None = None
    classifier_model: str | None = None
    map_bg: str | None = None


class PCIn(BaseModel):
    name: str
    klasse: str | None = None
    hintergrund: str = ""
    attribute: dict[str, int] | None = None
    skills: dict[str, int] | None = None


# --- Basis-Routen -------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
def get_state():
    settings = gsm.load_settings()
    pc = gsm.load_pc(settings["active_pc_slug"]) if settings["active_pc_slug"] else None
    awaiting = gsm.pending_roll(pc) if pc else None
    return {"settings": settings, "pc": pc, "awaiting_roll": awaiting,
            "providers": llm_adapter.available_providers()}


@app.get("/api/settings")
def get_settings():
    return gsm.load_settings()


@app.post("/api/settings")
def post_settings(s: SettingsIn):
    return gsm.save_settings({k: v for k, v in s.model_dump().items() if v is not None})


@app.get("/api/models")
def get_models():
    """Kuratierter Modell-Katalog fuers Dropdown (nur tool-faehige Modelle)."""
    return model_catalog.load_catalog()


@app.get("/api/models/openrouter")
async def get_models_openrouter(only_tools: bool = True):
    """Live-Verzeichnis von OpenRouter, gefiltert auf tool-faehige Modelle.
    Gegen die Rotation des Gratis-Bestands: liefert den aktuellen Stand."""
    try:
        models = await model_catalog.fetch_openrouter(only_tools=only_tools)
    except Exception as e:  # Netz/HTTP — Frontend faellt auf den Katalog zurueck
        raise HTTPException(status_code=502,
                            detail=f"OpenRouter-Verzeichnis nicht erreichbar: {e}")
    return {"models": models}


class ClassifierTestIn(BaseModel):
    model: str


@app.post("/api/models/test-classifier")
async def test_classifier_model(body: ClassifierTestIn):
    """Testet ein Classifier-Modell mit einem Dummy-Zug, BEVOR es gespeichert
    wird — Fehlkonfiguration (z.B. eine tote :free-ID oder ein Modell ohne
    zuverlaessiges JSON) faellt beim Einstellen auf, nicht mitten in der Szene."""
    try:
        # Bewusst eine echte Probe-Situation: eine Floskel wie "Ich schaue
        # mich um" faengt der Trivial-Skip ab, dann wuerde gar kein Modell
        # geprueft und der Test waere wertlos.
        result = await classifier.classify(
            {}, "Ich versuche den Waechter zu ueberreden, mich durchzulassen.",
            body.model)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/pcs")
def get_pcs():
    return gsm.list_pcs()


@app.post("/api/pcs")
def post_pc(body: PCIn):
    try:
        gs = gsm.create_pc(body.name, klasse=body.klasse,
                           hintergrund=body.hintergrund,
                           attribute=body.attribute, skills=body.skills)
    except ValueError as e:
        code = 409 if "existiert bereits" in str(e) else 400
        raise HTTPException(code, str(e))
    gsm.set_active_pc_slug(gs["slug"])
    return gs


@app.get("/api/rules")
def get_rules():
    from . import rules
    return {"attrs": list(rules.ATTRS), "skills": list(rules.SKILLS.values()),
            "classes": rules.CLASSES, "tiers": rules.TIERS,
            "attr_pool": rules.RULEBOOK["attr_start_pool"],
            "attr_min": rules.RULEBOOK["attr_start_min"],
            "attr_max": rules.RULEBOOK["attr_start_max"],
            "skill_pool": rules.RULEBOOK["skill_start_pool"],
            "skill_max": rules.RULEBOOK["skill_start_max"]}


@app.post("/api/pcs/{slug}/activate")
def activate_pc(slug: str):
    if gsm.load_pc(slug) is None:
        raise HTTPException(404, f"PC '{slug}' existiert nicht")
    return gsm.set_active_pc_slug(slug)


@app.get("/api/map")
def get_map():
    idx = wiki_index.get_index()["entries"]
    return [e for e in idx.values()
            if e["type"] in tools.COORD_TYPES and e.get("koordinaten")]


@app.get("/api/wiki")
def list_wiki(type: str | None = None):
    idx = wiki_index.get_index()["entries"]
    entries = list(idx.values())
    if type:
        entries = [e for e in entries if e["type"] == type]
    return sorted(entries, key=lambda e: (e["type"], e["slug"]))


@app.get("/api/wiki/{slug}")
def get_wiki(slug: str):
    from .wiki_io import read_world_entry
    entry = read_world_entry(slug)
    if entry is None:
        raise HTTPException(404, f"'{slug}' nicht gefunden")
    meta, body = entry
    return {"meta": meta, "body": body}


class WikiEditIn(BaseModel):
    name: str | None = None
    status: str | None = None
    region: str | None = None
    parent: str | None = None
    tags: list[str] | None = None
    links: list[str] | None = None
    koordinaten: list[int] | None = None
    gesperrt: bool | None = None
    bild: str | None = None
    body: str | None = None


class ScopeIn(BaseModel):
    scope: str  # "welt" (in Kanon uebernehmen) | "charakter" (an PC binden)


class WikiCreateIn(BaseModel):
    type: str
    name: str
    body: str
    slug: str | None = None
    region: str | None = None
    stadt: str | None = None
    parent: str | None = None
    status: str | None = None
    scope: str | None = None
    koordinaten: list[int] | None = None


@app.put("/api/wiki/{slug}")
def put_wiki(slug: str, patch: WikiEditIn):
    from .wiki_io import read_world_entry, write_world_entry
    entry = read_world_entry(slug)
    if entry is None:
        raise HTTPException(404, f"'{slug}' nicht gefunden")
    meta, body = entry
    data = patch.model_dump(exclude_none=True)
    new_body = data.pop("body", body)
    # Gesperrte Kanon-Orte: Koordinaten nur aenderbar, wenn im selben
    # Request entsperrt wird (Schutz gegen versehentliches Verschieben).
    if "koordinaten" in data and meta.get("gesperrt") and data.get("gesperrt") is not False:
        raise HTTPException(409, f"'{slug}' ist gesperrt — erst entsperren, dann verschieben.")
    if "links" in data:
        idx = wiki_index.get_index()["entries"]
        dead = [l for l in data["links"] if l not in idx and l != slug]
        if dead:
            raise HTTPException(400, f"Links auf fehlende Eintraege: {', '.join(dead)}")
    meta.update(data)
    meta["aktualisiert"] = gsm.now_iso()
    write_world_entry(slug, meta, new_body)
    return {"meta": meta, "body": new_body}


@app.post("/api/wiki/{slug}/scope")
def post_scope(slug: str, body: ScopeIn):
    """Scope-Workflow: charaktergebundene Eintraege in den Kanon
    uebernehmen (welt) oder Welt-Eintraege an den aktiven PC binden."""
    from .wiki_io import read_world_entry, update_entry_meta
    entry = read_world_entry(slug)
    if entry is None:
        raise HTTPException(404, f"'{slug}' nicht gefunden")
    meta = entry[0]
    if body.scope not in ("welt", "charakter"):
        raise HTTPException(400, "scope muss 'welt' oder 'charakter' sein.")
    if body.scope == "welt":
        update_entry_meta(slug, {"scope": "welt", "pc": None})
    else:
        if meta.get("gesperrt"):
            raise HTTPException(409, f"'{slug}' ist gesperrter Kanon — nicht an einen Charakter bindbar.")
        active = gsm.load_settings()["active_pc_slug"]
        if not active:
            raise HTTPException(400, "Kein aktiver PC zum Binden.")
        update_entry_meta(slug, {"scope": "charakter", "pc": active})
    return {"slug": slug, "scope": body.scope}


@app.post("/api/wiki")
def post_wiki(body: WikiCreateIn):
    # scope=charakter braucht einen aktiven PC zum Binden (Slug, kein Ort —
    # manuell angelegte Eintraege werden nicht automatisch verlinkt).
    ctx = {}
    active = gsm.load_settings()["active_pc_slug"]
    if body.scope == "charakter" and active:
        ctx = {"slug": active}
    result = tools.add_wiki_entry(ctx, body.model_dump(exclude_none=True))
    if result.startswith(("FEHLER", "WARNUNG")):
        raise HTTPException(400, result)
    return json.loads(result)


# --- Bilder: Import (base64) + Serving + Prompt-Generator ---------------

IMAGES_DIR = gsm.BASE_DIR / "data" / "images"
_DATA_URL_RE = re.compile(r"data:image/([\w.+-]+);base64,(.+)", re.DOTALL)


class UploadIn(BaseModel):
    data_url: str


@app.post("/api/upload")
def upload_image(body: UploadIn):
    """Bild als base64-Data-URL entgegennehmen (kein Multipart, keine
    Extra-Abhaengigkeit), unter data/images/ ablegen, Pfad zurueckgeben."""
    import base64
    import uuid
    m = _DATA_URL_RE.match(body.data_url.strip())
    if not m:
        raise HTTPException(400, "Kein Bild-Data-URL (data:image/...;base64,...)")
    ext = m.group(1).lower().split("+")[0].replace("jpeg", "jpg")
    if ext not in ("png", "jpg", "webp", "gif"):
        raise HTTPException(400, f"Format '{ext}' nicht unterstuetzt")
    try:
        data = base64.b64decode(m.group(2))
    except Exception:
        raise HTTPException(400, "base64 nicht dekodierbar")
    if len(data) > 15_000_000:
        raise HTTPException(400, "Bild zu gross (max 15 MB)")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    (IMAGES_DIR / fname).write_bytes(data)
    return {"path": f"/images/{fname}"}


@app.get("/images/{fname}")
def serve_image(fname: str):
    if "/" in fname or ".." in fname or not re.match(r"^[\w.-]+$", fname):
        raise HTTPException(400, "Ungueltiger Dateiname")
    p = IMAGES_DIR / fname
    if not p.exists():
        raise HTTPException(404, "Bild nicht gefunden")
    return FileResponse(p)


IMG_PROMPT_SYSTEM = """Du schreibst Bild-Prompts fuer ComfyUI/Krea in natuerlicher
Sprache (Englisch, weil Bildmodelle darauf besser reagieren). Aus einer
Ortsbeschreibung machst du EINEN lebendigen First-Person-Prompt: was eine
Person sieht, die dort steht — Architektur, Materialien, Licht, Wetter,
Stimmung, wichtige Objekte, Vorder- und Hintergrund. 60-90 Woerter,
Praesens, konkrete Nomen. Keine erfundenen Fakten, bleib bei der
Beschreibung. Schliesse mit Stil-Tags:
grimdark low-fantasy, painterly concept art, muted earthy palette,
volumetric light, highly detailed, no text.
Antworte NUR mit dem Prompt, ohne Vorrede."""


class PromptIn(BaseModel):
    slug: str | None = None


@app.post("/api/scene_prompt")
async def scene_prompt(body: PromptIn):
    """Natural-Language-Bild-Prompt fuer einen Ort (Default: aktuelle
    PC-Szene). Zum Kopieren in ComfyUI/Krea."""
    from .wiki_io import read_world_entry
    settings = gsm.load_settings()
    slug = body.slug
    pc = gsm.load_pc(settings["active_pc_slug"]) if settings["active_pc_slug"] else None
    if not slug and pc and pc.get("location"):
        slug = pc["location"]["slug"]
    if not slug:
        raise HTTPException(400, "Kein Ort angegeben und kein aktueller PC-Ort.")
    entry = read_world_entry(slug)
    if entry is None:
        raise HTTPException(404, f"'{slug}' nicht gefunden")
    meta, body_text = entry
    if not llm_adapter.available_providers():
        raise HTTPException(400, "Kein LLM-Key gesetzt.")
    canon = read_world_entry("canon")
    stil = f"Welt-Stil: {canon[1][:400]}" if canon else ""
    zeit = f"Tageszeit: {pc['kalender']['stunde']} Uhr." if pc and pc.get("kalender") else ""
    npcs = ""
    if pc and pc.get("location", {}).get("slug") == slug and pc.get("anwesende_npcs"):
        npcs = "Anwesend (als Figuren einbauen): " + ", ".join(pc["anwesende_npcs"])
    user = (f"Ort: {meta.get('name', slug)} ({meta.get('type', '')})\n"
            f"Beschreibung: {body_text.strip()}\n{zeit}\n{npcs}\n{stil}")
    try:
        prompt = (await llm_adapter.complete(settings["model"], IMG_PROMPT_SYSTEM, user,
                                             max_tokens=350)).strip()
    except Exception as e:
        raise HTTPException(502, f"Prompt-Erzeugung fehlgeschlagen: {str(e)[:120]}")
    return {"slug": slug, "name": meta.get("name", slug), "prompt": prompt}


@app.get("/api/graph")
def get_graph():
    idx = wiki_index.get_index(force=True)["entries"]
    active = gsm.load_settings()["active_pc_slug"]
    # Fremde Character-Scope-Eintraege bleiben unsichtbar (ADR-0002)
    visible = {s: e for s, e in idx.items()
               if e.get("scope", "welt") == "welt" or e.get("pc") == active}
    nodes = [{"slug": e["slug"], "name": e["name"], "type": e["type"],
              "status": e.get("status"), "scope": e.get("scope", "welt"),
              "gesperrt": e.get("gesperrt", False), "pc": e.get("pc"),
              "koordinaten": e.get("koordinaten"), "bild": e.get("bild"),
              "tags": e.get("tags") or []}
             for e in visible.values()]
    edges = set()
    for e in visible.values():
        for target in e["links"]:
            if target in visible and target != e["slug"]:
                edges.add(tuple(sorted((e["slug"], target))))
        for rel in (e.get("region"), e.get("parent")):
            if rel:
                rslug = gsm.slugify(rel)
                if rslug in visible and rslug != e["slug"]:
                    edges.add(tuple(sorted((e["slug"], rslug))))
    return {"nodes": nodes, "edges": sorted(edges)}


@app.get("/api/history")
def get_history(limit: int = 24):
    """Juengste Chat-Turns (User + Erzaehler) fuer die Wiederherstellung
    des Verlaufs nach einem Reload."""
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug:
        return {"messages": []}
    history = load_history(pc_slug)
    msgs = [{"role": m["role"], "content": m["content"]}
            for m in history
            if m["role"] in ("user", "assistant") and m.get("content", "").strip()]
    return {"messages": msgs[-limit:]}


@app.get("/api/journal")
def get_journal():
    settings = gsm.load_settings()
    if not settings["active_pc_slug"]:
        return {"journal": ""}
    return {"journal": read_journal_tail(settings["active_pc_slug"], max_entries=20)}


# --- Agent-Loop ---------------------------------------------------------

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"




SYNOPSIS_SYSTEM = """Du fasst den juengsten Abschnitt einer laufenden Solo-RPG-Session
in 4-8 knappen Saetzen zusammen (Deutsch, Prosa, wie eine kurze Kapitel-
Zusammenfassung). Nur Fakten aus dem Verlauf: wichtige Ereignisse,
Entscheidungen, neue NPCs/Orte, offene Faeden. Keine Mechanik-Zahlen
(keine Ticks/XP/HP/Gold-Betraege) — die gehoeren in den Spielstand, nicht
in die Synopse."""


async def _maybe_write_synopsis(pc_slug: str, history: list[dict], gs: dict) -> None:
    """Alle rulebook.synopsis_every_n_turns abgeschlossene Handeln/Sprechen-
    Zuege: kurze Zusammenfassung generieren und ins Synopsen-Log schreiben
    (siehe wiki_context.build_context). Best-effort — ein Fehler hier darf
    den eigentlichen Spielzug nie stoeren (Komfort-Feature, kein Spielzug)."""
    every = rules.RULEBOOK.get("synopsis_every_n_turns", 0)
    if not every or gs.get("turn_count", 0) % every != 0:
        return
    if not llm_adapter.available_providers():
        return
    turns = [m for m in history if m["role"] in ("user", "assistant") and m.get("content")]
    recent = turns[-every * 3:]  # grosszuegig: mehrere Nachrichten pro Zug
    if not recent:
        return
    raw = "\n\n".join(f"[{m['role']}] {m['content'][:500]}" for m in recent)
    try:
        settings = gsm.load_settings()
        text = (await llm_adapter.complete(settings["model"], SYNOPSIS_SYSTEM, raw,
                                           max_tokens=300)).strip()
        if text:
            append_synopsis(pc_slug, text)
    except Exception:
        pass


# --- Undo (Ringpuffer pro PC) -------------------------------------------


async def _agent_stream(pc_slug: str, history: list[dict],
                        resume_tool_result: dict | None = None,
                        mode: str = "handeln", gate: dict | None = None,
                        buffered: bool = False, _retry: bool = False):
    """Der eigentliche Agent-Loop. Streamt SSE-Events, fuehrt Tools aus,
    macht Continuations bis das LLM fertig ist oder ein Blocking-Tool
    auf den Spieler wartet.

    buffered=True haelt den Erzaehltext zurueck, bis der Validator ihn
    freigibt (ADR-0003) — damit ein regelwidriger Zug einmal wiederholt
    werden kann, bevor der Spieler ihn zu sehen bekommt."""
    settings = gsm.load_settings()
    gs = gsm.load_pc(pc_slug)
    if gs is None:
        yield _sse({"type": "error", "error": f"PC '{pc_slug}' nicht gefunden"})
        return

    def _gs_event():
        """Live-Snapshot fuer die Sidebar (HP-Status frisch berechnet)."""
        gs["hp_status"] = gsm.hp_status_tag(gs["hp"], gs["hp_max"])
        return _sse({"type": "gamestate", "pc": gs})

    if resume_tool_result is not None:
        history.append({"role": "tool",
                        "tool_call_id": resume_tool_result["tool_call_id"],
                        "name": resume_tool_result["name"],
                        "content": resume_tool_result["content"]})
        yield _gs_event()  # Wurf-Folgen (Tick/HP) sofort sichtbar, vor der Erzaehlung

    turn_text = ""
    turn_tools: list[str] = []
    try:
        for _round in range(MAX_CONTINUATIONS):
            system = build_system_prompt() + "\n\n" + wiki_context.build_context(gs)
            window = llm_window(history, settings["history_window"])
            assistant_text = ""
            tool_calls: list[dict] = []
            stop_reason = "end"

            async for ev in llm_adapter.stream_with_tools(
                    settings["model"], system, window, tools.TOOLS):
                if ev["type"] == "text":
                    assistant_text += ev["text"]
                    if not buffered:
                        yield _sse({"type": "text", "text": ev["text"]})
                elif ev["type"] == "tool_call":
                    tool_calls.append(ev)
                elif ev["type"] == "stop":
                    stop_reason = ev["reason"]

            turn_text += assistant_text
            turn_tools += [t["name"] for t in tool_calls]
            history.append({"role": "assistant", "content": assistant_text,
                            "tool_calls": [{"id": t["id"], "name": t["name"],
                                            "args": t["args"]} for t in tool_calls]})

            if stop_reason != "tool_use" or not tool_calls:
                break

            blocked = False
            for i, tc in enumerate(tool_calls):
                result = tools.execute_tool(gs, tc["name"], tc["args"])
                if result == tools.BLOCKING:
                    _pending_responses[pc_slug] = {
                        "tool_call_id": tc["id"], "name": tc["name"]}
                    _stash_pending_call(gs, tc["id"])
                    # Jeder tool_use braucht ein tool_result, sonst weist die
                    # LLM-API die Fortsetzung ab. Verbleibende (nach dem Blocker)
                    # Tool-Calls dieses Batches werden nicht ausgefuehrt — sie
                    # bekommen ein Skip-Result, damit die Paarung gueltig bleibt.
                    for skipped in tool_calls[i + 1:]:
                        history.append({"role": "tool", "tool_call_id": skipped["id"],
                                        "name": skipped["name"],
                                        "content": "FEHLER: nicht ausgefuehrt — zuerst wird "
                                                   "der Wurf aufgeloest. Nach dem Wurf bei "
                                                   "Bedarf erneut aufrufen."})
                    gsm.save_pc(gs)
                    save_history(pc_slug, history)
                    yield _sse({"type": "awaiting_roll", "pending": gsm.pending_roll(gs)})
                    blocked = True
                    break
                yield _sse({"type": "tool", "name": tc["name"],
                            "result": result[:500]})
                history.append({"role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"], "content": result})
                yield _gs_event()  # Sidebar direkt nach jedem Tool aktualisieren
            if blocked:
                return
            gsm.save_pc(gs)
    except Exception as e:
        yield _sse({"type": "error", "error": str(e)})

    # --- Retry: regelwidrigen Zug einmal wiederholen, BEVOR er sichtbar wird
    if buffered and not _retry and turn_text.strip():
        probleme = validate_narration(turn_text, turn_tools, gs, mode, gate)
        if probleme:
            hinweis = ("REGELVERSTOSS in deiner letzten Antwort — sie wurde "
                       "verworfen und wird NICHT angezeigt. Erzaehle den Zug neu "
                       "und rufe diesmal die fehlenden Tools auf:\n- "
                       + "\n- ".join(probleme))
            history.append({"role": "user", "content": f"[SYSTEM] {hinweis}"})
            async for ev in _agent_stream(pc_slug, history, mode=mode, gate=gate,
                                          buffered=True, _retry=True):
                yield ev
            return

    if buffered and turn_text.strip():
        yield _sse({"type": "text", "text": turn_text})

    # Kampfrunde schliessen, Zeit nachziehen, speichern — dieselbe Routine,
    # die auch die DM-CLI benutzt (app/session.finalize_turn).
    bericht = session.finalize_turn(pc_slug, gs, history, mode, turn_text, turn_tools)
    auto_advanced_minutes = bericht["auto_zeit"]

    if mode in ("handeln", "sprechen"):
        await _maybe_write_synopsis(pc_slug, history, gs)
    if turn_text.strip():
        if auto_advanced_minutes:
            yield _sse({"type": "hinweis",
                        "text": f"Zeit automatisch um {auto_advanced_minutes} Minuten "
                                f"vorgestellt (advance_time fehlte in der Erzaehlung)."})
        problems = validate_narration(turn_text, turn_tools, gs, mode, gate)
        if problems:
            yield _sse({"type": "validator", "problems": problems})
    # Wiki-Lint (voller Rescan) nur, wenn der DM diesen Zug ins Wiki geschrieben
    # hat — sonst waere es ein O(alle Dateien)-Scan pro Spielzug ohne Nutzen.
    if {"add_wiki_entry", "update_wiki_entry"} & set(turn_tools):
        last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        lint = _quick_lint(last_user if isinstance(last_user, str) else "")
        if lint:
            yield _sse({"type": "lint", "problems": lint})
    yield _sse({"type": "gamestate", "pc": gsm.load_pc(pc_slug)})
    yield _sse({"type": "done"})


MODE_PREFIX = {"handeln": "", "sprechen": "[SPRECHEN] ",
               "dm": "[DM-FRAGE] ", "korrektur": "[KORREKTUR] "}


_gate_counter = 0


async def _gate_stream(pc_slug: str, history: list[dict], gate: dict):
    """Engine-initiierte Probe (Classifier-Gate): setzt die Probe als
    synthetischen request_skill_roll-Call in die History, blockiert auf
    den Spielerwurf. Die Erzaehlung folgt erst nach /api/roll."""
    global _gate_counter
    gs = gsm.load_pc(pc_slug)
    res = tools.request_skill_roll(gs, {"skill": gate["skill"], "schwierigkeit": gate["tier"]})
    if res != tools.BLOCKING:  # Skill/Tier doch ungueltig -> ohne Gate erzaehlen
        async for ev in _agent_stream(pc_slug, history, mode="handeln"):
            yield ev
        return
    _gate_counter += 1
    call_id = f"gate_{_gate_counter}"
    history.append({"role": "assistant", "content": "",
                    "tool_calls": [{"id": call_id, "name": "request_skill_roll",
                                    "args": {"skill": gate["skill"], "schwierigkeit": gate["tier"]}}]})
    _pending_responses[pc_slug] = {"tool_call_id": call_id, "name": "request_skill_roll"}
    _stash_pending_call(gs, call_id)
    gsm.save_pc(gs)
    save_history(pc_slug, history)
    yield _sse({"type": "gate", "grund": gate.get("grund", ""),
                "skill": gate["skill"], "tier": gate["tier"]})
    yield _sse({"type": "awaiting_roll", "pending": gsm.pending_roll(gs)})


_classifier_state = {"fail_streak": 0}
CLASSIFIER_ESCALATE_AFTER = 3  # so viele Ausfaelle in Folge -> deutlicherer Hinweis


async def _turn_stream(pc_slug: str, history: list[dict], mode: str, user_message: str):
    """Ein Zug: erst das Proben-Gate (Classifier), dann die Erzaehlung.
    Classifier-Fehler (z.B. ungueltige Modell-ID) werden sichtbar gemeldet
    und der Erzaehler-Tool-Loop uebernimmt als Fallback."""
    settings = gsm.load_settings()
    gs = gsm.load_pc(pc_slug)
    gate = None
    if (settings.get("use_classifier") and mode in ("handeln", "sprechen")
            and gs and not gs.get("combat")):
        model = settings.get("classifier_model") or settings["model"]
        try:
            gate = await classifier.classify(gs, user_message, model)
            _classifier_state["fail_streak"] = 0
        except Exception as e:
            _classifier_state["fail_streak"] += 1
            streak = _classifier_state["fail_streak"]
            hint = (f"Proben-Gate uebersprungen — Classifier-Modell '{model}' "
                    f"nicht nutzbar ({str(e)[:80]}). Im Zahnrad die volle Modell-ID "
                    f"eintragen (z.B. or/anthropic/...) oder leer lassen.")
            if streak >= CLASSIFIER_ESCALATE_AFTER:
                hint += (f" Das ist der {streak}. Ausfall in Folge — im Zahnrad den "
                        f"'Testen'-Button neben dem Classifier-Modell nutzen.")
            yield _sse({"type": "hinweis", "text": hint})
        if gate and gate.get("braucht_probe"):
            async for ev in _gate_stream(pc_slug, history, gate):
                yield ev
            return
    # Gepuffert (mit Retry-Chance) nur dort, wo Zahlen zaehlen: im Kampf und
    # bei Angriffs-Aktionen. Sonst bleibt der Text live, damit sich Erkundung
    # und Gespraech weiter fluessig anfuehlen (ADR-0003).
    buffered = bool((gs and gs.get("combat")) or mode == "korrektur"
                    or (gate and gate.get("angriff")))
    async for ev in _agent_stream(pc_slug, history, mode=mode, gate=gate,
                                  buffered=buffered):
        yield ev


@app.post("/api/chat")
async def chat(body: ChatIn):
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug:
        raise HTTPException(400, "Kein aktiver PC. Erst /api/pcs anlegen.")
    if _resolve_pending_call(pc_slug, gsm.load_pc(pc_slug)):
        raise HTTPException(409, "Es steht noch ein Wuerfelwurf aus (/api/roll).")
    if body.mode not in MODE_PREFIX:
        raise HTTPException(400, f"Unbekannter Modus '{body.mode}'.")
    snapshot_turn(pc_slug, body.message)   # Undo-Punkt VOR dem Zug
    history = load_history(pc_slug)
    history.append({"role": "user", "content": MODE_PREFIX[body.mode] + body.message})
    return StreamingResponse(_turn_stream(pc_slug, history, body.mode, body.message),
                             media_type="text/event-stream")


@app.post("/api/roll")
async def roll(body: RollIn):
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug:
        raise HTTPException(409, "Kein ausstehender Wurf.")
    gs = gsm.load_pc(pc_slug)
    pending = _resolve_pending_call(pc_slug, gs)
    if not pending:
        raise HTTPException(409, "Kein ausstehender Wurf.")
    if not (1 <= body.wurf <= 20):
        raise HTTPException(400, "Wurf muss 1-20 sein (d20).")
    _pending_responses.pop(pc_slug, None)
    try:
        outcome = tools.resolve_player_roll(gs, body.wurf)
    except ValueError as e:
        raise HTTPException(409, str(e))
    gsm.save_pc(gs)
    history = load_history(pc_slug)
    resume = {"tool_call_id": pending["tool_call_id"], "name": pending["name"],
              "content": json.dumps(outcome, ensure_ascii=False)}
    # Die Auflösung gehoert zum Kampfzug — also gilt hier dieselbe Pufferung.
    return StreamingResponse(_agent_stream(pc_slug, history, resume_tool_result=resume,
                                           buffered=bool(gs.get("combat"))),
                             media_type="text/event-stream")


@app.get("/api/undo")
def get_undo():
    """Wieviele Zuege lassen sich zuruecknehmen (fuer den Button-Zustand)."""
    pc_slug = gsm.load_settings()["active_pc_slug"]
    if not pc_slug:
        return {"verfuegbar": 0, "letzter": ""}
    snaps = list_snapshots(pc_slug)
    letzter = ""
    if snaps:
        snap = gsm.read_json(snaps[-1]) or {}
        letzter = snap.get("label", "")
    return {"verfuegbar": len(snaps), "letzter": letzter}


@app.post("/api/undo")
def post_undo():
    """Letzten Zug zuruecknehmen: Gamestate und History werden auf den Stand
    VOR dem Zug zurueckgesetzt. Wiki-Eintraege bleiben bestehen (World-Scope,
    ADR-0002); Journal und Synopsen sind Append-Logs und bleiben ebenfalls."""
    pc_slug = gsm.load_settings()["active_pc_slug"]
    if not pc_slug:
        raise HTTPException(400, "Kein aktiver PC.")
    result = restore_last_snapshot(pc_slug)
    if result is None:
        raise HTTPException(409, "Kein Zug zum Zuruecknehmen vorhanden.")
    # Die Blocking-Queue gehoert dem Server, nicht dem Snapshot-Modul: ein
    # offener Wurf aus dem zurueckgenommenen Zug darf nicht wiederkommen.
    _pending_responses.pop(pc_slug, None)
    return {**result, "pc": gsm.load_pc(pc_slug)}


# --- Session-Protokoll --------------------------------------------------

@app.post("/api/protocol")
async def protocol():
    """Session-Protokoll: fasst die juengste History als Chronik-Eintrag
    ins Journal. Ohne LLM-Key: roher Auszug als Fallback."""
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug:
        raise HTTPException(400, "Kein aktiver PC.")
    history = load_history(pc_slug)
    turns = [m for m in history if m["role"] in ("user", "assistant") and m.get("content")]
    recent = turns[-30:]
    if not recent:
        return {"protokoll": "Keine Historie."}
    raw = "\n\n".join(f"[{m['role']}] {m['content'][:600]}" for m in recent)
    pc = gsm.load_pc(pc_slug)
    anker = f"Aktueller Boersen-Stand (Wahrheit): {gsm.format_coins(pc['coins'])}." if pc else ""
    text = None
    if llm_adapter.available_providers():
        try:
            text = (await llm_adapter.complete(
                settings["model"],
                "Fasse den folgenden RPG-Sessionverlauf als knappes Chronik-Protokoll "
                "zusammen (Deutsch, Stichpunkte, max 15 Zeilen). Nur Fakten aus dem "
                "Verlauf. Erfinde KEINE Zahlen — keine Ausgaben-Summen, keine XP/Ticks. "
                "Wenn du den Geldstand nennst, nutze exakt den angegebenen Anker.",
                f"{anker}\n\nVERLAUF:\n{raw}", max_tokens=600)).strip()
        except Exception:
            text = None
    if not text:
        text = "Protokoll (roh):\n" + raw[:3000]
    append_pc_journal(pc_slug, "SESSION-PROTOKOLL\n\n" + text)
    return {"protokoll": text}


if __name__ == "__main__":
    import uvicorn
    # HOST=0.0.0.0 macht den Server im LAN erreichbar (z.B. fuers iPhone
    # ueber http://<rechner-lan-ip>:3111). Default bleibt lokal.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 3111))
    if host == "0.0.0.0":
        print(f"Server im LAN erreichbar auf Port {port} — "
              f"oeffne vom iPhone http://<lan-ip>:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
