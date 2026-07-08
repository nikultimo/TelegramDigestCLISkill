import asyncio

from tg_digest import profile


CURRENT = {
    "likes_text": "backend",
    "dislikes_text": "crypto",
    "notes_text": "cases",
    "min_score": 6.0,
}


def _tune(request, monkeypatch, response):
    async def fake_chat(messages, **kwargs):
        fake_chat.prompt = messages[0]["content"]
        return response

    monkeypatch.setattr("tg_digest.profile.llm.chat", fake_chat)
    result = asyncio.run(
        profile.tune_profile(request, current=CURRENT, base_url="", api_key="", model="m")
    )
    return result, fake_chat.prompt


def test_tune_preserves_current_min_score_when_llm_omits_it(monkeypatch):
    result, _ = _tune(
        "меньше хайпа",
        monkeypatch,
        '{"likes_text": "backend", "dislikes_text": "crypto, hype", "notes_text": "cases"}',
    )

    assert result["min_score"] == 6.0


def test_tune_applies_min_score_returned_by_llm(monkeypatch):
    result, _ = _tune(
        "показывай больше",
        monkeypatch,
        '{"likes_text": "backend", "dislikes_text": "crypto", "notes_text": "cases", "min_score": 5.0}',
    )

    assert result["min_score"] == 5.0


def test_tune_prompt_explains_min_score_threshold(monkeypatch):
    _, prompt = _tune("показывай больше", monkeypatch, "{}")

    assert "min_score" in prompt
    assert "lower" in prompt.lower()
    assert "show more" in prompt.lower()
