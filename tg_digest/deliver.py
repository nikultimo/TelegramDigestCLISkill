from datetime import date
from html import escape
from pathlib import Path
import re

import httpx


CATEGORIES = ["do", "learn", "read", "practice"]
TOPIC_AREAS = ["ai_ml", "backend", "career", "other"]

TOPIC_HEADERS = {
    "ai_ml":   "🤖 AI / ML",
    "backend": "⚙️ Backend / Highload",
    "career":  "💼 Карьера / Деньги",
    "other":   "📌 Разное",
}
ACTION_PREFIXES = {
    "do":       "🛠 Попробовать",
    "learn":    "📚 Изучить",
    "read":     "📰 Прочитать",
    "practice": "💻 Попрактиковать",
}
SECTION_SEPARATOR = "━━━━━━━━━━━━━━━"


def render_digest(items: list[dict], run_date: str, channel_count: int, post_count: int) -> str:
    """Render digest items grouped by topic area, then by action category."""
    lines = [f"🗓 AI ДАЙДЖЕСТ • {_format_digest_date(run_date)}", ""]

    by_topic: dict[str, list[dict]] = {t: [] for t in TOPIC_AREAS}
    for item in items:
        topic = item.get("topic_area", "other")
        if topic not in by_topic:
            topic = "other"
        by_topic[topic].append(item)

    for topic in TOPIC_AREAS:
        topic_items = by_topic[topic]
        if not topic_items:
            continue
        lines.append(SECTION_SEPARATOR)
        lines.append(TOPIC_HEADERS[topic])
        lines.append("")

        by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
        for item in topic_items:
            cat = item.get("category", "read")
            if cat not in by_cat:
                cat = "read"
            by_cat[cat].append(item)

        for cat in CATEGORIES:
            cat_items = by_cat[cat]
            if not cat_items:
                continue
            lines.append(f"{ACTION_PREFIXES[cat]}:")
            for item in cat_items:
                title = item.get("title", "Без названия")
                item_id = item.get("_db_id")
                url = item.get("primary_url", "")
                desc = item.get("description", "")
                sources = item.get("sources", [url])
                source_str = _format_sources(sources)
                if source_str:
                    desc = f"{desc} {source_str}".strip()
                prefix = f"#{item_id} " if item_id is not None else ""
                lines.append(f"🔹 {prefix}{title}")
                lines.append(desc)
                lines.append("")
        lines.append("")

    lines.append(SECTION_SEPARATOR)
    lines.append(f"Каналов: {channel_count} · Постов просмотрено: {post_count} · В дайджесте: {len(items)}")
    lines.append("Для обратной связи: `tg-digest feedback <id> like|dislike`")
    return "\n".join(lines)


def _format_digest_date(value: str) -> str:
    if " to " in value:
        start, end = value.split(" to ", 1)
        return f"{_format_single_date(start)}–{_format_single_date(end)}"
    return _format_single_date(value)


def _format_single_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


def _format_sources(sources: list[str]) -> str:
    urls = [source for source in sources if source]
    return ", ".join(f"[{index}] ({url})" for index, url in enumerate(urls, start=1))


def write_md(content: str, output_dir: Path, run_date: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run_date}.md"
    path.write_text(content, encoding="utf-8")
    return path


async def send_telegram(content: str, bot_token: str, chat_id: str) -> None:
    if not bot_token or not chat_id:
        raise ValueError("TG_BOT_TOKEN and TG_CHAT_ID must be set for Telegram delivery")

    # Telegram MarkdownV2 is finicky; use plain HTML instead
    html = _md_to_html(content)

    # Telegram messages have 4096 char limit — split if needed
    chunks = _split_message(html, 4000)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in chunks:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"},
            )
            resp.raise_for_status()


def _md_to_html(md: str) -> str:
    """Minimal Markdown → Telegram HTML conversion."""
    placeholders: list[str] = []

    def hold(value: str) -> str:
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    def link(match: re.Match) -> str:
        text = escape(match.group(1), quote=False)
        url = escape(match.group(2), quote=True)
        return hold(f'<a href="{url}">{text}</a>')

    def bold(match: re.Match) -> str:
        return hold(f"<b>{escape(match.group(1), quote=False)}</b>")

    def italic(match: re.Match) -> str:
        return hold(f"<i>{escape(match.group(1), quote=False)}</i>")

    def code(match: re.Match) -> str:
        return hold(f"<code>{escape(match.group(1), quote=False)}</code>")

    md = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, md)
    md = re.sub(r"\*\*(.+?)\*\*", bold, md)
    md = re.sub(r"`(.+?)`", code, md)
    md = re.sub(r"\*(.+?)\*", italic, md)
    md = re.sub(
        r"^#{1,3} (.+)$",
        lambda m: hold(f"<b>{escape(m.group(1), quote=False)}</b>"),
        md,
        flags=re.MULTILINE,
    )

    md = escape(md, quote=False)
    for index in range(len(placeholders) - 1, -1, -1):
        value = placeholders[index]
        md = md.replace(escape(f"\x00{index}\x00"), value)
    return md


def _split_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks, current = [], []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > max_len and current:
            chunks.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks
