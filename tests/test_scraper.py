import sys
from types import ModuleType

import pytest

from tg_digest import scraper


@pytest.mark.asyncio
async def test_fetch_all_channels_reports_partial_failures(monkeypatch):
    async def fake_fetch(url, limit):
        if url.endswith("broken"):
            raise RuntimeError("unavailable")
        return [
            scraper.RawPost(
                post_id="1",
                text="ok",
                url="https://t.me/working/1",
                timestamp="2026-07-18T10:00:00+00:00",
            )
        ]

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(scraper, "fetch_channel", fake_fetch)
    monkeypatch.setattr(scraper.asyncio, "sleep", no_sleep)
    failures = []
    result = await scraper.fetch_all_channels(
        [
            {"id": 1, "name": "working", "url": "https://t.me/s/working"},
            {"id": 2, "name": "broken", "url": "https://t.me/s/broken"},
        ],
        failures=failures,
    )

    assert len(result[1]) == 1
    assert result[2] == []
    assert failures[0]["name"] == "broken"


@pytest.mark.asyncio
async def test_telethon_fallback_never_starts_interactive_login(monkeypatch):
    class FakeClient:
        def __init__(self, *args):
            self.disconnected = False

        async def connect(self):
            return None

        async def is_user_authorized(self):
            return False

        async def start(self):
            raise AssertionError("interactive login must not be started")

        async def disconnect(self):
            self.disconnected = True

    telethon_module = ModuleType("telethon")
    telethon_module.TelegramClient = FakeClient
    errors_module = ModuleType("telethon.errors")
    errors_module.RPCError = RuntimeError
    monkeypatch.setitem(sys.modules, "telethon", telethon_module)
    monkeypatch.setitem(sys.modules, "telethon.errors", errors_module)

    with pytest.raises(RuntimeError, match="not authorized"):
        await scraper.fetch_all_channels_telethon(
            [],
            session_path="missing.session",
            api_id=1,
            api_hash="test",
        )
