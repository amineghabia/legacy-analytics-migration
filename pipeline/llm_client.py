"""Minimal client for the local Ollama server (no external API, no SDK).

A single function, so every LLM call in the pipeline uses the same model and
the same deterministic settings. Code never leaves the machine.
"""
import json

import requests

from config import LLM_TIMEOUT_S, MODEL_NAME, NUM_CTX, OLLAMA_URL, SEED, TEMPERATURE


class LLMError(RuntimeError):
    pass


def chat(system: str, user: str, schema: dict | None = None) -> str:
    """Send one system + user message and return the model's text answer.

    If a JSON schema is given, Ollama constrains generation so the answer
    is guaranteed to be JSON matching that schema (structured outputs).
    """
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": TEMPERATURE, "seed": SEED, "num_ctx": NUM_CTX},
    }
    if schema:
        payload["format"] = schema

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=LLM_TIMEOUT_S)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise LLMError(f"Cannot reach Ollama at {OLLAMA_URL}. Is it running?") from exc
    except requests.RequestException as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc

    return response.json()["message"]["content"]


def chat_json(system: str, user: str, schema: dict) -> dict:
    """Same as chat(), parsed as JSON. Raises LLMError if it is not valid JSON."""
    answer = chat(system, user, schema)
    try:
        return json.loads(answer)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model did not return valid JSON: {answer[:200]}") from exc
