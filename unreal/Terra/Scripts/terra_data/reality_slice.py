#!/usr/bin/env python3
"""Physical audit and deterministic reality-slice layout for TERRA capital.

The existing ``export_ue/capital`` layout is treated as immutable evidence,
not edited.  This module first measures it as a physical city, then generates
one explicitly bounded, independently validated ward-scale slice.  Only the
Python standard library is required.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import hashlib
import json
import math
import random
import re
import statistics
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


GENERATOR_VERSION = "1.0.0"
AUDIT_SCHEMA = "terra.capital-physical-audit/v1"
LAYOUT_SCHEMA = "terra.reality-slice-layout/v1"
SLICE_ID = "raflir-south-gate-market-ward-v1"
SLICE_NAMESPACE_UUID = uuid.UUID("1ac37594-cd21-5bbf-90cd-0908a66c4e3b")
CM2_PER_M2 = 10_000.0
CM2_PER_KM2 = 10_000_000_000.0
EPSILON = 1e-7
REQUIRED_SCOPE_CLAIM = "one_ward_reality_slice_not_full_city"
MIN_WARD_RESIDENTS = 800
MAX_WARD_RESIDENTS = 1_500
MAX_BUILDING_GRADE_PERCENT = 5.0
REQUIRED_GATE_COUNT = 1
# 4 cm² across a 12-15 m serialized party wall corresponds to only a few
# micrometres of coordinate residue.  This constant is code-authoritative;
# input JSON cannot enlarge it to hide a real overlap.
OVERLAP_SERIALIZATION_TOLERANCE_CM2 = 4.0
EXPECTED_VALIDATION_POLICY: dict[str, Any] = {
    "building_overlap_allowed": False,
    "party_wall_touch_allowed": True,
    "overlap_numeric_tolerance_cm2": OVERLAP_SERIALIZATION_TOLERANCE_CM2,
    "road_overlap_only_by_explicit_id": True,
    "maximum_building_grade_percent": MAX_BUILDING_GRADE_PERCENT,
    "population_capacity_range": [MIN_WARD_RESIDENTS, MAX_WARD_RESIDENTS],
    "required_gate_count": REQUIRED_GATE_COUNT,
}


Point = tuple[float, float]
Polygon = list[Point]


@dataclasses.dataclass(frozen=True, order=True)
class LayoutFinding:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rect_polygon(center: Sequence[float], size: Sequence[float], yaw_deg: float) -> Polygon:
    """Return a rectangle where local +X is the front normal."""

    cx, cy = float(center[0]), float(center[1])
    depth, width = float(size[0]), float(size[1])
    angle = math.radians(float(yaw_deg))
    cosine, sine = math.cos(angle), math.sin(angle)
    points: Polygon = []
    for local_x, local_y in (
        (depth / 2.0, width / 2.0),
        (-depth / 2.0, width / 2.0),
        (-depth / 2.0, -width / 2.0),
        (depth / 2.0, -width / 2.0),
    ):
        points.append(
            (
                cx + cosine * local_x - sine * local_y,
                cy + sine * local_x + cosine * local_y,
            )
        )
    return points


def polygon_signed_area(polygon: Sequence[Point]) -> float:
    return sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    ) / 2.0


def polygon_area(polygon: Sequence[Point]) -> float:
    return abs(polygon_signed_area(polygon))


def polygon_axes(polygon: Sequence[Point]) -> Iterable[Point]:
    for index in range(len(polygon)):
        start = polygon[index]
        end = polygon[(index + 1) % len(polygon)]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length > EPSILON:
            yield (-dy / length, dx / length)


def polygons_overlap(first: Sequence[Point], second: Sequence[Point], *, touching_is_overlap: bool = False) -> bool:
    """Separating-axis test for convex polygons."""

    axes = list(polygon_axes(first)) + list(polygon_axes(second))
    for axis in axes:
        first_projection = [point[0] * axis[0] + point[1] * axis[1] for point in first]
        second_projection = [point[0] * axis[0] + point[1] * axis[1] for point in second]
        if touching_is_overlap:
            separated = max(first_projection) < min(second_projection) - EPSILON or max(second_projection) < min(first_projection) - EPSILON
        else:
            separated = max(first_projection) <= min(second_projection) + EPSILON or max(second_projection) <= min(first_projection) + EPSILON
        if separated:
            return False
    return True


def convex_intersection(subject: Sequence[Point], clip: Sequence[Point]) -> Polygon:
    """Sutherland-Hodgman intersection, used only after an OBB overlap."""

    output = list(subject)
    orientation = 1.0 if polygon_signed_area(clip) >= 0 else -1.0
    for clip_index in range(len(clip)):
        edge_start = clip[clip_index]
        edge_end = clip[(clip_index + 1) % len(clip)]
        input_points = output
        output = []
        if not input_points:
            break

        def inside(point: Point) -> bool:
            cross = (edge_end[0] - edge_start[0]) * (point[1] - edge_start[1]) - (edge_end[1] - edge_start[1]) * (point[0] - edge_start[0])
            return orientation * cross >= -EPSILON

        def intersection(start: Point, end: Point) -> Point:
            dx, dy = end[0] - start[0], end[1] - start[1]
            cx, cy = edge_end[0] - edge_start[0], edge_end[1] - edge_start[1]
            denominator = dx * cy - dy * cx
            if abs(denominator) < EPSILON:
                return end
            factor = ((edge_start[0] - start[0]) * cy - (edge_start[1] - start[1]) * cx) / denominator
            return start[0] + factor * dx, start[1] + factor * dy

        previous = input_points[-1]
        for current in input_points:
            if inside(current):
                if not inside(previous):
                    output.append(intersection(previous, current))
                output.append(current)
            elif inside(previous):
                output.append(intersection(previous, current))
            previous = current
    return output


def point_segment_nearest(point: Point, start: Point, end: Point) -> tuple[float, Point, Point, float]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    factor = 0.0 if squared <= EPSILON else max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / squared))
    nearest = start[0] + factor * dx, start[1] + factor * dy
    length = math.sqrt(squared) if squared > EPSILON else 1.0
    tangent = dx / length, dy / length
    return math.dist(point, nearest), nearest, tangent, factor


def nearest_on_paths(point: Point, paths: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for path in paths:
        points = path["points_cm"]
        for segment_index, (start, end) in enumerate(zip(points, points[1:])):
            distance, nearest, tangent, factor = point_segment_nearest(
                point,
                (float(start[0]), float(start[1])),
                (float(end[0]), float(end[1])),
            )
            if best is None or distance < best["centerline_distance_cm"]:
                best = {
                    "path_id": path.get("id"),
                    "segment_index": segment_index,
                    "centerline_distance_cm": distance,
                    "nearest_cm": nearest,
                    "tangent": tangent,
                    "factor": factor,
                    "width_cm": float(path["width_cm"]),
                }
    if best is None:
        raise ValueError("At least one non-empty path is required")
    best["edge_distance_cm"] = max(0.0, best["centerline_distance_cm"] - best["width_cm"] / 2.0)
    return best


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(first_start: Point, first_end: Point, second_start: Point, second_end: Point) -> bool:
    values = (
        _orientation(first_start, first_end, second_start),
        _orientation(first_start, first_end, second_end),
        _orientation(second_start, second_end, first_start),
        _orientation(second_start, second_end, first_end),
    )
    return values[0] * values[1] <= EPSILON and values[2] * values[3] <= EPSILON


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    sign: bool | None = None
    for index in range(len(polygon)):
        cross = _orientation(polygon[index], polygon[(index + 1) % len(polygon)], point)
        if abs(cross) <= EPSILON:
            continue
        current = cross > 0
        if sign is None:
            sign = current
        elif sign != current:
            return False
    return True


def segment_polygon_distance(start: Point, end: Point, polygon: Sequence[Point]) -> float:
    if point_in_polygon(start, polygon) or point_in_polygon(end, polygon):
        return 0.0
    for index in range(len(polygon)):
        edge_start, edge_end = polygon[index], polygon[(index + 1) % len(polygon)]
        if segments_intersect(start, end, edge_start, edge_end):
            return 0.0
    distances: list[float] = []
    for vertex in polygon:
        distances.append(point_segment_nearest(vertex, start, end)[0])
    for endpoint in (start, end):
        for index in range(len(polygon)):
            edge_start, edge_end = polygon[index], polygon[(index + 1) % len(polygon)]
            distances.append(point_segment_nearest(endpoint, edge_start, edge_end)[0])
    return min(distances)


def polygon_path_clearance(polygon: Sequence[Point], path: Mapping[str, Any]) -> float:
    centerline_distance = min(
        segment_polygon_distance(
            (float(start[0]), float(start[1])),
            (float(end[0]), float(end[1])),
            polygon,
        )
        for start, end in zip(path["points_cm"], path["points_cm"][1:])
    )
    return centerline_distance - float(path["width_cm"]) / 2.0


def nearest_polygon_boundary(point: Point, polygon: Sequence[Point]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for index in range(len(polygon)):
        start, end = polygon[index], polygon[(index + 1) % len(polygon)]
        distance, nearest, tangent, factor = point_segment_nearest(point, start, end)
        if best is None or distance < best["distance_cm"]:
            best = {
                "distance_cm": distance,
                "nearest_cm": nearest,
                "tangent": tangent,
                "edge_index": index,
                "factor": factor,
            }
    if best is None:
        raise ValueError("Polygon is empty")
    return best


class TerrainSampler:
    """Bilinear height sampler for the regular OBJ grid exported by TERRA."""

    def __init__(self, xs: Sequence[float], ys: Sequence[float], heights: Mapping[tuple[float, float], float]) -> None:
        self.xs = list(xs)
        self.ys = list(ys)
        self.heights = dict(heights)
        if len(self.xs) < 2 or len(self.ys) < 2 or len(self.heights) != len(self.xs) * len(self.ys):
            raise ValueError("Terrain OBJ is not a complete regular XY grid")

    @classmethod
    def from_obj(cls, path: Path) -> "TerrainSampler":
        vertices: list[tuple[float, float, float]] = []
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("v "):
                    tokens = line.split()
                    if len(tokens) >= 4:
                        vertices.append((float(tokens[1]), float(tokens[2]), float(tokens[3])))
        xs = sorted({vertex[0] for vertex in vertices})
        ys = sorted({vertex[1] for vertex in vertices})
        heights = {(x, y): z for x, y, z in vertices}
        return cls(xs, ys, heights)

    def sample(self, x: float, y: float) -> float:
        if x < self.xs[0] - EPSILON or x > self.xs[-1] + EPSILON or y < self.ys[0] - EPSILON or y > self.ys[-1] + EPSILON:
            raise ValueError(f"Terrain sample lies outside grid: {(x, y)}")
        x_index = max(0, min(len(self.xs) - 2, bisect.bisect_right(self.xs, x) - 1))
        y_index = max(0, min(len(self.ys) - 2, bisect.bisect_right(self.ys, y) - 1))
        x0, x1 = self.xs[x_index], self.xs[x_index + 1]
        y0, y1 = self.ys[y_index], self.ys[y_index + 1]
        tx = (x - x0) / (x1 - x0)
        ty = (y - y0) / (y1 - y0)
        return (
            (1.0 - tx) * (1.0 - ty) * self.heights[(x0, y0)]
            + tx * (1.0 - ty) * self.heights[(x1, y0)]
            + (1.0 - tx) * ty * self.heights[(x0, y1)]
            + tx * ty * self.heights[(x1, y1)]
        )


def _quantile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[int(round((len(ordered) - 1) * fraction))]


def _frontage_measure(building: Mapping[str, Any], roads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    x, y = float(building["pos_cm"][0]), float(building["pos_cm"][1])
    depth = float(building["size_cm"][0])
    angle = math.radians(float(building["yaw_deg"]))
    normal = math.cos(angle), math.sin(angle)
    front = x + normal[0] * depth / 2.0, y + normal[1] * depth / 2.0
    nearest = nearest_on_paths(front, roads)
    toward = nearest["nearest_cm"][0] - front[0], nearest["nearest_cm"][1] - front[1]
    toward_length = math.hypot(*toward)
    facing_dot = 0.0 if toward_length <= EPSILON else (normal[0] * toward[0] + normal[1] * toward[1]) / toward_length
    tangent = nearest["tangent"]
    facade_parallel_deviation = math.degrees(math.asin(min(1.0, abs(normal[0] * tangent[0] + normal[1] * tangent[1]))))
    return {
        "front_midpoint_cm": [round(front[0], 3), round(front[1], 3)],
        "nearest_road_index": nearest["path_id"],
        "road_edge_distance_m": round(nearest["edge_distance_cm"] / 100.0, 3),
        "front_faces_road_dot": round(facing_dot, 6),
        "facade_parallel_deviation_deg": round(facade_parallel_deviation, 3),
    }


def audit_capital(project_root: Path, comparison_population: int = 2_300_000) -> dict[str, Any]:
    """Measure the current capital as geometry rather than a JSON schema."""

    scene_root = project_root / "export_ue" / "capital"
    meta = json.loads((scene_root / "meta.json").read_text(encoding="utf-8"))
    document = json.loads((scene_root / "buildings.json").read_text(encoding="utf-8"))
    buildings: list[dict[str, Any]] = document["buildings"]
    roads = [
        {"id": index, "width_cm": road["width_cm"], "points_cm": road["points_cm"]}
        for index, road in enumerate(document["roads"])
    ]
    polygons = [rect_polygon(building["pos_cm"], building["size_cm"], building["yaw_deg"]) for building in buildings]

    overlaps: list[dict[str, Any]] = []
    compositional_pairs = {
        ("gate", "wall_segment"),
        ("tower", "wall_segment"),
        ("wall_segment", "wall_segment"),
    }
    for first_index in range(len(buildings)):
        for second_index in range(first_index + 1, len(buildings)):
            if not polygons_overlap(polygons[first_index], polygons[second_index]):
                continue
            intersection = convex_intersection(polygons[first_index], polygons[second_index])
            overlap_area_m2 = polygon_area(intersection) / CM2_PER_M2 if intersection else 0.0
            pair = tuple(sorted((buildings[first_index]["type"], buildings[second_index]["type"])))
            overlaps.append(
                {
                    "a_index": first_index,
                    "a_type": buildings[first_index]["type"],
                    "b_index": second_index,
                    "b_type": buildings[second_index]["type"],
                    "overlap_area_m2": round(overlap_area_m2, 4),
                    "classification": "likely_compositional_but_not_booleaned" if pair in compositional_pairs else "unintended_collision",
                }
            )

    road_collisions: list[dict[str, Any]] = []
    for building_index, polygon in enumerate(polygons):
        for road in roads:
            clearance = polygon_path_clearance(polygon, road)
            if clearance < -EPSILON:
                road_collisions.append(
                    {
                        "building_index": building_index,
                        "building_type": buildings[building_index]["type"],
                        "road_index": road["id"],
                        "penetration_m": round(-clearance / 100.0, 3),
                    }
                )

    all_x = [point[0] for polygon in polygons for point in polygon]
    all_y = [point[1] for polygon in polygons for point in polygon]
    bounds_width = max(all_x) - min(all_x)
    bounds_height = max(all_y) - min(all_y)
    layout_bbox_km2 = bounds_width * bounds_height / CM2_PER_KM2
    terrain_km2 = float(meta["terrain"]["size_cm"]) ** 2 / CM2_PER_KM2
    # The wall coordinates define a 356 m by 356 m enclosure.
    wall_enclosure_km2 = 356.0 * 356.0 / 1_000_000.0
    source_population = int(meta["population"])
    total_footprint_m2 = sum(float(building["size_cm"][0]) * float(building["size_cm"][1]) for building in buildings) / CM2_PER_M2
    houses = [building for building in buildings if building["type"] == "house_gable"]
    residential_gfa_m2 = sum(
        float(building["size_cm"][0])
        * float(building["size_cm"][1])
        / CM2_PER_M2
        * max(1, round(float(building["size_cm"][2]) / 300.0))
        for building in houses
    )

    frontage_types = {"house_gable", "market_stall", "temple", "gate"}
    frontage_records = [
        {"building_index": index, "building_type": building["type"], **_frontage_measure(building, roads)}
        for index, building in enumerate(buildings)
        if building["type"] in frontage_types
    ]
    house_frontages = [record for record in frontage_records if record["building_type"] == "house_gable"]
    market_frontages = [record for record in frontage_records if record["building_type"] == "market_stall"]

    player_xy = (float(meta["player_start_cm"][0]), float(meta["player_start_cm"][1]))
    player_road = nearest_on_paths(player_xy, roads)
    special_access: list[dict[str, Any]] = []
    for index, building in enumerate(buildings):
        if building["type"] not in {"gate", "market_stall", "well", "temple"}:
            continue
        record = _frontage_measure(building, roads)
        center_nearest = nearest_on_paths((float(building["pos_cm"][0]), float(building["pos_cm"][1])), roads)
        special_access.append(
            {
                "building_index": index,
                "type": building["type"],
                "center_to_road_edge_m": round(center_nearest["edge_distance_cm"] / 100.0, 3),
                **record,
            }
        )

    def density(population: int, area: float) -> float:
        return population / area if area > 0 else math.inf

    audit = {
        "schema": AUDIT_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "source": {
            "run_id": meta["run_id"],
            "scene": "capital",
            "source_declared_population": source_population,
            "comparison_population": comparison_population,
            "comparison_note": "2.3M is evaluated because it was requested; source meta actually declares 8,367,729",
            "meta_sha256": sha256_file(scene_root / "meta.json"),
            "buildings_sha256": sha256_file(scene_root / "buildings.json"),
        },
        "geometry": {
            "terrain_area_km2": round(terrain_km2, 6),
            "layout_bbox": {
                "min_cm": [round(min(all_x), 3), round(min(all_y), 3)],
                "max_cm": [round(max(all_x), 3), round(max(all_y), 3)],
                "width_m": round(bounds_width / 100.0, 3),
                "height_m": round(bounds_height / 100.0, 3),
                "area_km2": round(layout_bbox_km2, 6),
            },
            "wall_enclosure_area_km2": round(wall_enclosure_km2, 6),
            "building_count": len(buildings),
            "building_types": dict(sorted(Counter(building["type"] for building in buildings).items())),
            "total_pairwise_footprint_m2": round(total_footprint_m2, 3),
            "house_count": len(houses),
            "estimated_house_gfa_m2": round(residential_gfa_m2, 3),
            "road_count": len(roads),
            "road_centerline_km": round(
                sum(math.dist(start[:2], end[:2]) for road in roads for start, end in zip(road["points_cm"], road["points_cm"][1:])) / 100_000.0,
                6,
            ),
        },
        "density": {
            "source_population": {
                "people_per_proxy": round(source_population / len(buildings), 3),
                "people_per_house_proxy": round(source_population / len(houses), 3),
                "people_per_km2_terrain": round(density(source_population, terrain_km2), 3),
                "people_per_km2_layout_bbox": round(density(source_population, layout_bbox_km2), 3),
                "people_per_km2_wall_enclosure": round(density(source_population, wall_enclosure_km2), 3),
                "people_per_estimated_house_gfa_m2": round(source_population / residential_gfa_m2, 3),
            },
            "comparison_2_3m": {
                "people_per_proxy": round(comparison_population / len(buildings), 3),
                "people_per_house_proxy": round(comparison_population / len(houses), 3),
                "people_per_km2_terrain": round(density(comparison_population, terrain_km2), 3),
                "people_per_km2_layout_bbox": round(density(comparison_population, layout_bbox_km2), 3),
                "people_per_km2_wall_enclosure": round(density(comparison_population, wall_enclosure_km2), 3),
                "people_per_estimated_house_gfa_m2": round(comparison_population / residential_gfa_m2, 3),
            },
        },
        "overlaps": {
            "pair_count": len(overlaps),
            "unintended_pair_count": sum(item["classification"] == "unintended_collision" for item in overlaps),
            "pairwise_overlap_area_m2": round(sum(item["overlap_area_m2"] for item in overlaps), 3),
            "type_pairs": {
                " + ".join(pair): count
                for pair, count in sorted(Counter(tuple(sorted((item["a_type"], item["b_type"]))) for item in overlaps).items())
            },
            "pairs": overlaps,
        },
        "roads_and_frontage": {
            "building_road_collision_count": len(road_collisions),
            "building_road_collisions": road_collisions,
            "house_frontage": _frontage_summary(house_frontages),
            "market_frontage": _frontage_summary(market_frontages),
            "frontage_records": frontage_records,
        },
        "access": {
            "public_square_status": "not_explicit_in_source",
            "player_start_used_only_as_square_proxy_cm": [player_xy[0], player_xy[1]],
            "player_start_to_road_edge_m": round(player_road["edge_distance_cm"] / 100.0, 3),
            "player_start_to_road_centerline_m": round(player_road["centerline_distance_cm"] / 100.0, 3),
            "special_buildings": special_access,
            "gate_count": sum(building["type"] == "gate" for building in buildings),
            "market_stall_count": sum(building["type"] == "market_stall" for building in buildings),
        },
        "conclusion": {
            "physical_city_status": "blockout_not_population_scale_city",
            "why": [
                "300 proxies cannot physically represent either 2.3M or the 8.37M declared in source meta at this footprint",
                "the source contains OBB collisions and road/building penetrations",
                "most house facade normals are not simultaneously close, parallel, and facing their nearest road",
                "no explicit public-square polygon or pedestrian/service access graph exists",
            ],
            "safe_use": "historical macro-placement/blockout evidence only; not a street-level reality claim",
        },
    }
    audit_without_digest = dict(audit)
    audit["audit_digest"] = "sha256:" + hashlib.sha256(canonical_json(audit_without_digest).encode("utf-8")).hexdigest()
    return audit


def _frontage_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    distances = [float(record["road_edge_distance_m"]) for record in records]
    return {
        "count": len(records),
        "road_edge_distance_median_m": round(statistics.median(distances), 3) if distances else None,
        "road_edge_distance_p90_m": round(_quantile(distances, 0.9), 3) if distances else None,
        "within_10m_count": sum(distance <= 10.0 for distance in distances),
        "facade_parallel_within_20deg_count": sum(float(record["facade_parallel_deviation_deg"]) <= 20.0 for record in records),
        "front_faces_road_dot_gt_0_25_count": sum(float(record["front_faces_road_dot"]) > 0.25 for record in records),
        "near_parallel_and_facing_count": sum(
            float(record["road_edge_distance_m"]) <= 10.0
            and float(record["facade_parallel_deviation_deg"]) <= 20.0
            and float(record["front_faces_road_dot"]) > 0.25
            for record in records
        ),
    }


def _local_to_world(origin: Sequence[float], point: Sequence[float]) -> list[float]:
    return [round(float(origin[0]) + float(point[0]), 3), round(float(origin[1]) + float(point[1]), 3)]


def _path_with_terrain(
    sampler: TerrainSampler,
    origin: Sequence[float],
    path_id: str,
    path_class: str,
    width_cm: float,
    local_points: Sequence[Sequence[float]],
) -> dict[str, Any]:
    points: list[list[float]] = []
    for local in local_points:
        world = _local_to_world(origin, local)
        points.append([world[0], world[1], round(sampler.sample(world[0], world[1]), 3)])
    return {
        "id": path_id,
        "class": path_class,
        "width_cm": float(width_cm),
        "points_cm": points,
        "surface": "compacted_earth_with_stone_drains",
    }


def _terrain_binding(sampler: TerrainSampler, polygon: Sequence[Point], center: Point) -> dict[str, Any]:
    corner_heights = [sampler.sample(point[0], point[1]) for point in polygon]
    center_height = sampler.sample(center[0], center[1])
    horizontal_span = max(
        math.dist(polygon[0], polygon[1]),
        math.dist(polygon[1], polygon[2]),
        1.0,
    )
    delta = max(corner_heights) - min(corner_heights)
    return {
        "sample_method": "bilinear_from_exported_terrain_obj_grid",
        "center_z_cm": round(center_height, 3),
        "corner_z_cm": [round(value, 3) for value in corner_heights],
        "base_z_cm": round(max(corner_heights), 3),
        "max_corner_delta_cm": round(delta, 3),
        "grade_percent": round(delta / horizontal_span * 100.0, 4),
        "foundation_strategy": "stepped_plinth_cut_fill",
    }


def _partition_frontage(length_cm: float, rng: random.Random) -> list[float]:
    count = max(1, int(round(length_cm / 850.0)))
    weights = [rng.uniform(0.9, 1.1) for _ in range(count)]
    total_weight = sum(weights)
    widths = [round(length_cm * weight / total_weight, 3) for weight in weights]
    widths[-1] = round(length_cm - sum(widths[:-1]), 3)
    if min(widths) < 600.0 or max(widths) > 1_150.0:
        raise ValueError(f"Frontage partition outside supported width: {widths}")
    return widths


def _zone_for_block(x_index: int, y_index: int) -> str:
    if y_index == 0:
        return "gate_craft_mixed"
    if y_index in (1, 2) and x_index in (1, 2):
        return "market_mixed"
    if x_index in (0, 3):
        return "craft_residential"
    return "courtyard_residential"


def _prototype_and_floors(zone: str, sequence: int, rng: random.Random) -> tuple[str, int, float]:
    if zone == "gate_craft_mixed":
        prototype = "adobe_workshop_house" if sequence % 3 == 0 else "adobe_rowhouse"
        floors = rng.choice((1, 2, 2, 2, 3))
        residential_fraction = 0.45 if prototype == "adobe_workshop_house" else 0.75
    elif zone == "market_mixed":
        prototype = "adobe_shop_house" if sequence % 2 == 0 else "adobe_rowhouse"
        floors = rng.choice((2, 2, 3, 3, 3))
        residential_fraction = 0.55 if prototype == "adobe_shop_house" else 0.78
    elif zone == "craft_residential":
        prototype = "adobe_courtyard_house" if sequence % 4 else "adobe_workshop_house"
        floors = rng.choice((1, 2, 2, 2, 3))
        residential_fraction = 0.82 if prototype == "adobe_courtyard_house" else 0.42
    else:
        prototype = "adobe_courtyard_house"
        floors = rng.choice((2, 2, 3, 3, 3))
        residential_fraction = 0.88
    return prototype, floors, residential_fraction


def _capacity(footprint_m2: float, floors: int, residential_fraction: float, prototype: str) -> dict[str, int | float]:
    gross = footprint_m2 * floors
    net = gross * 0.76
    # A compact premodern household assumption: 16 net residential m² per
    # resident.  It yields ~20k residents/km² for this ward, not millions.
    residents = int(math.floor(net * residential_fraction / 16.0))
    employment_area = net * (1.0 - residential_fraction)
    job_area = 18.0 if "shop" in prototype or "workshop" in prototype else 28.0
    jobs = int(math.floor(employment_area / job_area))
    return {
        "gross_floor_area_m2": round(gross, 3),
        "residents_capacity": max(0, residents),
        "jobs_capacity": max(0, jobs),
    }


def _entity_id(key: str, payload: Mapping[str, Any]) -> str:
    seed = canonical_json({"slice_id": SLICE_ID, "key": key, "payload": payload})
    return str(uuid.uuid5(SLICE_NAMESPACE_UUID, seed))


def _building_draft(
    sampler: TerrainSampler,
    origin: Sequence[float],
    *,
    key: str,
    block_id: str,
    kind: str,
    zone: str,
    prototype: str,
    local_center: Sequence[float],
    yaw_deg: float,
    depth_cm: float,
    width_cm: float,
    floors: int,
    residential_fraction: float,
    frontage_target: str | None,
    front_entry_local: Sequence[float] | None,
    service_target: str | None,
    service_entry_local: Sequence[float] | None,
    road_overlap_allowed: Sequence[str] = (),
) -> dict[str, Any]:
    world_center = _local_to_world(origin, local_center)
    polygon = rect_polygon(world_center, (depth_cm, width_cm), yaw_deg)
    terrain = _terrain_binding(sampler, polygon, (world_center[0], world_center[1]))
    payload = {
        "block_id": block_id,
        "kind": kind,
        "prototype": prototype,
        "local_center_cm": [round(float(local_center[0]), 3), round(float(local_center[1]), 3)],
        "yaw_deg": round(float(yaw_deg), 3),
        "size_cm": [round(float(depth_cm), 3), round(float(width_cm), 3), round(float(floors) * 320.0, 3)],
    }
    identity = _entity_id(key, payload)
    building: dict[str, Any] = {
        "id": identity,
        "key": key,
        "identity_status": "generator_authoritative_within_slice_v1",
        "block_id": block_id,
        "kind": kind,
        "zone": zone,
        "prototype": prototype,
        "architecture": {
            "form": "attached_courtyard_or_row_building",
            "roof": "flat_timber_reed_earth_roof",
            "wall": "adobe_or_mud_brick_with_lime_earth_plaster",
            "facade_rule": "local_plus_x_is_entrance_normal",
            "gabled_roof": False,
        },
        "pos_cm": [world_center[0], world_center[1], terrain["base_z_cm"]],
        "yaw_deg": round(float(yaw_deg), 3),
        "size_cm": payload["size_cm"],
        "floors": floors,
        "footprint_cm": [[round(point[0], 3), round(point[1], 3)] for point in polygon],
        "terrain": terrain,
        "road_overlap_allowed": list(road_overlap_allowed),
    }
    building["capacity"] = _capacity(depth_cm * width_cm / CM2_PER_M2, floors, residential_fraction, prototype)
    if frontage_target and front_entry_local:
        entry = _local_to_world(origin, front_entry_local)
        entry_z = sampler.sample(entry[0], entry[1])
        building["frontage"] = {
            "target_id": frontage_target,
            "entry_cm": [entry[0], entry[1], round(entry_z, 3)],
            "max_clearance_cm": 300.0,
        }
    else:
        building["frontage"] = None
    if service_target and service_entry_local:
        entry = _local_to_world(origin, service_entry_local)
        entry_z = sampler.sample(entry[0], entry[1])
        building["service_access"] = {
            "target_id": service_target,
            "entry_cm": [entry[0], entry[1], round(entry_z, 3)],
            "max_clearance_cm": 200.0,
        }
    else:
        building["service_access"] = None
    return building


def _generate_frontage_row(
    sampler: TerrainSampler,
    origin: Sequence[float],
    rng: random.Random,
    *,
    block_id: str,
    zone: str,
    bounds: tuple[float, float, float, float],
    side: str,
    road_id: str,
    exclusion: Polygon,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None]:
    xmin, xmax, ymin, ymax = bounds
    frontage_start, frontage_end = xmin + 200.0, xmax - 200.0
    widths = _partition_frontage(frontage_end - frontage_start, rng)
    depth = float(rng.choice((1_250, 1_350, 1_450, 1_550)))
    front_setback = 100.0
    alley_width = 240.0
    alley_rear_gap = 150.0
    if side == "south":
        normal = (0.0, -1.0)
        yaw = -90.0
        front_y = ymin + front_setback
        center_y = front_y + depth / 2.0
        rear_y = front_y + depth
        alley_y = rear_y + alley_rear_gap + alley_width / 2.0
        inner_boundary = alley_y + alley_width / 2.0
    elif side == "north":
        normal = (0.0, 1.0)
        yaw = 90.0
        front_y = ymax - front_setback
        center_y = front_y - depth / 2.0
        rear_y = front_y - depth
        alley_y = rear_y - alley_rear_gap - alley_width / 2.0
        inner_boundary = alley_y - alley_width / 2.0
    else:
        raise ValueError(f"Unsupported frontage side: {side}")

    candidates: list[dict[str, Any]] = []
    cursor = frontage_start
    for sequence, width in enumerate(widths):
        center_x = cursor + width / 2.0
        local_polygon = rect_polygon((center_x, center_y), (depth, width), yaw)
        cursor += width
        if polygons_overlap(local_polygon, exclusion):
            candidates.append({"skipped": True, "sequence": sequence})
            continue
        prototype, floors, residential_fraction = _prototype_and_floors(zone, sequence, rng)
        candidates.append(
            {
                "skipped": False,
                "sequence": sequence,
                "center_x": center_x,
                "width": width,
                "prototype": prototype,
                "floors": floors,
                "residential_fraction": residential_fraction,
            }
        )

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_sequence: int | None = None
    for candidate in candidates:
        if candidate["skipped"]:
            if current:
                groups.append(current)
                current = []
            previous_sequence = None
            continue
        if previous_sequence is not None and candidate["sequence"] != previous_sequence + 1:
            groups.append(current)
            current = []
        current.append(candidate)
        previous_sequence = candidate["sequence"]
    if current:
        groups.append(current)

    buildings: list[dict[str, Any]] = []
    service_paths: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        service_id = f"S_{block_id}_{side}_{group_index:02d}"
        first = group[0]
        last = group[-1]
        service_start = first["center_x"] - first["width"] / 2.0
        service_end = last["center_x"] + last["width"] / 2.0
        service_paths.append(
            _path_with_terrain(
                sampler,
                origin,
                service_id,
                "service_alley",
                alley_width,
                ((service_start, alley_y), (service_end, alley_y)),
            )
        )
        for member_index, candidate in enumerate(group):
            key = f"{block_id}:{side}:{candidate['sequence']:02d}"
            building = _building_draft(
                sampler,
                origin,
                key=key,
                block_id=block_id,
                kind="street_front_building",
                zone=zone,
                prototype=candidate["prototype"],
                local_center=(candidate["center_x"], center_y),
                yaw_deg=yaw,
                depth_cm=depth,
                width_cm=candidate["width"],
                floors=candidate["floors"],
                residential_fraction=candidate["residential_fraction"],
                frontage_target=road_id,
                front_entry_local=(candidate["center_x"], front_y),
                service_target=service_id,
                service_entry_local=(candidate["center_x"], rear_y),
            )
            building["urban_form"] = {
                "party_wall_group": f"{block_id}:{side}:{group_index:02d}",
                "party_wall_left": member_index > 0,
                "party_wall_right": member_index < len(group) - 1,
                "rear_court_or_yard": True,
            }
            buildings.append(building)
    return buildings, service_paths, inner_boundary if groups else None


def generate_reality_slice(project_root: Path, seed: int | None = None) -> dict[str, Any]:
    """Generate one 200 x 200 m ward; never claim to generate the full city."""

    scene_root = project_root / "export_ue" / "capital"
    meta = json.loads((scene_root / "meta.json").read_text(encoding="utf-8"))
    sampler = TerrainSampler.from_obj(scene_root / "terrain.obj")
    actual_seed = int(meta["seed"] if seed is None else seed)
    rng = random.Random(actual_seed)
    origin = [0.0, -7200.0]
    boundary_local: Polygon = [(-10_000.0, -10_000.0), (10_000.0, -10_000.0), (10_000.0, 10_000.0), (-10_000.0, 10_000.0)]
    boundary_world = [_local_to_world(origin, point) for point in boundary_local]

    road_definitions = (
        ("R_main_gate_avenue", "main_street", 800.0, ((0.0, -10_000.0), (0.0, 10_000.0))),
        ("R_market_street", "secondary_street", 450.0, ((-10_000.0, 0.0), (10_000.0, 0.0))),
        ("R_lane_west", "secondary_street", 400.0, ((-6_500.0, -9_500.0), (-6_500.0, 10_000.0))),
        ("R_lane_east", "secondary_street", 400.0, ((6_500.0, -9_500.0), (6_500.0, 10_000.0))),
        ("R_secondary_south", "secondary_street", 400.0, ((-10_000.0, -6_000.0), (10_000.0, -6_000.0))),
        ("R_secondary_north", "secondary_street", 400.0, ((-10_000.0, 6_000.0), (10_000.0, 6_000.0))),
    )
    roads = [
        _path_with_terrain(sampler, origin, path_id, path_class, width, points)
        for path_id, path_class, width, points in road_definitions
    ]

    square_local: Polygon = [(-1_800.0, -1_500.0), (1_800.0, -1_500.0), (1_800.0, 1_500.0), (-1_800.0, 1_500.0)]
    square_world = [_local_to_world(origin, point) for point in square_local]
    exclusion_local: Polygon = [(-3_800.0, -3_100.0), (3_800.0, -3_100.0), (3_800.0, 3_400.0), (-3_800.0, 3_400.0)]

    x_intervals = ((-10_000.0, -6_700.0), (-6_300.0, -400.0), (400.0, 6_300.0), (6_700.0, 10_000.0))
    y_intervals = ((-10_000.0, -6_200.0), (-5_800.0, -225.0), (225.0, 5_800.0), (6_200.0, 10_000.0))
    south_roads = (None, "R_secondary_south", "R_market_street", "R_secondary_north")
    north_roads = ("R_secondary_south", "R_market_street", "R_secondary_north", None)

    buildings: list[dict[str, Any]] = []
    service_paths: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    courtyards: list[dict[str, Any]] = []
    for y_index, (ymin, ymax) in enumerate(y_intervals):
        for x_index, (xmin, xmax) in enumerate(x_intervals):
            block_id = f"B_{x_index}_{y_index}"
            zone = _zone_for_block(x_index, y_index)
            block_polygon_local: Polygon = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
            block_record = {
                "id": block_id,
                "zone": zone,
                "polygon_cm": [_local_to_world(origin, point) for point in block_polygon_local],
                "street_frontage_model": "attached_party_wall_rows_with_rear_service",
            }
            blocks.append(block_record)
            inner: dict[str, float] = {}
            if south_roads[y_index]:
                row_buildings, row_paths, inner_boundary = _generate_frontage_row(
                    sampler,
                    origin,
                    rng,
                    block_id=block_id,
                    zone=zone,
                    bounds=(xmin, xmax, ymin, ymax),
                    side="south",
                    road_id=str(south_roads[y_index]),
                    exclusion=exclusion_local,
                )
                buildings.extend(row_buildings)
                service_paths.extend(row_paths)
                if inner_boundary is not None:
                    inner["south"] = inner_boundary
            if north_roads[y_index]:
                row_buildings, row_paths, inner_boundary = _generate_frontage_row(
                    sampler,
                    origin,
                    rng,
                    block_id=block_id,
                    zone=zone,
                    bounds=(xmin, xmax, ymin, ymax),
                    side="north",
                    road_id=str(north_roads[y_index]),
                    exclusion=exclusion_local,
                )
                buildings.extend(row_buildings)
                service_paths.extend(row_paths)
                if inner_boundary is not None:
                    inner["north"] = inner_boundary
            if "south" in inner and "north" in inner and inner["south"] + 200.0 < inner["north"]:
                courtyard_local: Polygon = [
                    (xmin + 300.0, inner["south"] + 100.0),
                    (xmax - 300.0, inner["south"] + 100.0),
                    (xmax - 300.0, inner["north"] - 100.0),
                    (xmin + 300.0, inner["north"] - 100.0),
                ]
                if not polygons_overlap(courtyard_local, exclusion_local):
                    courtyard_world = [_local_to_world(origin, point) for point in courtyard_local]
                    courtyards.append(
                        {
                            "id": f"C_{block_id}",
                            "block_id": block_id,
                            "polygon_cm": courtyard_world,
                            "use": "shared_household_court_kitchen_garden_and_light_well",
                            "permeable_surface": True,
                        }
                    )

    # Civic/market buildings deliberately replace generic rows around the
    # exclusion envelope.  Their front doors address the square itself.
    civic_specs = (
        ("civic:temple", "temple", "civic_religious", "adobe_flat_roof_temple", (-1_400.0, 2_350.0), -90.0, 1_200.0, 1_800.0, 2, 0.0, ( -1_400.0, 1_750.0), "S_civic_north", (-1_400.0, 2_950.0)),
        ("civic:admin", "administration", "civic_administrative", "adobe_council_archive", (1_400.0, 2_350.0), -90.0, 1_200.0, 1_800.0, 2, 0.0, (1_400.0, 1_750.0), "S_civic_north", (1_400.0, 2_950.0)),
        ("market:east:south", "market_pavilion", "market_public", "timber_shade_adobe_store", (2_350.0, -850.0), 180.0, 900.0, 900.0, 1, 0.0, (1_900.0, -850.0), "S_market_east", (2_800.0, -850.0)),
        ("market:east:north", "market_pavilion", "market_public", "timber_shade_adobe_store", (2_350.0, 850.0), 180.0, 900.0, 900.0, 1, 0.0, (1_900.0, 850.0), "S_market_east", (2_800.0, 850.0)),
        ("market:west:south", "market_pavilion", "market_public", "timber_shade_adobe_store", (-2_350.0, -850.0), 0.0, 900.0, 900.0, 1, 0.0, (-1_900.0, -850.0), "S_market_west", (-2_800.0, -850.0)),
        ("market:west:north", "market_pavilion", "market_public", "timber_shade_adobe_store", (-2_350.0, 850.0), 0.0, 900.0, 900.0, 1, 0.0, (-1_900.0, 850.0), "S_market_west", (-2_800.0, 850.0)),
    )
    service_paths.extend(
        (
            _path_with_terrain(sampler, origin, "S_civic_north", "service_alley", 240.0, ((-2_300.0, 3_220.0), (2_300.0, 3_220.0))),
            _path_with_terrain(sampler, origin, "S_market_east", "service_alley", 240.0, ((3_070.0, -1_350.0), (3_070.0, 1_350.0))),
            _path_with_terrain(sampler, origin, "S_market_west", "service_alley", 240.0, ((-3_070.0, -1_350.0), (-3_070.0, 1_350.0))),
        )
    )
    for spec in civic_specs:
        key, kind, zone, prototype, center, yaw, depth, width, floors, residential_fraction, front, service_id, rear = spec
        buildings.append(
            _building_draft(
                sampler,
                origin,
                key=key,
                block_id="B_CIVIC_CORE",
                kind=kind,
                zone=zone,
                prototype=prototype,
                local_center=center,
                yaw_deg=yaw,
                depth_cm=depth,
                width_cm=width,
                floors=floors,
                residential_fraction=residential_fraction,
                frontage_target="P_market_square",
                front_entry_local=front,
                service_target=service_id,
                service_entry_local=rear,
            )
        )

    # One justified gate: this slice is anchored to the source south wall at
    # global Y=-17200 cm.  The gatehouse carries the main street through it.
    gatehouse = _building_draft(
        sampler,
        origin,
        key="defense:south_gatehouse",
        block_id="B_DEFENSE_SOUTH",
        kind="gatehouse",
        zone="defensive_access",
        prototype="adobe_timber_south_gatehouse",
        local_center=(0.0, -9_600.0),
        yaw_deg=-90.0,
        depth_cm=800.0,
        width_cm=1_400.0,
        floors=2,
        residential_fraction=0.0,
        frontage_target="R_main_gate_avenue",
        front_entry_local=(0.0, -10_000.0),
        service_target=None,
        service_entry_local=None,
        road_overlap_allowed=("R_main_gate_avenue",),
    )
    gatehouse["capacity"] = {"gross_floor_area_m2": 224.0, "residents_capacity": 0, "jobs_capacity": 12}
    buildings.append(gatehouse)
    for side, center_x in (("west", -5_350.0), ("east", 5_350.0)):
        wall = _building_draft(
            sampler,
            origin,
            key=f"defense:south_wall:{side}",
            block_id="B_DEFENSE_SOUTH",
            kind="wall_segment",
            zone="defensive_access",
            prototype="adobe_city_wall",
            local_center=(center_x, -9_850.0),
            yaw_deg=0.0,
            depth_cm=9_300.0,
            width_cm=300.0,
            floors=1,
            residential_fraction=0.0,
            frontage_target=None,
            front_entry_local=None,
            service_target=None,
            service_entry_local=None,
        )
        wall["capacity"] = {"gross_floor_area_m2": 279.0, "residents_capacity": 0, "jobs_capacity": 0}
        buildings.append(wall)

    paths = roads + service_paths
    square_terrain = _terrain_binding(sampler, square_world, (origin[0], origin[1]))
    public_spaces = [
        {
            "id": "P_market_square",
            "kind": "market_civic_square",
            "polygon_cm": square_world,
            "area_m2": round(polygon_area(square_world) / CM2_PER_M2, 3),
            "surface": "compacted_earth_with_stone_drainage_bands",
            "terrain": square_terrain,
            "access_links": [
                {"path_id": "R_main_gate_avenue", "edge": "south"},
                {"path_id": "R_main_gate_avenue", "edge": "north"},
                {"path_id": "R_market_street", "edge": "west"},
                {"path_id": "R_market_street", "edge": "east"},
            ],
            "amenities": [
                {
                    "id": "A_square_well",
                    "kind": "public_well",
                    "pos_cm": [origin[0] - 450.0, origin[1], round(sampler.sample(origin[0] - 450.0, origin[1]), 3)],
                    "clear_radius_cm": 180.0,
                },
                {"id": "A_shade_colonnade", "kind": "shade_and_seating", "edge": "south"},
            ],
        }
    ]

    residents_capacity = sum(int(building["capacity"]["residents_capacity"]) for building in buildings)
    jobs_capacity = sum(int(building["capacity"]["jobs_capacity"]) for building in buildings)
    layout: dict[str, Any] = {
        "schema": LAYOUT_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "slice_id": SLICE_ID,
        "identity": {
            "status": "generator_authoritative_within_slice_v1",
            "scheme": "UUIDv5 fixed namespace + canonical building payload",
            "namespace_uuid": str(SLICE_NAMESPACE_UUID),
        },
        "scope": {
            "claim": REQUIRED_SCOPE_CLAIM,
            "name": "Raflir South Gate Market Ward",
            "source_scene": "capital",
            "anchor_cm": [origin[0], origin[1], round(sampler.sample(origin[0], origin[1]), 3)],
            "boundary_cm": boundary_world,
            "width_m": 200.0,
            "height_m": 200.0,
            "area_ha": 4.0,
            "residents_capacity": residents_capacity,
            "jobs_capacity": jobs_capacity,
            "source_city_population": int(meta["population"]),
            "population_representation": "only the ward capacity is represented; no claim to instantiate the whole city population",
        },
        "provenance": {
            "run_id": meta["run_id"],
            "scene": "capital",
            "year": meta["year"],
            "biome": meta["biome"],
            "meta_sha256": sha256_file(scene_root / "meta.json"),
            "terrain_obj_sha256": sha256_file(scene_root / "terrain.obj"),
            "source_buildings_used_as_layout_truth": False,
            "source_buildings_treatment": "audited separately; not copied into this physical slice",
            "design_assumptions": [
                "Mediterranean/desert urban fabric around year 500 uses predominantly flat-roof adobe or mud-brick courtyard/row forms",
                "main street width is 8 m; secondary streets are 4.0-4.5 m; service alleys are 2.4 m",
                "attached party-wall frontage replaces scattered identical gabled houses",
                "public market square has a well, temple, administration, shaded market pavilions and four path links",
                "south wall and one gatehouse are included because the 200 m slice is intentionally anchored to the source south wall coordinate",
                "capacity uses 16 net residential m2/person and is an engineering assumption for compact premodern households, not an archaeological fact",
            ],
        },
        "coordinates": {
            "units": "cm",
            "axes": "X/Y horizontal, Z up; source north is -Y",
            "facade": "local +X is front/entrance normal",
            "terrain_height": "bilinear sample from export_ue/capital/terrain.obj",
        },
        "generation": {"seed": actual_seed, "deterministic": True},
        "roads": roads,
        "service_paths": service_paths,
        "blocks": blocks,
        "buildings": buildings,
        "courtyards": courtyards,
        "public_spaces": public_spaces,
        "validation_policy": dict(EXPECTED_VALIDATION_POLICY),
    }
    digest_source = dict(layout)
    layout["layout_digest"] = "sha256:" + hashlib.sha256(canonical_json(digest_source).encode("utf-8")).hexdigest()
    return layout


def validate_reality_slice(layout: Mapping[str, Any], project_root: Path) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []

    def error(code: str, path: str, message: str) -> None:
        findings.append(LayoutFinding("error", code, path, message))

    def warn(code: str, path: str, message: str) -> None:
        findings.append(LayoutFinding("warning", code, path, message))

    if layout.get("schema") != LAYOUT_SCHEMA:
        error("schema", "/schema", f"Expected {LAYOUT_SCHEMA}")
        return sorted(findings)
    digest_value = layout.get("layout_digest")
    digest_source = dict(layout)
    digest_source.pop("layout_digest", None)
    expected_digest = "sha256:" + hashlib.sha256(canonical_json(digest_source).encode("utf-8")).hexdigest()
    if digest_value != expected_digest:
        error("layout_digest", "/layout_digest", "Layout digest does not match canonical content")

    validation_policy = layout.get("validation_policy")
    if validation_policy != EXPECTED_VALIDATION_POLICY:
        error(
            "validation_policy",
            "/validation_policy",
            "Declared policy must exactly match the code-authoritative validation thresholds",
        )

    scope = layout.get("scope")
    if not isinstance(scope, dict) or scope.get("claim") != REQUIRED_SCOPE_CLAIM:
        error("scope_claim", "/scope/claim", "Layout must explicitly claim one ward, not the full city")
        return sorted(findings)
    if not math.isclose(float(scope.get("width_m", 0)), 200.0) or not math.isclose(float(scope.get("height_m", 0)), 200.0):
        error("scope_extent", "/scope", "Reality slice must be the declared 200 x 200 m ward")
    residents = scope.get("residents_capacity")
    if (
        not isinstance(residents, int)
        or isinstance(residents, bool)
        or not MIN_WARD_RESIDENTS <= residents <= MAX_WARD_RESIDENTS
    ):
        error(
            "population_capacity",
            "/scope/residents_capacity",
            f"Ward capacity {residents!r} is outside [{MIN_WARD_RESIDENTS}, {MAX_WARD_RESIDENTS}]",
        )

    boundary = _parse_polygon(scope.get("boundary_cm"), "/scope/boundary_cm", error)
    if boundary is None:
        return sorted(findings)
    sampler = TerrainSampler.from_obj(project_root / "export_ue" / "capital" / "terrain.obj")

    roads = layout.get("roads")
    service_paths = layout.get("service_paths")
    if not isinstance(roads, list) or not isinstance(service_paths, list):
        error("paths_type", "/roads", "roads and service_paths must be arrays")
        return sorted(findings)
    path_ids: set[str] = set()
    path_by_id: dict[str, Mapping[str, Any]] = {}
    for collection_name, collection in (("roads", roads), ("service_paths", service_paths)):
        for index, path in enumerate(collection):
            base = f"/{collection_name}/{index}"
            if not isinstance(path, dict) or not isinstance(path.get("id"), str) or path["id"] in path_ids:
                error("path_id", base + "/id", "Path ID must be unique text")
                continue
            path_ids.add(path["id"])
            path_by_id[path["id"]] = path
            width = path.get("width_cm")
            if not isinstance(width, (int, float)) or isinstance(width, bool) or width <= 0:
                error("path_width", base + "/width_cm", "Path width must be positive")
                continue
            if path.get("class") == "main_street" and not 700.0 <= width <= 900.0:
                error("main_street_width", base + "/width_cm", "Main street must be 7-9 m")
            elif path.get("class") == "secondary_street" and not 350.0 <= width <= 500.0:
                error("secondary_street_width", base + "/width_cm", "Secondary street must be 3.5-5 m")
            elif path.get("class") == "service_alley" and not 180.0 <= width <= 300.0:
                error("service_alley_width", base + "/width_cm", "Service alley must be 1.8-3 m")
            points = path.get("points_cm")
            if not isinstance(points, list) or len(points) < 2:
                error("path_points", base + "/points_cm", "Path requires at least two points")
                continue
            for point_index, point in enumerate(points):
                if not isinstance(point, list) or len(point) != 3 or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in point):
                    error("path_point", f"{base}/points_cm/{point_index}", "Expected finite XYZ")
                    continue
                expected_z = sampler.sample(float(point[0]), float(point[1]))
                if abs(float(point[2]) - expected_z) > 0.01:
                    error("path_terrain", f"{base}/points_cm/{point_index}/2", "Path Z differs from terrain sample")

    public_spaces = layout.get("public_spaces")
    if not isinstance(public_spaces, list) or len(public_spaces) != 1:
        error("public_square_count", "/public_spaces", "Exactly one explicit public market square is required")
        return sorted(findings)
    square = public_spaces[0]
    square_polygon = _parse_polygon(square.get("polygon_cm") if isinstance(square, dict) else None, "/public_spaces/0/polygon_cm", error)
    if square_polygon is None:
        return sorted(findings)
    if square.get("id") != "P_market_square" or float(square.get("area_m2", 0)) < 800.0:
        error("public_square", "/public_spaces/0", "Market square must be explicit and at least 800 m2")
    links = square.get("access_links")
    if not isinstance(links, list) or len(links) < 4 or len({link.get("edge") for link in links if isinstance(link, dict)}) < 4:
        error("public_square_access", "/public_spaces/0/access_links", "Square requires north/south/east/west access")
    else:
        for link in links:
            if link.get("path_id") not in path_by_id:
                error("public_square_path", "/public_spaces/0/access_links", f"Unknown square path {link.get('path_id')}")
    amenities = square.get("amenities")
    if not isinstance(amenities, list) or sum(isinstance(item, dict) and item.get("kind") == "public_well" for item in amenities) != 1:
        error("public_well", "/public_spaces/0/amenities", "Square requires exactly one public well")

    buildings = layout.get("buildings")
    if not isinstance(buildings, list) or not buildings:
        error("buildings_type", "/buildings", "Layout requires buildings")
        return sorted(findings)
    building_ids: set[str] = set()
    building_polygons: list[Polygon | None] = []
    allowed_zones = {
        "gate_craft_mixed",
        "market_mixed",
        "craft_residential",
        "courtyard_residential",
        "civic_religious",
        "civic_administrative",
        "market_public",
        "defensive_access",
    }
    gate_count = 0
    party_wall_count = 0
    summed_residents_capacity = 0
    summed_jobs_capacity = 0
    for index, building in enumerate(buildings):
        base = f"/buildings/{index}"
        if not isinstance(building, dict):
            error("building_type", base, "Building must be an object")
            building_polygons.append(None)
            continue
        entity_id = building.get("id")
        try:
            parsed = uuid.UUID(entity_id) if isinstance(entity_id, str) else None
        except ValueError:
            parsed = None
        if parsed is None or parsed.version != 5 or str(parsed) != entity_id or entity_id in building_ids:
            error("building_id", base + "/id", "Building requires a unique canonical UUIDv5")
        else:
            building_ids.add(entity_id)
        if building.get("zone") not in allowed_zones:
            error("building_zone", base + "/zone", f"Unknown zone {building.get('zone')!r}")
        if building.get("architecture", {}).get("gabled_roof") is not False:
            error("roof_form", base + "/architecture/gabled_roof", "This ward assumption requires non-gabled flat roofs")
        if building.get("kind") == "gatehouse":
            gate_count += 1
        if building.get("urban_form", {}).get("party_wall_left") or building.get("urban_form", {}).get("party_wall_right"):
            party_wall_count += 1
        capacity = building.get("capacity")
        if not isinstance(capacity, dict):
            error("building_capacity", base + "/capacity", "Building capacity must be an object")
        else:
            gross_floor_area = capacity.get("gross_floor_area_m2")
            if (
                not isinstance(gross_floor_area, (int, float))
                or isinstance(gross_floor_area, bool)
                or not math.isfinite(gross_floor_area)
                or gross_floor_area <= 0
            ):
                error(
                    "building_capacity",
                    base + "/capacity/gross_floor_area_m2",
                    "Gross floor area must be a positive finite number",
                )
            for capacity_name in ("residents_capacity", "jobs_capacity"):
                capacity_value = capacity.get(capacity_name)
                if (
                    not isinstance(capacity_value, int)
                    or isinstance(capacity_value, bool)
                    or capacity_value < 0
                ):
                    error(
                        "building_capacity",
                        f"{base}/capacity/{capacity_name}",
                        "Capacity must be a non-negative integer",
                    )
                elif capacity_name == "residents_capacity":
                    summed_residents_capacity += capacity_value
                else:
                    summed_jobs_capacity += capacity_value
        polygon = _parse_polygon(building.get("footprint_cm"), base + "/footprint_cm", error)
        building_polygons.append(polygon)
        if polygon is None:
            continue
        for point in polygon:
            if not point_in_polygon(point, boundary):
                error("building_outside", base + "/footprint_cm", "Building footprint escapes ward boundary")
                break
        if polygons_overlap(polygon, square_polygon):
            error("building_in_square", base + "/footprint_cm", "Building overlaps public square")

        position = building.get("pos_cm")
        size = building.get("size_cm")
        if not isinstance(position, list) or len(position) != 3 or not isinstance(size, list) or len(size) != 3:
            error("building_transform", base, "Building requires XYZ position and XYZ size")
            continue
        expected_polygon = rect_polygon(position, size, float(building.get("yaw_deg", 0.0)))
        if any(math.dist(a, b) > 0.02 for a, b in zip(polygon, expected_polygon)):
            error("footprint_transform", base + "/footprint_cm", "Footprint differs from position/size/yaw")
        expected_terrain = _terrain_binding(sampler, polygon, (float(position[0]), float(position[1])))
        terrain = building.get("terrain")
        if not isinstance(terrain, dict) or any(
            abs(float(terrain.get(key, math.inf)) - float(expected_terrain[key])) > 0.01
            for key in ("center_z_cm", "base_z_cm", "max_corner_delta_cm", "grade_percent")
        ):
            error("building_terrain", base + "/terrain", "Stored terrain binding differs from bilinear samples")
        elif float(terrain["grade_percent"]) > MAX_BUILDING_GRADE_PERCENT:
            error(
                "building_grade",
                base + "/terrain/grade_percent",
                f"Grade exceeds {MAX_BUILDING_GRADE_PERCENT}%",
            )
        if abs(float(position[2]) - float(expected_terrain["base_z_cm"])) > 0.01:
            error("building_z", base + "/pos_cm/2", "Building Z must use sampled maximum-corner plinth")

        allowed_road_overlaps = set(building.get("road_overlap_allowed", []))
        for road in roads:
            clearance = polygon_path_clearance(polygon, road)
            if clearance < -0.02 and road["id"] not in allowed_road_overlaps:
                error("building_road_overlap", base + "/footprint_cm", f"Building penetrates {road['id']} by {-clearance:.2f} cm")
        for service_path in service_paths:
            clearance = polygon_path_clearance(polygon, service_path)
            if clearance < -0.02:
                error("building_service_overlap", base + "/footprint_cm", f"Building penetrates {service_path['id']}")

        if building.get("kind") == "wall_segment":
            if building.get("frontage") is not None or building.get("service_access") is not None:
                error("wall_access", base, "Wall segment should not claim door access")
            continue
        frontage = building.get("frontage")
        if not isinstance(frontage, dict) or frontage.get("target_id") not in path_by_id | {"P_market_square": square}:
            error("frontage", base + "/frontage", "Occupied/gate building requires a known frontage target")
        else:
            _validate_frontage(building, frontage, path_by_id, square_polygon, base, error)
        service = building.get("service_access")
        if building.get("kind") == "gatehouse":
            if service is not None:
                warn("gate_service", base + "/service_access", "Gatehouse service access is represented by its through road")
        elif not isinstance(service, dict) or service.get("target_id") not in path_by_id:
            error("service_access", base + "/service_access", "Building requires a known service path")
        else:
            target = path_by_id[service["target_id"]]
            entry = service.get("entry_cm")
            if not isinstance(entry, list) or len(entry) != 3:
                error("service_entry", base + "/service_access/entry_cm", "Expected service XYZ")
            else:
                nearest = nearest_on_paths((float(entry[0]), float(entry[1])), [target])
                if nearest["edge_distance_cm"] > float(service.get("max_clearance_cm", 0)) + 0.02:
                    error("service_clearance", base + "/service_access", "Rear entry is too far from service alley")

    for first_index in range(len(buildings)):
        if building_polygons[first_index] is None:
            continue
        for second_index in range(first_index + 1, len(buildings)):
            if building_polygons[second_index] is None:
                continue
            if polygons_overlap(building_polygons[first_index], building_polygons[second_index]):
                intersection = convex_intersection(building_polygons[first_index], building_polygons[second_index])
                overlap_area_cm2 = polygon_area(intersection)
                # Shared party walls transformed through ±90° rotations and
                # serialized to 0.001 cm can leave a few square centimetres of
                # numeric residue across a 12-15 m wall.  It is edge touching,
                # not a meaningful physical area overlap.
                if overlap_area_cm2 <= OVERLAP_SERIALIZATION_TOLERANCE_CM2:
                    continue
                error(
                    "building_overlap",
                    f"/buildings/{first_index}",
                    f"Overlaps building {second_index} by {overlap_area_cm2 / CM2_PER_M2:.3f} m2",
                )

    if scope.get("residents_capacity") != summed_residents_capacity:
        error(
            "capacity_total",
            "/scope/residents_capacity",
            f"Scope residents must equal building sum {summed_residents_capacity}",
        )
    if scope.get("jobs_capacity") != summed_jobs_capacity:
        error(
            "capacity_total",
            "/scope/jobs_capacity",
            f"Scope jobs must equal building sum {summed_jobs_capacity}",
        )

    if gate_count != REQUIRED_GATE_COUNT:
        error("gate_count", "/buildings", f"Expected {REQUIRED_GATE_COUNT} gatehouse, found {gate_count}")
    if party_wall_count < 20:
        error("party_wall_density", "/buildings", "Dense ward needs at least 20 attached party-wall buildings")

    courtyards = layout.get("courtyards")
    if not isinstance(courtyards, list) or len(courtyards) < 2:
        error("courtyards", "/courtyards", "Ward needs multiple explicit shared courtyards")
    else:
        for courtyard_index, courtyard in enumerate(courtyards):
            polygon = _parse_polygon(courtyard.get("polygon_cm") if isinstance(courtyard, dict) else None, f"/courtyards/{courtyard_index}/polygon_cm", error)
            if polygon is None:
                continue
            for building_index, building_polygon in enumerate(building_polygons):
                if building_polygon is not None and polygons_overlap(polygon, building_polygon):
                    error("courtyard_overlap", f"/courtyards/{courtyard_index}", f"Courtyard overlaps building {building_index}")

    return sorted(findings)


def _parse_polygon(value: Any, path: str, error: Any) -> Polygon | None:
    if not isinstance(value, list) or len(value) < 3:
        error("polygon", path, "Expected at least three XY points")
        return None
    polygon: Polygon = []
    for point in value:
        if not isinstance(point, list) or len(point) < 2 or not all(isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) for number in point[:2]):
            error("polygon_point", path, "Expected finite XY points")
            return None
        polygon.append((float(point[0]), float(point[1])))
    if polygon_area(polygon) <= EPSILON:
        error("polygon_area", path, "Polygon area must be positive")
        return None
    return polygon


def _validate_frontage(
    building: Mapping[str, Any],
    frontage: Mapping[str, Any],
    paths: Mapping[str, Mapping[str, Any]],
    square: Polygon,
    base: str,
    error: Any,
) -> None:
    entry = frontage.get("entry_cm")
    if not isinstance(entry, list) or len(entry) != 3:
        error("front_entry", base + "/frontage/entry_cm", "Expected frontage XYZ")
        return
    point = float(entry[0]), float(entry[1])
    yaw = math.radians(float(building["yaw_deg"]))
    normal = math.cos(yaw), math.sin(yaw)
    expected_front = (
        float(building["pos_cm"][0]) + normal[0] * float(building["size_cm"][0]) / 2.0,
        float(building["pos_cm"][1]) + normal[1] * float(building["size_cm"][0]) / 2.0,
    )
    if math.dist(point, expected_front) > 0.02:
        error("front_entry_transform", base + "/frontage/entry_cm", "Entry is not at local +X front midpoint")
    target_id = frontage["target_id"]
    if target_id == "P_market_square":
        nearest = nearest_polygon_boundary(point, square)
        distance = nearest["distance_cm"]
        nearest_point = nearest["nearest_cm"]
        tangent = nearest["tangent"]
    else:
        target = paths[target_id]
        nearest_path = nearest_on_paths(point, [target])
        distance = nearest_path["edge_distance_cm"]
        nearest_point = nearest_path["nearest_cm"]
        tangent = nearest_path["tangent"]
    if distance > float(frontage.get("max_clearance_cm", 0)) + 0.02:
        error("frontage_clearance", base + "/frontage", f"Front entry is {distance:.2f} cm from target edge")
    # Gatehouses carry the street through a perpendicular opening rather than
    # presenting a parallel shopfront.
    if building.get("kind") == "gatehouse":
        return
    toward = nearest_point[0] - point[0], nearest_point[1] - point[1]
    length = math.hypot(*toward)
    if length > EPSILON:
        dot = (normal[0] * toward[0] + normal[1] * toward[1]) / length
        if dot < 0.8:
            error("frontage_facing", base + "/yaw_deg", f"Facade normal does not face target (dot={dot:.3f})")
    parallel_deviation = math.degrees(math.asin(min(1.0, abs(normal[0] * tangent[0] + normal[1] * tangent[1]))))
    if parallel_deviation > 5.0:
        error("frontage_parallel", base + "/yaw_deg", f"Facade deviates {parallel_deviation:.2f} degrees from target edge")


def make_runtime_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the rich layout into TerraRuntime's element schema v1."""

    scope = layout["scope"]
    anchor = scope["anchor_cm"]
    elements: list[dict[str, Any]] = []

    def add(
        element_id: str,
        kind: str,
        location: Sequence[float],
        size: Sequence[float],
        yaw: float = 0.0,
        *,
        collision: bool,
        pitch: float = 0.0,
    ) -> None:
        elements.append(
            {
                "id": element_id,
                "kind": kind,
                "location_cm": {"x": round(float(location[0]), 3), "y": round(float(location[1]), 3), "z": round(float(location[2]), 3)},
                "size_cm": {"x": round(float(size[0]), 3), "y": round(float(size[1]), 3), "z": round(float(size[2]), 3)},
                "yaw_deg": round(float(yaw), 3),
                "pitch_deg": round(float(pitch), 3),
                "collision": bool(collision),
            }
        )

    add("E_ground", "ground", (anchor[0], anchor[1], anchor[2] - 20.0), (20_000.0, 20_000.0, 40.0), collision=True)
    for path in list(layout["roads"]) + list(layout["service_paths"]):
        for segment_index, (start, end) in enumerate(zip(path["points_cm"], path["points_cm"][1:])):
            dx, dy = float(end[0]) - float(start[0]), float(end[1]) - float(start[1])
            length = math.hypot(dx, dy)
            midpoint = ((float(start[0]) + float(end[0])) / 2.0, (float(start[1]) + float(end[1])) / 2.0, (float(start[2]) + float(end[2])) / 2.0 + 2.0)
            add(
                f"E_{path['id']}_{segment_index}",
                "road",
                midpoint,
                (length, float(path["width_cm"]), 8.0),
                math.degrees(math.atan2(dy, dx)),
                collision=True,
            )
    for building in layout["buildings"]:
        kind = "building"
        if building["kind"] == "wall_segment":
            kind = "wall"
        elif building["kind"] == "gatehouse":
            kind = "gate"
        elif building["kind"] == "market_pavilion":
            kind = "market_stall"
        pos = building["pos_cm"]
        size = building["size_cm"]
        add(f"E_{building['id']}_body", kind, (pos[0], pos[1], pos[2] + size[2] / 2.0), size, building["yaw_deg"], collision=True)
        if building["kind"] != "wall_segment":
            add(f"E_{building['id']}_roof", "roof", (pos[0], pos[1], pos[2] + size[2] + 10.0), (size[0] + 30.0, size[1] + 30.0, 20.0), building["yaw_deg"], collision=False)
        frontage = building.get("frontage")
        if isinstance(frontage, dict):
            entry = frontage["entry_cm"]
            add(f"E_{building['id']}_door", "door", (entry[0], entry[1], pos[2] + 110.0), (20.0, 100.0, 220.0), building["yaw_deg"], collision=False)
            if building["kind"] in {"street_front_building", "administration", "temple"}:
                yaw = math.radians(float(building["yaw_deg"]))
                tangent = -math.sin(yaw), math.cos(yaw)
                for window_index, offset in enumerate((-float(size[1]) * 0.27, float(size[1]) * 0.27)):
                    add(
                        f"E_{building['id']}_window_{window_index}",
                        "window",
                        (entry[0] + tangent[0] * offset, entry[1] + tangent[1] * offset, pos[2] + 210.0),
                        (16.0, 90.0, 100.0),
                        building["yaw_deg"],
                        collision=False,
                    )
            if building["prototype"] in {"adobe_shop_house", "timber_shade_adobe_store"}:
                yaw = math.radians(float(building["yaw_deg"]))
                normal = math.cos(yaw), math.sin(yaw)
                add(
                    f"E_{building['id']}_awning",
                    "awning",
                    (entry[0] + normal[0] * 90.0, entry[1] + normal[1] * 90.0, pos[2] + 245.0),
                    (180.0, float(size[1]) * 0.8, 18.0),
                    building["yaw_deg"],
                    collision=False,
                )
    square = layout["public_spaces"][0]
    for amenity in square["amenities"]:
        if amenity.get("kind") == "public_well":
            pos = amenity["pos_cm"]
            add(f"E_{amenity['id']}", "well", (pos[0], pos[1], pos[2] + 75.0), (200.0, 200.0, 150.0), collision=True)

    player_z = float(anchor[2]) + 120.0
    return {
        "schema_version": 1,
        "layout_id": layout["slice_id"],
        "title": scope["name"],
        "extent_cm": {"x": 20_000.0, "y": 20_000.0},
        "player_start": {
            "location_cm": {"x": float(anchor[0]) + 450.0, "y": float(anchor[1]) + 250.0, "z": round(player_z, 3)},
            "yaw_deg": 90.0,
        },
        "elements": elements,
    }


def validate_runtime_layout(runtime: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if runtime.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    allowed = {"ground", "road", "building", "roof", "door", "window", "awning", "market_stall", "well", "wall", "gate"}
    seen: set[str] = set()
    elements = runtime.get("elements")
    if not isinstance(elements, list) or not elements:
        return ["elements must be non-empty"]
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            errors.append(f"elements[{index}] must be an object")
            continue
        if not isinstance(element.get("id"), str) or element["id"] in seen:
            errors.append(f"elements[{index}] id must be unique")
        else:
            seen.add(element["id"])
        if element.get("kind") not in allowed:
            errors.append(f"elements[{index}] kind is unsupported")
        for key, dimensions in (("location_cm", ("x", "y", "z")), ("size_cm", ("x", "y", "z"))):
            value = element.get(key)
            if not isinstance(value, dict) or not all(isinstance(value.get(axis), (int, float)) and math.isfinite(value[axis]) for axis in dimensions):
                errors.append(f"elements[{index}] {key} is invalid")
        size = element.get("size_cm", {})
        if isinstance(size, dict) and any(float(size.get(axis, 0)) <= 0 for axis in ("x", "y", "z")):
            errors.append(f"elements[{index}] size must be positive")
        if not isinstance(element.get("collision"), bool):
            errors.append(f"elements[{index}] collision must be boolean")
    return errors


def render_audit_report(audit: Mapping[str, Any]) -> str:
    geometry = audit["geometry"]
    density = audit["density"]
    frontage = audit["roads_and_frontage"]
    access = audit["access"]
    return "\n".join(
        [
            "# Raflir capital: physical audit",
            "",
            "## Verdict",
            "",
            "The current `capital` export is a useful macro blockout, not a physically populated city at street-level fidelity.",
            "",
            f"- Source meta population: {audit['source']['source_declared_population']:,}; requested comparison: {audit['source']['comparison_population']:,}.",
            f"- Terrain: {geometry['terrain_area_km2']:.3f} km²; building-layout bounding box: {geometry['layout_bbox']['area_km2']:.3f} km²; inferred wall enclosure: {geometry['wall_enclosure_area_km2']:.3f} km².",
            f"- 300 proxies imply {density['source_population']['people_per_proxy']:,.0f} people/proxy at source population, or {density['comparison_2_3m']['people_per_proxy']:,.0f} at 2.3M.",
            f"- 255 house proxies provide about {geometry['estimated_house_gfa_m2']:,.0f} m² estimated GFA: {density['source_population']['people_per_estimated_house_gfa_m2']:.1f} people/m² at source population.",
            f"- OBB overlap pairs: {audit['overlaps']['pair_count']} ({audit['overlaps']['unintended_pair_count']} non-compositional); road/building penetrations: {frontage['building_road_collision_count']}.",
            "",
            "## Streets and frontage",
            "",
            f"- House fronts within 10 m of a road edge: {frontage['house_frontage']['within_10m_count']}/{frontage['house_frontage']['count']}.",
            f"- House fronts simultaneously near, road-parallel and facing the road: {frontage['house_frontage']['near_parallel_and_facing_count']}/{frontage['house_frontage']['count']}.",
            f"- Market stalls simultaneously near, road-parallel and facing: {frontage['market_frontage']['near_parallel_and_facing_count']}/{frontage['market_frontage']['count']}.",
            f"- No square polygon exists. PlayerStart-as-proxy is {access['player_start_to_road_edge_m']:.1f} m from the nearest road edge.",
            f"- Gates: {access['gate_count']}; market stalls: {access['market_stall_count']}. Gate centers meet roads, while the market cluster lacks a direct square/access graph.",
            "",
            "## Interpretation",
            "",
            "Wall/tower and wall/gate overlaps may be intentional composition, but they need booleaned modular geometry. Other collisions, absent pedestrian/service graphs, and population ratios prevent a reality-level claim.",
            "",
            f"Audit digest: `{audit['audit_digest']}`",
            "",
        ]
    )


def render_layout_report(layout: Mapping[str, Any], findings: Sequence[LayoutFinding], runtime: Mapping[str, Any]) -> str:
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    kind_counts = Counter(building["kind"] for building in layout["buildings"])
    zone_counts = Counter(building["zone"] for building in layout["buildings"])
    max_grade = max(float(building["terrain"]["grade_percent"]) for building in layout["buildings"])
    runtime_counts = Counter(element["kind"] for element in runtime["elements"])
    lines = [
        "# Raflir South Gate Market Ward — reality slice",
        "",
        f"Status: **{'VALID' if not errors else 'INVALID'}** ({len(errors)} errors, {len(warnings)} warnings).",
        "",
        "This artifact represents one 200 × 200 m, 4 ha ward. It does not represent all of Raflir or millions of simultaneous inhabitants.",
        "",
        f"- Resident capacity: {layout['scope']['residents_capacity']}; jobs: {layout['scope']['jobs_capacity']}.",
        f"- Buildings/defensive structures: {len(layout['buildings'])}; one gatehouse; two wall segments.",
        f"- Roads: {len(layout['roads'])}; service alleys: {len(layout['service_paths'])}; courtyards: {len(layout['courtyards'])}.",
        f"- Public square: {layout['public_spaces'][0]['area_m2']:.0f} m² with four links, well, temple, administration and four market pavilions.",
        f"- Maximum sampled building grade: {max_grade:.3f}%.",
        "- Building overlap policy: no area overlap; attached party-wall edge touching is intentional.",
        "- Built form: predominantly attached flat-roof adobe/mud-brick courtyard and row buildings, not repeated gabled proxies.",
        "",
        "## Building kinds",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(kind_counts.items()))
    lines.extend(["", "## Zones", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(zone_counts.items()))
    lines.extend(["", "## Runtime adapter elements", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(runtime_counts.items()))
    if findings:
        lines.extend(["", "## Validation findings", ""])
        lines.extend(f"- {finding.severity.upper()} `{finding.code}` `{finding.path}` — {finding.message}" for finding in findings)
    lines.extend(["", f"Layout digest: `{layout['layout_digest']}`", ""])
    return "\n".join(lines)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "generate", "validate", "all"), nargs="?", default="all")
    parser.add_argument("--project-root", type=Path, default=_default_project_root())
    parser.add_argument("--seed", type=int)
    parser.add_argument("--layout", type=Path, default=Path(__file__).resolve().parent / "generated" / "reality_slice_capital.json")
    parser.add_argument("--audit-json", type=Path, default=Path(__file__).resolve().parent / "generated" / "capital_physical_audit.json")
    parser.add_argument("--audit-report", type=Path, default=Path(__file__).resolve().parent / "generated" / "capital_physical_audit.md")
    parser.add_argument("--layout-report", type=Path, default=Path(__file__).resolve().parent / "generated" / "reality_slice_capital_report.md")
    parser.add_argument("--runtime-layout", type=Path, default=Path(__file__).resolve().parent / "generated" / "reality_slice_capital_runtime_v1.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = args.project_root.resolve()
    if args.command == "audit":
        audit = audit_capital(project)
        _write_json(args.audit_json, audit)
        _write_text(args.audit_report, render_audit_report(audit))
        print(json.dumps({"status": "complete", "audit": args.audit_json.as_posix(), "report": args.audit_report.as_posix()}, sort_keys=True, indent=2))
        return 0
    if args.command == "validate":
        layout = json.loads(args.layout.read_text(encoding="utf-8"))
        findings = validate_reality_slice(layout, project)
        print(json.dumps({"valid": not any(item.severity == "error" for item in findings), "findings": [item.as_dict() for item in findings]}, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if not any(item.severity == "error" for item in findings) else 2

    layout = generate_reality_slice(project, args.seed)
    findings = validate_reality_slice(layout, project)
    runtime = make_runtime_layout(layout)
    runtime_errors = validate_runtime_layout(runtime)
    if runtime_errors:
        findings.extend(LayoutFinding("error", "runtime_adapter", "/runtime", message) for message in runtime_errors)
    _write_json(args.layout, layout)
    _write_json(args.runtime_layout, runtime)
    _write_text(args.layout_report, render_layout_report(layout, findings, runtime))
    if args.command == "all":
        audit = audit_capital(project)
        _write_json(args.audit_json, audit)
        _write_text(args.audit_report, render_audit_report(audit))
    errors = [item for item in findings if item.severity == "error"]
    payload = {
        "valid": not errors,
        "errors": len(errors),
        "warnings": sum(item.severity == "warning" for item in findings),
        "layout": args.layout.as_posix(),
        "runtime_layout": args.runtime_layout.as_posix(),
        "report": args.layout_report.as_posix(),
        "residents_capacity": layout["scope"]["residents_capacity"],
        "jobs_capacity": layout["scope"]["jobs_capacity"],
        "buildings": len(layout["buildings"]),
        "gates": sum(building["kind"] == "gatehouse" for building in layout["buildings"]),
        "roads": len(layout["roads"]),
        "service_paths": len(layout["service_paths"]),
        "runtime_elements": len(runtime["elements"]),
        "findings": [item.as_dict() for item in findings],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
