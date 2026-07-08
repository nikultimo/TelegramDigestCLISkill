from pathlib import Path

from tg_digest.config import get_settings, project_root

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_project_root_prefers_tg_digest_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TG_DIGEST_HOME", str(tmp_path))
    assert project_root() == tmp_path


def test_project_root_falls_back_to_repo_checkout(monkeypatch):
    monkeypatch.delenv("TG_DIGEST_HOME", raising=False)
    assert project_root() == REPO_ROOT


def test_relative_paths_resolve_against_root_from_foreign_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_DIGEST_HOME", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("DIGEST_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("TG_SESSION", raising=False)
    monkeypatch.chdir(tmp_path)
    s = get_settings()
    assert s.db_path.is_absolute()
    assert s.db_path == REPO_ROOT / "data" / "tg_digest.db"
    assert s.digest_output_dir == REPO_ROOT / "digest_output"
    assert Path(s.tg_session).is_absolute()


def test_absolute_env_paths_are_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "digest.db"))
    monkeypatch.setenv("DIGEST_OUTPUT_DIR", str(tmp_path / "out"))
    s = get_settings()
    assert s.db_path == tmp_path / "digest.db"
    assert s.digest_output_dir == tmp_path / "out"
