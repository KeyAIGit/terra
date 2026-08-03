#!/usr/bin/env python3
"""Validate a TERRA Unreal export and build a deterministic import manifest.

This module deliberately uses only the Python standard library.  It is safe to
run outside Unreal Engine and never writes to ``Content``.  Its generated
manifest is consumed by ``unreal_import_terra_life.py`` inside the editor.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import math
import re
import shlex
import struct
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TOOL_VERSION = "1.1.0"
MANIFEST_SCHEMA = "terra.unreal-import-manifest/v1"
EXPECTED_RUN_ID = "terra-life"
CONTENT_NAMESPACE = "/Game/TerraLife"
IDENTITY_SCHEME = "terra.provisional-entity-uuidv5/v1"
IDENTITY_NAMESPACE_UUID = uuid.UUID("c6e6fa94-b92b-5bae-b40e-62f31a09bdcf")
CANONICAL_SCENES = ("neolithic", "bronze", "capital")
SCENE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclasses.dataclass(frozen=True, order=True)
class Diagnostic:
    """A stable, machine-readable validation finding."""

    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class ValidationResult:
    """Complete validation state used by the CLI and manifest generator."""

    export_root: Path
    scenes: list[dict[str, Any]]
    files: list[dict[str, Any]]
    diagnostics: list[Diagnostic]

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    @property
    def valid(self) -> bool:
        return not self.errors

    def summary(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "scene_count": len(self.scenes),
            "scenes": [s["name"] for s in self.scenes],
            "file_count": len(self.files),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }


class Validator:
    """Schema and invariant validator for the ``terra-life`` UE export."""

    def __init__(self, export_root: Path) -> None:
        self.root = export_root.resolve()
        self.diagnostics: list[Diagnostic] = []
        self._files: dict[str, dict[str, Any]] = {}

    def error(self, code: str, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic("error", code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic("warning", code, path, message))

    def validate(self) -> ValidationResult:
        if not self.root.is_dir():
            self.error("export_root_missing", ".", "Export root is not a directory")
            return self._result([])

        scene_dirs = sorted(
            (p for p in self.root.iterdir() if p.is_dir() and (p / "meta.json").is_file()),
            key=lambda p: p.name,
        )
        if not scene_dirs:
            self.error("no_scenes", ".", "No scene directories containing meta.json were found")
            return self._result([])

        discovered = {p.name for p in scene_dirs}
        for expected in CANONICAL_SCENES:
            if expected not in discovered:
                self.warn(
                    "canonical_scene_missing",
                    ".",
                    f"Canonical scene '{expected}' is absent from this export",
                )

        scenes = [self._validate_scene(scene_dir) for scene_dir in scene_dirs]
        run_ids = {s.get("run_id") for s in scenes if s.get("run_id")}
        if len(run_ids) > 1:
            self.error("mixed_run_ids", ".", f"Scenes contain multiple run_id values: {sorted(run_ids)}")

        return self._result(scenes)

    def _result(self, scenes: list[dict[str, Any]]) -> ValidationResult:
        return ValidationResult(
            export_root=self.root,
            scenes=sorted(scenes, key=lambda s: s.get("name", "")),
            files=sorted(self._files.values(), key=lambda f: f["path"]),
            diagnostics=sorted(self.diagnostics),
        )

    def _read_json(self, scene: str, relative: str) -> dict[str, Any]:
        rel = f"{scene}/{relative}"
        path = self.root / rel
        self._record_file(rel, _role_for(relative))
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.error("json_invalid", rel, f"Cannot parse JSON: {exc}")
            return {}
        if not isinstance(value, dict):
            self.error("json_root_type", rel, "JSON root must be an object")
            return {}
        return value

    def _record_file(self, relative: str, role: str) -> Path | None:
        relative = Path(relative).as_posix()
        path = self.root / relative
        if relative in self._files:
            return path if path.is_file() else None
        if path.is_symlink():
            self.error("symlink_rejected", relative, "Symlinks are not allowed in import input")
            return None
        if not path.is_file():
            self.error("required_file_missing", relative, f"Required {role} file is missing")
            return None
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, ValueError):
            self.error("path_escape", relative, "Input file resolves outside the export root")
            return None
        digest = _sha256_file(path)
        self._files[relative] = {
            "path": relative,
            "role": role,
            "bytes": path.stat().st_size,
            "sha256": digest,
        }
        return path

    def _validate_scene(self, scene_dir: Path) -> dict[str, Any]:
        scene = scene_dir.name
        if not SCENE_NAME_RE.fullmatch(scene):
            self.error("scene_name_invalid", scene, "Scene folder must be a safe lowercase slug")

        meta = self._read_json(scene, "meta.json")
        buildings_doc = self._read_json(scene, "buildings.json")
        people_doc = self._read_json(scene, "people.json")
        proxy_index = self._read_json(scene, "proxy_meshes/proxy_index.json")

        self._validate_meta(scene, meta)
        self._validate_proxy_index(scene, proxy_index)
        building_counts = self._validate_buildings(scene, buildings_doc, meta, proxy_index)
        people_count = self._validate_people(scene, people_doc, meta)
        self._validate_declared_counts(scene, meta, building_counts, people_count)
        self._validate_scene_files(scene, meta, proxy_index)

        counts = {
            "buildings": building_counts[0],
            "roads": building_counts[1],
            "people": people_count,
        }
        return {
            "name": scene,
            "run_id": meta.get("run_id"),
            "title": meta.get("title"),
            "settlement": meta.get("settlement"),
            "polity": meta.get("polity"),
            "era": meta.get("era"),
            "year": meta.get("year"),
            "population": meta.get("population"),
            "seed": meta.get("seed"),
            "built_at": meta.get("built_at"),
            "counts": counts,
            "proxy_types": sorted(proxy_index) if isinstance(proxy_index, dict) else [],
        }

    def _validate_meta(self, scene: str, meta: Mapping[str, Any]) -> None:
        rel = f"{scene}/meta.json"
        required_text = (
            "run_id",
            "scene",
            "title",
            "settlement",
            "polity",
            "era",
            "year_ru",
            "biome",
            "desc",
            "exporter",
            "built_at",
        )
        for key in required_text:
            if not isinstance(meta.get(key), str) or not meta.get(key):
                self.error("meta_field_invalid", f"{rel}#/{key}", "Expected a non-empty string")
        if meta.get("run_id") != EXPECTED_RUN_ID:
            self.error(
                "run_id_mismatch",
                f"{rel}#/run_id",
                f"Expected '{EXPECTED_RUN_ID}', got {meta.get('run_id')!r}",
            )
        if meta.get("scene") != scene:
            self.error("scene_mismatch", f"{rel}#/scene", "Scene value must match its folder name")
        if meta.get("exporter") != "terra.export_ue":
            self.warn("exporter_unexpected", f"{rel}#/exporter", "Exporter is not terra.export_ue")

        for key in ("year", "population", "seed", "latitude_deg"):
            if not _is_finite_number(meta.get(key)):
                self.error("meta_number_invalid", f"{rel}#/{key}", "Expected a finite number")
        if _is_finite_number(meta.get("population")) and meta["population"] < 0:
            self.error("population_negative", f"{rel}#/population", "Population cannot be negative")
        if _is_finite_number(meta.get("latitude_deg")) and not -90 <= meta["latitude_deg"] <= 90:
            self.error("latitude_range", f"{rel}#/latitude_deg", "Latitude must be between -90 and 90")

        built_at = meta.get("built_at")
        if isinstance(built_at, str):
            try:
                dt.datetime.fromisoformat(built_at.replace("Z", "+00:00"))
            except ValueError:
                self.error("built_at_invalid", f"{rel}#/built_at", "Expected an ISO-8601 timestamp")

        gods = meta.get("gods")
        if not isinstance(gods, list) or not all(isinstance(x, str) and x for x in gods):
            self.error("gods_invalid", f"{rel}#/gods", "Expected a list of non-empty names")
        self._vector(meta.get("player_start_cm"), 3, f"{rel}#/player_start_cm")

        coords = meta.get("coords")
        if not isinstance(coords, dict):
            self.error("coords_invalid", f"{rel}#/coords", "Expected a coordinate metadata object")
        elif coords.get("units") != "см":
            self.error("coords_units", f"{rel}#/coords/units", "Unreal export coordinates must be centimetres")

        terrain = meta.get("terrain")
        if not isinstance(terrain, dict):
            self.error("terrain_invalid", f"{rel}#/terrain", "Expected a terrain object")
        else:
            for key in ("size_cm", "grid", "step_cm", "z_min_cm", "z_max_cm", "far_size_cm"):
                if not _is_finite_number(terrain.get(key)):
                    self.error("terrain_number_invalid", f"{rel}#/terrain/{key}", "Expected a finite number")
            if _is_finite_number(terrain.get("size_cm")) and terrain["size_cm"] <= 0:
                self.error("terrain_size", f"{rel}#/terrain/size_cm", "Terrain size must be positive")
            if _is_finite_number(terrain.get("grid")) and int(terrain["grid"]) != terrain["grid"]:
                self.error("terrain_grid", f"{rel}#/terrain/grid", "Grid must be an integer")
            if all(_is_finite_number(terrain.get(k)) for k in ("z_min_cm", "z_max_cm")):
                if terrain["z_min_cm"] >= terrain["z_max_cm"]:
                    self.error("terrain_z_range", f"{rel}#/terrain", "z_min_cm must be less than z_max_cm")
            if all(_is_finite_number(terrain.get(k)) for k in ("size_cm", "grid", "step_cm")) and terrain["grid"] > 1:
                expected_step = terrain["size_cm"] / (terrain["grid"] - 1)
                if not math.isclose(terrain["step_cm"], expected_step, rel_tol=0.0, abs_tol=0.02):
                    self.error("terrain_step", f"{rel}#/terrain/step_cm", "step_cm does not match size_cm/(grid-1)")
            if all(_is_finite_number(terrain.get(k)) for k in ("size_cm", "far_size_cm")):
                if terrain["far_size_cm"] < terrain["size_cm"]:
                    self.error("far_terrain_size", f"{rel}#/terrain/far_size_cm", "Far terrain cannot be smaller than terrain")
            water_z = terrain.get("water_z_cm")
            if water_z is not None and not _is_finite_number(water_z):
                self.error("water_z_invalid", f"{rel}#/terrain/water_z_cm", "Expected null or a finite number")

        heightmap = meta.get("heightmap")
        if not isinstance(heightmap, dict):
            self.error("heightmap_invalid", f"{rel}#/heightmap", "Expected a heightmap object")
        else:
            for key in ("px", "min_cm", "max_cm", "landscape_scale_xy", "landscape_scale_z", "landscape_z_location_cm"):
                if not _is_finite_number(heightmap.get(key)):
                    self.error("heightmap_number_invalid", f"{rel}#/heightmap/{key}", "Expected a finite number")
            if _is_finite_number(heightmap.get("px")) and (int(heightmap["px"]) != heightmap["px"] or heightmap["px"] <= 1):
                self.error("heightmap_px", f"{rel}#/heightmap/px", "Heightmap px must be an integer greater than one")

        sun = meta.get("sun")
        if not isinstance(sun, dict) or not _is_finite_number(sun.get("elevation_deg")):
            self.error("sun_invalid", f"{rel}#/sun", "Expected sun.elevation_deg as a finite number")
        elif not -90 <= sun["elevation_deg"] <= 90:
            self.error("sun_elevation_range", f"{rel}#/sun/elevation_deg", "Sun elevation must be between -90 and 90")

        if not isinstance(meta.get("counts"), dict):
            self.error("counts_invalid", f"{rel}#/counts", "Expected a counts object")

    def _validate_proxy_index(self, scene: str, proxy_index: Mapping[str, Any]) -> None:
        rel = f"{scene}/proxy_meshes/proxy_index.json"
        if not proxy_index:
            self.error("proxy_index_empty", rel, "Proxy index must contain at least one proxy type")
            return
        for kind, spec in sorted(proxy_index.items()):
            base = f"{rel}#/{kind}"
            if not SCENE_NAME_RE.fullmatch(kind):
                self.error("proxy_name_invalid", base, "Proxy type must be a safe lowercase slug")
            if not isinstance(spec, dict):
                self.error("proxy_spec_invalid", base, "Proxy entry must be an object")
                continue
            native = spec.get("native_size_cm")
            if native is not None and (not _is_finite_number(native) or native <= 0):
                self.error("proxy_native_size", f"{base}/native_size_cm", "Expected null or a positive number")
            bbox = spec.get("bbox_cm")
            if not isinstance(bbox, list) or len(bbox) != 2:
                self.error("proxy_bbox", f"{base}/bbox_cm", "Expected [min_xyz, max_xyz]")
            else:
                lo = self._vector(bbox[0], 3, f"{base}/bbox_cm/0")
                hi = self._vector(bbox[1], 3, f"{base}/bbox_cm/1")
                if lo and hi and any(a >= b for a, b in zip(lo, hi)):
                    self.error("proxy_bbox_order", f"{base}/bbox_cm", "Every minimum bound must be less than its maximum")
            slots = spec.get("slots")
            if not isinstance(slots, list) or not slots or not all(isinstance(x, str) and x for x in slots):
                self.error("proxy_slots", f"{base}/slots", "Expected a non-empty list of slot names")
            elif len(slots) != len(set(slots)):
                self.error("proxy_slots_duplicate", f"{base}/slots", "Material slot names must be unique")
            colors = spec.get("colors")
            if not isinstance(colors, dict):
                self.error("proxy_colors", f"{base}/colors", "Expected a material color object")
            else:
                for slot, color in colors.items():
                    if not isinstance(slot, str) or not isinstance(color, str) or not HEX_COLOR_RE.fullmatch(color):
                        self.error("proxy_color", f"{base}/colors/{slot}", "Expected a #RRGGBB color")

    def _validate_buildings(
        self,
        scene: str,
        doc: Mapping[str, Any],
        meta: Mapping[str, Any],
        proxy_index: Mapping[str, Any],
    ) -> tuple[int, int]:
        rel = f"{scene}/buildings.json"
        records = doc.get("buildings")
        roads = doc.get("roads")
        if not isinstance(doc.get("coords"), str) or not doc.get("coords"):
            self.error("building_coords", f"{rel}#/coords", "Expected coordinate description text")
        if not isinstance(doc.get("scale_rule"), str) or not doc.get("scale_rule"):
            self.error("building_scale_rule", f"{rel}#/scale_rule", "Expected scale rule text")
        if not isinstance(records, list):
            self.error("buildings_type", f"{rel}#/buildings", "Expected a building array")
            records = []
        terrain_size = _nested_number(meta, "terrain", "size_cm")
        half = terrain_size / 2 if terrain_size else None
        for index, record in enumerate(records):
            base = f"{rel}#/buildings/{index}"
            if not isinstance(record, dict):
                self.error("building_record", base, "Building must be an object")
                continue
            kind = record.get("type")
            if not isinstance(kind, str) or not kind:
                self.error("building_type", f"{base}/type", "Expected a non-empty proxy type")
            elif kind not in proxy_index:
                self.error("building_proxy_missing", f"{base}/type", f"Proxy '{kind}' is absent from proxy_index")
            if not isinstance(record.get("src"), str) or not record.get("src"):
                self.error("building_src", f"{base}/src", "Expected a non-empty source category")
            pos = self._vector(record.get("pos_cm"), 3, f"{base}/pos_cm")
            size = self._vector(record.get("size_cm"), 3, f"{base}/size_cm")
            if size and any(v <= 0 for v in size):
                self.error("building_size", f"{base}/size_cm", "Every building dimension must be positive")
            if pos and size and half is not None:
                if abs(pos[0]) > half + size[0] / 2 or abs(pos[1]) > half + size[1] / 2:
                    self.error("building_outside_terrain", f"{base}/pos_cm", "Building lies outside terrain bounds")
            if not _is_finite_number(record.get("yaw_deg")):
                self.error("building_yaw", f"{base}/yaw_deg", "Expected a finite yaw")

        if not isinstance(roads, list):
            self.error("roads_type", f"{rel}#/roads", "Expected a roads array")
            roads = []
        for index, road in enumerate(roads):
            base = f"{rel}#/roads/{index}"
            if not isinstance(road, dict):
                self.error("road_record", base, "Road must be an object")
                continue
            width = road.get("width_cm")
            if not _is_finite_number(width) or width <= 0:
                self.error("road_width", f"{base}/width_cm", "Road width must be positive")
            points = road.get("points_cm")
            if not isinstance(points, list) or len(points) < 2:
                self.error("road_points", f"{base}/points_cm", "Road must contain at least two points")
            else:
                for point_index, point in enumerate(points):
                    self._vector(point, 3, f"{base}/points_cm/{point_index}")
        return len(records), len(roads)

    def _validate_people(self, scene: str, doc: Mapping[str, Any], meta: Mapping[str, Any]) -> int:
        rel = f"{scene}/people.json"
        people = doc.get("people")
        if not isinstance(doc.get("coords"), str) or not doc.get("coords"):
            self.error("people_coords", f"{rel}#/coords", "Expected coordinate description text")
        if not isinstance(people, list):
            self.error("people_type", f"{rel}#/people", "Expected a people array")
            return 0
        names: set[str] = set()
        terrain_size = _nested_number(meta, "terrain", "size_cm")
        half = terrain_size / 2 if terrain_size else None
        for index, person in enumerate(people):
            base = f"{rel}#/people/{index}"
            if not isinstance(person, dict):
                self.error("person_record", base, "Person must be an object")
                continue
            name = person.get("name")
            if not isinstance(name, str) or not name.strip():
                self.error("person_name", f"{base}/name", "Expected a non-empty name")
            elif name in names:
                self.error("person_name_duplicate", f"{base}/name", f"Duplicate person name '{name}'")
            else:
                names.add(name)
            for key in ("role", "role_ru"):
                if not isinstance(person.get(key), str) or not person.get(key):
                    self.error("person_role", f"{base}/{key}", "Expected a non-empty role")
            for key in ("sex", "age", "real", "yaw_deg"):
                if not _is_finite_number(person.get(key)):
                    self.error("person_number", f"{base}/{key}", "Expected a finite number")
            if _is_finite_number(person.get("age")) and not 0 <= person["age"] <= 130:
                self.error("person_age", f"{base}/age", "Age must be between 0 and 130")
            if person.get("sex") not in (0, 1):
                self.warn("person_sex_domain", f"{base}/sex", "Expected the current exporter domain 0 or 1")
            if person.get("real") not in (0, 1, False, True):
                self.error("person_real_domain", f"{base}/real", "Expected 0/1 or boolean")
            born = person.get("born")
            if born is not None and not _is_finite_number(born):
                self.error("person_born", f"{base}/born", "Expected null or a finite birth year")
            if person.get("real") in (0, 1):
                if bool(person["real"]) != (born is not None):
                    self.error(
                        "person_born_real_mismatch",
                        f"{base}/born",
                        "Real people require a birth year; population proxies require null",
                    )
            for key in ("cloth_hex", "skin_hex"):
                if not isinstance(person.get(key), str) or not HEX_COLOR_RE.fullmatch(person[key]):
                    self.error("person_color", f"{base}/{key}", "Expected a #RRGGBB color")
            spawn = self._vector(person.get("spawn_cm"), 3, f"{base}/spawn_cm")
            if spawn and half is not None and (abs(spawn[0]) > half or abs(spawn[1]) > half):
                self.error("person_outside_terrain", f"{base}/spawn_cm", "Person spawn lies outside terrain bounds")
            route = person.get("route_cm")
            if not isinstance(route, list) or not route:
                self.error("person_route", f"{base}/route_cm", "Expected a non-empty route")
            else:
                parsed_route = [self._vector(point, 3, f"{base}/route_cm/{i}") for i, point in enumerate(route)]
                if spawn and parsed_route and parsed_route[0] and math.dist(spawn, parsed_route[0]) > 250:
                    self.warn("person_route_start", f"{base}/route_cm/0", "Route starts more than 250 cm from spawn")
            card = person.get("card")
            if not isinstance(card, dict):
                self.error("person_card", f"{base}/card", "Expected a person card object")
            else:
                for key in ("deeds", "traits", "beliefs"):
                    if not isinstance(card.get(key), list) or not all(isinstance(x, str) for x in card.get(key, [])):
                        self.error("person_card_list", f"{base}/card/{key}", "Expected a list of strings")
                if not _is_finite_number(card.get("prestige")):
                    self.error("person_prestige", f"{base}/card/prestige", "Expected finite prestige")
                if not isinstance(card.get("real_person"), bool):
                    self.error("real_person_type", f"{base}/card/real_person", "Expected a boolean")
                if isinstance(card.get("real_person"), bool) and person.get("real") in (0, 1):
                    if card["real_person"] != bool(person["real"]):
                        self.error("real_person_mismatch", f"{base}/card/real_person", "Card flag differs from person.real")
        return len(people)

    def _validate_declared_counts(
        self,
        scene: str,
        meta: Mapping[str, Any],
        building_counts: tuple[int, int],
        people_count: int,
    ) -> None:
        counts = meta.get("counts")
        if not isinstance(counts, dict):
            return
        actual = {
            "buildings": building_counts[0],
            "roads": building_counts[1],
            "people": people_count,
        }
        for key, value in actual.items():
            declared = counts.get(key)
            if not isinstance(declared, int) or isinstance(declared, bool):
                self.error("declared_count_type", f"{scene}/meta.json#/counts/{key}", "Expected an integer")
            elif declared != value:
                self.error(
                    "declared_count_mismatch",
                    f"{scene}/meta.json#/counts/{key}",
                    f"Declared {declared}, found {value}",
                )

    def _validate_scene_files(
        self,
        scene: str,
        meta: Mapping[str, Any],
        proxy_index: Mapping[str, Any],
    ) -> None:
        object_pairs = [("terrain.obj", "terrain.mtl"), ("terrain_far.obj", "terrain_far.mtl")]
        terrain = meta.get("terrain") if isinstance(meta.get("terrain"), dict) else {}
        if terrain.get("water_z_cm") is not None:
            object_pairs.append(("water.obj", "water.mtl"))
        for obj_name, mtl_name in object_pairs:
            obj_rel = f"{scene}/{obj_name}"
            mtl_rel = f"{scene}/{mtl_name}"
            obj_path = self._record_file(obj_rel, "static_mesh_obj")
            mtl_path = self._record_file(mtl_rel, "material_mtl")
            if obj_path:
                self._validate_obj(obj_path, obj_rel)
            if mtl_path:
                self._validate_mtl(mtl_path, mtl_rel)

        color_rel = f"{scene}/terrain_color.png"
        color_path = self._record_file(color_rel, "terrain_color")
        if color_path:
            info = self._validate_png(color_path, color_rel)
            if info and (info[2] != 8 or info[3] not in (2, 6)):
                self.error("terrain_color_format", color_rel, "Expected an 8-bit RGB or RGBA PNG")

        height_rel = f"{scene}/masks/heightmap.png"
        height_path = self._record_file(height_rel, "heightmap")
        if height_path:
            info = self._validate_png(height_path, height_rel)
            expected_px = _nested_number(meta, "heightmap", "px")
            if info:
                if expected_px and (info[0], info[1]) != (int(expected_px), int(expected_px)):
                    self.error("heightmap_dimensions", height_rel, f"Expected {int(expected_px)}x{int(expected_px)}, got {info[0]}x{info[1]}")
                if info[2:] != (16, 0):
                    self.error("heightmap_format", height_rel, "Expected a 16-bit grayscale PNG")

        mask_dimensions: set[tuple[int, int]] = set()
        for name in ("grass", "dirt", "rock", "sand"):
            rel = f"{scene}/masks/{name}.png"
            path = self._record_file(rel, "terrain_weight_mask")
            if path:
                info = self._validate_png(path, rel)
                if info:
                    mask_dimensions.add(info[:2])
                    if info[2:] != (8, 0):
                        self.error("weight_mask_format", rel, "Expected an 8-bit grayscale PNG")
        if len(mask_dimensions) > 1:
            self.error("weight_mask_dimensions", f"{scene}/masks", "All weight masks must use identical dimensions")

        for kind in sorted(proxy_index):
            obj_rel = f"{scene}/proxy_meshes/{kind}.obj"
            mtl_rel = f"{scene}/proxy_meshes/{kind}.mtl"
            obj_path = self._record_file(obj_rel, "proxy_mesh_obj")
            mtl_path = self._record_file(mtl_rel, "proxy_material_mtl")
            if obj_path:
                self._validate_obj(obj_path, obj_rel)
            if mtl_path:
                self._validate_mtl(mtl_path, mtl_rel)

    def _validate_png(self, path: Path, rel: str) -> tuple[int, int, int, int] | None:
        try:
            with path.open("rb") as stream:
                header = stream.read(33)
        except OSError as exc:
            self.error("png_unreadable", rel, f"Cannot read PNG: {exc}")
            return None
        if len(header) < 33 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
            self.error("png_header", rel, "Missing a valid PNG IHDR header")
            return None
        width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
            ">IIBBBBB", header[16:29]
        )
        if width <= 0 or height <= 0:
            self.error("png_dimensions", rel, "PNG dimensions must be positive")
        if compression != 0 or filter_method != 0 or interlace not in (0, 1):
            self.error("png_encoding", rel, "Unsupported PNG encoding flags")
        return width, height, bit_depth, color_type

    def _validate_obj(self, path: Path, rel: str) -> None:
        vertices = texture_vertices = faces = missing_uv = 0
        max_vertex = max_texture = 0
        libraries: set[str] = set()
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line_number, raw in enumerate(stream, 1):
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("v "):
                        vertices += 1
                    elif line.startswith("vt "):
                        texture_vertices += 1
                    elif line.startswith("f "):
                        faces += 1
                        tokens = line.split()[1:]
                        if len(tokens) < 3:
                            self.error("obj_face_arity", f"{rel}:{line_number}", "Face has fewer than three vertices")
                        for token in tokens:
                            parts = token.split("/")
                            if len(parts) < 2 or not parts[1]:
                                missing_uv += 1
                                continue
                            try:
                                vertex_index = int(parts[0])
                                texture_index = int(parts[1])
                            except ValueError:
                                self.error("obj_face_index", f"{rel}:{line_number}", "Face contains a non-integer index")
                                continue
                            if vertex_index == 0 or texture_index == 0:
                                self.error("obj_zero_index", f"{rel}:{line_number}", "OBJ indices are one-based and cannot be zero")
                            if vertex_index > 0:
                                max_vertex = max(max_vertex, vertex_index)
                            if texture_index > 0:
                                max_texture = max(max_texture, texture_index)
                    elif line.startswith("mtllib "):
                        libraries.update(line.split()[1:])
        except (OSError, UnicodeError) as exc:
            self.error("obj_unreadable", rel, f"Cannot read OBJ: {exc}")
            return
        if vertices == 0 or faces == 0:
            self.error("obj_geometry_empty", rel, "OBJ must contain vertices and faces")
        if texture_vertices == 0 or missing_uv:
            self.error("obj_uv_missing", rel, f"OBJ has no complete UV mapping ({missing_uv} face vertices lack UVs)")
        if max_vertex > vertices:
            self.error("obj_vertex_index_range", rel, f"Face references vertex {max_vertex}, but only {vertices} exist")
        if max_texture > texture_vertices:
            self.error("obj_uv_index_range", rel, f"Face references UV {max_texture}, but only {texture_vertices} exist")
        if not libraries:
            self.warn("obj_mtl_missing", rel, "OBJ does not declare an mtllib")
        for library in sorted(libraries):
            candidate = Path(library)
            if candidate.is_absolute() or ".." in candidate.parts:
                self.error("obj_mtl_path", rel, f"Unsafe mtllib reference '{library}'")
            elif not (path.parent / candidate).is_file():
                self.error("obj_mtl_unresolved", rel, f"mtllib reference '{library}' does not exist")

    def _validate_mtl(self, path: Path, rel: str) -> None:
        materials = 0
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            self.error("mtl_unreadable", rel, f"Cannot read MTL: {exc}")
            return
        for line_number, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("newmtl "):
                materials += 1
            elif line.startswith("map_"):
                try:
                    tokens = shlex.split(line)
                except ValueError as exc:
                    self.error("mtl_map_syntax", f"{rel}:{line_number}", f"Invalid texture map line: {exc}")
                    continue
                if len(tokens) < 2:
                    self.error("mtl_map_missing", f"{rel}:{line_number}", "Texture map has no file")
                    continue
                texture_name = tokens[-1]
                candidate = Path(texture_name)
                if candidate.is_absolute() or ".." in candidate.parts:
                    self.error("mtl_map_path", f"{rel}:{line_number}", f"Unsafe texture reference '{texture_name}'")
                elif not (path.parent / candidate).is_file():
                    self.error("mtl_map_unresolved", f"{rel}:{line_number}", f"Texture '{texture_name}' does not exist")
        if materials == 0:
            self.error("mtl_empty", rel, "MTL must define at least one material")

    def _vector(self, value: Any, length: int, path: str) -> tuple[float, ...] | None:
        if not isinstance(value, list) or len(value) != length or not all(_is_finite_number(x) for x in value):
            self.error("vector_invalid", path, f"Expected {length} finite numbers")
            return None
        return tuple(float(x) for x in value)


def validate_export(export_root: Path) -> ValidationResult:
    """Validate an export root without modifying it."""

    return Validator(export_root).validate()


def canonical_json(value: Any) -> str:
    """Canonical JSON used as input to provisional identity generation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def provisional_entity_identity(
    run_id: str,
    scene: str,
    entity_kind: str,
    source_index: int,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic UUIDv5 identity record for an un-IDed entity.

    Source index is intentionally part of the seed: it makes duplicate source
    records unique, but also means reordering is an identity-breaking upstream
    change.  The manifest declares this limitation and requires eventual
    migration to exporter-owned authoritative IDs.
    """

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be non-empty text")
    if not isinstance(scene, str) or not SCENE_NAME_RE.fullmatch(scene):
        raise ValueError("scene must be a safe slug")
    if entity_kind not in {"building", "person"}:
        raise ValueError("entity_kind must be 'building' or 'person'")
    if not isinstance(source_index, int) or isinstance(source_index, bool) or source_index < 0:
        raise ValueError("source_index must be a non-negative integer")
    if not isinstance(record, Mapping):
        raise ValueError("record must be a mapping")
    record_json = canonical_json(record)
    seed = canonical_json(
        {
            "entity_kind": entity_kind,
            "record": record,
            "run_id": run_id,
            "scene": scene,
            "source_index": source_index,
        }
    )
    entity_uuid = uuid.uuid5(IDENTITY_NAMESPACE_UUID, seed)
    return {
        "entity_id": str(entity_uuid),
        "kind": entity_kind,
        "source_index": source_index,
        "record_sha256": hashlib.sha256(record_json.encode("utf-8")).hexdigest(),
        "status": "provisional",
    }


def build_manifest(result: ValidationResult, project_root: Path) -> dict[str, Any]:
    """Build a portable deterministic manifest from a valid result."""

    if not result.valid:
        raise ValueError(f"Cannot build a manifest with {len(result.errors)} validation errors")
    project_root = project_root.resolve()
    try:
        source_root = result.export_root.relative_to(project_root).as_posix()
    except ValueError as exc:
        raise ValueError("Export root must be inside project_root; absolute source paths are forbidden") from exc
    if source_root.startswith("../") or source_root == "..":
        raise ValueError("Export source path escapes project root")

    export_digest = _digest_entries(result.files)
    content_digest = _content_revision_digest(export_digest)
    version = f"v_{content_digest[:12]}"
    version_root = f"{CONTENT_NAMESPACE}/{version}"
    scenes: list[dict[str, Any]] = []
    entity_ids: set[str] = set()
    for scene in result.scenes:
        name = scene["name"]
        entries = [entry for entry in result.files if entry["path"].startswith(name + "/")]
        scene_digest = _digest_entries(entries)
        buildings_doc = json.loads((result.export_root / name / "buildings.json").read_text(encoding="utf-8"))
        people_doc = json.loads((result.export_root / name / "people.json").read_text(encoding="utf-8"))
        building_entities = [
            provisional_entity_identity(EXPECTED_RUN_ID, name, "building", index, record)
            for index, record in enumerate(buildings_doc["buildings"])
        ]
        people_entities = [
            provisional_entity_identity(EXPECTED_RUN_ID, name, "person", index, record)
            for index, record in enumerate(people_doc["people"])
        ]
        for entity in building_entities + people_entities:
            if entity["entity_id"] in entity_ids:
                raise ValueError(f"Provisional entity UUID collision: {entity['entity_id']}")
            entity_ids.add(entity["entity_id"])
        scenes.append(
            {
                "name": name,
                "title": scene.get("title"),
                "settlement": scene.get("settlement"),
                "polity": scene.get("polity"),
                "era": scene.get("era"),
                "year": scene.get("year"),
                "population": scene.get("population"),
                "seed": scene.get("seed"),
                "built_at": scene.get("built_at"),
                "counts": scene["counts"],
                "proxy_types": scene["proxy_types"],
                "digest": f"sha256:{scene_digest}",
                "entities": {
                    "buildings": building_entities,
                    "people": people_entities,
                },
                "files": entries,
                "unreal": {
                    "content_root": f"{version_root}/{name}",
                    "level": f"{version_root}/Maps/L_{name}",
                    "mesh_root": f"{version_root}/{name}/Meshes",
                    "data_root": f"{version_root}/{name}/Data",
                },
            }
        )
    return {
        "schema": MANIFEST_SCHEMA,
        "tool_version": TOOL_VERSION,
        "content_namespace": CONTENT_NAMESPACE,
        "version": version,
        "version_content_root": version_root,
        "content_digest": f"sha256:{content_digest}",
        "identity": {
            "status": "provisional",
            "scheme": IDENTITY_SCHEME,
            "namespace_uuid": str(IDENTITY_NAMESPACE_UUID),
            "namespace_derivation": "UUIDv5(NAMESPACE_URL, 'urn:terra:entity:provisional:v1')",
            "algorithm": "UUIDv5(namespace_uuid, canonical UTF-8 JSON identity seed)",
            "canonicalization": "JSON keys sorted; separators ',' and ':'; UTF-8; Unicode preserved; NaN forbidden",
            "seed_fields": ["run_id", "scene", "entity_kind", "source_index", "record"],
            "source_authoritative_id_field": None,
            "stability_scope": "Stable only while source index and canonical record are unchanged",
            "migration_required": True,
            "migration_target": "Exporter-owned authoritative IDs plus a provisional-to-authoritative alias map",
        },
        "source": {
            "run_id": EXPECTED_RUN_ID,
            "project_relative_root": source_root,
            "digest": f"sha256:{export_digest}",
        },
        "validation": {
            "status": "valid",
            "errors": 0,
            "warnings": len(result.warnings),
            "diagnostics": [d.as_dict() for d in result.warnings],
        },
        "import_order": [s["name"] for s in scenes],
        "scenes": scenes,
    }


def scan_legacy_content(legacy_root: Path) -> dict[str, Any]:
    """Read only coarse, recoverable metadata from legacy Unreal packages.

    This is intentionally not a general UAsset parser.  It inventories package
    names and extracts stable actor-label strings from maps when those strings
    remain readable in the binary package.
    """

    root = legacy_root.resolve()
    if not root.exists():
        return {"status": "missing", "root": legacy_root.as_posix(), "files": 0, "extensions": {}, "maps": []}
    if not root.is_dir():
        return {"status": "unreadable", "root": legacy_root.as_posix(), "files": 0, "extensions": {}, "maps": [], "reason": "not a directory"}
    package_files = sorted(
        (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".uasset", ".umap"}),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    extensions = Counter(p.suffix.lower() for p in package_files)
    maps: list[dict[str, Any]] = []
    for path in (p for p in package_files if p.suffix.lower() == ".umap"):
        rel = path.relative_to(root).as_posix()
        scene = path.stem[2:] if path.stem.startswith("L_") else path.stem
        item: dict[str, Any] = {
            "path": rel,
            "scene": scene,
            "bytes": path.stat().st_size,
            "readable": False,
            "building_labels": None,
            "npc_label_occurrences": None,
            "building_types": [],
            "package_roots": [],
        }
        if item["bytes"] > 512 * 1024 * 1024:
            item["reason"] = "map exceeds the 512 MiB safety scan limit"
            maps.append(item)
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            item["reason"] = str(exc)
            maps.append(item)
            continue
        labels = {
            match.decode("ascii")
            for match in re.findall(rb"B_[A-Za-z0-9_]+_[0-9]+", data)
        }
        npc_ascii = data.count(b"NPC_")
        npc_utf16 = data.count("NPC_".encode("utf-16le"))
        package_roots = {
            match.decode("ascii")
            for match in re.findall(rb"/Game/Terra(?:/[A-Za-z0-9_]+)+", data)
        }
        item.update(
            {
                "readable": True,
                "building_labels": len(labels),
                "npc_label_occurrences": max(npc_ascii, npc_utf16),
                "building_types": sorted({label[2:].rsplit("_", 1)[0] for label in labels}),
                "package_roots": sorted(package_roots),
            }
        )
        maps.append(item)
    scene_assets: dict[str, dict[str, Any]] = {}
    for directory in sorted((p for p in root.iterdir() if p.is_dir() and p.name != "Maps"), key=lambda p: p.name):
        proxies = directory / "Meshes" / "Proxies"
        scene_assets[directory.name] = {
            "package_files": sum(1 for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in {".uasset", ".umap"}),
            "proxy_assets": sorted(p.stem for p in proxies.glob("*.uasset")) if proxies.is_dir() else [],
        }
    return {
        "status": "found",
        "root": legacy_root.as_posix(),
        "files": len(package_files),
        "extensions": dict(sorted(extensions.items())),
        "maps": maps,
        "scene_assets": scene_assets,
        "method": "filename inventory plus recoverable ASCII/UTF-16 actor labels; not a full UAsset parse",
    }


def render_report(result: ValidationResult, manifest: Mapping[str, Any], legacy: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown report."""

    status = "VALID" if result.valid else "INVALID"
    lines = [
        "# TERRA Unreal export validation report",
        "",
        f"- Status: **{status}**",
        f"- Manifest schema: `{MANIFEST_SCHEMA}`",
        f"- Run: `{EXPECTED_RUN_ID}`",
        f"- Export digest: `{manifest['source']['digest']}`",
        f"- Content revision digest: `{manifest['content_digest']}`",
        f"- Safe Unreal namespace: `{manifest['version_content_root']}`",
        f"- Files covered by digest: {len(result.files)}",
        f"- Errors: {len(result.errors)}; warnings: {len(result.warnings)}",
        "",
        "## Current export",
        "",
        "| Scene | Year | Settlement | Buildings | Roads | People | Scene digest |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for scene in manifest["scenes"]:
        counts = scene["counts"]
        lines.append(
            f"| `{scene['name']}` | {scene['year']} | {scene['settlement']} | "
            f"{counts['buildings']} | {counts['roads']} | {counts['people']} | `{scene['digest']}` |"
        )

    identity = manifest["identity"]
    identity_count = sum(
        len(scene["entities"]["buildings"]) + len(scene["entities"]["people"])
        for scene in manifest["scenes"]
    )
    lines.extend(
        [
            "",
            "## Entity identity",
            "",
            f"- Status: **{identity['status']}**",
            f"- Scheme: `{identity['scheme']}`",
            f"- Namespace UUID: `{identity['namespace_uuid']}`",
            f"- Deterministic entity IDs generated: {identity_count}",
            f"- Stability: {identity['stability_scope']}.",
            "- Migration required: upstream exporter must provide authoritative IDs and an alias map from every provisional UUID.",
        ]
    )

    lines.extend(["", "## Diagnostics", ""])
    if not result.diagnostics:
        lines.append("No schema or invariant findings.")
    else:
        lines.extend(["| Severity | Code | Path | Message |", "|---|---|---|---|"])
        for diagnostic in result.diagnostics:
            lines.append(
                f"| {diagnostic.severity} | `{_md(diagnostic.code)}` | `{_md(diagnostic.path)}` | {_md(diagnostic.message)} |"
            )

    lines.extend(["", "## Legacy `/Game/Terra` comparison", ""])
    if legacy.get("status") != "found":
        lines.append(f"Legacy content status: `{legacy.get('status', 'unknown')}`.")
    else:
        maps_by_scene = {m.get("scene"): m for m in legacy.get("maps", [])}
        lines.extend(
            [
                "| Scene | Legacy map | Legacy building labels | Current buildings | Δ | Legacy NPC labels | Current people | Δ |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for scene in manifest["scenes"]:
            old = maps_by_scene.get(scene["name"])
            if not old:
                lines.append(
                    f"| `{scene['name']}` | no | — | {scene['counts']['buildings']} | — | — | {scene['counts']['people']} | — |"
                )
                continue
            old_buildings = old.get("building_labels")
            old_people = old.get("npc_label_occurrences")
            building_delta = old_buildings - scene["counts"]["buildings"] if isinstance(old_buildings, int) else None
            people_delta = old_people - scene["counts"]["people"] if isinstance(old_people, int) else None
            lines.append(
                f"| `{scene['name']}` | yes | {_num(old_buildings)} | {scene['counts']['buildings']} | {_signed(building_delta)} | "
                f"{_num(old_people)} | {scene['counts']['people']} | {_signed(people_delta)} |"
            )
        lines.extend(
            [
                "",
                f"Legacy package files inventoried: {legacy.get('files', 0)}. "
                "Counts from `.umap` are recoverable actor-label evidence, not a full Unreal package parse.",
            ]
        )

    lines.extend(
        [
            "",
            "## Import safety contract",
            "",
            f"The importer accepts only `{CONTENT_NAMESPACE}` and the digest-versioned root "
            f"`{manifest['version_content_root']}`. It refuses `/Game/Terra`, verifies source hashes before any "
            "editor mutation, and refuses to overwrite an existing generated scene destination or level.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    project = _default_project_root()
    parser.add_argument("--project-root", type=Path, default=project, help="Unreal project root")
    parser.add_argument("--export-root", type=Path, default=project / "export_ue", help="terra-life export root")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate schema, files, and scene invariants")
    _add_common_paths(validate)
    validate.add_argument("--json", action="store_true", help="Print diagnostics as JSON")

    compare = sub.add_parser("compare", help="Inspect readable metadata in legacy Content/Terra")
    _add_common_paths(compare)
    compare.add_argument("--legacy-content", type=Path, default=_default_project_root() / "Content" / "Terra")

    generate = sub.add_parser("generate", help="Validate and generate manifest plus report")
    _add_common_paths(generate)
    generate.add_argument("--legacy-content", type=Path, default=_default_project_root() / "Content" / "Terra")
    generate.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parent / "generated" / "import_manifest.json")
    generate.add_argument("--report", type=Path, default=Path(__file__).resolve().parent / "generated" / "validation_report.md")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_export(args.export_root)
    if args.command == "validate":
        payload = result.summary()
        if args.json:
            payload["diagnostics"] = [d.as_dict() for d in result.diagnostics]
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result.valid else 2

    if args.command == "compare":
        legacy = scan_legacy_content(args.legacy_content)
        payload = {"validation": result.summary(), "legacy": legacy}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result.valid else 2

    if not result.valid:
        print(json.dumps({"validation": result.summary(), "diagnostics": [d.as_dict() for d in result.diagnostics]}, ensure_ascii=False, sort_keys=True, indent=2), file=sys.stderr)
        return 2
    try:
        manifest = build_manifest(result, args.project_root)
    except ValueError as exc:
        print(f"manifest generation failed: {exc}", file=sys.stderr)
        return 2
    legacy = scan_legacy_content(args.legacy_content)
    report = render_report(result, manifest, legacy)
    write_json(args.manifest, manifest)
    write_text(args.report, report)
    print(
        json.dumps(
            {
                "validation": result.summary(),
                "export_digest": manifest["source"]["digest"],
                "content_digest": manifest["content_digest"],
                "version_content_root": manifest["version_content_root"],
                "manifest": args.manifest.as_posix(),
                "report": args.report.as_posix(),
                "legacy_status": legacy.get("status"),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def _role_for(relative: str) -> str:
    return {
        "meta.json": "scene_meta",
        "buildings.json": "building_data",
        "people.json": "people_data",
        "proxy_meshes/proxy_index.json": "proxy_index",
    }.get(relative, "data")


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _nested_number(value: Mapping[str, Any], outer: str, inner: str) -> float | None:
    nested = value.get(outer)
    if isinstance(nested, dict) and _is_finite_number(nested.get(inner)):
        return float(nested[inner])
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_entries(entries: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(b"terra-life-unreal-export-v1\0")
    for entry in sorted(entries, key=lambda item: str(item["path"])):
        digest.update(str(entry["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry["sha256"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(entry["bytes"]).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _content_revision_digest(export_digest: str) -> str:
    digest = hashlib.sha256(b"terra-unreal-content-revision-v1\0")
    digest.update(export_digest.encode("ascii"))
    digest.update(b"\0")
    digest.update(IDENTITY_SCHEME.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(IDENTITY_NAMESPACE_UUID).encode("ascii"))
    return digest.hexdigest()


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _num(value: Any) -> str:
    return str(value) if isinstance(value, int) else "—"


def _signed(value: int | None) -> str:
    return f"{value:+d}" if isinstance(value, int) else "—"


if __name__ == "__main__":
    raise SystemExit(main())
