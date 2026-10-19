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


def test_adjacent_mode_bridges_small_gaps_but_keeps_larger_gaps_separate():
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    second = replace(first, latitude=first.latitude + 400 / 111_320)
    assert len(cluster_detections([first, second], resolution_meters=375,
                                  projection="latitude_adjusted")) == 1
    assert len(cluster_detections([first, second], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")) == 1
    distant = replace(first, latitude=first.latitude + 800 / 111_320)
    assert len(cluster_detections([first, distant], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")) == 2


def test_adjacent_mode_keeps_touching_pixels_in_one_cluster():
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    second = replace(first, longitude=first.longitude + 300 / 111_320)
    clusters = cluster_detections([first, second], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")
    assert len(clusters) == 1
    assert len(clusters[0].detections) == 2


def test_adjacent_mode_keeps_large_diagonal_gap_separate():
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    diagonal = replace(first, latitude=first.latitude + 800 / 111_320,
                       longitude=first.longitude + 550 / 111_320)
    assert len(cluster_detections([first, diagonal], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")) == 2


def test_viirs_adjacent_mode_matches_close_center_neighbors():
    first = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0]
    diagonal = replace(first, latitude=first.latitude + 500 / 111_320,
                       longitude=first.longitude + 500 / 111_320)
    assert len(cluster_detections([first, diagonal], resolution_meters=375,
                                  projection="latitude_adjusted", method="adjacent")) == 1


@pytest.mark.parametrize("satellite", ["snpp", "noaa20"])
def test_viirs_adjacent_mode_joins_cardinal_gaps_and_overlaps(satellite):
    first = replace(parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0],
                    satellite=satellite)
    east = replace(first, longitude=first.longitude + 700 / 111_320)
    further_east = replace(first, longitude=first.longitude + 1400 / 111_320)
    overlap = replace(first, longitude=first.longitude + 100 / 111_320)
    diagonal = replace(first, latitude=first.latitude + 1400 / 111_320,
                       longitude=first.longitude + 1400 / 111_320)
    clusters = cluster_detections([first, east, further_east, overlap, diagonal],
                                  resolution_meters=375, method="adjacent")
    assert sorted(len(cluster.detections) for cluster in clusters) == [1, 4]


@pytest.mark.parametrize("satellite", ["snpp", "noaa20"])
def test_viirs_adjacent_mode_joins_chained_small_gaps_on_both_axes(satellite):
    first = replace(parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0],
                    satellite=satellite)
    second = replace(first, latitude=first.latitude + 700 / 111_320,
                     longitude=first.longitude + 700 / 111_320)
    third = replace(first, latitude=first.latitude + 1400 / 111_320,
                    longitude=first.longitude + 1400 / 111_320)
    clusters = cluster_detections([first, second, third], resolution_meters=375,
                                  method="adjacent")
    assert len(clusters) == 1
    assert len(clusters[0].detections) == 3


def test_other_satellites_keep_half_pixel_gap_rule():
    first = replace(parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])[0],
                    satellite="aqua")
    east = replace(first, longitude=first.longitude + 1700 / 111_320)
    assert len(cluster_detections([first, east], resolution_meters=1000,
                                  method="adjacent")) == 2


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

