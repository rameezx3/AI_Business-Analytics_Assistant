"""Small dependency-free Claude/OpenAI chat adapter for Module 19."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def generate_chat_reply(
    provider: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    system_prompt: str,
) -> str:
    """Generate a bounded chat reply without logging credentials or API bodies."""
    if not api_key:
        raise RuntimeError(f"{provider} is not configured. Add its API key to local `.env` or Streamlit secrets.")
    if not model:
        raise RuntimeError(f"Set a model name for {provider} in local configuration.")

    clean_messages = [
        {"role": item["role"], "content": str(item["content"])[:4000]}
        for item in messages[-10:]
        if item.get("role") in {"user", "assistant"}
    ]
    headers = {"Content-Type": "application/json"}
    if provider == "OpenAI API":
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, *clean_messages],
            "max_tokens": 500,
        }
        url = "https://api.openai.com/v1/chat/completions"
    elif provider == "Claude API":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        payload = {
            "model": model,
            "max_tokens": 500,
            "system": system_prompt,
            "messages": clean_messages,
        }
        url = "https://api.anthropic.com/v1/messages"
    else:
        raise ValueError("Choose the built-in parser, Claude API, or OpenAI API.")

    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(f"{provider} rejected the API key (HTTP {exc.code}). Check local secret configuration.") from None
        if exc.code == 429:
            raise RuntimeError(f"{provider} rate or billing limit was reached (HTTP 429).") from None
        raise RuntimeError(f"{provider} request failed with HTTP {exc.code}.") from None
    except (URLError, TimeoutError):
        raise RuntimeError(f"Could not reach {provider}. Check the internet connection and try again.") from None

    try:
        if provider == "OpenAI API":
            content = body["choices"][0]["message"]["content"]
        else:
            content = "".join(
                block.get("text", "") for block in body.get("content", [])
                if block.get("type") == "text"
            )
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"{provider} returned an unexpected response. Try again.") from None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{provider} returned an empty answer. Try again.")
    return content.strip()
