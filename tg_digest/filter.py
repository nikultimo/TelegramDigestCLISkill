import asyncio
import json
import re
from tg_digest import llm


_SCORE_PROMPT = """\
You are a relevance filter for a personal digest of a backend/AI engineer (25-35).
Score each post 0-10 based on usefulness. Extract 1-5 topic tags per post.

The readable user profile is the primary source of relevance.
Preference weights are only a weak secondary signal from item-level feedback.
Never let weak weights override an explicit profile match or explicit profile dislike.

Readable user profile:
{profile_block}

Preference weights (higher = more relevant):
{weights_block}

Posts to score:
{posts_json}

Return JSON:
{{
  "results": [
    {{"index": 0, "score": 8.5, "topics": ["ai agents", "fastapi"]}},
    ...
  ]
}}

Scoring guide:
10 = must-read, directly matches core interests with depth
7-9 = very relevant, actionable or insightful
4-6 = moderately interesting
1-3 = tangentially related
0 = irrelevant, hype-only, or explicitly deprioritized topic
"""

_BATCH_SIZE = 50  # posts per LLM call


def _sanitize(text: str) -> str:
    """Remove control characters that break JSON."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text or "")


def _weights_block(weights: dict[str, float]) -> str:
    if not weights:
        return "(none — score based on general backend/AI engineering value)"
    top = sorted(weights.items(), key=lambda x: -x[1])[:30]
    lines = [f"  - {t}: {w:.1f}x" for t, w in top]
    return "\n".join(lines)


def _profile_block(profile: dict | None) -> str:
    if not profile or not any((profile.get(key) or "").strip() for key in ("likes_text", "dislikes_text", "notes_text")):
        return (
            "Fallback personal profile:\n"
            "Likes: practical, applicable posts about AI agents, LLM products, automation, production ML, "
            "backend architecture, DevOps, highload, career growth, money, entrepreneurship, English through "
            "interesting content, health, fitness, style, World of Warcraft lore, travel, cars, and useful tech.\n"
            "Dislikes: shallow AI tool lists, hype, generic news without depth, crypto hype, empty motivation, "
            "and advice without examples, numbers, architecture, personal experience, or practical use.\n"
            "Notes: prefer real case studies, business impact, concrete implementation details, budgets, routes, "
            "cost of ownership, evidence-based health advice, and formats that can improve life, work, or income."
        )
    return "\n".join(
        [
            f"Likes: {profile.get('likes_text') or '(not specified)'}",
            f"Dislikes: {profile.get('dislikes_text') or '(not specified)'}",
            f"Notes: {profile.get('notes_text') or '(not specified)'}",
        ]
    )


def filter_by_min_score(posts: list[dict], min_score: float) -> list[dict]:
    return [post for post in posts if float(post.get("score", 0.0)) >= min_score]


async def _score_batch(
    batch: list[tuple[int, dict]],
    weights: dict[str, float],
    profile: dict | None,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> dict[int, dict]:
    """Score a single batch. Returns {original_index: {score, topics}}."""
    posts_json = json.dumps(
        [{"index": orig_idx, "text": _sanitize(p["text"])[:600]}
         for orig_idx, p in batch],
        ensure_ascii=False,
    )
    prompt = _SCORE_PROMPT.format(
        profile_block=_profile_block(profile),
        weights_block=_weights_block(weights),
        posts_json=posts_json,
    )
    raw = await llm.chat(
        [{"role": "user", "content": prompt}],
        base_url=base_url,
        api_key=api_key,
        model=model,
        json_mode=True,
    )
    data = llm.parse_json(raw)
    return {r["index"]: r for r in data.get("results", [])}


async def score_posts(
    posts: list[dict],
    weights: dict[str, float],
    profile: dict | None = None,
    *,
    base_url: str,
    api_key: str,
    model: str,
    top_n: int = 20,
) -> list[dict]:
    """Score all posts in batches. Returns top_n posts sorted by score."""
    if not posts:
        return []

    batches = [
        [(i, posts[i]) for i in range(start, min(start + _BATCH_SIZE, len(posts)))]
        for start in range(0, len(posts), _BATCH_SIZE)
    ]

    # run batches concurrently (max 5 at a time to avoid rate limits)
    result_map: dict[int, dict] = {}
    sem = asyncio.Semaphore(5)

    async def run_batch(batch):
        async with sem:
            return await _score_batch(batch, weights, profile, base_url=base_url, api_key=api_key, model=model)

    results = await asyncio.gather(*[run_batch(b) for b in batches], return_exceptions=True)
    for r in results:
        if isinstance(r, dict):
            result_map.update(r)

    scored = []
    for i, post in enumerate(posts):
        info = result_map.get(i, {})
        scored.append({
            **post,
            "score": info.get("score", 0.0),
            "topics": info.get("topics", []),
        })

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored[:top_n]
