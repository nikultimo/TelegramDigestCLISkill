from typer.testing import CliRunner

from tg_digest.cli import app


def test_run_help_shows_range_options():
    result = CliRunner().invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "--range" in result.output
    assert "--from" in result.output
    assert "--to" in result.output
    assert "--days" in result.output


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
