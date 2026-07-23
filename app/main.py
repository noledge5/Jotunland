"""NovaTerrum — FastAPI-Server: Agent-Loop, Routen, Blocking-Tool-Queue.

Start lokal:  python3 app/main.py   (Port 3111, oder PORT aus Env)
"""
from __future__ import annotations

import json
import os
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


SYSTEM_PROMPT = """Du bist der Spielleiter (DM) eines grimdark Low-Fantasy-Solo-Rollenspiels.
Sprache: Deutsch. Ton: duester, konkret, koerperlich — aber nie wahllos grausam.
Der Spieler steuert genau einen Charakter (PC). Du steuerst Welt und NPCs.

REGELN:
- Nutze IMMER die Tools fuer Spielmechanik: Muenzen (pay/receive_coins),
  HP (adjust_hp), XP (add_xp), Inventar, Orte (set_location), Kampf.
  Erfinde keine Zahlen im Text, die nicht durch ein Tool gelaufen sind.
- Neue Orte, Personen, Fraktionen: erst add_wiki_entry, dann erzaehlen.
  Bei Stadt-Institutionen den Parameter 'stadt' setzen.
- Kampf laeuft ueber die State-Machine: start_combat -> pc_turn
  (request_attack_roll blockiert bis der Spieler wuerfelt) -> end_turn ->
  npc_turn (npc_action) -> end_turn -> naechste Runde -> end_combat.
- Wichtige Wendungen ins Journal (append_journal).
- Der Spieler wuerfelt selbst nur seine Angriffe (d20). Alles andere
  wuerfelst du serverseitig mit roll_dice.

SZENEN-KONTINUITAET:
- Bleibe in der aktuellen Szene bis der Spieler sie verlaesst oder ein
  Tool (set_location) den Ort wechselt.
- Keine Zeitspruenge, keine neuen Figuren aus dem Nichts, kein Umdeuten
  etablierter Fakten. Was im Wiki oder Journal steht, ist kanonisch.
- Antworte knapp: 2-6 Absaetze, dann Handlungsoptionen offen lassen
  (keine Aufzaehlung von Optionen, der Spieler entscheidet frei).

META:
- Nachrichten, die mit [META] beginnen, sind Regie-Anweisungen des
  Spielers an dich — beantworte sie direkt, ohne Erzaehltext."""


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


class RollIn(BaseModel):
    wurf: int


class SettingsIn(BaseModel):
    model: str | None = None
    active_pc_slug: str | None = None
    history_window: int | None = None


class PCIn(BaseModel):
    name: str


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
        gs = gsm.create_pc(body.name)
    except ValueError as e:
        raise HTTPException(409, str(e))
    gsm.set_active_pc_slug(gs["slug"])
    return gs


@app.post("/api/pcs/{slug}/activate")
def activate_pc(slug: str):
    if gsm.load_pc(slug) is None:
        raise HTTPException(404, f"PC '{slug}' existiert nicht")
    return gsm.set_active_pc_slug(slug)


@app.get("/api/map")
def get_map():
    idx = wiki_index.get_index()["entries"]
    return [e for e in idx.values()
            if e["type"] in ("location", "region", "subregion") and e.get("koordinaten")]


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
    """Wiki-Lint-Fallback nach jedem Zug — aber nicht bei [META]-Regie."""
    if user_message.startswith("[META]"):
        return []
    try:
        from scripts.wiki_lint import run_lint
        problems = run_lint()
        return [f"{p['check']}: {p['msg']}" for p in problems if p["level"] == "error"][:5]
    except Exception:
        return []


async def _agent_stream(pc_slug: str, history: list[dict],
                        resume_tool_result: dict | None = None):
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

    try:
        for _round in range(MAX_CONTINUATIONS):
            system = SYSTEM_PROMPT + "\n\n" + wiki_context.build_context(gs)
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
                    yield _sse({"type": "awaiting_roll",
                                "pending": gs["combat"]["pending_roll"]})
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
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    lint = _quick_lint(last_user if isinstance(last_user, str) else "")
    if lint:
        yield _sse({"type": "lint", "problems": lint})
    yield _sse({"type": "gamestate", "pc": gsm.load_pc(pc_slug)})
    yield _sse({"type": "done"})


@app.post("/api/chat")
async def chat(body: ChatIn):
    settings = gsm.load_settings()
    pc_slug = settings["active_pc_slug"]
    if not pc_slug:
        raise HTTPException(400, "Kein aktiver PC. Erst /api/pcs anlegen.")
    if pc_slug in _pending_responses:
        raise HTTPException(409, "Es steht noch ein Wuerfelwurf aus (/api/roll).")
    history = load_history(pc_slug)
    history.append({"role": "user", "content": body.message})
    return StreamingResponse(_agent_stream(pc_slug, history),
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
    uvicorn.run("app.main:app", host="127.0.0.1",
                port=int(os.environ.get("PORT", 3111)), reload=False)
