import asyncio
import random
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


@dataclass
class RawPost:
    post_id: str
    text: str
    url: str
    timestamp: str


_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def _channel_name_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].lstrip("@")


def _ensure_preview_url(url: str) -> str:
    """Convert t.me/channel or t.me/s/channel to t.me/s/channel."""
    url = url.rstrip("/")
    if "/s/" not in url:
        parts = url.split("t.me/")
        if len(parts) == 2:
            return f"https://t.me/s/{parts[1]}"
    return url


def _parse_posts(html: str, channel_url: str, limit: int) -> list[RawPost]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []

    for msg in soup.select(".tgme_widget_message"):
        data_post = msg.get("data-post", "")
        # data-post is "channel_name/12345"
        match = re.match(r"^([^/]+)/(\d+)$", data_post)
        if not match:
            continue
        actual_channel, post_id = match.group(1), match.group(2)

        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""
        if not text:
            continue  # skip media-only posts

        date_el = msg.select_one(".tgme_widget_message_date time")
        timestamp = date_el.get("datetime", "") if date_el else ""

        posts.append(RawPost(
            post_id=post_id,
            text=text,
            url=f"https://t.me/{actual_channel}/{post_id}",
            timestamp=timestamp,
        ))

    return posts[-limit:]  # keep the most recent N


async def fetch_channel(url: str, limit: int = 20) -> list[RawPost]:
    preview_url = _ensure_preview_url(url)
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
                resp = await client.get(preview_url, headers=_HEADERS)
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return _parse_posts(resp.text, url, limit)
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_err = exc
            await asyncio.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


async def fetch_all_channels(channels: list[dict], limit: int = 20) -> dict[int, list[RawPost]]:
    """Fetch all channels with jitter between requests. Returns {channel_id: posts}."""
    results: dict[int, list[RawPost]] = {}
    for i, ch in enumerate(channels):
        if i > 0:
            await asyncio.sleep(1.5 + random.random())
        try:
            posts = await fetch_channel(ch["url"], limit)
            results[ch["id"]] = posts
        except RuntimeError:
            results[ch["id"]] = []
    return results
