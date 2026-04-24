from brin_hotspot.repositories.geo_repository import _normalize_kabupaten


def test_normalize_kabupaten_removes_legacy_prefixes():
    assert _normalize_kabupaten("KAB. SIAK") == "SIAK"
    assert _normalize_kabupaten("KOTA PEKANBARU") == "PEKANBARU"

