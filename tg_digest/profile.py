import json
from pathlib import Path

from tg_digest import db, llm


DEFAULT_MIN_SCORE = 7.0

_TUNE_PROMPT = """\
Update a Telegram digest preference profile from a natural-language user request.
Preserve existing preferences unless the request clearly changes them.

min_score is the 0-10 relevance threshold: posts scored below it are dropped
from the digest. If the user asks to see more items ("show more", "показывай
больше"), lower min_score by about 1.0; if they ask for a stricter or shorter
digest, raise it by about 1.0. Keep it within 0-10. If the request is not
about digest volume, return the current min_score unchanged.

Current profile:
{profile_json}

User request:
{request}

Return JSON with exactly these keys:
{{
  "likes_text": "what to prioritize",
  "dislikes_text": "what to avoid",
  "notes_text": "extra nuance",
  "min_score": 7.0
}}
"""


def has_readable_profile(profile: dict | None) -> bool:
    if not profile:
        return False
    return any((profile.get(key) or "").strip() for key in ("likes_text", "dislikes_text", "notes_text"))


def merge_profile(
    current: dict | None,
    *,
    likes_text: str | None = None,
    dislikes_text: str | None = None,
    notes_text: str | None = None,
    min_score: float | None = None,
) -> dict:
    current = current or {}
    return {
        "likes_text": likes_text if likes_text is not None else current.get("likes_text", ""),
        "dislikes_text": dislikes_text if dislikes_text is not None else current.get("dislikes_text", ""),
        "notes_text": notes_text if notes_text is not None else current.get("notes_text", ""),
        "min_score": float(min_score if min_score is not None else current.get("min_score", DEFAULT_MIN_SCORE)),
    }


def save_profile(db_path: Path, profile: dict) -> None:
    db.save_preference_profile(
        db_path,
        likes_text=profile.get("likes_text", ""),
        dislikes_text=profile.get("dislikes_text", ""),
        notes_text=profile.get("notes_text", ""),
        min_score=float(profile.get("min_score", DEFAULT_MIN_SCORE)),
    )


async def tune_profile(
    request: str,
    *,
    current: dict | None,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    raw = await llm.chat(
        [
            {
                "role": "user",
                "content": _TUNE_PROMPT.format(
                    profile_json=json.dumps(current or {}, ensure_ascii=False),
                    request=request,
                ),
            }
        ],
        base_url=base_url,
        api_key=api_key,
        model=model,
        json_mode=True,
    )
    try:
        data = llm.parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"LLM returned invalid JSON while tuning the profile: {e}") from e
    raw_min_score = data.get("min_score")
    return merge_profile(
        current,
        likes_text=str(data.get("likes_text", "")),
        dislikes_text=str(data.get("dislikes_text", "")),
        notes_text=str(data.get("notes_text", "")),
        min_score=float(raw_min_score) if raw_min_score is not None else None,
    )
