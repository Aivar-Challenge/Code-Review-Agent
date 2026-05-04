"""
Config module — loads settings from .env via Pydantic Settings.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    # GitHub
    github_token: str = Field(default="", env="GITHUB_TOKEN")
    github_api_base: str = "https://api.github.com"

    # LLM
    llm_provider: Literal["openai", "anthropic", "google", "groq"] = Field(
        default="openai", env="LLM_PROVIDER"
    )
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    google_api_key: str = Field(default="", env="GOOGLE_API_KEY")
    groq_api_key: str = Field(default="", env="GROQ_API_KEY")
    default_model: str = Field(default="gpt-4o-mini", env="DEFAULT_MODEL")

    # Agent defaults
    max_tokens_per_chunk: int = Field(default=6000, env="MAX_TOKENS_PER_CHUNK")
    min_confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="MEDIUM", env="MIN_CONFIDENCE"
    )
    dry_run: bool = Field(default=False, env="DRY_RUN")

    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")

    # DB
    database_url: str = Field(
        default="sqlite+aiosqlite:///./review_agent.db", env="DATABASE_URL"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
