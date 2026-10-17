from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from brin_hotspot.domain import HotspotDetection
from brin_hotspot.repositories.geo_repository import GeoRepository, _normalize_kabupaten


def test_normalize_kabupaten_removes_legacy_prefixes():
    assert _normalize_kabupaten("KAB. SIAK") == "SIAK"
    assert _normalize_kabupaten("KOTA PEKANBARU") == "PEKANBARU"


def test_detection_without_admin_match_is_kept(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def cursor(self):
            return self

        def execute(self, *_):
            pass

        def fetchone(self):
            return None, None, None

    monkeypatch.setattr("brin_hotspot.repositories.geo_repository.psycopg.connect",
                        lambda *_args, **_kwargs: FakeConnection())
    repository = GeoRepository(SimpleNamespace(dsn="unused"))
    detection = HotspotDetection(
        latitude=-1.7, longitude=104.1, confidence=8, observed_at=datetime(2026, 10, 6),
        satellite="snpp", source_file=Path("AFIMG.txt"), scene_id="scene",
        source_station="Parepare",
    )

    assert repository.enrich_detection(detection, duplicate_buffer_degrees=0.00027) is detection

