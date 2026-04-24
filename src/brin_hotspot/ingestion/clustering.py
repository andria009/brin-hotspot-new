from __future__ import annotations

from collections import deque
from math import cos, radians, sqrt

from brin_hotspot.domain import HotspotCluster, HotspotDetection


def cluster_detections(
    detections: list[HotspotDetection],
    *,
    resolution_meters: float,
    neighbor_multiplier: float = 2.0,
) -> list[HotspotCluster]:
    """Group detections using the legacy connected-neighbor distance rule."""
    if not detections:
        return []

    threshold = resolution_meters * neighbor_multiplier
    projected = [_project_to_local_meters(item) for item in detections]
    neighbors = _build_neighbor_graph(projected, threshold)
    groups = _connected_components(neighbors)

    clusters: list[HotspotCluster] = []
    for group in groups:
        grouped = tuple(detections[index] for index in group)
        latitude = sum(item.latitude for item in grouped) / len(grouped)
        longitude = sum(item.longitude for item in grouped) / len(grouped)
        confidence = round(sum(item.confidence for item in grouped) / len(grouped))
        radius = round(resolution_meters * (sqrt(len(grouped)) + 2))
        clusters.append(
            HotspotCluster(
                latitude=latitude,
                longitude=longitude,
                confidence=confidence,
                radius_meters=radius,
                detections=grouped,
            )
        )

    return clusters


def _project_to_local_meters(detection: HotspotDetection) -> tuple[float, float]:
    # Fast equirectangular projection. Good enough for clustering nearby fire pixels.
    meters_per_degree = 111_320.0
    lat = detection.latitude * meters_per_degree
    lon = detection.longitude * meters_per_degree * cos(radians(detection.latitude))
    return lat, lon


def _build_neighbor_graph(points: list[tuple[float, float]], threshold: float) -> list[set[int]]:
    graph = [set() for _ in points]
    for left_index, left in enumerate(points):
        for right_index in range(left_index + 1, len(points)):
            right = points[right_index]
            distance = sqrt((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2)
            if distance < threshold:
                graph[left_index].add(right_index)
                graph[right_index].add(left_index)
    return graph


def _connected_components(graph: list[set[int]]) -> list[list[int]]:
    seen: set[int] = set()
    components: list[list[int]] = []

    for start in range(len(graph)):
        if start in seen:
            continue
        seen.add(start)
        component: list[int] = []
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(graph[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

    return components

