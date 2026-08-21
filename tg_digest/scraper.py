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


async def fetch_all_channels(
    channels: list[dict],
    limit: int = 20,
    *,
    failures: list[dict] | None = None,
) -> dict[int, list[RawPost]]:
    """Fetch all channels concurrently with a semaphore for rate limiting. Returns {channel_id: posts}."""
    sem = asyncio.Semaphore(10)  # max 10 concurrent requests

    async def _fetch_one(ch: dict) -> tuple[int, list[RawPost]]:
        async with sem:
            await asyncio.sleep(0.3 + random.random() * 0.5)  # minimal jitter
            try:
                posts = await fetch_channel(ch["url"], limit)
                return ch["id"], posts
            except RuntimeError as exc:
                if failures is not None:
                    failures.append({"id": ch["id"], "name": ch["name"], "error": str(exc)})
                return ch["id"], []

    tasks = [_fetch_one(ch) for ch in channels]
    results: dict[int, list[RawPost]] = {}
    for ch_id, posts in await asyncio.gather(*tasks):
        results[ch_id] = posts
    return results


# ── Telethon fallback scraper (used when t.me DNS is blocked) ────────────

def _channel_name(url: str) -> str:
    """Extract the channel username from a t.me/s/ URL."""
    return url.rstrip("/").split("/")[-1].lstrip("@").lower()


async def fetch_all_channels_telethon(
    channels: list[dict],
    session_path: str,
    api_id: int,
    api_hash: str,
    limit: int = 20,
    failures: list[dict] | None = None,
) -> dict[int, list[RawPost]]:
    """Fetch all channels via the Telegram client API (MTProto) — bypasses t.me DNS.

    Uses the existing Telethon session to authenticate.
    Returns {channel_id: posts} same shape as fetch_all_channels.
    """
    from telethon import TelegramClient
    from telethon.errors import RPCError

    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "Telethon session is not authorized; run `tg-digest sync` "
            "interactively before using the fallback"
        )

    sem = asyncio.Semaphore(5)  # 5 concurrent MTProto requests

    async def _fetch_one(ch: dict) -> tuple[int, list[RawPost]]:
        async with sem:
            name = _channel_name(ch["url"])
            try:
                entity = await client.get_entity(name)
                messages = await client.get_messages(entity, limit=limit)
            except (ValueError, RPCError) as exc:
                if failures is not None:
                    failures.append({"id": ch["id"], "name": name, "error": str(exc)})
                return ch["id"], []

            posts: list[RawPost] = []
            for msg in reversed(messages):
                if not msg.text:
                    continue
                # Extract text, removing entities formatting artifacts
                text = msg.text.strip()
                if not text:
                    continue
                timestamp = msg.date.isoformat() if msg.date else ""
                posts.append(RawPost(
                    post_id=str(msg.id),
                    text=text,
                    url=f"https://t.me/{name}/{msg.id}",
                    timestamp=timestamp,
                ))
            return ch["id"], posts

    tasks = [_fetch_one(ch) for ch in channels]
    results: dict[int, list[RawPost]] = {}
    for ch_id, posts in await asyncio.gather(*tasks):
        results[ch_id] = posts

    await client.disconnect()
    return results
