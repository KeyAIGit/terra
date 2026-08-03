#!/usr/bin/env python3
"""Digest-verified Unreal Editor loader for the ``terra-life`` scene bible.

The module is intentionally inert when loaded: call :func:`run` explicitly.
It imports into a digest-versioned child of ``/Game/TerraLife`` and refuses to
read or mutate the legacy ``/Game/Terra`` namespace.

Example in Unreal's Python console (first run should stay dry):

    exec(open("/absolute/project/Scripts/terra_data/unreal_import_terra_life.py",
              encoding="utf-8").read())
    run("capital", dry_run=True)
    run("capital", dry_run=False)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping


MANIFEST_SCHEMA = "terra.unreal-import-manifest/v1"
CONTENT_NAMESPACE = "/Game/TerraLife"
LEGACY_NAMESPACE = "/Game/Terra"
IDENTITY_SCHEME = "terra.provisional-entity-uuidv5/v1"
IDENTITY_NAMESPACE_UUID = uuid.UUID("c6e6fa94-b92b-5bae-b40e-62f31a09bdcf")
VERSION_RE = re.compile(r"^v_[0-9a-f]{12}$")
GAME_PATH_RE = re.compile(r"^/Game(?:/[A-Za-z0-9_]+)+$")


class ImportSafetyError(RuntimeError):
    """Raised before mutation when an input or destination is unsafe."""


def assert_safe_game_path(path: str) -> str:
    """Return a normalized safe path or reject it.

    The boundary checks are exact: ``/Game/TerraLife`` is accepted even though
    its textual prefix contains ``/Game/Terra``; ``/Game/Terra/...`` is not.
    """

    if not isinstance(path, str) or not GAME_PATH_RE.fullmatch(path):
        raise ImportSafetyError(f"Unsafe Unreal package path: {path!r}")
    if path == LEGACY_NAMESPACE or path.startswith(LEGACY_NAMESPACE + "/"):
        raise ImportSafetyError(f"Legacy namespace is read-only: {path}")
    if path != CONTENT_NAMESPACE and not path.startswith(CONTENT_NAMESPACE + "/"):
        raise ImportSafetyError(f"Destination must be inside {CONTENT_NAMESPACE}: {path}")
    return path


def load_manifest(project_root: Path, manifest_path: Path | None = None) -> tuple[dict[str, Any], Path]:
    """Load and structurally validate a portable import manifest."""

    project = project_root.resolve()
    path = (manifest_path or project / "Scripts" / "terra_data" / "generated" / "import_manifest.json").resolve()
    try:
        path.relative_to(project)
    except ValueError as exc:
        raise ImportSafetyError("Manifest must be inside the Unreal project") from exc
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImportSafetyError(f"Cannot read import manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ImportSafetyError(f"Manifest schema must be {MANIFEST_SCHEMA}")
    if manifest.get("content_namespace") != CONTENT_NAMESPACE:
        raise ImportSafetyError(f"Manifest namespace must be exactly {CONTENT_NAMESPACE}")
    version = manifest.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ImportSafetyError("Manifest version must be v_ followed by 12 lowercase SHA-256 characters")
    version_root = manifest.get("version_content_root")
    if version_root != f"{CONTENT_NAMESPACE}/{version}":
        raise ImportSafetyError("Version content root does not match namespace and digest version")
    assert_safe_game_path(version_root)

    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("run_id") != "terra-life":
        raise ImportSafetyError("Manifest source is not a terra-life run")
    source_rel = source.get("project_relative_root")
    if not isinstance(source_rel, str):
        raise ImportSafetyError("Manifest source path must be project-relative text")
    relative = Path(source_rel)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ImportSafetyError("Manifest source path is unsafe")
    source_root = (project / relative).resolve()
    try:
        source_root.relative_to(project)
    except ValueError as exc:
        raise ImportSafetyError("Export source resolves outside the project") from exc

    source_digest = source.get("digest")
    if not isinstance(source_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", source_digest):
        raise ImportSafetyError("Manifest source digest is not a SHA-256 value")
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise ImportSafetyError("Manifest has no identity declaration")
    if (
        identity.get("status") != "provisional"
        or identity.get("scheme") != IDENTITY_SCHEME
        or identity.get("namespace_uuid") != str(IDENTITY_NAMESPACE_UUID)
        or identity.get("migration_required") is not True
    ):
        raise ImportSafetyError("Manifest provisional identity declaration is incompatible")
    expected_content_digest = "sha256:" + _content_revision_digest(source_digest.removeprefix("sha256:"))
    if manifest.get("content_digest") != expected_content_digest:
        raise ImportSafetyError("Manifest content revision digest is inconsistent")
    if version != "v_" + expected_content_digest.removeprefix("sha256:")[:12]:
        raise ImportSafetyError("Manifest version does not match content revision digest")

    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ImportSafetyError("Manifest has no scenes")
    names: set[str] = set()
    entity_ids: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, dict) or not isinstance(scene.get("name"), str):
            raise ImportSafetyError("Every manifest scene needs a name")
        scene_name = scene["name"]
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", scene_name):
            raise ImportSafetyError(f"Unsafe manifest scene name: {scene_name!r}")
        if scene_name in names:
            raise ImportSafetyError(f"Duplicate manifest scene: {scene_name}")
        names.add(scene_name)
        unreal_paths = scene.get("unreal")
        if not isinstance(unreal_paths, dict):
            raise ImportSafetyError(f"Scene {scene_name} has no Unreal path plan")
        for key in ("content_root", "level", "mesh_root", "data_root"):
            planned = assert_safe_game_path(unreal_paths.get(key))
            if planned != version_root and not planned.startswith(version_root + "/"):
                raise ImportSafetyError(f"Scene path escapes version root: {planned}")
        expected_paths = {
            "content_root": f"{version_root}/{scene_name}",
            "level": f"{version_root}/Maps/L_{scene_name}",
            "mesh_root": f"{version_root}/{scene_name}/Meshes",
            "data_root": f"{version_root}/{scene_name}/Data",
        }
        if unreal_paths != expected_paths:
            raise ImportSafetyError(f"Scene {scene_name} Unreal path plan is not canonical")
        proxy_types = scene.get("proxy_types")
        if not isinstance(proxy_types, list) or not all(
            isinstance(kind, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", kind)
            for kind in proxy_types
        ):
            raise ImportSafetyError(f"Scene {scene_name} has an unsafe proxy type table")
        if len(proxy_types) != len(set(proxy_types)):
            raise ImportSafetyError(f"Scene {scene_name} repeats proxy types")
        counts = scene.get("counts")
        entities = scene.get("entities")
        if not isinstance(counts, dict) or not isinstance(entities, dict):
            raise ImportSafetyError(f"Scene {scene_name} has no counts or entity identity table")
        for collection, entity_kind, count_key in (
            ("buildings", "building", "buildings"),
            ("people", "person", "people"),
        ):
            records = entities.get(collection)
            expected_count = counts.get(count_key)
            if not isinstance(records, list) or not isinstance(expected_count, int) or len(records) != expected_count:
                raise ImportSafetyError(f"Scene {scene_name} identity count mismatch for {collection}")
            for index, entity in enumerate(records):
                if not isinstance(entity, dict):
                    raise ImportSafetyError(f"Scene {scene_name} has an invalid {entity_kind} identity")
                entity_id = entity.get("entity_id")
                try:
                    parsed_id = uuid.UUID(entity_id) if isinstance(entity_id, str) else None
                except ValueError as exc:
                    raise ImportSafetyError(f"Scene {scene_name} has an invalid entity UUID") from exc
                if parsed_id is None or parsed_id.version != 5 or str(parsed_id) != entity_id:
                    raise ImportSafetyError(f"Scene {scene_name} entity ID is not canonical UUIDv5")
                if entity_id in entity_ids:
                    raise ImportSafetyError(f"Duplicate entity ID in manifest: {entity_id}")
                entity_ids.add(entity_id)
                if (
                    entity.get("kind") != entity_kind
                    or entity.get("source_index") != index
                    or entity.get("status") != "provisional"
                    or not isinstance(entity.get("record_sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", entity["record_sha256"])
                ):
                    raise ImportSafetyError(f"Scene {scene_name} has inconsistent {entity_kind} identity metadata")
        files = scene.get("files")
        if not isinstance(files, list):
            raise ImportSafetyError(f"Scene {scene_name} has no file table")
        allowed = _allowed_scene_files(scene_name, set(proxy_types))
        for entry in files:
            if not isinstance(entry, dict) or entry.get("path") not in allowed:
                raise ImportSafetyError(
                    f"Scene {scene_name} manifest contains a non-whitelisted source file: "
                    f"{entry.get('path') if isinstance(entry, dict) else entry!r}"
                )
    return manifest, source_root


def preflight(
    project_root: Path,
    scene_name: str,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Verify every source file hash and selected scene invariant, without Unreal."""

    manifest, source_root = load_manifest(project_root, manifest_path)
    scene = _find_scene(manifest, scene_name)
    entries = _all_entries(manifest)
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ImportSafetyError("Manifest file entry must be an object")
        rel_text = entry.get("path")
        expected_hash = entry.get("sha256")
        expected_size = entry.get("bytes")
        if not isinstance(rel_text, str) or rel_text in seen:
            raise ImportSafetyError(f"Duplicate or invalid manifest file path: {rel_text!r}")
        seen.add(rel_text)
        relative = Path(rel_text)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ImportSafetyError(f"Unsafe source file path: {rel_text!r}")
        source_path = (source_root / relative).resolve()
        try:
            source_path.relative_to(source_root)
        except ValueError as exc:
            raise ImportSafetyError(f"Source path escapes export root: {rel_text}") from exc
        if source_path.is_symlink() or not source_path.is_file():
            raise ImportSafetyError(f"Required source file is absent or a symlink: {rel_text}")
        actual_size = source_path.stat().st_size
        if not isinstance(expected_size, int) or actual_size != expected_size:
            raise ImportSafetyError(f"Source size mismatch for {rel_text}: expected {expected_size}, got {actual_size}")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ImportSafetyError(f"Invalid SHA-256 in manifest for {rel_text}")
        actual_hash = _sha256_file(source_path)
        if actual_hash != expected_hash:
            raise ImportSafetyError(f"Source SHA-256 mismatch for {rel_text}")

    expected_export_digest = manifest["source"].get("digest")
    actual_export_digest = "sha256:" + _digest_entries(entries)
    if expected_export_digest != actual_export_digest:
        raise ImportSafetyError("Manifest export digest does not match its file table")

    scene_root = source_root / scene_name
    meta = _read_json_object(scene_root / "meta.json")
    buildings = _read_json_object(scene_root / "buildings.json")
    people = _read_json_object(scene_root / "people.json")
    proxies = _read_json_object(scene_root / "proxy_meshes" / "proxy_index.json")
    if meta.get("run_id") != "terra-life" or meta.get("scene") != scene_name:
        raise ImportSafetyError("Selected scene metadata does not match terra-life manifest")
    expected_counts = scene.get("counts")
    actual_counts = {
        "buildings": len(buildings.get("buildings", [])),
        "roads": len(buildings.get("roads", [])),
        "people": len(people.get("people", [])),
    }
    if expected_counts != actual_counts or meta.get("counts") != actual_counts:
        raise ImportSafetyError("Selected scene counts differ from manifest")
    if sorted(proxies) != sorted(scene.get("proxy_types", [])):
        raise ImportSafetyError("Selected scene proxy index differs from manifest")
    expected_entities = {
        "buildings": [
            _provisional_entity_identity("terra-life", scene_name, "building", index, record)
            for index, record in enumerate(buildings["buildings"])
        ],
        "people": [
            _provisional_entity_identity("terra-life", scene_name, "person", index, record)
            for index, record in enumerate(people["people"])
        ],
    }
    if scene.get("entities") != expected_entities:
        raise ImportSafetyError("Selected scene provisional identities differ from canonical source records")
    return {
        "manifest": manifest,
        "scene": scene,
        "source_root": source_root,
        "scene_root": scene_root,
        "meta": meta,
        "buildings": buildings,
        "people": people,
        "proxies": proxies,
        "files_verified": len(entries),
        "counts": actual_counts,
    }


def run(
    scene: str = "capital",
    *,
    dry_run: bool = True,
    manifest_path: str | Path | None = None,
    spawn_name_labels: bool = False,
) -> dict[str, Any]:
    """Verify and optionally import one scene inside Unreal Editor.

    ``dry_run=True`` is the safe default.  A real import requires an entirely
    empty digest-versioned destination.  Existing generated packages are never
    replaced; legacy packages are never inspected or touched by this function.
    """

    try:
        import unreal  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised inside Unreal
        raise RuntimeError("run() must execute inside Unreal Editor's Python environment") from exc

    project_root = Path(str(unreal.Paths.project_dir())).resolve()
    manifest_file = Path(manifest_path).resolve() if manifest_path is not None else None
    plan = preflight(project_root, scene, manifest_file)
    scene_plan = plan["scene"]
    version_root = plan["manifest"]["version_content_root"]
    assert_safe_game_path(version_root)
    scene_destination = scene_plan["unreal"]["content_root"]
    existing = _list_assets(unreal, scene_destination)
    if existing:
        raise ImportSafetyError(
            f"Generated scene destination is not empty ({len(existing)} assets): {scene_destination}. "
            "This loader refuses in-place overwrite."
        )
    level_path = scene_plan["unreal"]["level"]
    if unreal.EditorAssetLibrary.does_asset_exist(level_path):
        raise ImportSafetyError(f"Generated level already exists: {level_path}")

    summary = {
        "status": "verified" if dry_run else "importing",
        "dry_run": dry_run,
        "scene": scene,
        "files_verified": plan["files_verified"],
        "source_digest": plan["manifest"]["source"]["digest"],
        "destination": scene_destination,
        "version_root": version_root,
        "level": level_path,
        "counts": dict(plan["counts"]),
        "identity_status": "provisional",
        "identity_scheme": IDENTITY_SCHEME,
        "roads_imported": 0,
    }
    _log(unreal, "Preflight verified %d files for '%s'" % (plan["files_verified"], scene))
    if dry_run:
        _log(unreal, "Dry run complete; no Unreal assets or actors were created")
        return summary

    importer = _UnrealSceneImporter(unreal, plan, spawn_name_labels=spawn_name_labels)
    result = importer.execute()
    summary.update(result)
    summary["status"] = "imported"
    return summary


class _UnrealSceneImporter:
    """Editor-only implementation isolated behind a preflight gate."""

    def __init__(self, unreal_module: Any, plan: Mapping[str, Any], *, spawn_name_labels: bool) -> None:
        self.u = unreal_module
        self.plan = plan
        self.scene = plan["scene"]["name"]
        self.scene_root: Path = plan["scene_root"]
        self.meta: Mapping[str, Any] = plan["meta"]
        self.buildings_doc: Mapping[str, Any] = plan["buildings"]
        self.people_doc: Mapping[str, Any] = plan["people"]
        self.proxy_index: Mapping[str, Any] = plan["proxies"]
        self.paths: Mapping[str, str] = plan["scene"]["unreal"]
        self.version_root: str = plan["manifest"]["version_content_root"]
        self.version: str = plan["manifest"]["version"]
        self.spawn_name_labels = spawn_name_labels
        self.asset_subsystem = self._subsystem("EditorAssetSubsystem")
        self.actor_subsystem = self._subsystem("EditorActorSubsystem")
        self.level_subsystem = self._subsystem("LevelEditorSubsystem")

    def _subsystem(self, class_name: str) -> Any:
        cls = getattr(self.u, class_name, None)
        if cls is None:
            return None
        try:
            return self.u.get_editor_subsystem(cls)
        except Exception:
            return None

    def execute(self) -> dict[str, Any]:
        assert_safe_game_path(self.version_root)
        _log(self.u, f"Import destination: {self.version_root}")

        mesh_root = self.paths["mesh_root"]
        terrain = self._import_static_mesh(self.scene_root / "terrain.obj", mesh_root + "/Terrain")
        terrain_far = self._import_static_mesh(self.scene_root / "terrain_far.obj", mesh_root + "/TerrainFar")
        water = None
        if self.meta["terrain"].get("water_z_cm") is not None:
            water = self._import_static_mesh(self.scene_root / "water.obj", mesh_root + "/Water")

        proxies: dict[str, Any] = {}
        for kind in sorted(self.proxy_index):
            proxies[kind] = self._import_static_mesh(
                self.scene_root / "proxy_meshes" / f"{kind}.obj",
                mesh_root + "/Proxies/" + kind,
            )

        self._new_level(self.paths["level"])
        fix_roll, fix_scale = self._calibrate(terrain)
        terrain_actor = self._spawn_object(terrain, (0.0, 0.0, 0.0), self._rotation(0.0, fix_roll))
        self._label_actor(terrain_actor, "TL_Terrain", "Environment", ("TerraLife", "Terrain"))
        if not math.isclose(fix_scale, 1.0):
            terrain_actor.set_actor_scale3d(self.u.Vector(fix_scale, fix_scale, fix_scale))

        far_actor = self._spawn_object(terrain_far, (0.0, 0.0, 0.0), self._rotation(0.0, fix_roll))
        self._label_actor(far_actor, "TL_TerrainFar", "Environment", ("TerraLife", "TerrainFar"))
        if not math.isclose(fix_scale, 1.0):
            far_actor.set_actor_scale3d(self.u.Vector(fix_scale, fix_scale, fix_scale))

        if water is not None:
            water_actor = self._spawn_object(water, (0.0, 0.0, 0.0), self._rotation(0.0, fix_roll))
            self._label_actor(water_actor, "TL_Water", "Environment", ("TerraLife", "Water"))
            if not math.isclose(fix_scale, 1.0):
                water_actor.set_actor_scale3d(self.u.Vector(fix_scale, fix_scale, fix_scale))

        spawned_buildings = self._spawn_buildings(proxies, fix_roll, fix_scale)
        spawned_people = self._spawn_people(proxies.get("person"), fix_roll, fix_scale)
        self._spawn_lighting()
        self._spawn_player_start()
        self._save()
        _log(
            self.u,
            "Imported '%s': %d buildings, %d people; %d roads retained in scene bible"
            % (self.scene, spawned_buildings, spawned_people, len(self.buildings_doc["roads"])),
        )
        return {
            "assets_created": len(_list_assets(self.u, self.paths["content_root"])),
            "buildings_spawned": spawned_buildings,
            "people_spawned": spawned_people,
            "roads_available_in_scene_bible": len(self.buildings_doc["roads"]),
            "roads_imported": 0,
            "name_labels_spawned": min(spawned_people, 60) if self.spawn_name_labels else 0,
        }

    def _import_static_mesh(self, source: Path, destination: str) -> Any:
        assert_safe_game_path(destination)
        task = self.u.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", False)
        self.u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        imported: list[str] = []
        try:
            imported = [str(path) for path in task.get_editor_property("imported_object_paths")]
        except Exception:
            imported = []
        candidates = imported or _list_assets(self.u, destination)
        for object_path in candidates:
            asset = self._load_asset(object_path.split(".", 1)[0])
            if asset is not None and isinstance(asset, self.u.StaticMesh):
                return asset
        raise RuntimeError(f"Interchange did not create a StaticMesh from {source.name} in {destination}")

    def _load_asset(self, path: str) -> Any:
        if self.asset_subsystem is not None:
            try:
                return self.asset_subsystem.load_asset(path)
            except Exception:
                pass
        return self.u.EditorAssetLibrary.load_asset(path)

    def _new_level(self, level_path: str) -> None:
        assert_safe_game_path(level_path)
        if self.u.EditorAssetLibrary.does_asset_exist(level_path):
            raise ImportSafetyError(f"Generated level already exists: {level_path}")
        made = False
        if self.level_subsystem is not None:
            try:
                made = bool(self.level_subsystem.new_level(level_path))
            except Exception:
                made = False
        if not made:
            try:
                made = bool(self.u.EditorLevelLibrary.new_level(level_path))
            except Exception:
                made = False
        if not made:
            raise RuntimeError(f"Unreal could not create level {level_path}")

    def _calibrate(self, terrain: Any) -> tuple[float, float]:
        expected_xy = float(self.meta["terrain"]["size_cm"])
        expected_z = max(1.0, float(self.meta["terrain"]["z_max_cm"]) - float(self.meta["terrain"]["z_min_cm"]))
        bounds = terrain.get_bounding_box()
        extents = (
            float(bounds.max.x - bounds.min.x),
            float(bounds.max.y - bounds.min.y),
            float(bounds.max.z - bounds.min.z),
        )
        largest = max(extents)
        scale = expected_xy / largest if largest > 1.0 and abs(largest - expected_xy) / expected_xy > 0.05 else 1.0
        swapped = extents[2] > expected_z * 3.0 and min(extents[0], extents[1]) < expected_xy * 0.5
        if not swapped:
            return 0.0, scale
        # Interchange may interpret OBJ as Y-up.  Test both compensating rolls
        # in the fresh generated level and immediately destroy the probe.
        for roll in (90.0, -90.0):
            probe = self._spawn_object(terrain, (0.0, 0.0, 0.0), self._rotation(0.0, roll))
            try:
                probe.set_actor_scale3d(self.u.Vector(scale, scale, scale))
                _origin, extent = probe.get_actor_bounds(False)
                dimensions = (float(extent.x) * 2.0, float(extent.y) * 2.0, float(extent.z) * 2.0)
                aligned = (
                    dimensions[0] > expected_xy * 0.5
                    and dimensions[1] > expected_xy * 0.5
                    and dimensions[2] < expected_z * 3.0
                )
            finally:
                self._destroy_actor(probe)
            if aligned:
                _log(self.u, f"Interchange axis compensation selected roll {roll:.0f} degrees")
                return roll, scale
        raise RuntimeError("Imported terrain axes are inconsistent with scene metadata")

    def _rotation(self, yaw: float, fix_roll: float) -> Any:
        return self.u.Rotator(float(fix_roll), 0.0, float(yaw))

    def _spawn_object(self, obj: Any, location: Iterable[float], rotation: Any) -> Any:
        loc = self.u.Vector(*[float(value) for value in location])
        actor = None
        if self.actor_subsystem is not None:
            actor = self.actor_subsystem.spawn_actor_from_object(obj, loc, rotation)
        else:
            actor = self.u.EditorLevelLibrary.spawn_actor_from_object(obj, loc, rotation)
        if actor is None:
            raise RuntimeError("Unreal failed to spawn an actor from imported object")
        return actor

    def _spawn_class(self, cls: Any, location: Iterable[float], rotation: Any | None = None) -> Any:
        loc = self.u.Vector(*[float(value) for value in location])
        rot = rotation or self.u.Rotator(0.0, 0.0, 0.0)
        if self.actor_subsystem is not None:
            return self.actor_subsystem.spawn_actor_from_class(cls, loc, rot)
        return self.u.EditorLevelLibrary.spawn_actor_from_class(cls, loc, rot)

    def _destroy_actor(self, actor: Any) -> None:
        if self.actor_subsystem is not None:
            self.actor_subsystem.destroy_actor(actor)
        else:
            self.u.EditorLevelLibrary.destroy_actor(actor)

    def _label_actor(self, actor: Any, label: str, folder: str, tags: Iterable[str]) -> None:
        actor.set_actor_label(label)
        try:
            actor.set_folder_path(f"TerraLife/{self.version}/{self.scene}/{folder}")
        except Exception:
            pass
        try:
            actor.set_editor_property("tags", [self.u.Name(tag) for tag in tags])
        except Exception:
            pass

    def _spawn_buildings(self, proxies: Mapping[str, Any], fix_roll: float, fix_scale: float) -> int:
        count = 0
        for index, building in enumerate(self.buildings_doc["buildings"]):
            kind = building["type"]
            identity = self.plan["scene"]["entities"]["buildings"][index]
            mesh = proxies.get(kind)
            if mesh is None:
                raise RuntimeError(f"No imported proxy mesh for building type '{kind}'")
            actor = self._spawn_object(mesh, building["pos_cm"], self._rotation(building["yaw_deg"], fix_roll))
            native = self.proxy_index[kind].get("native_size_cm") or 100.0
            sx, sy, sz = (float(value) / float(native) for value in building["size_cm"])
            if abs(fix_roll) > 45.0:
                sy, sz = sz, sy
            actor.set_actor_scale3d(self.u.Vector(sx * fix_scale, sy * fix_scale, sz * fix_scale))
            self._label_actor(
                actor,
                f"TL_B_{kind}_{index:04d}",
                "Buildings",
                (
                    "TerraLife",
                    "Building",
                    "EntityId",
                    f"EntityId={identity['entity_id']}",
                    "ProvisionalIdentity",
                    f"BuildingIndex_{index:04d}",
                    f"Type_{kind}",
                ),
            )
            count += 1
        return count

    def _spawn_people(self, person_mesh: Any, fix_roll: float, fix_scale: float) -> int:
        if person_mesh is None:
            raise RuntimeError("Proxy index did not produce a person StaticMesh")
        count = 0
        for index, person in enumerate(self.people_doc["people"]):
            identity = self.plan["scene"]["entities"]["people"][index]
            actor = self._spawn_object(person_mesh, person["spawn_cm"], self._rotation(person["yaw_deg"], fix_roll))
            if not math.isclose(fix_scale, 1.0):
                actor.set_actor_scale3d(self.u.Vector(fix_scale, fix_scale, fix_scale))
            self._label_actor(
                actor,
                f"TL_NPC_{index:03d}_{person['name']}",
                "People",
                (
                    "TerraLife",
                    "Person",
                    "EntityId",
                    f"EntityId={identity['entity_id']}",
                    "ProvisionalIdentity",
                    f"PersonIndex_{index:03d}",
                    f"Role_{person['role']}",
                ),
            )
            if self.spawn_name_labels and index < 60:
                label = self._spawn_class(
                    self.u.TextRenderActor,
                    (person["spawn_cm"][0], person["spawn_cm"][1], person["spawn_cm"][2] + 205.0),
                    self.u.Rotator(0.0, 0.0, 180.0),
                )
                if label is not None:
                    self._label_actor(label, f"TL_Name_{index:03d}", "People/Labels", ("TerraLife", "PersonLabel"))
                    try:
                        component = label.get_component_by_class(self.u.TextRenderComponent)
                        component.set_text(f"{person['name']} · {person['role_ru']}")
                        component.set_world_size(26.0)
                    except Exception:
                        pass
            count += 1
        return count

    def _spawn_lighting(self) -> None:
        latitude = float(self.meta.get("latitude_deg", 30.0))
        elevation = float(self.meta.get("sun", {}).get("elevation_deg", 55.0))
        yaw = -55.0 if latitude >= 0 else 125.0
        actors = (
            (self.u.DirectionalLight, (0, 0, 20000), self.u.Rotator(0.0, -elevation, yaw), "TL_Sun"),
            (self.u.SkyAtmosphere, (0, 0, 0), None, "TL_SkyAtmosphere"),
            (self.u.SkyLight, (0, 0, 12000), None, "TL_SkyLight"),
            (self.u.ExponentialHeightFog, (0, 0, self.meta["terrain"]["z_min_cm"]), None, "TL_Fog"),
            (self.u.PostProcessVolume, (0, 0, 0), None, "TL_PostProcess"),
        )
        for cls, location, rotation, label in actors:
            actor = self._spawn_class(cls, location, rotation)
            if actor is not None:
                self._label_actor(actor, label, "Lighting", ("TerraLife", "Lighting"))
                if label == "TL_PostProcess":
                    try:
                        actor.set_editor_property("unbound", True)
                    except Exception:
                        pass
                elif label == "TL_Sun":
                    try:
                        component = actor.get_component_by_class(self.u.DirectionalLightComponent)
                        component.set_editor_property("intensity", 9.0)
                        component.set_editor_property("atmosphere_sun_light", True)
                    except Exception:
                        pass
                elif label == "TL_SkyLight":
                    try:
                        component = actor.get_component_by_class(self.u.SkyLightComponent)
                        component.set_editor_property("real_time_capture", True)
                    except Exception:
                        pass

    def _spawn_player_start(self) -> None:
        location = list(self.meta["player_start_cm"])
        location[2] += 60.0
        actor = self._spawn_class(self.u.PlayerStart, location)
        if actor is None:
            raise RuntimeError("Unreal failed to create PlayerStart")
        self._label_actor(actor, "TL_PlayerStart", "Gameplay", ("TerraLife", "PlayerStart"))

    def _save(self) -> None:
        assert_safe_game_path(self.version_root)
        scene_content_root = self.paths["content_root"]
        assert_safe_game_path(scene_content_root)
        if not self.u.EditorAssetLibrary.save_directory(scene_content_root, recursive=True):
            raise RuntimeError(f"Failed to save generated assets under {scene_content_root}")
        saved = False
        if self.level_subsystem is not None:
            try:
                saved = bool(self.level_subsystem.save_current_level())
            except Exception:
                saved = False
        if not saved:
            saved = bool(self.u.EditorLevelLibrary.save_current_level())
        if not saved:
            raise RuntimeError("Failed to save generated level")


def _find_scene(manifest: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise ImportSafetyError(f"Unsafe scene name: {name!r}")
    for scene in manifest["scenes"]:
        if scene.get("name") == name:
            return scene
    raise ImportSafetyError(f"Scene '{name}' is absent from manifest")


def _allowed_scene_files(scene: str, proxy_types: set[str]) -> set[str]:
    base = {
        "meta.json",
        "buildings.json",
        "people.json",
        "terrain.obj",
        "terrain.mtl",
        "terrain_far.obj",
        "terrain_far.mtl",
        "terrain_color.png",
        "water.obj",
        "water.mtl",
        "masks/heightmap.png",
        "masks/grass.png",
        "masks/dirt.png",
        "masks/rock.png",
        "masks/sand.png",
        "proxy_meshes/proxy_index.json",
    }
    for kind in proxy_types:
        base.add(f"proxy_meshes/{kind}.obj")
        base.add(f"proxy_meshes/{kind}.mtl")
    return {f"{scene}/{relative}" for relative in base}


def _all_entries(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for scene in manifest["scenes"]:
        files = scene.get("files")
        if not isinstance(files, list):
            raise ImportSafetyError(f"Scene {scene.get('name')} has no file table")
        entries.extend(files)
    return sorted(entries, key=lambda item: str(item.get("path")))


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImportSafetyError(f"Cannot parse verified JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ImportSafetyError(f"Verified JSON root is not an object: {path.name}")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _provisional_entity_identity(
    run_id: str,
    scene: str,
    entity_kind: str,
    source_index: int,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    record_json = _canonical_json(record)
    seed = _canonical_json(
        {
            "entity_kind": entity_kind,
            "record": record,
            "run_id": run_id,
            "scene": scene,
            "source_index": source_index,
        }
    )
    return {
        "entity_id": str(uuid.uuid5(IDENTITY_NAMESPACE_UUID, seed)),
        "kind": entity_kind,
        "source_index": source_index,
        "record_sha256": hashlib.sha256(record_json.encode("utf-8")).hexdigest(),
        "status": "provisional",
    }


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


def _list_assets(unreal_module: Any, root: str) -> list[str]:
    assert_safe_game_path(root)
    try:
        subsystem = unreal_module.get_editor_subsystem(unreal_module.EditorAssetSubsystem)
        return sorted(str(path) for path in subsystem.list_assets(root, recursive=True))
    except Exception:
        try:
            return sorted(str(path) for path in unreal_module.EditorAssetLibrary.list_assets(root, recursive=True))
        except Exception:
            return []


def _log(unreal_module: Any, message: str) -> None:
    unreal_module.log("[TerraLife] " + message)


if __name__ == "__main__":
    print("TerraLife loader ready. Inside Unreal Editor, call run('capital', dry_run=True) first.")
