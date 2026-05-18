import anthropic
import httpx
import json
import re
import os

_DEFAULT_MODEL_ANTHROPIC = "claude-sonnet-4-6"
_DEFAULT_MODEL_OPENROUTER = "anthropic/claude-sonnet-4-5"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _call_anthropic(system: str, messages: list, max_tokens: int, api_key: str | None) -> str:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    model = _DEFAULT_MODEL_ANTHROPIC
    c = anthropic.Anthropic(api_key=key)
    resp = c.messages.create(model=model, max_tokens=max_tokens, system=system, messages=messages)
    return resp.content[0].text


def _call_openrouter(system: str, messages: list, max_tokens: int, api_key: str, model: str) -> str:
    oai_messages = [{"role": "system", "content": system}] + messages
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/noledge5/jotunland",
        "X-Title": "Avarr RPG",
    }
    payload = {"model": model or _DEFAULT_MODEL_OPENROUTER, "messages": oai_messages, "max_tokens": max_tokens}
    resp = httpx.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_llm(system: str, messages: list, max_tokens: int,
              api_key: str | None = None, model: str | None = None,
              provider: str = "anthropic") -> str:
    if provider == "openrouter":
        if not api_key:
            raise ValueError("OpenRouter requires an API key")
        return _call_openrouter(system, messages, max_tokens, api_key, model or _DEFAULT_MODEL_OPENROUTER)
    return _call_anthropic(system, messages, max_tokens, api_key)


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


def classify_action(player_input, skill_list, scene_context, in_combat,
                    api_key=None, model=None, provider="anthropic"):
    """Call #1: classify player intent. Returns dict."""
    skill_names = ", ".join(skill_list)

    system_prompt = f"""You are an action classifier for a solo RPG engine. Given a player's text input, determine:
1. Does this action require a dice roll? (skill check, combat, contested action)
2. If yes: which skill from the list applies? What difficulty tier?

Available skills: {skill_names}
Current scene: {scene_context}
In combat: {str(in_combat).lower()}

Respond with ONLY valid JSON:
{{"needs_roll": true/false, "skill": "SkillName or null", "difficulty_tier": "Trivial/Easy/Medium/Hard/Very Hard/Nearly Impossible or null", "target": "what or who the action targets, or null"}}

If no roll is needed (resting, observing, talking casually, moving between known locations), return {{"needs_roll": false, "skill": null, "difficulty_tier": null, "target": null}}"""

    if in_combat:
        system_prompt += "\n\nPLAYER IS IN COMBAT. Force needs_roll=true and use Melee or Ranged skill."

    raw = ""
    try:
        raw = _call_llm(system_prompt, [{"role": "user", "content": player_input}],
                        150, api_key, model, provider)
        result = _try_parse_json(raw)
        if result is None:
            result = {"needs_roll": False, "skill": None, "difficulty_tier": None, "target": None}
        if in_combat and not result.get("needs_roll"):
            result["needs_roll"] = True
            result.setdefault("skill", "Melee")
            result.setdefault("difficulty_tier", "Medium")
        return result
    except Exception as e:
        print(f"[LLM] classify_action error: {e}")
        return {"needs_roll": False, "skill": None, "difficulty_tier": None, "target": None}


def generate_narration(context_prompt, api_key=None, model=None, provider="anthropic"):
    """Call #2: generate narration + state changes. Returns parsed dict."""
    fallback = {
        "narration": "The world shifts around you, though the moment passes without clear resolution.",
        "time_delta_minutes": 5,
        "generated_locations": [],
        "generated_npcs": [],
        "generated_groups": [],
        "world_state_changes": []
    }

    def _ensure_fields(d):
        d.setdefault("narration", fallback["narration"])
        d.setdefault("time_delta_minutes", 5)
        d.setdefault("generated_locations", [])
        d.setdefault("generated_npcs", [])
        d.setdefault("generated_groups", [])
        d.setdefault("world_state_changes", [])
        return d

    try:
        raw = _call_llm("", [{"role": "user", "content": context_prompt}],
                        1000, api_key, model, provider)
        result = _try_parse_json(raw)
        if result:
            return _ensure_fields(result)

        # Retry once
        retry_msg = [
            {"role": "user", "content": context_prompt},
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Your response was not valid JSON. Respond with ONLY the JSON object."}
        ]
        raw2 = _call_llm("", retry_msg, 1000, api_key, model, provider)
        result2 = _try_parse_json(raw2)
        if result2:
            return _ensure_fields(result2)

        fallback_copy = dict(fallback)
        if raw:
            lines = [l.strip() for l in raw.split('\n') if l.strip() and not l.strip().startswith('{')]
            if lines:
                fallback_copy["narration"] = ' '.join(lines[:3])
        return fallback_copy

    except Exception as e:
        print(f"[LLM] generate_narration error: {e}")
        return fallback


def generate_session_synopsis(recent_narrations, player_summary,
                               api_key=None, model=None, provider="anthropic"):
    """Compress recent turns into a session synopsis."""
    narrations_text = "\n".join(f"- {n}" for n in recent_narrations)
    prompt = f"""Compress the following RPG session events into a 2-3 sentence synopsis.
Focus on what happened, decisions made, and consequences. Be concise and use past tense.

Player: {player_summary}

Recent events:
{narrations_text}

Respond with only the synopsis text, no JSON."""

    try:
        return _call_llm("", [{"role": "user", "content": prompt}],
                         200, api_key, model, provider).strip()
    except Exception as e:
        print(f"[LLM] generate_session_synopsis error: {e}")
        return f"The session continued. {player_summary}"
