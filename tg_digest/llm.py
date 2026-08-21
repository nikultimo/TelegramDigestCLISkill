import asyncio
import json
import re
import httpx


async def chat(
    messages: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
    json_mode: bool = False,
    response_schema: dict | None = None,
    temperature: float | None = None,
    require_parameters: bool = False,
    return_metadata: bool = False,
    timeout: float = 60.0,
    max_attempts: int = 3,
) -> str | tuple[str, dict]:
    """Call any OpenAI-compatible chat endpoint. Returns response text."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/tg-digest",
        "X-Title": "tg-digest",
    }
    payload: dict = {"model": model, "messages": messages}
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "tg_digest_response",
                "strict": True,
                "schema": response_schema,
            },
        }
    elif json_mode:
        payload["response_format"] = {"type": "json_object"}
    if temperature is not None:
        payload["temperature"] = temperature
    if require_parameters:
        payload["provider"] = {"require_parameters": True}

    # Ensure base_url ends with / so httpx keeps the path prefix intact
    url = base_url.rstrip("/") + "/chat/completions"

    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if return_metadata:
                    return content, {
                        "id": data.get("id"),
                        "model": data.get("model", model),
                        "usage": data.get("usage", {}),
                    }
                return content
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    provider_message = exc.response.json().get("error", {}).get("message")
                except (ValueError, AttributeError):
                    provider_message = None
                if provider_message:
                    provider_message = re.sub(
                        r"(/keys/)[A-Za-z0-9_-]+",
                        r"\1<redacted>",
                        provider_message,
                    )
                    last_err = RuntimeError(
                        f"HTTP {exc.response.status_code}: {provider_message}"
                    )
                else:
                    last_err = exc
            else:
                last_err = exc
            if attempt + 1 < max_attempts:
                await asyncio.sleep(2 ** attempt)

    raise RuntimeError(f"LLM call failed after {max_attempts} attempt(s): {last_err}")


def parse_json(text: str) -> dict | list:
    text = text.strip()
    # strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text)
