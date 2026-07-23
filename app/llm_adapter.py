"""Unified LLM-Adapter: streamt mit Tool-Use ueber drei Provider.

Provider-Routing ueber Modell-ID:
  or/<provider>/<model>  -> OpenRouter (OpenAI-kompatible SSE)
  gemini-*               -> Google (REST streamGenerateContent, alt=sse)
  claude-*               -> Anthropic (Messages API SSE)

Neutrales Nachrichtenformat:
  {"role": "user"|"assistant", "content": str, "tool_calls": [{id,name,args}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}

stream_with_tools yielded Events:
  {"type": "text", "text": str}
  {"type": "tool_call", "id": str, "name": str, "args": dict}
  {"type": "stop", "reason": "end"|"tool_use"}
"""
from __future__ import annotations

import json
import os
from typing import AsyncIterator

import httpx

TIMEOUT = httpx.Timeout(120.0, connect=15.0)


def provider_for(model_id: str) -> str:
    if model_id.startswith("or/"):
        return "openrouter"
    if model_id.startswith("gemini"):
        return "google"
    if model_id.startswith("claude"):
        return "anthropic"
    raise ValueError(f"Unbekanntes Modell-Schema: {model_id}")


def api_key_for(provider: str) -> str | None:
    env = {"anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY",
           "openrouter": "OPENROUTER_API_KEY"}[provider]
    return os.environ.get(env) or None


def available_providers() -> list[str]:
    return [p for p in ("openrouter", "google", "anthropic") if api_key_for(p)]


# --- Payload-Builder (pur, damit testbar) -------------------------------

def build_anthropic_payload(model: str, system: str, messages: list[dict],
                            tools: list[dict], max_tokens: int = 4000) -> dict:
    out = []
    for m in messages:
        if m["role"] == "tool":
            out.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": m["tool_call_id"],
                "content": m["content"]}]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use", "id": tc["id"],
                               "name": tc["name"], "input": tc["args"]})
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return {"model": model, "system": system, "messages": out,
            "tools": tools, "max_tokens": max_tokens, "stream": True}


def build_openai_payload(model: str, system: str, messages: list[dict],
                         tools: list[dict], max_tokens: int = 4000) -> dict:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"],
                        "content": m["content"]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": m.get("content") or None,
                        "tool_calls": [{"id": tc["id"], "type": "function",
                                        "function": {"name": tc["name"],
                                                     "arguments": json.dumps(tc["args"], ensure_ascii=False)}}
                                       for tc in m["tool_calls"]]})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return {"model": model, "messages": out, "stream": True, "max_tokens": max_tokens,
            "tools": [{"type": "function",
                       "function": {"name": t["name"], "description": t["description"],
                                    "parameters": t["input_schema"]}} for t in tools]}


def build_google_payload(system: str, messages: list[dict], tools: list[dict]) -> dict:
    contents = []
    for m in messages:
        if m["role"] == "tool":
            # Double-Encoding-Fix: Tool-Result als JSON parsen, damit Gemini
            # ein Objekt bekommt statt eines JSON-Strings im String.
            try:
                response_obj = json.loads(m["content"])
                if not isinstance(response_obj, dict):
                    response_obj = {"result": response_obj}
            except (json.JSONDecodeError, TypeError):
                response_obj = {"result": m["content"]}
            contents.append({"role": "user", "parts": [{
                "functionResponse": {"name": m["name"], "response": response_obj}}]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            parts: list[dict] = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m["tool_calls"]:
                parts.append({"functionCall": {"name": tc["name"], "args": tc["args"]}})
            contents.append({"role": "model", "parts": parts})
        else:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "tools": [{"function_declarations": [
            {"name": t["name"], "description": t["description"],
             "parameters": t["input_schema"]} for t in tools]}],
    }


# --- SSE-Helfer ---------------------------------------------------------

async def _iter_sse(response: httpx.Response) -> AsyncIterator[dict]:
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


# --- Provider-Streams ---------------------------------------------------

async def _stream_anthropic(model: str, system: str, messages: list[dict],
                            tools: list[dict]) -> AsyncIterator[dict]:
    payload = build_anthropic_payload(model, system, messages, tools)
    headers = {"x-api-key": api_key_for("anthropic"),
               "anthropic-version": "2023-06-01"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", "https://api.anthropic.com/v1/messages",
                                 json=payload, headers=headers) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode(errors="replace")
                raise RuntimeError(f"Anthropic {r.status_code}: {body[:400]}")
            current_tool: dict | None = None
            stop_reason = "end"
            async for ev in _iter_sse(r):
                t = ev.get("type")
                if t == "content_block_start":
                    block = ev.get("content_block", {})
                    if block.get("type") == "tool_use":
                        current_tool = {"id": block["id"], "name": block["name"], "json": ""}
                elif t == "content_block_delta":
                    d = ev.get("delta", {})
                    if d.get("type") == "text_delta":
                        yield {"type": "text", "text": d["text"]}
                    elif d.get("type") == "input_json_delta" and current_tool is not None:
                        current_tool["json"] += d.get("partial_json", "")
                elif t == "content_block_stop" and current_tool is not None:
                    args = json.loads(current_tool["json"] or "{}")
                    yield {"type": "tool_call", "id": current_tool["id"],
                           "name": current_tool["name"], "args": args}
                    current_tool = None
                elif t == "message_delta":
                    if ev.get("delta", {}).get("stop_reason") == "tool_use":
                        stop_reason = "tool_use"
                elif t == "error":
                    raise RuntimeError(f"Anthropic stream error: {ev}")
            yield {"type": "stop", "reason": stop_reason}


async def _stream_openrouter(model: str, system: str, messages: list[dict],
                             tools: list[dict]) -> AsyncIterator[dict]:
    payload = build_openai_payload(model.removeprefix("or/"), system, messages, tools)
    headers = {"Authorization": f"Bearer {api_key_for('openrouter')}",
               "HTTP-Referer": "http://localhost:3111", "X-Title": "NovaTerrum"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", "https://openrouter.ai/api/v1/chat/completions",
                                 json=payload, headers=headers) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode(errors="replace")
                raise RuntimeError(f"OpenRouter {r.status_code}: {body[:400]}")
            # tool_calls kommen als Deltas mit index — akkumulieren
            pending: dict[int, dict] = {}
            stop_reason = "end"
            async for ev in _iter_sse(r):
                for choice in ev.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        yield {"type": "text", "text": delta["content"]}
                    for tc in delta.get("tool_calls") or []:
                        i = tc.get("index", 0)
                        slot = pending.setdefault(i, {"id": "", "name": "", "json": ""})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["json"] += fn["arguments"]
                    if choice.get("finish_reason") == "tool_calls":
                        stop_reason = "tool_use"
            for slot in pending.values():
                if slot["name"]:
                    stop_reason = "tool_use"
                    yield {"type": "tool_call", "id": slot["id"] or f"call_{slot['name']}",
                           "name": slot["name"], "args": json.loads(slot["json"] or "{}")}
            yield {"type": "stop", "reason": stop_reason}


_google_call_counter = 0


async def _stream_google(model: str, system: str, messages: list[dict],
                         tools: list[dict]) -> AsyncIterator[dict]:
    global _google_call_counter
    payload = build_google_payload(system, messages, tools)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:streamGenerateContent?alt=sse")
    headers = {"x-goog-api-key": api_key_for("google")}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode(errors="replace")
                raise RuntimeError(f"Google {r.status_code}: {body[:400]}")
            stop_reason = "end"
            async for ev in _iter_sse(r):
                for cand in ev.get("candidates", []):
                    for part in (cand.get("content") or {}).get("parts", []):
                        if part.get("text"):
                            yield {"type": "text", "text": part["text"]}
                        elif part.get("functionCall"):
                            fc = part["functionCall"]
                            _google_call_counter += 1
                            stop_reason = "tool_use"
                            yield {"type": "tool_call",
                                   "id": f"gcall_{_google_call_counter}",
                                   "name": fc["name"], "args": fc.get("args") or {}}
            yield {"type": "stop", "reason": stop_reason}


async def stream_with_tools(model_id: str, system: str, messages: list[dict],
                            tools: list[dict]) -> AsyncIterator[dict]:
    provider = provider_for(model_id)
    if not api_key_for(provider):
        raise RuntimeError(f"Kein API-Key fuer Provider '{provider}' "
                           f"(.env: {provider.upper()}_API_KEY)")
    stream = {"anthropic": _stream_anthropic, "google": _stream_google,
              "openrouter": _stream_openrouter}[provider]
    async for ev in stream(model_id, system, messages, tools):
        yield ev
