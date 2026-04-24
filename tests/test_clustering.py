from brin_hotspot.ingestion.clustering import cluster_detections
from brin_hotspot.satellites.snpp import find_snpp_files, parse_snpp_file


def test_cluster_detections_groups_nearby_pixels():
    detections = parse_snpp_file(find_snpp_files("tests/fixtures/snpp")[0])

    clusters = cluster_detections(detections, resolution_meters=375)

    assert len(clusters) == 2
    assert len(clusters[0].detections) == 2
    assert clusters[0].confidence == 8
    assert clusters[0].radius_meters == 1280
    assert len(clusters[1].detections) == 1

