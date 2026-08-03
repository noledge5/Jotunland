"""DM-CLI: die Engine ohne LLM-Adapter, fuer einen Erzaehler mit Shell-Zugriff.

Gedacht fuer Claude Code als Spielleiter. Der Unterschied zum Server ist NUR,
wer den Text schreibt — Regeln, Validator, Kampf-State-Machine, Wiki und
Spielstand sind dieselben Module (app/session.py, app/tools.py). Beide Wege
schreiben denselben Spielstand unter data/pcs/<slug>/, man kann also mitten
in einer Kampagne wechseln.

Ablauf eines Zugs:

    python3 -m scripts.dm_cli kontext                 # was der DM wissen muss
    python3 -m scripts.dm_cli call <tool> '<json>'    # so oft wie noetig
    python3 -m scripts.dm_cli wurf 14                 # W20 des Spielers
    python3 -m scripts.dm_cli zugende --text '...'    # Validator + Speichern

Ausgaben sind bewusst JSON, wo ein Programm sie liest, und Klartext, wo der
Erzaehler sie liest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gamestate as gsm  # noqa: E402
from app import session, tools, wiki_context  # noqa: E402
from app.wiki_io import append_pc_journal, append_synopsis  # noqa: E402


def _pc(slug: str | None) -> dict:
    slug = slug or gsm.load_settings().get("active_pc_slug")
    if not slug:
        raise SystemExit("FEHLER: Kein aktiver PC. 'dm_cli pcs' zeigt die "
                         "vorhandenen, --pc <slug> waehlt einen.")
    gs = gsm.load_pc(slug)
    if gs is None:
        raise SystemExit(f"FEHLER: PC '{slug}' hat keinen Spielstand.")
    return gs


def _json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# --- Befehle --------------------------------------------------------------

def cmd_pcs(args) -> None:
    aktiv = gsm.load_settings().get("active_pc_slug")
    for p in gsm.list_pcs():
        mark = " *aktiv*" if p["slug"] == aktiv else ""
        print(f"{p['slug']:<20} {p['name']} (Level {p.get('level', 1)}){mark}")


def cmd_charakter(args) -> None:
    """Schnellstart-Charakter. Der Wizard der Web-App verteilt 78 Attribut-
    und 80 Skillpunkte frei; hier entstehen Standardwerte, damit man ohne
    zweiten Weg ins Spiel kommt."""
    try:
        gs = gsm.create_pc(args.name, klasse=args.klasse)
    except ValueError as e:
        raise SystemExit(f"FEHLER: {e}")
    gsm.set_active_pc_slug(gs["slug"])
    print(f"{gs['name']} ({gs['klasse']}) angelegt und aktiv.\n")
    print(session.state_panel(gs))


def cmd_regeln(args) -> None:
    """Systemprompt + Regelwerk — einmal am Sessionanfang lesen."""
    print(session.build_system_prompt())


def cmd_kontext(args) -> None:
    """Die acht Kontext-Schichten fuer diesen Zug plus offener Wurf."""
    gs = _pc(args.pc)
    print(wiki_context.build_context(gs))
    pr = gsm.pending_roll(gs)
    if pr:
        print(f"\n## OFFENER WURF\nDer Spieler muss {pr['skill']} "
              f"({pr['tier']}) wuerfeln. Erst nach 'dm_cli wurf <W20>' geht es "
              f"weiter — erzaehle das Ergebnis nicht vorweg.")
    if args.verlauf:
        hist = session.load_history(gs["slug"])[-args.verlauf:]
        if hist:
            print("\n## Letzte Nachrichten")
            for m in hist:
                if m.get("role") in ("user", "assistant") and m.get("content"):
                    print(f"[{m['role']}] {str(m['content'])[:600]}")


def cmd_zustand(args) -> None:
    print(session.state_panel(_pc(args.pc)))


def cmd_tools(args) -> None:
    liste = tools.TOOLS
    if args.name:
        liste = [t for t in liste if t["name"] == args.name]
        if not liste:
            raise SystemExit(f"FEHLER: Kein Tool '{args.name}'.")
    if args.kurz:
        for t in liste:
            print(f"{t['name']}: {t['description'][:150]}")
    else:
        _json(liste)


def cmd_call(args) -> None:
    gs = _pc(args.pc)
    try:
        tool_args = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"FEHLER: args ist kein gueltiges JSON ({e}).")
    if not isinstance(tool_args, dict):
        raise SystemExit("FEHLER: args muss ein JSON-Objekt sein.")

    if not _turnlog(gs["slug"]).exists():
        # Undo-Punkt automatisch, wie im Server vor jedem Zug — sonst haengt
        # er an der Selbstdisziplin des Erzaehlers (ADR-0005-Schwachstelle).
        session.snapshot_turn(gs["slug"], f"CLI-Zug: {args.tool}")
    _zug_beginnt(gs)          # Fingerprint VOR dem ersten Tool des Zugs
    res = tools.execute_tool(gs, args.tool, tool_args)
    gsm.save_pc(gs)
    # Tool-Namen fuer den Validator mitschreiben, damit 'zugende' weiss, was in
    # diesem Zug tatsaechlich lief — sonst muesste der Erzaehler es selbst
    # melden, und genau das war die Luecke, die der Validator schliessen soll.
    # Auch bei BLOCKING: request_skill_roll ist eine Zeit-Handlung, faellt es
    # hier raus, stellt die Automatik die Uhr ein zweites Mal vor.
    if not res.startswith("FEHLER"):
        _merke_tool(gs["slug"], args.tool)
    if res == tools.BLOCKING:
        pr = gsm.pending_roll(gs) or {}
        print(f"WARTET AUF WURF: Der Spieler wuerfelt {pr.get('skill', '?')} "
              f"({pr.get('tier', '?')}). Frag ihn nach seinem W20 und melde ihn "
              f"mit 'dm_cli wurf <zahl>'. Bis dahin kein Ergebnis erzaehlen.")
        return
    print(res)


def cmd_wurf(args) -> None:
    gs = _pc(args.pc)
    if not gsm.pending_roll(gs):
        raise SystemExit("FEHLER: Es steht kein Wurf aus.")
    if not 1 <= args.wert <= 20:
        raise SystemExit("FEHLER: Ein W20 liegt zwischen 1 und 20.")
    out = tools.resolve_player_roll(gs, args.wert)
    gsm.save_pc(gs)
    _json(out)


def cmd_zugende(args) -> None:
    """Zug abschliessen: Kampfrunde schliessen, Zeit nachziehen, validieren,
    History und Spielstand speichern."""
    gs = _pc(args.pc)
    slug = gs["slug"]
    if gsm.pending_roll(gs):
        raise SystemExit("FEHLER: Es steht noch ein Wurf aus — erst 'dm_cli "
                         "wurf <zahl>', dann den Zug abschliessen.")
    history = session.load_history(slug)
    if args.spieler:
        history.append({"role": "user", "content": args.spieler})
    if args.text:
        history.append({"role": "assistant", "content": args.text})

    zug = _hole_zug(slug)
    turn_tools = zug.get("tools") or []
    bericht = session.finalize_turn(slug, gs, history, args.modus,
                                    args.text or "", turn_tools)
    bericht["tools"] = turn_tools
    if args.text:
        bericht["validator"] = session.validate_narration(
            args.text, turn_tools, gs, args.modus, vorher=zug.get("vorher"))
    _json(bericht)


def cmd_journal(args) -> None:
    append_pc_journal(_pc(args.pc)["slug"], args.text)
    print("Journal-Eintrag geschrieben.")


def cmd_synopse(args) -> None:
    append_synopsis(_pc(args.pc)["slug"], args.text)
    print("Synopse geschrieben.")


def cmd_schnappschuss(args) -> None:
    gs = _pc(args.pc)
    session.snapshot_turn(gs["slug"], args.label)
    print(f"Schnappschuss abgelegt ({len(session.list_snapshots(gs['slug']))} "
          f"von {session.UNDO_DEPTH} belegt).")


def cmd_undo(args) -> None:
    gs = _pc(args.pc)
    res = session.restore_last_snapshot(gs["slug"])
    if res is None:
        raise SystemExit("FEHLER: Kein Zug zum Zuruecknehmen vorhanden.")
    _json(res)


# --- Protokoll des laufenden Zugs -----------------------------------------
# Der Validator braucht zweierlei: die Tools DIESES Zugs und den Zustand VOR
# ihm. Im Server haelt der Agent-Loop beides im Speicher; in der CLI ist jeder
# Aufruf ein eigener Prozess, also muss es auf die Platte. Der Fingerprint
# wird beim ersten Tool des Zugs genommen — vor dessen Ausfuehrung.

def _turnlog(pc_slug: str) -> Path:
    return gsm.PC_DIR / pc_slug / "cli_turn.json"


def _zug_beginnt(gs: dict) -> None:
    """Legt den Rueckfall-Fingerprint an, falls dieser Zug noch keinen hat."""
    p = _turnlog(gs["slug"])
    if not p.exists():
        gsm.atomic_write_json(p, {"vorher": session.state_fingerprint(gs),
                                  "tools": []})


def _merke_tool(pc_slug: str, name: str) -> None:
    p = _turnlog(pc_slug)
    log = gsm.read_json(p, {"vorher": None, "tools": []})
    log.setdefault("tools", []).append(name)
    gsm.atomic_write_json(p, log)


def _hole_zug(pc_slug: str) -> dict:
    p = _turnlog(pc_slug)
    log = gsm.read_json(p, {"vorher": None, "tools": []})
    p.unlink(missing_ok=True)
    return log


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="dm_cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pc", help="PC-Slug (Default: aktiver PC aus den Settings)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pcs", help="Charaktere auflisten").set_defaults(fn=cmd_pcs)

    p = sub.add_parser("charakter", help="Schnellstart-Charakter anlegen")
    p.add_argument("name")
    p.add_argument("--klasse", default=None,
                   help="Krieger | Schurke | Haendler | Essenzkundiger | Waldlaeufer")
    p.set_defaults(fn=cmd_charakter)
    sub.add_parser("regeln", help="Systemprompt + DM.md ausgeben").set_defaults(fn=cmd_regeln)
    sub.add_parser("zustand", help="Zustandspanel des PC").set_defaults(fn=cmd_zustand)

    p = sub.add_parser("kontext", help="Kontext-Schichten fuer diesen Zug")
    p.add_argument("--verlauf", type=int, default=0, metavar="N",
                   help="zusaetzlich die letzten N History-Nachrichten")
    p.set_defaults(fn=cmd_kontext)

    p = sub.add_parser("tools", help="Tool-Schemata")
    p.add_argument("--name", help="nur dieses Tool")
    p.add_argument("--kurz", action="store_true", help="nur Name und Kurzbeschreibung")
    p.set_defaults(fn=cmd_tools)

    p = sub.add_parser("call", help="Tool ausfuehren")
    p.add_argument("tool")
    p.add_argument("args", nargs="?", default="{}", help="Argumente als JSON-Objekt")
    p.set_defaults(fn=cmd_call)

    p = sub.add_parser("wurf", help="W20 des Spielers aufloesen")
    p.add_argument("wert", type=int)
    p.set_defaults(fn=cmd_wurf)

    p = sub.add_parser("zugende", help="Zug abschliessen und validieren")
    p.add_argument("--text", default="", help="die Erzaehlung dieses Zugs")
    p.add_argument("--spieler", default="", help="die Eingabe des Spielers")
    p.add_argument("--modus", default="handeln",
                   choices=["handeln", "sprechen", "dm", "korrektur"])
    p.set_defaults(fn=cmd_zugende)

    p = sub.add_parser("journal", help="Wendung ins Journal schreiben")
    p.add_argument("text")
    p.set_defaults(fn=cmd_journal)

    p = sub.add_parser("synopse", help="Kapitel-Zusammenfassung ablegen")
    p.add_argument("text")
    p.set_defaults(fn=cmd_synopse)

    p = sub.add_parser("schnappschuss", help="Undo-Punkt vor dem Zug setzen")
    p.add_argument("label", nargs="?", default="")
    p.set_defaults(fn=cmd_schnappschuss)

    sub.add_parser("undo", help="letzten Zug zuruecknehmen").set_defaults(fn=cmd_undo)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
