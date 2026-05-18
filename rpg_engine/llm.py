import anthropic
import json
import re
import os

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"


def classify_action(player_input, skill_list, scene_context, in_combat):
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
        response = client.messages.create(
            model=MODEL,
            max_tokens=150,
            system=system_prompt,
            messages=[{"role": "user", "content": player_input}]
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        # Validate and normalize
        if in_combat and not result.get("needs_roll"):
            result["needs_roll"] = True
            if not result.get("skill"):
                result["skill"] = "Melee"
            if not result.get("difficulty_tier"):
                result["difficulty_tier"] = "Medium"
        return result
    except json.JSONDecodeError:
        # Try to extract JSON from response
        match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        # Fallback
        return {"needs_roll": False, "skill": None, "difficulty_tier": None, "target": None}
    except Exception as e:
        print(f"[LLM] classify_action error: {e}")
        return {"needs_roll": False, "skill": None, "difficulty_tier": None, "target": None}


def generate_narration(context_prompt):
    """Call #2: generate narration + state changes. Returns parsed dict."""
    fallback = {
        "narration": "The world shifts around you, though the moment passes without clear resolution.",
        "time_delta_minutes": 5,
        "generated_locations": [],
        "generated_npcs": [],
        "generated_groups": [],
        "world_state_changes": []
    }

    def _try_parse(text):
        text = text.strip()
        # Direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # Extract JSON block
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return None

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": context_prompt}]
        )
        raw = response.content[0].text
        result = _try_parse(raw)
        if result:
            # Ensure required fields
            result.setdefault("narration", fallback["narration"])
            result.setdefault("time_delta_minutes", 5)
            result.setdefault("generated_locations", [])
            result.setdefault("generated_npcs", [])
            result.setdefault("generated_groups", [])
            result.setdefault("world_state_changes", [])
            return result

        # Retry once
        retry_response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[
                {"role": "user", "content": context_prompt},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your response was not valid JSON. Please respond with ONLY the JSON object, no other text."}
            ]
        )
        raw2 = retry_response.content[0].text
        result2 = _try_parse(raw2)
        if result2:
            result2.setdefault("narration", fallback["narration"])
            result2.setdefault("time_delta_minutes", 5)
            result2.setdefault("generated_locations", [])
            result2.setdefault("generated_npcs", [])
            result2.setdefault("generated_groups", [])
            result2.setdefault("world_state_changes", [])
            return result2

        # Final fallback: extract narration from text
        fallback_copy = dict(fallback)
        # Try to get some narration text
        if raw:
            lines = [l.strip() for l in raw.split('\n') if l.strip() and not l.strip().startswith('{')]
            if lines:
                fallback_copy["narration"] = ' '.join(lines[:3])
        return fallback_copy

    except Exception as e:
        print(f"[LLM] generate_narration error: {e}")
        return fallback


def generate_session_synopsis(recent_narrations, player_summary):
    """Compress recent turns into a session synopsis."""
    narrations_text = "\n".join(f"- {n}" for n in recent_narrations)
    prompt = f"""Compress the following RPG session events into a 2-3 sentence synopsis.
Focus on what happened, decisions made, and consequences. Be concise and use past tense.

Player: {player_summary}

Recent events:
{narrations_text}

Respond with only the synopsis text, no JSON."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[LLM] generate_session_synopsis error: {e}")
        return f"The session continued. {player_summary}"
