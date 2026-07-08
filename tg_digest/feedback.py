import json
from pathlib import Path
from tg_digest import db, llm


_TOPIC_PROMPT = """\
Extract 1-5 short topic tags from this text. Tags should be lowercase, 1-3 words each.
Examples: "rust", "system design", "docker", "machine learning", "web scraping"

Text:
{text}

Return JSON: {{"topics": ["tag1", "tag2"]}}
"""


async def process_feedback(
    item_id: int,
    signal: int,
    *,
    db_path: Path,
    base_url: str,
    api_key: str,
    model: str,
) -> list[str]:
    """Record feedback and update topic weights. Returns list of topics updated."""
    item = db.get_digest_item(db_path, item_id)
    if not item:
        raise ValueError(f"Digest item #{item_id} not found")

    db.insert_feedback(db_path, item_id, signal)

    topics = item.get("topics") or []
    if not topics:
        text = item.get("text", "") or item.get("summary", "")
        if not text:
            return []

        raw = await llm.chat(
            [{"role": "user", "content": _TOPIC_PROMPT.format(text=text[:500])}],
            base_url=base_url,
            api_key=api_key,
            model=model,
            json_mode=True,
        )
        data = llm.parse_json(raw)
        topics = data.get("topics", [])

    weights = db.get_topic_weights(db_path)
    delta = 0.1 * signal  # +0.1 for like, -0.1 for dislike
    for topic in topics:
        topic = topic.lower().strip()
        if not topic:
            continue
        current = weights.get(topic, 1.0)
        db.upsert_topic_weight(db_path, topic, current + delta)

    return topics
