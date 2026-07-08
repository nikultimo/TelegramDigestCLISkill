import pytest

from tg_digest import filter as filt


@pytest.mark.asyncio
async def test_score_posts_includes_readable_profile_in_prompt(monkeypatch):
    prompts = []

    async def fake_chat(messages, **kwargs):
        prompts.append(messages[0]["content"])
        return '{"results": [{"index": 0, "score": 8.0, "topics": ["agents"]}]}'

    monkeypatch.setattr(filt.llm, "chat", fake_chat)

    scored, failed_batches = await filt.score_posts(
        [{"text": "Agent case study", "url": "https://t.me/demo/1"}],
        {"agents": 1.3},
        {
            "likes_text": "production agent systems",
            "dislikes_text": "generic AI tool lists",
            "notes_text": "prefer real numbers",
            "min_score": 7.0,
        },
        base_url="http://llm.test/v1",
        api_key="test",
        model="test-model",
    )

    assert failed_batches == 0
    assert scored[0]["score"] == 8.0
    assert "production agent systems" in prompts[0]
    assert "generic AI tool lists" in prompts[0]
    assert "prefer real numbers" in prompts[0]
    assert "agents: 1.3x" in prompts[0]
    assert "primary source of relevance" in prompts[0]
    assert "weak secondary signal" in prompts[0]


@pytest.mark.asyncio
async def test_score_posts_reports_failed_batches_without_dropping_posts(monkeypatch):
    async def failing_chat(messages, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(filt.llm, "chat", failing_chat)

    posts = [{"text": "post one", "url": "https://t.me/demo/1"}]
    scored, failed_batches = await filt.score_posts(
        posts, {}, None,
        base_url="http://llm.test/v1",
        api_key="test",
        model="test-model",
    )

    assert failed_batches == 1
    assert len(scored) == 1
    assert scored[0]["score"] == 0.0


def test_filter_by_min_score_keeps_only_relevant_posts():
    posts = [
        {"text": "weak", "score": 6.9},
        {"text": "strong", "score": 7.0},
        {"text": "great", "score": 8.5},
    ]

    assert filt.filter_by_min_score(posts, 7.0) == posts[1:]


def test_missing_readable_profile_falls_back_to_broad_personal_profile():
    block = filt._profile_block(None)

    assert "AI agents" in block
    assert "health" in block
    assert "travel" in block
    assert "World of Warcraft" in block
    assert "shallow" in block
