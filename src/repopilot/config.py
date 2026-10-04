"""Runtime configuration."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOPILOT_", extra="ignore")

    allowed_root: Path = Field(default_factory=Path.cwd)
    max_file_bytes: int = Field(default=1_000_000, gt=0)
    embedding_provider: Literal["none", "local", "openai"] = "none"
    embedding_model: str | None = None
    openai_api_key: SecretStr | None = None
    rerank_model: str | None = None
    rerank_candidates: int = Field(default=20, ge=1, le=100)
    investigation_model: str | None = None
    investigation_provider: Literal["openai", "local"] = "openai"
    local_model_url: str = "http://127.0.0.1:8081/v1"
    model_timeout: float = Field(default=120, ge=1, le=300)
    max_agent_calls: int = Field(default=6, ge=1, le=20)
    investigation_workflow: Literal["direct", "langgraph"] = "direct"
