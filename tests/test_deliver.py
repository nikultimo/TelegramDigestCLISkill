from tg_digest import deliver


def test_render_digest_uses_russian_telegram_style():
    content = deliver.render_digest(
        [
            {
                "_db_id": 7,
                "category": "read",
                "topic_area": "ai_ml",
                "title": "Claude Code подключился к чужому серверу",
                "primary_url": "https://t.me/ai/10487",
                "description": "Инцидент показывает, почему изоляция контекста критична для AI-агентов.",
                "sources": ["https://t.me/ai/10487", "https://t.me/dev/42"],
            },
            {
                "_db_id": 8,
                "category": "do",
                "topic_area": "backend",
                "title": "Попробовать Shepherd",
                "primary_url": "https://t.me/dev/43",
                "description": "Система помогает откатывать ошибки агентов через сохранение состояния.",
                "sources": ["https://t.me/dev/43"],
            },
        ],
        "2026-07-08",
        3,
        24,
    )

    assert content.startswith("🗓 AI ДАЙДЖЕСТ • 08.07.2026")
    assert "━━━━━━━━━━━━━━━" in content
    assert "🤖 AI / ML" in content
    assert "⚙️ Backend / Highload" in content
    assert "🛠 Попробовать:" in content
    assert "📰 Прочитать:" in content
    assert "🔹 #7 Claude Code подключился к чужому серверу" in content
    assert "🔹 #8 Попробовать Shepherd" in content
    assert "Инцидент показывает, почему изоляция контекста критична для AI-агентов. [1](https://t.me/ai/10487), [2](https://t.me/dev/42)" in content
    assert "Каналов: 3 · Постов просмотрено: 24 · В дайджесте: 2" in content
    assert "Для обратной связи: `tg-digest feedback <id> like|dislike`" in content
    assert "What to Read" not in content


def test_render_digest_sorts_items_by_score_within_section():
    content = deliver.render_digest(
        [
            {
                "_db_id": 1,
                "category": "read",
                "topic_area": "ai_ml",
                "title": "Low score item",
                "primary_url": "https://t.me/ai/1",
                "description": "Less relevant.",
                "sources": ["https://t.me/ai/1"],
                "_post": {"score": 3.0},
            },
            {
                "_db_id": 2,
                "category": "read",
                "topic_area": "ai_ml",
                "title": "High score item",
                "primary_url": "https://t.me/ai/2",
                "description": "More relevant.",
                "sources": ["https://t.me/ai/2"],
                "_post": {"score": 9.0},
            },
        ],
        "2026-07-08",
        1,
        2,
    )

    assert content.index("High score item") < content.index("Low score item")


def test_render_digest_uses_range_date_in_header():
    content = deliver.render_digest([], "2026-07-07 to 2026-07-08", 1, 2)

    assert content.startswith("🗓 AI ДАЙДЖЕСТ • 07.07.2026–08.07.2026")


def test_markdown_to_telegram_html_escapes_text_and_links():
    content = deliver.render_digest(
        [
            {
                "_db_id": 1,
                "category": "read",
                "title": "A < B & C",
                "primary_url": "https://example.com/?a=1&b=2",
                "description": "Use x < y & z",
                "sources": ["https://example.com/?a=1&b=2"],
            }
        ],
        "2026-07-08",
        1,
        1,
    )

    html = deliver._md_to_html(content)

    assert "A &lt; B &amp; C" in html
    assert "Use x &lt; y &amp; z" in html
    assert '<a href="https://example.com/?a=1&amp;b=2">[1]</a>' in html
    assert "[1](" not in html
    assert "< y" not in html
