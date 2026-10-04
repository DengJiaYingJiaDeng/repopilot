"""Runtime configuration."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOPILOT_", extra="ignore")

    allowed_root: Path = Field(default_factory=Path.cwd)
    max_file_bytes: int = Field(default=1_000_000, gt=0)
