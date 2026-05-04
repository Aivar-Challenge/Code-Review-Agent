"""
LLM client abstraction — supports OpenAI, Anthropic, Google Gemini.
Returns structured JSON findings.
"""
import json
import logging
from typing import Any
from dataclasses import dataclass

from backend.config import settings

logger = logging.getLogger("agent.llm")


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
    response_format: str = "json",
) -> LLMResponse:
    """
    Unified LLM call. Returns an LLMResponse with content and token counts.
    The content is expected to be valid JSON.
    """
    model = model or settings.default_model
    provider = settings.llm_provider

    if provider == "openai":
        return await _call_openai(system_prompt, user_prompt, model, temperature)
    elif provider == "anthropic":
        return await _call_anthropic(system_prompt, user_prompt, model, temperature)
    elif provider == "google":
        return await _call_google(system_prompt, user_prompt, model, temperature)
    elif provider == "groq":
        return await _call_groq(system_prompt, user_prompt, model, temperature)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def _call_openai(
    system_prompt: str, user_prompt: str, model: str, temperature: float
) -> LLMResponse:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return LLMResponse(
        content=resp.choices[0].message.content or "{}",
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
        total_tokens=resp.usage.total_tokens,
        model=model,
    )


async def _call_anthropic(
    system_prompt: str, user_prompt: str, model: str, temperature: float
) -> LLMResponse:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    full_prompt = (
        f"{user_prompt}\n\nRespond ONLY with valid JSON, no markdown fences."
    )
    msg = await client.messages.create(
        model=model or "claude-3-haiku-20240307",
        max_tokens=4096,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": full_prompt}],
    )
    content = msg.content[0].text if msg.content else "{}"
    return LLMResponse(
        content=content,
        prompt_tokens=msg.usage.input_tokens,
        completion_tokens=msg.usage.output_tokens,
        total_tokens=msg.usage.input_tokens + msg.usage.output_tokens,
        model=model,
    )


async def _call_google(
    system_prompt: str, user_prompt: str, model: str, temperature: float
) -> LLMResponse:
    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)
    gemini = genai.GenerativeModel(
        model_name=model or "gemini-1.5-flash",
        system_instruction=system_prompt,
    )
    result = await gemini.generate_content_async(
        user_prompt + "\n\nRespond ONLY with valid JSON.",
        generation_config={"temperature": temperature, "response_mime_type": "application/json"},
    )
    tokens_in = result.usage_metadata.prompt_token_count or 0
    tokens_out = result.usage_metadata.candidates_token_count or 0
    return LLMResponse(
        content=result.text,
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        total_tokens=tokens_in + tokens_out,
        model=model,
    )


async def _call_groq(
    system_prompt: str, user_prompt: str, model: str, temperature: float
) -> LLMResponse:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)
    resp = await client.chat.completions.create(
        model=model or "llama-3.1-8b-instant",
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return LLMResponse(
        content=resp.choices[0].message.content or "{}",
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
        total_tokens=resp.usage.total_tokens,
        model=model,
    )

def parse_findings(raw_json: str) -> list[dict]:
    """
    Parse LLM response JSON into a list of finding dicts.
    Robust to minor formatting errors.
    """
    try:
        data = json.loads(raw_json)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Could be {"findings": [...]} or {"issues": [...]}
            for key in ("findings", "issues", "results", "comments"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # Single finding wrapped in object
            if "confidence" in data:
                return [data]
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM JSON response: {e}")
        return []
