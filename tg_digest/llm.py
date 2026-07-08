import asyncio
import json
import httpx


async def chat(
    messages: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
    json_mode: bool = False,
    timeout: float = 60.0,
) -> str:
    """Call any OpenAI-compatible chat endpoint. Returns response text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/tg-digest",
        "X-Title": "tg-digest",
    }
    payload: dict = {"model": model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # Ensure base_url ends with / so httpx keeps the path prefix intact
    url = base_url.rstrip("/") + "/chat/completions"

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_err = exc
            await asyncio.sleep(2 ** attempt)

    raise RuntimeError(f"LLM call failed after 3 attempts: {last_err}")


def parse_json(text: str) -> dict | list:
    text = text.strip()
    # strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text)
