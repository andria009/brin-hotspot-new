from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SatelliteInputSettings:
    satellite: str
    resolution_meters: float
    input_subdir: str | None = None
    source_station: str = "Parepare"
    neighbor_multiplier: float = 2.0
    duplicate_buffer_degrees: float = 0.00027027027


@dataclass(frozen=True)
class SourceItem:
    path: Path
    files: tuple[Path, ...]

    @classmethod
    def single(cls, path: Path) -> SourceItem:
        return cls(path=path, files=(path,))
