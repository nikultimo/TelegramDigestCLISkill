import asyncio
import re
from types import SimpleNamespace

from typer.testing import CliRunner

from tg_digest import cli
from tg_digest.cli import app


def test_run_help_shows_range_options():
    result = CliRunner().invoke(app, ["run", "--help"])
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.output)

    assert result.exit_code == 0
    assert "--range" in output
    assert "--from" in output
    assert "--to" in output
    assert "--days" in output


def test_run_rejects_reversed_custom_range(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))

    result = CliRunner().invoke(
        app,
        ["run", "--range", "custom", "--from", "2026-07-09", "--to", "2026-07-08", "--dry-run"],
    )

    assert result.exit_code == 1
    assert "--from must be before or equal to --to" in result.output


def test_db_backfill_dates_command_is_available():
    result = CliRunner().invoke(app, ["db", "backfill-dates", "--help"])

    assert result.exit_code == 0
    assert "backfill missing Telegram publish dates" in result.output


def test_profile_set_and_show_readable_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    runner = CliRunner()

    set_result = runner.invoke(
        app,
        [
            "profile",
            "set",
            "--likes",
            "production ML",
            "--dislikes",
            "crypto hype",
            "--notes",
            "prefer case studies",
            "--min-score",
            "7.5",
        ],
    )
    show_result = runner.invoke(app, ["profile", "show"])

    assert set_result.exit_code == 0
    assert show_result.exit_code == 0
    assert "production ML" in show_result.output
    assert "crypto hype" in show_result.output
    assert "prefer case studies" in show_result.output
    assert "7.5" in show_result.output


def test_profile_tune_updates_readable_profile_with_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    runner = CliRunner()
    runner.invoke(app, ["profile", "set", "--likes", "backend", "--dislikes", "crypto"])

    async def fake_chat(messages, **kwargs):
        return (
            '{"likes_text": "backend, production ML", '
            '"dislikes_text": "crypto, shallow AI lists", '
            '"notes_text": "prefer real cases", '
            '"min_score": 8.0}'
        )

    monkeypatch.setattr("tg_digest.profile.llm.chat", fake_chat)

    result = runner.invoke(app, ["profile", "tune", "меньше AI tool lists, больше production ML"])
    show_result = runner.invoke(app, ["profile", "show"])

    assert result.exit_code == 0
    assert show_result.exit_code == 0
    assert "production ML" in show_result.output
    assert "shallow AI lists" in show_result.output
    assert "8.0" in show_result.output


def test_profile_set_accepts_likes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    profile_file = tmp_path / "profile.md"
    profile_file.write_text("# Interests\n\nAI agents, health, travel, cars", encoding="utf-8")

    runner = CliRunner()
    set_result = runner.invoke(app, ["profile", "set", "--likes-file", str(profile_file)])
    show_result = runner.invoke(app, ["profile", "show"])

    assert set_result.exit_code == 0
    assert show_result.exit_code == 0
    assert "AI agents, health, travel, cars" in show_result.output


def test_profile_init_saves_readable_profile_from_prompts(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    runner = CliRunner()

    init_result = runner.invoke(
        app,
        ["profile", "init"],
        input="production ML, backend architecture\ncrypto hype\nprefer real case studies\n",
    )
    show_result = runner.invoke(app, ["profile", "show"])

    assert init_result.exit_code == 0
    assert show_result.exit_code == 0
    assert "production ML, backend architecture" in show_result.output
    assert "crypto hype" in show_result.output
    assert "prefer real case studies" in show_result.output


def test_profile_reset_clears_profile_and_weights(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    runner = CliRunner()
    runner.invoke(app, ["profile", "set", "--likes", "backend", "--dislikes", "crypto"])

    reset_result = runner.invoke(app, ["profile", "reset", "--yes"])
    show_result = runner.invoke(app, ["profile", "show"])

    assert reset_result.exit_code == 0
    assert show_result.exit_code == 0
    assert "backend" not in show_result.output
    assert "No preferences yet" in show_result.output


def test_check_reports_unset_openai_vars(tmp_path, monkeypatch):
    # Isolate from a real .env at the repo root, which would repopulate the vars
    monkeypatch.setenv("TG_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    result = CliRunner().invoke(app, ["check"])

    assert result.exit_code == 1
    assert "OPENAI_BASE_URL not set" in result.output
    assert "OPENAI_API_KEY not set" in result.output
    assert "OPENAI_MODEL not set" in result.output


def test_check_reports_configured_openai_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    result = CliRunner().invoke(app, ["check"])

    assert result.exit_code == 0
    assert "✅ OPENAI_BASE_URL" in result.output
    assert "✅ OPENAI_API_KEY" in result.output
    assert "✅ OPENAI_MODEL" in result.output


def test_dry_run_does_not_insert_digest_items_and_uses_preview_file(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        scrape_limit=40,
        openai_base_url="http://llm.test/v1",
        openai_api_key="test",
        openai_model="test-model",
        tg_api_id=0,
        tg_api_hash="",
        tg_session="",
        tg_bot_token="",
        tg_chat_id="",
        digest_output_dir=tmp_path,
        db_path=tmp_path / "digest.db",
    )
    monkeypatch.setattr(cli, "_ensure_db", lambda: settings)
    monkeypatch.setattr(cli.db, "get_active_channels", lambda _path: [{"id": 1, "name": "demo"}])

    async def fake_fetch(*args, **kwargs):
        return {
            1: [
                SimpleNamespace(
                    post_id="1",
                    text="Deep agent architecture",
                    url="https://t.me/demo/1",
                    timestamp="2026-07-18T10:00:00+00:00",
                )
            ]
        }

    monkeypatch.setattr(cli.scraper, "fetch_all_channels", fake_fetch)
    monkeypatch.setattr(
        cli.db,
        "insert_post",
        lambda *args, **kwargs: SimpleNamespace(inserted=True, timestamp_updated=False),
    )
    post = {
        "db_id": 1,
        "channel": "demo",
        "text": "Deep agent architecture",
        "url": "https://t.me/demo/1",
        "timestamp": "2026-07-18T10:00:00+00:00",
    }
    monkeypatch.setattr(cli.db, "get_posts_for_digest", lambda *args: [post])
    monkeypatch.setattr(
        cli.db,
        "get_digest_range_stats",
        lambda *args: {
            "dated_in_range": 1,
            "already_digested": 0,
            "eligible": 1,
            "unknown_dates": 0,
        },
    )
    monkeypatch.setattr(cli.db, "get_topic_weights", lambda _path: {})
    monkeypatch.setattr(
        cli.db,
        "get_preference_profile",
        lambda _path: {"likes_text": "agents", "dislikes_text": "", "notes_text": "", "min_score": 7},
    )

    scored = {
        **post,
        "score": 9.0,
        "topics": ["ai agents"],
        "score_reason": "Deep",
        "score_components": {"depth": 3},
    }

    async def fake_score(*args, **kwargs):
        return [scored], 0

    async def fake_digest(*args, **kwargs):
        return [
            {
                "category": "learn",
                "topic_area": "ai_ml",
                "title": "Архитектура агента",
                "description": "Практический разбор.",
                "primary_url": post["url"],
                "sources": [post["url"]],
                "post_indices": [0],
                "_post": scored,
                "_posts": [scored],
            }
        ]

    monkeypatch.setattr(cli.filt, "score_posts", fake_score)
    monkeypatch.setattr(cli.summarizer, "build_digest", fake_digest)
    monkeypatch.setattr(
        cli.db,
        "insert_digest_item",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry run persisted an item")),
    )
    written = {}

    def fake_write(content, output_dir, stem):
        written["stem"] = stem
        return output_dir / f"{stem}.md"

    monkeypatch.setattr(cli.deliver, "write_md", fake_write)

    asyncio.run(cli._run_digest(dry_run=True, range_name="today"))

    assert written["stem"].endswith(".preview")
