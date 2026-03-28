"""
Streaming AI service — supports Gemini (google-genai) and OpenRouter (openai-compat).

Both services expose a single method:
    stream_message(selected_text, user_input) -> Iterator[str]

Each yielded string is one text chunk to display immediately.
"""

from typing import Iterator


# ── Prompt builder ─────────────────────────────────────────────────────────

def _build_prompt(selected_text: str, user_input: str) -> str:
    return (
        "Use the selected text as context. Keep answers concise unless asked for detail.\n\n"
        f"Selected text:\n{selected_text or '(none)'}\n\n"
        f"User message:\n{user_input}"
    )


# ── Gemini streaming ───────────────────────────────────────────────────────

class GeminiStreamService:
    """Streaming chat service backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model_id: str) -> None:
        from google import genai
        self.model_id = model_id
        self._client = genai.Client(api_key=api_key)
        # Maintain conversation history manually so we can stream
        self._history: list = []  # list of {"role": ..., "parts": [...]}

    def stream_message(self, selected_text: str, user_input: str) -> Iterator[str]:
        prompt = _build_prompt(selected_text, user_input)
        self._history.append({"role": "user", "parts": [{"text": prompt}]})

        accumulated = ""
        for chunk in self._client.models.generate_content_stream(
            model=self.model_id,
            contents=self._history,
        ):
            text = chunk.text or ""
            if text:
                accumulated += text
                yield text

        if accumulated:
            self._history.append(
                {"role": "model", "parts": [{"text": accumulated}]}
            )
        elif not accumulated:
            yield "I could not generate a response for that message."


# ── OpenRouter streaming ───────────────────────────────────────────────────

class OpenRouterStreamService:
    """Streaming chat service backed by OpenRouter (OpenAI-compatible API)."""

    _BASE_URL = "https://openrouter.ai/api/v1"
    _SYSTEM = (
        "You are a helpful assistant. Use the selected text as context. "
        "Keep answers concise unless asked for detail."
    )

    def __init__(self, api_key: str, model_id: str) -> None:
        self.model_id = model_id
        self._api_key = api_key
        self._messages: list = []  # OpenAI-style message history

    def stream_message(self, selected_text: str, user_input: str) -> Iterator[str]:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "The 'openai' package is required for OpenRouter. "
                "Install it: pip install openai"
            )

        client = OpenAI(base_url=self._BASE_URL, api_key=self._api_key)
        user_content = _build_prompt(selected_text, user_input)
        self._messages.append({"role": "user", "content": user_content})

        stream = client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "system", "content": self._SYSTEM}] + self._messages,
            stream=True,
        )

        accumulated = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                accumulated += delta
                yield delta

        if accumulated:
            self._messages.append({"role": "assistant", "content": accumulated})
        else:
            yield "I could not generate a response for that message."


# ── Factory ────────────────────────────────────────────────────────────────

def create_service(provider: str, api_key: str, model_id: str):
    """Return the correct streaming service for the given provider string."""
    p = provider.lower().strip()
    if p == "gemini":
        return GeminiStreamService(api_key=api_key, model_id=model_id)
    if p == "openrouter":
        return OpenRouterStreamService(api_key=api_key, model_id=model_id)
    raise ValueError(
        f"Unknown provider {provider!r}. Supported: 'gemini', 'openrouter'."
    )
