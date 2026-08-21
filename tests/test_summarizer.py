import pytest

from tg_digest import summarizer


def test_summarizer_prompt_requires_russian_output_and_keeps_internal_categories():
    prompt = summarizer._SUMMARIZE_PROMPT

    assert "title" in prompt
    assert "description" in prompt
    assert "на русском" in prompt.lower()
    assert "try, learn, read, or practice" in prompt
    assert "health_fitness" in prompt
    assert "cars_tech" in prompt


@pytest.mark.asyncio
async def test_build_digest_passes_profile_and_attaches_all_merged_sources(monkeypatch):
    prompts = []

    async def fake_chat(messages, **kwargs):
        prompts.append(messages[0]["content"])
        assert kwargs["response_schema"] == summarizer.DIGEST_SCHEMA
        assert kwargs["temperature"] == 0.0
        return """{
          "items": [{
            "category": "learn",
            "topic_area": "ai_ml",
            "title": "Два источника об агентах",
            "description": "Практический разбор архитектуры.",
            "primary_url": "https://t.me/demo/1",
            "sources": ["https://t.me/demo/1", "https://t.me/demo/2"],
            "post_indices": [0, 1]
          }]
        }"""

    monkeypatch.setattr(summarizer.llm, "chat", fake_chat)
    posts = [
        {"db_id": 1, "text": "A" * 3500, "url": "https://t.me/demo/1", "score": 9},
        {"db_id": 2, "text": "B", "url": "https://t.me/demo/2", "score": 8},
    ]

    items = await summarizer.build_digest(
        posts,
        {"likes_text": "production agents", "dislikes_text": "", "notes_text": ""},
        base_url="http://llm.test/v1",
        api_key="test",
        model="test-model",
    )

    assert "production agents" in prompts[0]
    assert "A" * 3000 in prompts[0]
    assert "A" * 3001 not in prompts[0]
    assert items[0]["_post"]["db_id"] == 1
    assert [post["db_id"] for post in items[0]["_posts"]] == [1, 2]


def test_digest_validation_replaces_hallucinated_sources_with_canonical_urls():
    items = summarizer._validate_and_attach(
        {
            "items": [
                {
                    "category": "read",
                    "topic_area": "ai_ml",
                    "title": "Заголовок",
                    "description": "Описание",
                    "primary_url": "https://invalid.test",
                    "sources": ["https://invalid.test"],
                    "post_indices": [0],
                }
            ]
        },
        [{"url": "https://t.me/demo/1", "score": 8}],
    )

    assert items[0]["primary_url"] == "https://t.me/demo/1"
    assert items[0]["sources"] == ["https://t.me/demo/1"]


def test_digest_validation_hard_caps_borderline_items_at_two():
    posts = [
        {"url": f"https://t.me/demo/{index}", "score": 5}
        for index in range(3)
    ]
    data = {
        "items": [
            {
                "category": "read",
                "topic_area": "ai_ml",
                "title": f"Материал номер {index}",
                "description": "Описание",
                "primary_url": post["url"],
                "sources": [post["url"]],
                "post_indices": [index],
            }
            for index, post in enumerate(posts)
        ]
    }

    assert len(summarizer._validate_and_attach(data, posts)) == 2


def test_digest_validation_drops_items_below_borderline_score():
    post = {"url": "https://t.me/demo/1", "score": 4}
    data = {
        "items": [
            {
                "category": "read",
                "topic_area": "ai_ml",
                "title": "Поверхностная новость",
                "description": "Недостаточно практических деталей.",
                "primary_url": post["url"],
                "sources": [post["url"]],
                "post_indices": [0],
            }
        ]
    }

    assert summarizer._validate_and_attach(data, [post]) == []


def test_digest_validation_rejects_internal_post_references():
    data = {
        "items": [
            {
                "category": "try",
                "topic_area": "ai_ml",
                "title": "Минималистичный агент для кодинга",
                "description": "Дублирует пост 3, но добавляет практические детали.",
                "primary_url": "https://t.me/demo/1",
                "sources": ["https://t.me/demo/1"],
                "post_indices": [0],
            }
        ]
    }

    with pytest.raises(ValueError, match="internal post reference"):
        summarizer._validate_and_attach(
            data,
            [{"url": "https://t.me/demo/1", "score": 8}],
        )
