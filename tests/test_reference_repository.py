from pathlib import Path

from brin_hotspot.repositories.reference_repository import load_geojson_features


def test_load_geojson_features_reads_basic_properties():
    features = load_geojson_features(
        Path("tests/fixtures/reference/province.geojson"),
        id_field="gid",
        name_field="wa",
    )

    assert len(features) == 1
    assert features[0].gid == 1
    assert features[0].name == "TEST PROVINCE"
    assert features[0].geometry["type"] == "Polygon"


def test_load_geojson_features_reads_parent_ids():
    features = load_geojson_features(
        Path("tests/fixtures/reference/kecamatan.geojson"),
        id_field="gid",
        name_field="wa",
        prov_id_field="prov_id",
        kab_id_field="kab_id",
    )

    assert len(features) == 1
    assert features[0].prov_id == 1
    assert features[0].kab_id == 5

