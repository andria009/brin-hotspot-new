from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psycopg

from brin_hotspot.config import DatabaseSettings


@dataclass(frozen=True)
class MigrationResult:
    version: str
    applied: bool


def migration_dir() -> Path:
    candidates = [
        Path.cwd() / "db" / "migrations",
        Path(__file__).resolve().parents[2] / "db" / "migrations",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def list_migration_files(path: Path | None = None) -> list[Path]:
    path = path or migration_dir()
    return sorted(item for item in path.glob("*.sql") if item.is_file())


def apply_hotspot_migrations(
    database: DatabaseSettings,
    *,
    path: Path | None = None,
) -> list[MigrationResult]:
    return _apply_migrations(
        database,
        path=path,
        include=lambda migration_file: not migration_file.read_text(
            encoding="utf-8"
        ).lstrip().startswith("\\connect"),
    )


def apply_raster_migrations(
    database: DatabaseSettings,
    *,
    path: Path | None = None,
) -> list[MigrationResult]:
    return _apply_migrations(
        database,
        path=path,
        include=lambda migration_file: migration_file.read_text(
            encoding="utf-8"
        ).lstrip().startswith("\\connect raster"),
    )


def _apply_migrations(
    database: DatabaseSettings,
    *,
    path: Path | None,
    include: Callable[[Path], bool],
) -> list[MigrationResult]:
    results: list[MigrationResult] = []
    with psycopg.connect(database.dsn, connect_timeout=5) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version text PRIMARY KEY,
                        applied_at timestamptz NOT NULL DEFAULT now()
                    );
                    """
                )
                for migration_file in list_migration_files(path):
                    sql = migration_file.read_text(encoding="utf-8")
                    if not include(migration_file):
                        continue
                    version = migration_file.stem
                    cursor.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = %s;",
                        (version,),
                    )
                    if cursor.fetchone():
                        results.append(MigrationResult(version=version, applied=False))
                        continue
                    cursor.execute(_strip_psql_meta_commands(sql))
                    results.append(MigrationResult(version=version, applied=True))
    return results


def _strip_psql_meta_commands(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("\\")
    )
