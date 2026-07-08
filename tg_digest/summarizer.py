import json
from tg_digest import llm


_SUMMARIZE_PROMPT = """\
You are building a daily digest for a software engineer. Given the posts below, do the following:

1. DEDUPLICATE: If multiple posts cover the exact same story/event, merge them into one item
   and list all source URLs in "sources".

2. CLASSIFY each item into exactly one category:
   - "do"       — actionable tasks, tools to try, things to set up
   - "learn"    — concepts, tutorials, deep dives, courses
   - "read"     — articles, blog posts, news, opinion pieces
   - "practice" — coding challenges, exercises, projects to build

3. Assign "topic_area" — one of: "ai_ml", "backend", "career", "other"
   - ai_ml:   AI, ML, LLMs, agents, neural networks, automation, AI products
   - backend: backend, architecture, DevOps, highload, databases, infra, cloud
   - career:  career growth, salary, entrepreneurship, startups, hiring, business
   - other:   everything that doesn't fit above

4. Write "title" and "description" на русском языке.
   - "title": short, news-style, max 10 words.
   - "description": 1-2 dense sentences explaining what happened and why it matters.
   Keep source URLs unchanged.

Posts (JSON):
{posts_json}

Return a JSON object:
{{
  "items": [
    {{
      "category": "learn",
      "topic_area": "ai_ml",
      "title": "Rust объяснил модель владения",
      "description": "Материал кратко разбирает правила borrow checker и помогает быстрее понять типичные ошибки новичков.",
      "primary_url": "https://t.me/rustlang/1234",
      "sources": ["https://t.me/rustlang/1234"],
      "post_indices": [0]
    }}
  ]
}}

Return at most 20 items total. Prefer quality over quantity.
"""


async def build_digest(
    scored_posts: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> list[dict]:
    """Deduplicate, classify, and summarize posts. Returns digest items."""
    if not scored_posts:
        return []

    posts_json = json.dumps(
        [
            {"index": i, "text": p["text"][:600], "url": p["url"], "score": p["score"]}
            for i, p in enumerate(scored_posts)
        ],
        ensure_ascii=False,
    )

    raw = await llm.chat(
        [{"role": "user", "content": _SUMMARIZE_PROMPT.format(posts_json=posts_json)}],
        base_url=base_url,
        api_key=api_key,
        model=model,
        json_mode=True,
    )
    try:
        data = llm.parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"LLM returned invalid JSON while building the digest: {e}") from e
    items = data.get("items", [])

    # attach original post references for DB storage. If the LLM didn't return a
    # valid source index, leave "_post" empty rather than guessing — the caller
    # skips storing digest items with no resolvable source post.
    for item in items:
        indices = item.get("post_indices", [])
        if indices and indices[0] < len(scored_posts):
            item["_post"] = scored_posts[indices[0]]
        else:
            item["_post"] = {}

    return items
