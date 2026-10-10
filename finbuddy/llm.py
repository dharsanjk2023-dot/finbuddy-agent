"""Model factory. The provider is chosen with one environment variable, so the same
agent runs on Anthropic, OpenAI, Google, Groq, etc.

    LLM_MODEL="anthropic:claude-sonnet-5-5"        (default; needs ANTHROPIC_API_KEY)
    LLM_MODEL="openai:gpt-4o-mini"                 (needs langchain-openai + OPENAI_API_KEY)
    LLM_MODEL="google_genai:gemini-2.0-flash"      (needs langchain-google-genai + GOOGLE_API_KEY)
"""

import os

from langchain.chat_models import init_chat_model

DEFAULT_MODEL = "anthropic:claude-sonnet-5-5"


def get_llm(spec: str | None = None):
    return init_chat_model(spec or os.getenv("LLM_MODEL", DEFAULT_MODEL))
