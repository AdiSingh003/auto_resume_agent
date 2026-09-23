"""LLM client factory — Groq primary, Google Gemini fallback."""

import json
import logging
import re

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import settings

logger = logging.getLogger(__name__)


def get_primary_llm(temperature: float = 0.2) -> ChatGroq:
    """Get the primary Groq LLM client."""
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=temperature,
        max_tokens=8000,
        max_retries=4,  # Groq free tier rate-limits (429) are common during revision loops
    )


def get_fallback_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    """Get the fallback Google Gemini LLM client."""
    return ChatGoogleGenerativeAI(
        api_key=settings.google_api_key,
        model=settings.google_model,
        temperature=temperature,
        max_output_tokens=8000,
        max_retries=2,
    )


def _configured_providers() -> list[tuple[str, callable]]:
    providers = []
    if settings.groq_api_key:
        providers.append(("Groq", get_primary_llm))
    if settings.google_api_key:
        providers.append(("Gemini", get_fallback_llm))
    return providers


def _response_text(content) -> str:
    """LangChain message content may be a plain string or a list of content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in content
            if isinstance(part, (str, dict))
        )
    return str(content or "")


async def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Call the configured LLM providers in order, returning the first non-empty text response."""
    providers = _configured_providers()
    if not providers:
        raise RuntimeError("No LLM API key configured. Set GROQ_API_KEY (or GOOGLE_API_KEY) in .env")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    errors = []
    for name, factory in providers:
        try:
            response = await factory(temperature).ainvoke(messages)
            text = _response_text(response.content)
            if text.strip():
                return text
            errors.append(f"{name}: empty response")
        except Exception as e:
            logger.warning("%s call failed: %s", name, e)
            errors.append(f"{name}: {e}")

    raise RuntimeError("All LLM providers failed — " + "; ".join(errors))


async def call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
    """Call the LLM expecting a JSON object; retry once with a reminder if the reply isn't parseable."""
    data = parse_json_response(await call_llm(system_prompt, user_prompt, temperature))
    if isinstance(data, dict) and data:
        return data

    logger.warning("LLM reply was not a JSON object; retrying once")
    retry_prompt = (
        user_prompt
        + "\n\nIMPORTANT: Your previous reply was not valid JSON. "
        "Reply with ONLY a single valid JSON object — no prose, no markdown fences."
    )
    data = parse_json_response(await call_llm(system_prompt, retry_prompt, temperature))
    if isinstance(data, dict) and data:
        return data
    raise ValueError("LLM did not return a valid JSON object")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_json_response(text: str):
    """Extract JSON from an LLM response, handling markdown fences and surrounding prose.

    Returns the parsed value, or {} if nothing parseable was found.
    """
    cleaned = (text or "").strip()

    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    elif cleaned.startswith("```"):
        # Unterminated fence (e.g. truncated output): drop the opening line.
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for open_char, close_char in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(open_char), cleaned.rfind(close_char) + 1
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass

    logger.error("Failed to parse JSON from LLM response: %s", cleaned[:200])
    return {}
