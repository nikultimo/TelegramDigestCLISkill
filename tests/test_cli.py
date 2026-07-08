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
