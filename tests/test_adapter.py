import json

from app import llm_adapter as la


def test_provider_routing():
    assert la.provider_for("or/google/gemini-2.5-flash") == "openrouter"
    assert la.provider_for("or/anthropic/claude-sonnet-4.5") == "openrouter"
    assert la.provider_for("gemini-2.5-flash") == "google"
    assert la.provider_for("claude-sonnet-4-5") == "anthropic"
    import pytest
    with pytest.raises(ValueError):
        la.provider_for("gpt-4o")


TOOLS = [{"name": "pay", "description": "zahlt", "input_schema":
          {"type": "object", "properties": {"betrag_kp": {"type": "integer"}}, "required": []}}]

MESSAGES = [
    {"role": "user", "content": "Ich zahle den Wirt."},
    {"role": "assistant", "content": "Du legst Muenzen hin.",
     "tool_calls": [{"id": "t1", "name": "pay", "args": {"betrag_kp": 7}}]},
    {"role": "tool", "tool_call_id": "t1", "name": "pay",
     "content": '{"bezahlt_kp": 7, "boerse": "1 sm 8 kp"}'},
]


def test_anthropic_payload():
    p = la.build_anthropic_payload("claude-sonnet-4-5", "SYS", MESSAGES, TOOLS)
    assert p["system"] == "SYS"
    assert p["messages"][1]["content"][1]["type"] == "tool_use"
    assert p["messages"][2]["content"][0]["tool_use_id"] == "t1"


def test_openai_payload():
    p = la.build_openai_payload("m", "SYS", MESSAGES, TOOLS)
    assert p["messages"][0] == {"role": "system", "content": "SYS"}
    tc = p["messages"][2]["tool_calls"][0]
    assert tc["function"]["name"] == "pay"
    assert json.loads(tc["function"]["arguments"]) == {"betrag_kp": 7}
    assert p["messages"][3]["role"] == "tool"
    assert p["tools"][0]["function"]["parameters"]["type"] == "object"


def test_google_payload_no_double_encoding():
    """Gemini-Fix: Tool-Result muss als Objekt ankommen, nicht als
    JSON-String-in-String."""
    p = la.build_google_payload("SYS", MESSAGES, TOOLS)
    fr = p["contents"][2]["parts"][0]["functionResponse"]
    assert fr["name"] == "pay"
    assert isinstance(fr["response"], dict)
    assert fr["response"]["bezahlt_kp"] == 7  # geparst, nicht doppelt encodiert
    fc = p["contents"][1]["parts"][1]["functionCall"]
    assert fc["args"] == {"betrag_kp": 7}


def test_google_payload_plaintext_tool_result():
    msgs = [{"role": "tool", "tool_call_id": "t1", "name": "pay",
             "content": "FEHLER: Nicht genug Muenzen"}]
    p = la.build_google_payload("SYS", msgs, TOOLS)
    fr = p["contents"][0]["parts"][0]["functionResponse"]
    assert fr["response"] == {"result": "FEHLER: Nicht genug Muenzen"}
