import anthropic
import httpx
import json
import re
import os

_DEFAULT_MODEL_ANTHROPIC = "claude-sonnet-4-6"
_DEFAULT_MODEL_OPENROUTER = "anthropic/claude-sonnet-4-5"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_skills_cache = None


def _load_skill_names():
    global _skills_cache
    if _skills_cache is None:
        sk_path = os.path.join(os.path.dirname(__file__), 'config', 'skills.json')
        try:
            with open(sk_path) as f:
                data = json.load(f)
            _skills_cache = [s['name'] for s in data['skills']]
        except Exception:
            _skills_cache = []
    return _skills_cache


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
            raise ValueError("OpenRouter benötigt einen API-Key")
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
    # Use German skill names from config if not passed
    if not skill_list:
        skill_list = _load_skill_names()

    skill_names = ", ".join(skill_list)

    difficulty_tiers = "Sehr Leicht, Leicht, Durchschnitt, Schwer, Sehr Schwer, Heroisch, Extrem"

    system_prompt = f"""Du bist ein Aktionsklassifizierer für eine Solo-RPG-Engine. Gegeben den Texteingabe eines Spielers, bestimme:
1. Erfordert diese Aktion einen Würfelwurf? (Fertigkeitsprobe, Kampf, umstrittene Aktion)
2. Falls ja: Welcher Skill aus der Liste gilt? Welche Schwierigkeitsstufe?

Verfügbare Fertigkeiten: {skill_names}
Aktueller Schauplatz: {scene_context}
Im Kampf: {str(in_combat).lower()}

Schwierigkeitsstufen (von leicht bis schwer): {difficulty_tiers}

Wenn der Spieler eine Zielzone nennt (z.B. 'auf den Kopf', 'gezielt in die Kehle'), erhöhe den Schwierigkeitsgrad entsprechend.

Antworte NUR mit gültigem JSON:
{{"needs_roll": true/false, "skill": "Skillname oder null", "difficulty_tier": "Eine der Schwierigkeitsstufen oder null", "target": "Ziel der Aktion oder null"}}

Wenn kein Wurf nötig ist (Rasten, Beobachten, normales Gespräch, Bewegung zu bekannten Orten), gib zurück: {{"needs_roll": false, "skill": null, "difficulty_tier": null, "target": null}}"""

    if in_combat:
        system_prompt += "\n\nDER SPIELER IST IM KAMPF. Erzwinge needs_roll=true und nutze eine passende Kampffertigkeit (z.B. Klingenwaffen, Bogen, Waffenloser Kampf)."

    raw = ""
    try:
        raw = _call_llm(system_prompt, [{"role": "user", "content": player_input}],
                        150, api_key, model, provider)
        result = _try_parse_json(raw)
        if result is None:
            result = {"needs_roll": False, "skill": None, "difficulty_tier": None, "target": None}
        if in_combat and not result.get("needs_roll"):
            result["needs_roll"] = True
            result.setdefault("skill", "Klingenwaffen")
            result.setdefault("difficulty_tier", "Durchschnitt")
        # Validate difficulty_tier
        valid_tiers = ["Sehr Leicht", "Leicht", "Durchschnitt", "Schwer", "Sehr Schwer", "Heroisch", "Extrem"]
        if result.get("difficulty_tier") and result["difficulty_tier"] not in valid_tiers:
            result["difficulty_tier"] = "Durchschnitt"
        return result
    except Exception as e:
        print(f"[LLM] classify_action Fehler: {e}")
        return {"needs_roll": False, "skill": None, "difficulty_tier": None, "target": None}


def generate_narration(context_prompt, api_key=None, model=None, provider="anthropic"):
    """Call #2: generate narration + state changes. Returns parsed dict."""
    fallback = {
        "narration": "Die Welt verschiebt sich um dich herum, der Moment vergeht ohne klare Auflösung.",
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
            {"role": "user", "content": "Deine Antwort war kein gültiges JSON. Antworte NUR mit dem JSON-Objekt."}
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
        print(f"[LLM] generate_narration Fehler: {e}")
        return fallback


def generate_session_synopsis(recent_narrations, player_summary,
                               api_key=None, model=None, provider="anthropic"):
    """Compress recent turns into a session synopsis."""
    narrations_text = "\n".join(f"- {n}" for n in recent_narrations)
    prompt = f"""Fasse die folgenden RPG-Sitzungsereignisse in einer 2-3-Satz-Zusammenfassung zusammen.
Konzentriere dich auf das Geschehene, getroffene Entscheidungen und Konsequenzen. Sei präzise und verwende die Vergangenheitsform.

Spieler: {player_summary}

Jüngste Ereignisse:
{narrations_text}

Antworte nur mit dem Zusammenfassungstext, kein JSON."""

    try:
        return _call_llm("", [{"role": "user", "content": prompt}],
                         200, api_key, model, provider).strip()
    except Exception as e:
        print(f"[LLM] generate_session_synopsis Fehler: {e}")
        return f"Die Sitzung wurde fortgesetzt. {player_summary}"
