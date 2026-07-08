import asyncio
import json
import re
from tg_digest import llm


_SCORE_PROMPT = """\
You are a relevance filter for a personal digest of a backend/AI engineer (25-35).
Score each post 0-10 based on usefulness. Extract 1-5 topic tags per post.

User persona: values real case studies, architecture, numbers, and actionable content.
DISLIKES: shallow "10 AI tools that will change your life" content, crypto hype, generic news without depth.
LOVES: production AI/ML, agent systems, backend architecture, career growth, real startup breakdowns.

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


async def _score_batch(
    batch: list[tuple[int, dict]],
    weights: dict[str, float],
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
            return await _score_batch(batch, weights, base_url=base_url, api_key=api_key, model=model)

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
