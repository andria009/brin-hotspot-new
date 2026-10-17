from __future__ import annotations

from collections import deque
from math import cos, radians, sqrt
from typing import Literal

from brin_hotspot.domain import HotspotCluster, HotspotDetection

ClusteringProjection = Literal["latitude_adjusted", "epsg4087", "local_utm"]
ClusteringMethod = Literal["distance", "adjacent"]


def cluster_detections(
    detections: list[HotspotDetection],
    *,
    resolution_meters: float,
    neighbor_multiplier: float = 2.0,
    projection: ClusteringProjection = "latitude_adjusted",
    method: ClusteringMethod = "distance",
) -> list[HotspotCluster]:
    """Group detections by nearby centers or touching nominal pixel footprints."""
    if not detections:
        return []

    threshold = resolution_meters * neighbor_multiplier
    projected = _project_detections(detections, projection)
    neighbors = _build_neighbor_graph(projected, threshold, resolution_meters, method)
    groups = _connected_components(neighbors)

    clusters: list[HotspotCluster] = []
    for group in groups:
        grouped = tuple(detections[index] for index in group)
        latitude = sum(item.latitude for item in grouped) / len(grouped)
        longitude = sum(item.longitude for item in grouped) / len(grouped)
        confidence = round(sum(item.confidence for item in grouped) / len(grouped))
        center_x = sum(projected[index][0] for index in group) / len(group)
        center_y = sum(projected[index][1] for index in group) / len(group)
        radius = round(
            max(
                sqrt((projected[index][0] - center_x) ** 2 +
                     (projected[index][1] - center_y) ** 2)
                for index in group
            ) + resolution_meters / sqrt(2)
        )
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


def _project_detections(
    detections: list[HotspotDetection],
    projection: ClusteringProjection,
) -> list[tuple[float, float]]:
    if projection == "latitude_adjusted":
        reference_latitude = sum(item.latitude for item in detections) / len(detections)
        return [_project_to_local_meters(item, reference_latitude) for item in detections]
    if projection == "epsg4087":
        return _project_to_epsg4087(detections)
    if projection == "local_utm":
        return _project_to_local_utm(detections)
    raise ValueError(f"Unsupported clustering projection: {projection}")


def _project_to_local_meters(
    detection: HotspotDetection, reference_latitude: float
) -> tuple[float, float]:
    # Fast equirectangular approximation retained for operational comparison.
    meters_per_degree = 111_320.0
    lat = detection.latitude * meters_per_degree
    lon = detection.longitude * meters_per_degree * cos(radians(reference_latitude))
    return lat, lon


def _project_to_epsg4087(detections: list[HotspotDetection]) -> list[tuple[float, float]]:
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError(
            "EPSG:4087 clustering requires pyproj. Install the geo optional dependency."
        ) from exc

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:4087", always_xy=True)
    longitudes = [detection.longitude for detection in detections]
    latitudes = [detection.latitude for detection in detections]
    xs, ys = transformer.transform(longitudes, latitudes)
    return list(zip(xs, ys, strict=True))


def _project_to_local_utm(detections: list[HotspotDetection]) -> list[tuple[float, float]]:
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError(
            "Local UTM clustering requires pyproj. Install the geo optional dependency."
        ) from exc

    longitude = sum(item.longitude for item in detections) / len(detections)
    latitude = sum(item.latitude for item in detections) / len(detections)
    # shortcut: one UTM zone per source scene; split a scene first if it spans many zones.
    zone = min(60, max(1, int((longitude + 180) // 6) + 1))
    srid = (32600 if latitude >= 0 else 32700) + zone
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{srid}", always_xy=True)
    xs, ys = transformer.transform(
        [item.longitude for item in detections], [item.latitude for item in detections]
    )
    return list(zip(xs, ys, strict=True))


def _build_neighbor_graph(
    points: list[tuple[float, float]],
    threshold: float,
    resolution_meters: float,
    method: ClusteringMethod,
) -> list[set[int]]:
    graph = [set() for _ in points]
    for left_index, left in enumerate(points):
        for right_index in range(left_index + 1, len(points)):
            right = points[right_index]
            dx, dy = abs(left[0] - right[0]), abs(left[1] - right[1])
            connected = (
                sqrt(max(dx - resolution_meters, 0)**2 +
                     max(dy - resolution_meters, 0)**2) <= resolution_meters / 2
                if method == "adjacent" else sqrt(dx**2 + dy**2) < threshold
            )
            if connected:
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
