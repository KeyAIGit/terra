from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import unittest
import uuid
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import reality_slice  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def refresh_layout_digest(layout: dict) -> None:
    digest_source = dict(layout)
    digest_source.pop("layout_digest", None)
    layout["layout_digest"] = "sha256:" + hashlib.sha256(
        reality_slice.canonical_json(digest_source).encode("utf-8")
    ).hexdigest()


class GeometryTests(unittest.TestCase):
    def test_party_wall_touch_is_not_area_overlap(self) -> None:
        first = reality_slice.rect_polygon((0.0, 0.0), (100.0, 100.0), 0.0)
        touching = reality_slice.rect_polygon((0.0, 100.0), (100.0, 100.0), 0.0)
        penetrating = reality_slice.rect_polygon((0.0, 99.0), (100.0, 100.0), 0.0)
        self.assertFalse(reality_slice.polygons_overlap(first, touching))
        self.assertTrue(reality_slice.polygons_overlap(first, penetrating))
        intersection = reality_slice.convex_intersection(first, penetrating)
        self.assertAlmostEqual(100.0, reality_slice.polygon_area(intersection))

    def test_bilinear_sampler(self) -> None:
        sampler = reality_slice.TerrainSampler(
            [0.0, 10.0],
            [0.0, 10.0],
            {(0.0, 0.0): 0.0, (10.0, 0.0): 10.0, (0.0, 10.0): 20.0, (10.0, 10.0): 30.0},
        )
        self.assertAlmostEqual(15.0, sampler.sample(5.0, 5.0))
        with self.assertRaises(ValueError):
            sampler.sample(11.0, 5.0)


class CapitalPhysicalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = reality_slice.audit_capital(PROJECT_ROOT)

    def test_population_scale_and_physical_defects_are_quantified(self) -> None:
        audit = self.audit
        self.assertEqual(8_367_729, audit["source"]["source_declared_population"])
        self.assertEqual(2_300_000, audit["source"]["comparison_population"])
        self.assertEqual(300, audit["geometry"]["building_count"])
        self.assertEqual(255, audit["geometry"]["house_count"])
        self.assertEqual(20, audit["overlaps"]["pair_count"])
        self.assertEqual(2, audit["overlaps"]["unintended_pair_count"])
        self.assertEqual(63, audit["roads_and_frontage"]["building_road_collision_count"])
        self.assertEqual(24, audit["roads_and_frontage"]["house_frontage"]["near_parallel_and_facing_count"])
        self.assertEqual("not_explicit_in_source", audit["access"]["public_square_status"])
        self.assertEqual(2, audit["access"]["gate_count"])
        self.assertEqual(4, audit["access"]["market_stall_count"])

    def test_density_is_physically_impossible_as_instantiated_geometry(self) -> None:
        density = self.audit["density"]
        self.assertGreater(density["source_population"]["people_per_proxy"], 27_000)
        self.assertGreater(density["comparison_2_3m"]["people_per_proxy"], 7_000)
        self.assertGreater(density["source_population"]["people_per_estimated_house_gfa_m2"], 180)


class RealitySliceGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_paths = [
            PROJECT_ROOT / "export_ue" / "capital" / "meta.json",
            PROJECT_ROOT / "export_ue" / "capital" / "buildings.json",
            PROJECT_ROOT / "export_ue" / "capital" / "terrain.obj",
        ]
        cls.before_hashes = [reality_slice.sha256_file(path) for path in cls.source_paths]
        cls.layout = reality_slice.generate_reality_slice(PROJECT_ROOT)
        cls.after_hashes = [reality_slice.sha256_file(path) for path in cls.source_paths]

    def test_generator_is_deterministic_and_source_is_immutable(self) -> None:
        repeated = reality_slice.generate_reality_slice(PROJECT_ROOT)
        self.assertEqual(self.layout, repeated)
        self.assertEqual(self.before_hashes, self.after_hashes)

    def test_layout_passes_full_validator(self) -> None:
        findings = reality_slice.validate_reality_slice(self.layout, PROJECT_ROOT)
        self.assertEqual([], findings)
        scope = self.layout["scope"]
        self.assertEqual("one_ward_reality_slice_not_full_city", scope["claim"])
        self.assertEqual((200.0, 200.0, 4.0), (scope["width_m"], scope["height_m"], scope["area_ha"]))
        self.assertGreaterEqual(scope["residents_capacity"], 800)
        self.assertLessEqual(scope["residents_capacity"], 1500)

    def test_required_physical_program_is_present(self) -> None:
        layout = self.layout
        self.assertEqual(1, sum(building["kind"] == "gatehouse" for building in layout["buildings"]))
        self.assertEqual(2, sum(building["kind"] == "wall_segment" for building in layout["buildings"]))
        self.assertEqual(1, sum(building["kind"] == "temple" for building in layout["buildings"]))
        self.assertEqual(1, sum(building["kind"] == "administration" for building in layout["buildings"]))
        self.assertEqual(4, sum(building["kind"] == "market_pavilion" for building in layout["buildings"]))
        self.assertGreaterEqual(len(layout["courtyards"]), 4)
        self.assertTrue(all(building["architecture"]["gabled_roof"] is False for building in layout["buildings"]))
        self.assertTrue(any(building.get("urban_form", {}).get("party_wall_left") for building in layout["buildings"]))
        square = layout["public_spaces"][0]
        self.assertGreaterEqual(square["area_m2"], 800.0)
        self.assertEqual(4, len(square["access_links"]))
        self.assertEqual(1, sum(item["kind"] == "public_well" for item in square["amenities"]))

    def test_validation_rejects_population_claim_tamper(self) -> None:
        tampered = copy.deepcopy(self.layout)
        tampered["scope"]["residents_capacity"] = 2_300_000
        refresh_layout_digest(tampered)
        codes = {finding.code for finding in reality_slice.validate_reality_slice(tampered, PROJECT_ROOT)}
        self.assertIn("population_capacity", codes)
        self.assertIn("capacity_total", codes)

    def test_policy_tamper_cannot_allow_full_city_population(self) -> None:
        tampered = copy.deepcopy(self.layout)
        tampered["scope"]["residents_capacity"] = 2_300_000
        tampered["validation_policy"]["population_capacity_range"] = [0, 3_000_000]
        refresh_layout_digest(tampered)

        codes = {finding.code for finding in reality_slice.validate_reality_slice(tampered, PROJECT_ROOT)}

        self.assertIn("validation_policy", codes)
        self.assertIn("population_capacity", codes)
        self.assertIn("capacity_total", codes)

    def test_policy_tamper_cannot_hide_full_duplicate_overlap(self) -> None:
        tampered = copy.deepcopy(self.layout)
        duplicate = copy.deepcopy(tampered["buildings"][0])
        duplicate["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "terra-adversarial-full-duplicate"))
        tampered["buildings"].append(duplicate)
        tampered["validation_policy"]["overlap_numeric_tolerance_cm2"] = 1e20
        tampered["scope"]["residents_capacity"] += duplicate["capacity"]["residents_capacity"]
        tampered["scope"]["jobs_capacity"] += duplicate["capacity"]["jobs_capacity"]
        refresh_layout_digest(tampered)

        codes = {finding.code for finding in reality_slice.validate_reality_slice(tampered, PROJECT_ROOT)}

        self.assertIn("validation_policy", codes)
        self.assertIn("building_overlap", codes)

    def test_scope_capacity_cannot_diverge_from_building_sums(self) -> None:
        tampered = copy.deepcopy(self.layout)
        for building in tampered["buildings"]:
            building["capacity"]["residents_capacity"] = 0
            building["capacity"]["jobs_capacity"] = 0
        refresh_layout_digest(tampered)

        codes = {finding.code for finding in reality_slice.validate_reality_slice(tampered, PROJECT_ROOT)}

        self.assertIn("capacity_total", codes)

    def test_runtime_adapter_uses_center_transforms(self) -> None:
        runtime = reality_slice.make_runtime_layout(self.layout)
        self.assertEqual([], reality_slice.validate_runtime_layout(runtime))
        first = self.layout["buildings"][0]
        body = next(element for element in runtime["elements"] if element["id"] == f"E_{first['id']}_body")
        expected_z = first["pos_cm"][2] + first["size_cm"][2] / 2.0
        self.assertAlmostEqual(expected_z, body["location_cm"]["z"], places=3)
        self.assertAlmostEqual(self.layout["scope"]["anchor_cm"][2] + 120.0, runtime["player_start"]["location_cm"]["z"], places=3)
        self.assertEqual({"x": 20_000.0, "y": 20_000.0}, runtime["extent_cm"])


if __name__ == "__main__":
    unittest.main()
