from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5432
    name: str = "hotspot"
    user: str = "hotspot"
    password: SecretStr = SecretStr("hotspot_dev")

    model_config = SettingsConfigDict(
        env_prefix="HOTSPOT_DB_",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def dsn(self) -> str:
        password = self.password.get_secret_value()
        return f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.name}"


class RasterDatabaseSettings(DatabaseSettings):
    name: str = Field(default="raster", validation_alias="HOTSPOT_RASTER_DB_NAME")


class PathSettings(BaseSettings):
    input_dir: Path = Field(default=Path("data/input"), alias="HOTSPOT_INPUT_DIR")
    output_dir: Path = Field(default=Path("data/output"), alias="HOTSPOT_OUTPUT_DIR")
    log_dir: Path = Field(default=Path("logs"), alias="HOTSPOT_LOG_DIR")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class Settings(BaseSettings):
    environment: str = Field(default="development", alias="HOTSPOT_ENV")
    log_level: str = Field(default="INFO", alias="HOTSPOT_LOG_LEVEL")
    log_format: str = Field(default="json", alias="HOTSPOT_LOG_FORMAT")
    hotspot_database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    raster_database: RasterDatabaseSettings = Field(default_factory=RasterDatabaseSettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def ensure_runtime_directories(self) -> None:
        self.paths.input_dir.mkdir(parents=True, exist_ok=True)
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)

    def sanitized_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["hotspot_database"]["password"] = "********"
        payload["raster_database"]["password"] = "********"
        return payload

    def sanitized_json(self) -> str:
        return json.dumps(self.sanitized_dict(), indent=2)


@lru_cache
def get_settings() -> Settings:
    return Settings()
