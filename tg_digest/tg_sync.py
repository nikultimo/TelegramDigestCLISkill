"""
Telethon-based channel discovery.
Lists all public channels the user is subscribed to and adds them to the DB.
Requires interactive phone+OTP login on first run; session is saved after that.
"""
import asyncio
from pathlib import Path
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl.types import Channel, InputPeerChannel


@dataclass
class TGChannel:
    name: str
    username: str
    url: str
    title: str
    members: int | None


async def list_subscribed_channels(
    api_id: int,
    api_hash: str,
    session_path: str,
) -> list[TGChannel]:
    """
    Connect to Telegram as the user, list all channels they're in.
    Returns only public channels (those with a username / t.me/s/ URL).
    Interactive on first run — prompts for phone + OTP in the terminal.
    """
    Path(session_path).parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()  # prompts for phone/OTP if no saved session

    channels: list[TGChannel] = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, Channel):
            continue
        if not entity.broadcast:  # skip groups/megagroups, keep broadcast channels
            continue
        if not entity.username:   # skip private channels (no public username)
            continue

        username = entity.username.lower()
        channels.append(TGChannel(
            name=username,
            username=username,
            url=f"https://t.me/s/{username}",
            title=entity.title or username,
            members=getattr(entity, "participants_count", None),
        ))

    await client.disconnect()
    return channels


async def sync_channels_to_db(
    api_id: int,
    api_hash: str,
    session_path: str,
    db_path: Path,
) -> tuple[list[TGChannel], int]:
    """
    Fetch subscribed public channels and upsert them into the digest DB.
    Returns (all_channels, newly_added_count).
    """
    from tg_digest import db

    db.init_db(db_path)
    channels = await list_subscribed_channels(api_id, api_hash, session_path)

    existing = {ch["url"] for ch in db.list_channels(db_path)}
    added = 0
    for ch in channels:
        if ch.url not in existing:
            db.add_channel(db_path, ch.url, ch.name)
            added += 1

    return channels, added
