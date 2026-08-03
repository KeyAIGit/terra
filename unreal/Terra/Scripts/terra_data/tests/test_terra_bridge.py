from __future__ import annotations

import binascii
import json
import struct
import sys
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import terra_bridge  # noqa: E402
import unreal_import_terra_life as unreal_loader  # noqa: E402


def _png(width: int, height: int, bit_depth: int, color_type: int) -> bytes:
    channels = {0: 1, 2: 3}[color_type]
    bytes_per_sample = 2 if bit_depth == 16 else 1
    row = b"\x00" + b"\x00" * (width * channels * bytes_per_sample)
    raw = row * height

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    return terra_bridge.PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _obj(mtl_name: str) -> str:
    return (
        f"mtllib {mtl_name}\n"
        "v 0 0 0\n"
        "v 100 0 0\n"
        "v 0 100 10\n"
        "vt 0 0\n"
        "vt 1 0\n"
        "vt 0 1\n"
        "usemtl walls\n"
        "f 1/1 2/2 3/3\n"
    )


def _make_scene(root: Path, name: str, *, count_override: int | None = None) -> None:
    scene = root / name
    scene.mkdir(parents=True)
    counts = {"buildings": 1 if count_override is None else count_override, "roads": 1, "people": 1}
    meta = {
        "run_id": "terra-life",
        "scene": name,
        "title": name.title(),
        "settlement": "Test",
        "polity": "Test polity",
        "era": "test era",
        "year": 1,
        "year_ru": "1 г.",
        "gods": ["One"],
        "population": 10,
        "biome": "plain",
        "latitude_deg": 10.0,
        "seed": 7,
        "desc": "Fixture scene",
        "coords": {"axes": "X/Y/Z", "units": "см", "yaw": "Z"},
        "terrain": {
            "size_cm": 100.0,
            "grid": 3,
            "step_cm": 50.0,
            "z_min_cm": 0.0,
            "z_max_cm": 10.0,
            "water_z_cm": None,
            "far_size_cm": 200.0,
        },
        "heightmap": {
            "px": 3,
            "min_cm": 0.0,
            "max_cm": 10.0,
            "landscape_scale_xy": 1.0,
            "landscape_scale_z": 1.0,
            "landscape_z_location_cm": 5.0,
        },
        "sun": {"elevation_deg": 45.0},
        "player_start_cm": [0.0, 0.0, 1.0],
        "counts": counts,
        "built_at": "2026-08-02T00:00:00+00:00",
        "exporter": "terra.export_ue",
    }
    buildings = {
        "coords": "cm",
        "scale_rule": "size/native",
        "buildings": [
            {"type": "hut_round", "src": "hut", "pos_cm": [0.0, 0.0, 1.0], "yaw_deg": 0.0, "size_cm": [10.0, 10.0, 10.0]}
        ],
        "roads": [{"width_cm": 2.0, "points_cm": [[0.0, 0.0, 1.0], [10.0, 0.0, 1.0]]}],
    }
    people = {
        "coords": "cm",
        "people": [
            {
                "name": "Tester",
                "sex": 0,
                "age": 30,
                "role": "worker",
                "role_ru": "работник",
                "real": 0,
                "born": None,
                "cloth_hex": "#112233",
                "skin_hex": "#aabbcc",
                "spawn_cm": [0.0, 0.0, 1.0],
                "yaw_deg": 0.0,
                "route_cm": [[0.0, 0.0, 1.0], [5.0, 0.0, 1.0]],
                "card": {"deeds": [], "traits": [], "beliefs": [], "prestige": 0.0, "real_person": False},
            }
        ],
    }
    proxy_index = {
        "hut_round": {
            "native_size_cm": 100.0,
            "bbox_cm": [[0.0, 0.0, 0.0], [100.0, 100.0, 100.0]],
            "slots": ["walls"],
            "colors": {"walls": "#112233"},
        },
        "person": {
            "native_size_cm": None,
            "bbox_cm": [[-10.0, -10.0, 0.0], [10.0, 10.0, 165.0]],
            "slots": ["walls"],
            "colors": {"walls": "#445566"},
        },
    }
    _write(scene / "meta.json", json.dumps(meta))
    _write(scene / "buildings.json", json.dumps(buildings))
    _write(scene / "people.json", json.dumps(people))
    _write(scene / "proxy_meshes" / "proxy_index.json", json.dumps(proxy_index))
    _write(scene / "terrain.obj", _obj("terrain.mtl"))
    _write(scene / "terrain.mtl", "newmtl walls\nKd 1 1 1\nmap_Kd terrain_color.png\n")
    _write(scene / "terrain_far.obj", _obj("terrain_far.mtl"))
    _write(scene / "terrain_far.mtl", "newmtl walls\nKd 1 1 1\n")
    _write(scene / "terrain_color.png", _png(4, 4, 8, 2))
    _write(scene / "masks" / "heightmap.png", _png(3, 3, 16, 0))
    for mask in ("grass", "dirt", "rock", "sand"):
        _write(scene / "masks" / f"{mask}.png", _png(4, 4, 8, 0))
    for kind in proxy_index:
        _write(scene / "proxy_meshes" / f"{kind}.obj", _obj(f"{kind}.mtl"))
        _write(scene / "proxy_meshes" / f"{kind}.mtl", "newmtl walls\nKd 1 1 1\n")


def _make_export(project: Path) -> Path:
    export = project / "export_ue"
    export.mkdir(parents=True)
    for name in terra_bridge.CANONICAL_SCENES:
        _make_scene(export, name)
    return export


class ValidatorTests(unittest.TestCase):
    def test_valid_export_and_manifest_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            export = _make_export(project)
            result = terra_bridge.validate_export(export)
            self.assertTrue(result.valid, result.diagnostics)
            self.assertEqual([], result.diagnostics)
            first = terra_bridge.build_manifest(result, project)
            second = terra_bridge.build_manifest(terra_bridge.validate_export(export), project)
            self.assertEqual(first, second)
            self.assertEqual("/Game/TerraLife", first["content_namespace"])
            self.assertRegex(first["version_content_root"], r"^/Game/TerraLife/v_[0-9a-f]{12}$")
            self.assertEqual("provisional", first["identity"]["status"])
            identities = [
                entity["entity_id"]
                for scene in first["scenes"]
                for collection in ("buildings", "people")
                for entity in scene["entities"][collection]
            ]
            self.assertEqual(6, len(identities))
            self.assertEqual(len(identities), len(set(identities)))
            self.assertTrue(all(uuid.UUID(value).version == 5 for value in identities))

    def test_provisional_identity_is_deterministic_and_index_unique(self) -> None:
        record_a = {"name": "Áda", "position": [1.0, 2.0, 3.0], "traits": {"b": 2, "a": 1}}
        record_reordered = {"traits": {"a": 1, "b": 2}, "position": [1.0, 2.0, 3.0], "name": "Áda"}
        first = terra_bridge.provisional_entity_identity("terra-life", "capital", "person", 0, record_a)
        repeated = terra_bridge.provisional_entity_identity("terra-life", "capital", "person", 0, record_reordered)
        next_index = terra_bridge.provisional_entity_identity("terra-life", "capital", "person", 1, record_a)
        other_kind = terra_bridge.provisional_entity_identity("terra-life", "capital", "building", 0, record_a)
        changed_record = terra_bridge.provisional_entity_identity(
            "terra-life", "capital", "person", 0, {**record_a, "name": "Bea"}
        )
        self.assertEqual(first, repeated)
        self.assertEqual(5, uuid.UUID(first["entity_id"]).version)
        self.assertEqual("provisional", first["status"])
        self.assertEqual(
            4,
            len({first["entity_id"], next_index["entity_id"], other_kind["entity_id"], changed_record["entity_id"]}),
        )

    def test_declared_count_mismatch_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            export = _make_export(project)
            meta_path = export / "capital" / "meta.json"
            meta = json.loads(meta_path.read_text())
            meta["counts"]["buildings"] = 9
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            result = terra_bridge.validate_export(export)
            self.assertFalse(result.valid)
            self.assertIn("declared_count_mismatch", {item.code for item in result.errors})

    def test_obj_without_uv_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            export = _make_export(project)
            path = export / "capital" / "proxy_meshes" / "person.obj"
            path.write_text("mtllib person.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
            result = terra_bridge.validate_export(export)
            self.assertFalse(result.valid)
            self.assertIn("obj_uv_missing", {item.code for item in result.errors})


class LegacyComparisonTests(unittest.TestCase):
    def test_recovers_actor_label_counts_without_parsing_uasset_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Content" / "Terra"
            map_path = root / "Maps" / "L_capital.umap"
            payload = (
                b"/Game/Terra/Maps/L_capital\x00B_house_0\x00B_temple_1\x00"
                + "NPC_A\x00NPC_B\x00".encode("utf-16le")
            )
            _write(map_path, payload)
            _write(root / "capital" / "Meshes" / "Proxies" / "house.uasset", b"asset")
            legacy = terra_bridge.scan_legacy_content(root)
            self.assertEqual("found", legacy["status"])
            self.assertEqual(2, legacy["maps"][0]["building_labels"])
            self.assertEqual(2, legacy["maps"][0]["npc_label_occurrences"])
            self.assertEqual(["house", "temple"], legacy["maps"][0]["building_types"])


class LoaderSafetyTests(unittest.TestCase):
    def test_namespace_guard_rejects_legacy_and_lookalikes(self) -> None:
        self.assertEqual("/Game/TerraLife", unreal_loader.assert_safe_game_path("/Game/TerraLife"))
        self.assertEqual("/Game/TerraLife/v_123456789abc", unreal_loader.assert_safe_game_path("/Game/TerraLife/v_123456789abc"))
        for unsafe in ("/Game/Terra", "/Game/Terra/Maps", "/Game/TerraLifeHack", "/Game/TerraLife/../Terra"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(unreal_loader.ImportSafetyError):
                    unreal_loader.assert_safe_game_path(unsafe)

    def test_preflight_verifies_all_hashes_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            export = _make_export(project)
            result = terra_bridge.validate_export(export)
            manifest = terra_bridge.build_manifest(result, project)
            manifest_path = project / "Scripts" / "terra_data" / "generated" / "import_manifest.json"
            terra_bridge.write_json(manifest_path, manifest)
            plan = unreal_loader.preflight(project, "capital", manifest_path)
            self.assertEqual(len(result.files), plan["files_verified"])
            self.assertEqual(1, plan["counts"]["buildings"])
            (export / "capital" / "people.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(unreal_loader.ImportSafetyError, "size mismatch|SHA-256 mismatch"):
                unreal_loader.preflight(project, "capital", manifest_path)

    def test_preflight_recomputes_provisional_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            export = _make_export(project)
            manifest = terra_bridge.build_manifest(terra_bridge.validate_export(export), project)
            capital = next(scene for scene in manifest["scenes"] if scene["name"] == "capital")
            capital["entities"]["people"][0]["entity_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, "tampered"))
            manifest_path = project / "Scripts" / "terra_data" / "generated" / "import_manifest.json"
            terra_bridge.write_json(manifest_path, manifest)
            with self.assertRaisesRegex(unreal_loader.ImportSafetyError, "identities differ"):
                unreal_loader.preflight(project, "capital", manifest_path)


if __name__ == "__main__":
    unittest.main()
