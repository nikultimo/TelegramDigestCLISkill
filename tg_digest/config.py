from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    return Settings()
