"""Gemeinsame Zug-Maschinerie: Prompt, History, Undo, Validator, Zugabschluss.

Hier liegt alles, was ein Spielzug braucht und was NICHT am Transport haengt.
Der FastAPI-Server (app/main.py) und die DM-CLI (scripts/dm_cli.py) benutzen
dasselbe Modul — eine zweite Kopie des Validators waere genau die Art von
Drift, gegen die dieses Projekt seit ADR-0001 baut.

Was hier NICHT hingehoert: HTTP, SSE, der Agent-Loop und der LLM-Adapter.
Wer den Erzaehler stellt, ist Sache des Aufrufers.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import gamestate as gsm
from . import rules, tools, wiki_context

HISTORY_ACTIVE_LIMIT = 400      # Eintraege in history.json bevor archiviert wird
HISTORY_ARCHIVE_CHUNK = 200     # so viele wandern dann ins Archiv
AUTO_ADVANCE_MINUTES = 10       # Zeit-Fallback, wenn advance_time im Zug fehlt


SYSTEM_PROMPT = """Du bist der Spielleiter (DM) eines duesteren Low-Fantasy-Solo-Rollenspiels
in der Welt Avarr (Ostimperium, Jahr 743 IC). Sprache: Deutsch. Ton: konkret,
koerperlich, politisch — nie wahllos grausam. Der Spieler steuert genau einen
Charakter (PC). Du steuerst Welt und NPCs. Es gibt keine Magie und keine
Goetter — nur Essenz (selten, teuer, besteuert).

MECHANIK (PFLICHT):
- JEDE Aktion mit unsicherem Ausgang laeuft ueber request_skill_roll
  (Skill aus der Skill-Liste + Difficulty Tier). Das Tool blockiert, bis der
  Spieler seinen W20 physisch wuerfelt; die Engine berechnet Ergebnis, Crits
  und Ticks. Du loest NIEMALS eine unsichere Aktion nur in Prosa auf —
  weder Ueberreden/Einschuechtern/Taeuschen gegen einen NPC mit eigenem
  Willen, noch Schleichen, Stehlen, Angriff, Wahrnehmung o.ae. Steht der
  Ausgang schon durch eine gerade gewuerfelte Probe fest, erzaehle ihn und
  fordere KEINE zweite Probe fuer dieselbe Handlung.
- Mechanik-Werte gehoeren NICHT in die Prosa: nenne nie Ticks, XP,
  Skillpunkte, Level-Ups, HP-Zahlen oder den VW. Die Engine fuehrt sie,
  das Zustandspanel zeigt sie. Sag hoechstens "du wirst sicherer darin",
  nie "du hast jetzt 1/3 Ticks".
- Geld: Preise darf ein NPC frei nennen. Aber sobald Muenzen tatsaechlich
  die Hand wechseln, IMMER pay/receive_coins aufrufen — und fuehre keine
  eigene Buchhaltung in der Prosa (keine Ausgaben-Summen, kein Boersen-
  Stand im Text). Der Boersen-Stand im Panel ist die einzige Wahrheit.
- HP nur ueber adjust_hp, Zeit nur ueber advance_time/rest. Ein Validator
  prueft deine Erzaehlung gegen den Spielstand.
- Nach jeder erzaehlten Aktion advance_time aufrufen (Gespraech 5-15 min,
  Wege je Distanz, Einkauf 10-30 min).
- Kampf: start_combat legt die Gegner MIT Werten an (hp, angriffsbonus,
  schaden, distanz). Diese Werte gelten den ganzen Kampf — du nennst sie
  nie wieder. Dann: request_skill_roll mit 'ziel' fuer Angriffe des PC,
  npc_action fuer jeden Gegner (einmal pro Runde), request_defense_roll
  wenn der Spieler aktiv verteidigt. Die Runden schaltet die ENGINE
  selbst weiter — es gibt kein end_turn. Nahkaempfer muessen erst
  aufschliessen (distanz > 0 = noch nicht da). Im Kampf niemals roll_dice.
- Kampf-Ende und Gegnerbestand fuehrt ebenfalls die Engine: Sind alle
  Gegner kampfunfaehig, geflohen oder tot, beendet sie den Kampf von
  selbst und meldet 'kampf_beendet'. end_combat brauchst du nur fuer
  Abbruch ohne Sieger (Flucht des PC, Verhandlung, Uebergabe). Stoesst
  mitten im Kampf jemand dazu, ruf start_combat erneut auf — die neuen
  Gegner werden als Verstaerkung angehaengt. Fuehre nie zwei Gegner-
  Gruppen im Kopf: der Kampfzustand im Spielstand ist die vollstaendige
  Liste, und wer dort nicht steht, kaempft nicht mit.
- DER SPIELSTAND IST DIE WAHRHEIT, ausnahmslos. Weicht deine Erzaehlung
  von ihm ab, war DEINE ERZAEHLUNG falsch — nie der Spielstand. Tool-
  Ergebnisse und das Zustandspanel korrigierst du nicht "zurecht":
  adjust_hp ist fuer Schaden und Heilung in der Welt, niemals um eine
  Erzaehlung nachtraeglich passend zu machen. Einen "Fehler im System"
  gibt es fuer dich nicht.
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
- EIGENNAMEN: Jeder Name, den du nennst, steht im Kontext oder im
  Namensregister. Amt, Rolle und Zugehoerigkeit einer Figur stehen dort
  ebenfalls — uebernimm sie woertlich, statt sie neu zu erfinden. Ein
  Stadtwache-Hauptmann bleibt Stadtwache-Hauptmann. Brauchst du eine
  Figur, die nirgends steht, leg sie erst mit add_wiki_entry an.
- Bewegt sich der Spieler weiter (Treppe, Tunnel, Nebenraum, anderes
  Gebaeude), gehoert zu JEDEM Abschnitt ein set_location — auch wenn du
  den Ort gerade selbst erfindest ('body' mitgeben legt ihn an). Sonst
  liefert dir der Kontext im naechsten Zug weiter die alte Szene.
- Antworte knapp: 2-6 Absaetze, dann Handlungsfreiheit lassen (keine
  Optionslisten).

EINGABE-MODI (Prefix der Spieler-Nachricht):
- [SPRECHEN]: sozialer Zug — Dialog im Fokus, Proben nur bei Druck/Luege.
- [DM-FRAGE]: Regie-Frage an dich. Antworte direkt aus dem Spielstand,
  ohne Erzaehltext, ohne Zeitfortschritt, ohne Tools ausser Nachschlagen.
- [KORREKTUR]: Der Spieler korrigiert einen Fehler deiner letzten
  Erzaehlung. Eine Korrektur, die nur den Text aendert, ist WERTLOS —
  ziehe den Spielstand nach: falscher Ort -> set_location, falsche HP ->
  adjust_hp, Gegner raus -> set_enemy_status, Kampf beenden ->
  end_combat. Bestaetige kurz, kein Zeitfortschritt.
- Ohne Prefix: normales Handeln."""


def build_system_prompt() -> str:
    """DM-Verhalten + Regelwerk. DM.md im Projektroot ist die kanonische
    Regelquelle; fehlt sie, gilt nur der eingebaute Prompt."""
    dm_path = gsm.BASE_DIR / "DM.md"
    if dm_path.exists():
        return SYSTEM_PROMPT + "\n\n# REGELWERK\n\n" + dm_path.read_text(encoding="utf-8")
    return SYSTEM_PROMPT


# --- History (bounded persistence) ---------------------------------

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


# --- Lint & Validator ----------------------------------------------

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


HP_RE = re.compile(r"\b(\d+)\s*(?:LP|HP|Lebenspunkte)\b")
# Geld, das die Hand wechselt: Zahlwort/Ziffer + Muenze in Naehe eines
# Transaktionsverbs (zahlen/geben/kosten dich...). Reine Preisnennung eines
# NPC ist erlaubt; nur echte Ausgaben brauchen ein Tool.
_ZAHL = r"(?:\d+|ein(?:en|e)?|zwei|drei|vier|fuenf|fünf|sechs|sieben|acht|neun|zehn|elf|zwoelf|zwölf)"
_MUENZE = r"(?:kp|sm|gm|kupfer\w*|silber\w*|gold\w*)"
COIN_TX_RE = re.compile(
    rf"(?:zahl\w*|bezahl\w*|gibst|gabst|gib|gab|entrichte\w*|kostet\s+dich|abgezogen|aus\s+der\s+Börse)"
    rf".{{0,30}}?{_ZAHL}\s*{_MUENZE}|{_ZAHL}\s*{_MUENZE}.{{0,20}}?(?:bezahlt|gezahlt|hingelegt|übergeben)",
    re.IGNORECASE)
# Mechanik-Zahlen, die nur die Engine kennt (nie erzaehlen):
MECH_RE = re.compile(r"\b(ticks?|erfahrungspunkte?|\bXP\b|skill[- ]?up|skillpunkte?|"
                     r"level[- ]?up|steigst?\s+auf\s+stufe|verteidigungswert|\bVW\b)\b", re.IGNORECASE)
# Kampf-Ausgang in der Prosa, obwohl nie start_combat/request_skill_roll lief:
# starkes Rule-Bypass-Signal (ADR-0001s historischer Hauptbug — der Erzaehler
# loest eine unsichere Handlung in Prosa auf statt ueber die Engine). Bewusst
# eng gehalten auf eindeutige Treffer/Verfehlt/Tod-Sprache gegen Fehlalarme —
# erkennt nicht jeden Bypass (Ueberreden/Schleichen sind zu variantenreich
# fuer ein zuverlaessiges Regex), aber den offensichtlichsten Fall.
COMBAT_OUTCOME_RE = re.compile(
    r"\b(triffst|trifft|verfehlst|verfehlt|besiegst|besiegt|"
    r"t(?:ö|oe)test|t(?:ö|oe)tet|erschl(?:ä|ae)gst|erschl(?:ä|ae)gt|"
    r"schl(?:ä|ae)gst?\s+\w+\s+nieder|f(?:ä|ae)llt\s+tot|f(?:ä|ae)llt\s+zu\s+Boden|"
    r"sticht\s+(?:dich|zu)|verwundet\s+(?:dich|ihn|sie)|greift\s+dich\s+an|"
    r"bohrt\s+sich|geht\s+zu\s+Boden|st(?:ü|ue)rzt\s+(?:zu\s+Boden|nieder))\b",
    re.IGNORECASE)
# Tools, die "Zeit vergeht" bereits ueber ihre eigene Kampf-Rundenlogik
# abdecken — advance_time waere hier fachlich falsch (Runden sind Sekunden).
COMBAT_TOOLS = {"start_combat", "npc_action", "set_enemy_status", "end_combat",
                "request_defense_roll"}
# Tools, die den Spielstand tatsaechlich veraendern. Eine [KORREKTUR], die
# keines davon aufruft, hat nur den Text geaendert und den Zustand nicht —
# genau die Kette, die im Playtest den Spielstand hat auseinanderlaufen lassen.
STATE_CHANGING_TOOLS = {
    "pay", "receive_coins", "adjust_hp", "advance_time", "rest", "set_world_flag",
    "manage_inventory", "set_injury", "status_effect", "set_location",
    "npc_present", "manage_quest", "pin_entry", "add_wiki_entry",
    "update_wiki_entry", "promote_entry", "start_combat", "npc_action",
    "set_enemy_status", "end_combat", "request_skill_roll", "request_defense_roll",
}


def _needs_time_tool(tool_names: list[str], gs: dict) -> bool:
    """True wenn dieser Zug ausserhalb des Kampfs eine Zeit-Handlung braucht
    (advance_time/rest/request_skill_roll), aber keine bekam."""
    if gs.get("combat") or COMBAT_TOOLS & set(tool_names):
        return False
    return not ({"advance_time", "rest", "request_skill_roll"} & set(tool_names))


def validate_narration(text: str, tool_names: list[str], gs: dict,
                       mode: str = "handeln", gate: dict | None = None) -> list[str]:
    """Regelbasierter Narrator-Validator (ADR-0001): prueft die Erzaehlung
    gegen Gamestate und Tool-Calls, ohne LLM."""
    problems = []
    if mode == "korrektur":
        if not STATE_CHANGING_TOOLS & set(tool_names):
            problems.append("Korrektur hat nur den Text geaendert, nicht den Spielstand — "
                            "zieh ihn nach (set_location/adjust_hp/set_enemy_status/end_combat)")
        return problems
    if gate and gate.get("ortswechsel") and "set_location" not in tool_names:
        problems.append("Der Spieler wechselt den Ort, aber set_location fehlt — "
                        "der Kontext bleibt sonst auf der alten Szene stehen")
    if gs.get("combat") and "roll_dice" in tool_names:
        problems.append("roll_dice im Kampf benutzt — Kampfwuerfe gehoeren in "
                        "request_skill_roll/npc_action/request_defense_roll")
    if COIN_TX_RE.search(text) and not {"pay", "receive_coins"} & set(tool_names):
        problems.append("Geld wechselt in der Erzaehlung die Hand, aber kein pay/receive_coins aufgerufen")
    if MECH_RE.search(text):
        problems.append("Mechanik-Werte (Ticks/XP/Level/VW) erzaehlt — die gehoeren in den Spielstand, nicht in die Prosa")
    for m in HP_RE.finditer(text):
        val = int(m.group(1))
        if val not in (gs["hp"], gs["hp_max"]):
            problems.append(f"Erzaehlte HP ({val}) passen nicht zum Spielstand "
                            f"({gs['hp']}/{gs['hp_max']})")
            break
    if (COMBAT_OUTCOME_RE.search(text) and not gs.get("combat")
            and not {"request_skill_roll", "start_combat"} & set(tool_names)):
        problems.append("Erzaehlung beschreibt einen Kampf-Ausgang, aber kein request_skill_roll/"
                        "start_combat lief — moeglicher Regelverstoss (Rule Bypass)")
    if _needs_time_tool(tool_names, gs):
        problems.append("Kein Zeitfortschritt in diesem Zug (advance_time fehlt)")
    return problems


# --- Undo (Ringpuffer pro PC) --------------------------------------

UNDO_DEPTH = 10


def undo_dir(pc_slug: str) -> Path:
    return gsm.PC_DIR / pc_slug / "undo"


def snapshot_turn(pc_slug: str, label: str) -> None:
    """Schnappschuss von Gamestate + History vor einem Zug. Wiki-Eintraege
    bleiben bewusst aussen vor: sie sind World-Scope und ueberdauern den
    Charakter (ADR-0002)."""
    gs = gsm.load_pc(pc_slug)
    if gs is None:
        return
    d = undo_dir(pc_slug)
    d.mkdir(parents=True, exist_ok=True)
    snap = {"ts": gsm.now_iso(), "label": label[:120],
            "gamestate": gs, "history": load_history(pc_slug)}
    gsm.atomic_write_json(d / f"{gsm.now_iso().replace(':', '-')}-{os.urandom(3).hex()}.json", snap)
    alte = sorted(d.glob("*.json"))
    for p in alte[:-UNDO_DEPTH]:
        p.unlink(missing_ok=True)


def list_snapshots(pc_slug: str) -> list[Path]:
    d = undo_dir(pc_slug)
    return sorted(d.glob("*.json")) if d.exists() else []


def restore_last_snapshot(pc_slug: str) -> dict | None:
    """Letzten Schnappschuss zurueckspielen und verbrauchen."""
    snaps = list_snapshots(pc_slug)
    if not snaps:
        return None
    snap = gsm.read_json(snaps[-1])
    if not snap:
        snaps[-1].unlink(missing_ok=True)
        return None
    gsm.atomic_write_json(gsm.pc_path(pc_slug), snap["gamestate"])
    gsm.atomic_write_json(history_path(pc_slug), snap["history"])
    snaps[-1].unlink(missing_ok=True)
    # Eine offene Blocking-Tool-Continuation gehoert dem Aufrufer (beim Server
    # der In-Memory-Queue) — der raeumt sie nach diesem Aufruf selbst weg.
    return {"label": snap.get("label", ""), "ts": snap.get("ts", ""),
            "verbleibend": len(snaps) - 1}


# --- Zugabschluss ---------------------------------------------------------

def finalize_turn(pc_slug: str, gs: dict, history: list[dict], mode: str,
                  turn_text: str, turn_tools: list[str]) -> dict:
    """Alles, was am Ende JEDES Spielzugs passieren muss — unabhaengig davon,
    ob der Erzaehler ein API-Modell war oder Claude Code ueber die CLI.

    Reihenfolge ist bedeutsam: erst die Kampfrunde schliessen (sie kann den
    Kampf beenden), dann die Zeit nachziehen (im Kampf waere sie falsch),
    dann speichern.
    """
    bericht: dict = {"auto_zeit": 0, "kampf_ende": None, "synopse_faellig": False}

    # Eine Spieler-Nachricht = eine Kampfrunde. Die Engine schliesst sie in
    # jedem Fall — auch wenn Gegneraktionen fehlen oder der letzte Gegner
    # gefallen ist (ADR-0003, Nachtrag).
    bericht["kampf_ende"] = tools.close_combat_round(gs)

    if mode in ("handeln", "sprechen"):
        # Zeit-Enforcement statt nur Meldung: die Engine kennt den fehlenden
        # Tool-Call deterministisch, also holt sie ihn selbst nach.
        if turn_text.strip() and _needs_time_tool(turn_tools, gs):
            tools.advance_time(gs, {"minuten": AUTO_ADVANCE_MINUTES})
            turn_tools.append("advance_time")
            bericht["auto_zeit"] = AUTO_ADVANCE_MINUTES
        gs["turn_count"] = gs.get("turn_count", 0) + 1
        every = rules.RULEBOOK.get("synopsis_every_n_turns", 0)
        bericht["synopse_faellig"] = bool(every) and gs["turn_count"] % every == 0

    gsm.save_pc(gs)
    save_history(pc_slug, history)
    bericht["zeit"] = gsm.format_kalender(gs["kalender"])
    return bericht


def state_panel(gs: dict) -> str:
    """Das Zustandspanel als Text — im Web rendert es das Frontend, in der
    CLI muss es mitkommen, sonst faellt der Erzaehler auf sein Gedaechtnis
    zurueck. Mechanik-Zahlen gehoeren hierhin und nie in die Prosa."""
    return wiki_context.gamestate_summary(gs)

