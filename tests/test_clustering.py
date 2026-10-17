from dataclasses import replace

import pytest

from brin_hotspot.ingestion.clustering import cluster_detections
from brin_hotspot.satellites.snpp import find_snpp_files, parse_snpp_file


def test_cluster_detections_groups_nearby_pixels():
    detections = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])

    clusters = cluster_detections(detections, resolution_meters=375)

    assert len(clusters) == 2
    assert len(clusters[0].detections) == 2
    assert clusters[0].confidence == 8
    assert 265 < clusters[0].radius_meters < 375
    assert len(clusters[1].detections) == 1


def test_adjacent_mode_keeps_a_gap_separate_even_within_legacy_distance():
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    second = replace(first, latitude=first.latitude + 400 / 111_320)
    assert len(cluster_detections([first, second], resolution_meters=375,
                                  projection="latitude_adjusted")) == 1
    assert len(cluster_detections([first, second], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")) == 2


def test_adjacent_mode_keeps_touching_pixels_in_one_cluster():
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    second = replace(first, longitude=first.longitude + 300 / 111_320)
    clusters = cluster_detections([first, second], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")
    assert len(clusters) == 1
    assert len(clusters[0].detections) == 2


def test_adjacent_mode_uses_local_utm_when_geo_dependency_is_available():
    pytest.importorskip("pyproj")
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    second = replace(first, longitude=first.longitude + 300 / 111_320)
    clusters = cluster_detections([first, second], resolution_meters=375,
                                  projection="local_utm", method="adjacent")
    assert len(clusters) == 1


def test_latitude_adjusted_projection_uses_one_reference_latitude():
    first = replace(parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0],
                    latitude=-10, longitude=130)
    second = replace(first, latitude=first.latitude + 720 / 111_320)
    assert len(cluster_detections([first, second], resolution_meters=375)) == 1

