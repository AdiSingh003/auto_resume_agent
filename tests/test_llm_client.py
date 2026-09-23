import asyncio

import pytest

from backend.agents import llm_client
from backend.agents.llm_client import parse_json_response


@pytest.mark.parametrize("text, expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Here is the result:\n```\n{"a": 1}\n```\nHope that helps', {"a": 1}),
    ('Sure! {"a": {"b": [1, 2]}} done', {"a": {"b": [1, 2]}}),
    ('```json\n{"a": 1}', {"a": 1}),
    ("not json at all", {}),
])
def test_parse_json_response(text, expected):
    assert parse_json_response(text) == expected


def test_call_llm_json_retries_once_on_unparseable_reply(monkeypatch):
    replies = iter(["Sorry, here you go", '{"ok": true}'])
    prompts = []

    async def fake_call_llm(system, user, temperature=0.2):
        prompts.append(user)
        return next(replies)

    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm)
    assert asyncio.run(llm_client.call_llm_json("sys", "user")) == {"ok": True}
    assert "not valid JSON" in prompts[1]


def test_call_llm_json_raises_after_second_failure(monkeypatch):
    async def fake_call_llm(system, user, temperature=0.2):
        return "nope"

    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm)
    with pytest.raises(ValueError):
        asyncio.run(llm_client.call_llm_json("sys", "user"))


def test_call_llm_without_keys_raises_clear_error(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "groq_api_key", "")
    monkeypatch.setattr(llm_client.settings, "google_api_key", "")
    with pytest.raises(RuntimeError, match="No LLM API key"):
        asyncio.run(llm_client.call_llm("sys", "user"))
