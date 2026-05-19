"""
Lightweight turn tracer. Collects state-change events for the current turn
and exposes them via get_trace(). Also prints to stdout.
"""
import time
import json

_current_trace: list = []
_turn_id: int = 0


def new_turn(playthrough_id: int, player_input: str):
    global _current_trace, _turn_id
    _turn_id += 1
    _current_trace = []
    _log("TURN_START", {
        "turn_id": _turn_id,
        "playthrough_id": playthrough_id,
        "input": player_input[:120]
    })


def _log(event: str, data: dict):
    entry = {"t": round(time.time() * 1000), "event": event, **data}
    _current_trace.append(entry)
    # Pretty terminal output
    label = f"\033[36m[TRACE]\033[0m \033[1m{event}\033[0m"
    detail = "  " + "  ".join(f"\033[33m{k}\033[0m={v}" for k, v in data.items() if k != "t")
    print(f"{label}{detail if detail.strip() else ''}")


def log_llm_call(call_type: str, model: str, prompt_tokens_est: int = 0):
    _log("LLM_CALL", {"type": call_type, "model": model})


def log_llm_result(call_type: str, result: dict | str):
    if isinstance(result, dict):
        _log("LLM_RESULT", {"type": call_type, "result": json.dumps(result, ensure_ascii=False)[:200]})
    else:
        _log("LLM_RESULT", {"type": call_type, "result": str(result)[:200]})


def log_roll_requested(skill: str, sg: int, modifier: int, formula: str):
    _log("ROLL_REQUESTED", {"skill": skill, "SG": sg, "modifier": modifier, "formula": formula})


def log_roll_resolved(dice: int, modifier: int, total: int, sg: int, outcome: str):
    _log("ROLL_RESOLVED", {"dice": dice, "modifier": modifier, "total": total, "SG": sg, "outcome": outcome})


def log_db_write(table: str, op: str, fields: dict):
    short = {k: v for k, v in fields.items() if v is not None}
    _log("DB_WRITE", {"table": table, "op": op, **short})


def log_tick(skill: str, ticks: int, threshold: int, skill_up: bool, new_value: int):
    _log("TICK", {"skill": skill, "ticks": f"{ticks}/{threshold}", "skill_up": skill_up, "value": new_value})


def log_hp_change(entity: str, old_hp: int, new_hp: int, reason: str):
    delta = new_hp - old_hp
    sign = "+" if delta >= 0 else ""
    _log("HP_CHANGE", {"entity": entity, "change": f"{sign}{delta}", "hp": f"{old_hp}→{new_hp}", "reason": reason})


def log_state_change(key: str, old, new, reason: str = ""):
    _log("STATE_CHANGE", {"key": key, "old": old, "new": new, "reason": reason})


def log_narrator_output(narration: str, time_delta: int,
                        new_npcs: int, new_locations: int,
                        new_groups: int, world_flags: int):
    _log("NARRATOR_OUTPUT", {
        "narration": narration[:100] + ("…" if len(narration) > 100 else ""),
        "time_delta_min": time_delta,
        "new_npcs": new_npcs,
        "new_locations": new_locations,
        "new_groups": new_groups,
        "world_flags": world_flags
    })


def get_trace() -> list:
    return list(_current_trace)
