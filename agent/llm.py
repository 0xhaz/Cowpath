"""Shared LLM provider factory — the one-line env swap (techstacks §4).

`LLM_PROVIDER=ollama` (primary, on-device) | `anthropic` (filming insurance).
Both the intent labeler (indexer) and the agent loop use this, so flipping the
provider changes the whole system in one place. Never re-decide per call site.
"""

from __future__ import annotations

import os


def get_llm(temperature: float = 0.0, **kwargs):
    """Return a LangChain chat model per env config.

    ollama   -> ChatOllama (default model llama3.2; qwen3.6 is banned on this
                box — it OOMs alongside DataHub, see memory).
    anthropic-> ChatAnthropic (needs ANTHROPIC_API_KEY); default a current model.
    """
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        model = os.environ.get("LLM_MODEL", "llama3.2")
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=model, temperature=temperature,
                          base_url=base_url, **kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = os.environ.get("LLM_MODEL", "claude-sonnet-5")
        return ChatAnthropic(model=model, temperature=temperature, **kwargs)

    raise ValueError(f"Unknown LLM_PROVIDER={provider!r} (use ollama|anthropic)")


def provider_label() -> str:
    p = os.environ.get("LLM_PROVIDER", "ollama").lower()
    m = os.environ.get("LLM_MODEL", "llama3.2" if p == "ollama" else "claude-sonnet-5")
    return f"{p}:{m}"
