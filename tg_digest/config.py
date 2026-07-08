import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """Root against which .env and relative paths are resolved.

    Priority: TG_DIGEST_HOME env var, then the repo checkout containing this
    package (editable install), then the current working directory.
    """
    env_home = os.environ.get("TG_DIGEST_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    package_parent = Path(__file__).resolve().parents[1]
    if (package_parent / "pyproject.toml").exists():
        return package_parent
    return Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = "sk-placeholder"
    openai_model: str = "deepseek/deepseek-v4-flash"

    tg_bot_token: str = ""
    tg_chat_id: str = ""

    # Telethon MTProto credentials
    tg_api_id: int = 0
    tg_api_hash: str = ""
    tg_session: str = "./data/tg_session"

    scrape_limit: int = 20
    digest_output_dir: Path = Path("./digest_output")
    db_path: Path = Path("./data/tg_digest.db")


def get_settings() -> Settings:
    root = project_root()
    settings = Settings(_env_file=root / ".env")
    if not settings.db_path.is_absolute():
        settings.db_path = root / settings.db_path
    if not settings.digest_output_dir.is_absolute():
        settings.digest_output_dir = root / settings.digest_output_dir
    if not Path(settings.tg_session).is_absolute():
        settings.tg_session = str(root / settings.tg_session)
    return settings
