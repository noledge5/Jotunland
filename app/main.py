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

from . import gamestate as gsm
from . import llm_adapter, tools, wiki_context, wiki_index
from .wiki_io import append_pc_journal, read_journal_tail

app = FastAPI(title="NovaTerrum")

STATIC_DIR = Path(__file__).parent / "static"

MAX_CONTINUATIONS = 12          # Tool-Runden pro User-Nachricht
HISTORY_ACTIVE_LIMIT = 400      # Eintraege in history.json bevor archiviert wird
HISTORY_ARCHIVE_CHUNK = 200     # so viele wandern dann ins Archiv

# Blocking-Tool-Queue: pro PC eine ausstehende Continuation (Spieler-Wurf).
# In-Memory reicht fuer Single-Player; bei Neustart verfaellt nur der eine Wurf.
_pending_responses: dict[str, dict] = {}


SYSTEM_PROMPT = """Du bist der Spielleiter (DM) eines duesteren Low-Fantasy-Solo-Rollenspiels
in der Welt Avarr (Ostimperium, Jahr 743 IC). Sprache: Deutsch. Ton: konkret,
koerperlich, politisch — nie wahllos grausam. Der Spieler steuert genau einen
Charakter (PC). Du steuerst Welt und NPCs. Es gibt keine Magie und keine
Goetter — nur Essenz (selten, teuer, besteuert).

MECHANIK (PFLICHT):
- JEDE Aktion mit unsicherem Ausgang laeuft ueber request_skill_roll
  (Skill aus der Skill-Liste + Difficulty Tier). Das Tool blockiert, bis der
  Spieler seinen W20 physisch wuerfelt; die Engine berechnet Ergebnis, Crits
  und Ticks. Du loest NIEMALS eine unsichere Aktion nur in Prosa auf.
- Erfinde keine Zahlen: Muenzen nur ueber pay/receive_coins, HP nur ueber
  adjust_hp, Zeit nur ueber advance_time/rest. Ein Validator prueft deine
  Erzaehlung gegen den Spielstand.
- Nach jeder erzaehlten Aktion advance_time aufrufen (Gespraech 5-15 min,
  Wege je Distanz, Einkauf 10-30 min).
- Kampf: start_combat -> pc_turn (request_skill_roll mit ziel+schaden) ->
  end_turn -> npc_turn (npc_action: Engine wuerfelt gegen den VW des PC) ->
  end_turn -> naechste Runde. Sterbende bluten. end_combat beendet.
- NPC-Wissen: Ein NPC weiss nur, was er wissen kann. Kein NPC kennt den
  Namen des PC vor einer Vorstellung.

WELT (Zwei Schichten):
- Neue Orte, wichtige Personen, Fraktionen, Flora/Fauna: erst
  add_wiki_entry (Weltkanon), dann erzaehlen. Situative Klein-NPCs mit
  scope=charakter. Bei Stadt-Institutionen 'stadt' setzen.
- Aenderungen an BESTEHENDEN Welt-Eintraegen (zerstoert, Besitzer tot,
  Ruf verspielt) IMMER ueber set_world_flag — nie update_wiki_entry im Spiel.
- Ortswechsel ueber set_location, wichtige Wendungen ins Journal.

SZENEN-KONTINUITAET:
- Bleibe in der aktuellen Szene bis der Spieler sie verlaesst. Keine
  Zeitspruenge ohne advance_time, keine Figuren aus dem Nichts, kein
  Umdeuten etablierter Fakten. Wiki und Journal sind kanonisch.
- Antworte knapp: 2-6 Absaetze, dann Handlungsfreiheit lassen (keine
  Optionslisten).

EINGABE-MODI (Prefix der Spieler-Nachricht):
- [SPRECHEN]: sozialer Zug — Dialog im Fokus, Proben nur bei Druck/Luege.
- [DM-FRAGE]: Regie-Frage an dich. Antworte direkt aus dem Spielstand,
  ohne Erzaehltext, ohne Zeitfortschritt, ohne Tools ausser Nachschlagen.
- [KORREKTUR]: Der Spieler korrigiert einen Fehler deiner letzten
  Erzaehlung. Uebernimm die Korrektur (noetigenfalls set_world_flag/
  adjust-Tools), bestaetige kurz, kein Zeitfortschritt.
- Ohne Prefix: normales Handeln."""


def build_system_prompt() -> str:
    """DM-Verhalten + Regelwerk. DM.md im Projektroot ist die kanonische
    Regelquelle; fehlt sie, gilt nur der eingebaute Prompt."""
    dm_path = gsm.BASE_DIR / "DM.md"
    if dm_path.exists():
        return SYSTEM_PROMPT + "\n\n# REGELWERK\n\n" + dm_path.read_text(encoding="utf-8")
    return SYSTEM_PROMPT


# --- History (bounded persistence) --------------------------------------

def history_path(pc_slug: str) -> Path:
    return gsm.PC_DIR / pc_slug / "history.json"


def archive_path(pc_slug: str) -> Path:
    return gsm.PC_DIR / pc_slug / "history_archive.jsonl"


def load_history(pc_slug: str) -> list[dict]:
    return gsm.read_json(history_path(pc_slug), [])


def save_history(pc_slug: str, history: list[dict]) -> None:
    """Persistenz mit Deckel: aeltere Eintraege wandern ins JSONL-Archiv
    statt history.json unbegrenzt wachsen zu lassen (alter Deferred-Bug)."""
    if len(history) > HISTORY_ACTIVE_LIMIT:
        to_archive = history[:HISTORY_ARCHIVE_CHUNK]
        history = history[HISTORY_ARCHIVE_CHUNK:]
        ap = archive_path(pc_slug)
        ap.parent.mkdir(parents=True, exist_ok=True)
        with open(ap, "a", encoding="utf-8") as f:
            for m in to_archive:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
    gsm.atomic_write_json(history_path(pc_slug), history)


def llm_window(history: list[dict], window: int) -> list[dict]:
    """Rolling Window fuer den LLM-Input. Schneidet nie ein
    tool-Result von seinem tool_call ab."""
    tail = history[-window:]
    while tail and tail[0]["role"] == "tool":
        tail = tail[1:]
    return tail


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
    awaiting = None
    if pc and pc.get("combat") and pc["combat"].get("pending_roll"):
        awaiting = pc["combat"]["pending_roll"]
    return {"settings": settings, "pc": pc, "awaiting_roll": awaiting,
            "providers": llm_adapter.available_providers()}


@app.get("/api/settings")
def get_settings():
    return gsm.load_settings()


@app.post("/api/settings")
def post_settings(s: SettingsIn):
    return gsm.save_settings({k: v for k, v in s.model_dump().items() if v is not None})


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
    body: str | None = None


class WikiCreateIn(BaseModel):
    type: str
    name: str
    body: str
    slug: str | None = None
    region: str | None = None
    stadt: str | None = None
    parent: str | None = None
    status: str | None = None
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
    if "links" in data:
        idx = wiki_index.get_index()["entries"]
        dead = [l for l in data["links"] if l not in idx and l != slug]
        if dead:
            raise HTTPException(400, f"Links auf fehlende Eintraege: {', '.join(dead)}")
    meta.update(data)
    meta["aktualisiert"] = gsm.now_iso()
    write_world_entry(slug, meta, new_body)
    return {"meta": meta, "body": new_body}


@app.post("/api/wiki")
def post_wiki(body: WikiCreateIn):
    result = tools.add_wiki_entry({}, body.model_dump(exclude_none=True))
    if result.startswith(("FEHLER", "WARNUNG")):
        raise HTTPException(400, result)
    return json.loads(result)


@app.get("/api/graph")
def get_graph():
    idx = wiki_index.get_index(force=True)["entries"]
    active = gsm.load_settings()["active_pc_slug"]
    # Fremde Character-Scope-Eintraege bleiben unsichtbar (ADR-0002)
    visible = {s: e for s, e in idx.items()
               if e.get("scope", "welt") == "welt" or e.get("pc") == active}
    nodes = [{"slug": e["slug"], "name": e["name"], "type": e["type"],
              "status": e.get("status"), "scope": e.get("scope", "welt"),
              "koordinaten": e.get("koordinaten"), "tags": e.get("tags") or []}
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


@app.get("/api/journal")
def get_journal():
    settings = gsm.load_settings()
    if not settings["active_pc_slug"]:
        return {"journal": ""}
    return {"journal": read_journal_tail(settings["active_pc_slug"], max_entries=20)}


# --- Agent-Loop ---------------------------------------------------------

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _quick_lint(user_message: str) -> list[str]:
    """Wiki-Lint-Fallback nach jedem Zug — nicht bei Regie-Nachrichten."""
    if user_message.startswith(("[META]", "[DM-FRAGE]", "[KORREKTUR]")):
        return []
    try:
        from scripts.wiki_lint import run_lint
        problems = run_lint()
        return [f"{p['check']}: {p['msg']}" for p in problems if p["level"] == "error"][:5]
    except Exception:
        return []


COIN_RE = re.compile(r"\b(\d+)\s*(kp|sm|gm|kupfer|silber|gold(?:mark)?)\b", re.IGNORECASE)
HP_RE = re.compile(r"\b(\d+)\s*(?:LP|HP|Lebenspunkte)\b")


def validate_narration(text: str, tool_names: list[str], gs: dict) -> list[str]:
    """Regelbasierter Narrator-Validator (ADR-0001): prueft die Erzaehlung
    gegen Gamestate und Tool-Calls, ohne LLM."""
    problems = []
    if COIN_RE.search(text) and not {"pay", "receive_coins"} & set(tool_names):
        problems.append("Muenzbetrag erzaehlt, aber kein pay/receive_coins aufgerufen")
    for m in HP_RE.finditer(text):
        val = int(m.group(1))
        if val not in (gs["hp"], gs["hp_max"]):
            problems.append(f"Erzaehlte HP ({val}) passen nicht zum Spielstand "
                            f"({gs['hp']}/{gs['hp_max']})")
            break
    if not {"advance_time", "rest", "request_skill_roll"} & set(tool_names):
        problems.append("Kein Zeitfortschritt in diesem Zug (advance_time fehlt)")
    return problems


async def _agent_stream(pc_slug: str, history: list[dict],
                        resume_tool_result: dict | None = None,
                        mode: str = "handeln"):
    """Der eigentliche Agent-Loop. Streamt SSE-Events, fuehrt Tools aus,
    macht Continuations bis das LLM fertig ist oder ein Blocking-Tool
    auf den Spieler wartet."""
    settings = gsm.load_settings()
    gs = gsm.load_pc(pc_slug)
    if gs is None:
        yield _sse({"type": "error", "error": f"PC '{pc_slug}' nicht gefunden"})
        return

    if resume_tool_result is not None:
        history.append({"role": "tool",
                        "tool_call_id": resume_tool_result["tool_call_id"],
                        "name": resume_tool_result["name"],
                        "content": resume_tool_result["content"]})

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
            for tc in tool_calls:
                result = tools.execute_tool(gs, tc["name"], tc["args"])
                if result == tools.BLOCKING:
                    _pending_responses[pc_slug] = {
                        "tool_call_id": tc["id"], "name": tc["name"]}
                    gsm.save_pc(gs)
                    save_history(pc_slug, history)
                    pending = ((gs.get("combat") or {}).get("pending_roll")
                               or gs.get("pending_roll"))
                    yield _sse({"type": "awaiting_roll", "pending": pending})
                    blocked = True
                    break
                yield _sse({"type": "tool", "name": tc["name"],
                            "result": result[:500]})
                history.append({"role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"], "content": result})
            if blocked:
                return
            gsm.save_pc(gs)
    except Exception as e:
        yield _sse({"type": "error", "error": str(e)})

    gsm.save_pc(gs)
    save_history(pc_slug, history)
    if mode in ("handeln", "sprechen") and turn_text.strip():
        problems = validate_narration(turn_text, turn_tools, gs)
        if problems:
            yield _sse({"type": "validator", "problems": problems})
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    lint = _quick_lint(last_user if isinstance(last_user, str) else "")
    if lint:
        yield _sse({"type": "lint", "problems": lint})
    yield _sse({"type": "gamestate", "pc": gsm.load_pc(pc_slug)})
    yield _sse({"type": "done"})


MODE_PREFIX = {"handeln": "", "sprechen": "[SPRECHEN] ",
               "dm": "[DM-FRAGE] ", "korrektur": "[KORREKTUR] "}


@app.post("/api/chat")
async def chat(body: ChatIn):
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug:
        raise HTTPException(400, "Kein aktiver PC. Erst /api/pcs anlegen.")
    if pc_slug in _pending_responses:
        raise HTTPException(409, "Es steht noch ein Wuerfelwurf aus (/api/roll).")
    if body.mode not in MODE_PREFIX:
        raise HTTPException(400, f"Unbekannter Modus '{body.mode}'.")
    history = load_history(pc_slug)
    history.append({"role": "user", "content": MODE_PREFIX[body.mode] + body.message})
    return StreamingResponse(_agent_stream(pc_slug, history, mode=body.mode),
                             media_type="text/event-stream")


@app.post("/api/roll")
async def roll(body: RollIn):
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug or pc_slug not in _pending_responses:
        raise HTTPException(409, "Kein ausstehender Wurf.")
    if not (1 <= body.wurf <= 20):
        raise HTTPException(400, "Wurf muss 1-20 sein (d20).")
    pending = _pending_responses.pop(pc_slug)
    gs = gsm.load_pc(pc_slug)
    try:
        outcome = tools.resolve_player_roll(gs, body.wurf)
    except ValueError as e:
        raise HTTPException(409, str(e))
    gsm.save_pc(gs)
    history = load_history(pc_slug)
    resume = {"tool_call_id": pending["tool_call_id"], "name": pending["name"],
              "content": json.dumps(outcome, ensure_ascii=False)}
    return StreamingResponse(_agent_stream(pc_slug, history, resume_tool_result=resume),
                             media_type="text/event-stream")


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
    text = None
    if llm_adapter.available_providers():
        try:
            chunks = []
            async for ev in llm_adapter.stream_with_tools(
                    settings["model"],
                    "Fasse den folgenden RPG-Sessionverlauf als knappes Chronik-Protokoll "
                    "zusammen (Deutsch, Stichpunkte, max 15 Zeilen). Nur Fakten.",
                    [{"role": "user", "content": raw}], []):
                if ev["type"] == "text":
                    chunks.append(ev["text"])
            text = "".join(chunks).strip()
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
