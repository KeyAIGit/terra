"""Read-only diagnostics for the saved Terra capital level.

Run with UnrealEditor-Cmd/UnrealEditor and ``-ExecutePythonScript``.  The
script deliberately does not save packages or modify actors.
"""

from __future__ import annotations

import json

import unreal


LEVEL = "/Game/Terra/Maps/L_capital"


def vector(value: unreal.Vector) -> list[float]:
    return [round(value.x, 3), round(value.y, 3), round(value.z, 3)]


def rotator(value: unreal.Rotator) -> list[float]:
    return [round(value.pitch, 3), round(value.yaw, 3), round(value.roll, 3)]


def main() -> None:
    world = unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
    if not world:
        raise RuntimeError(f"Could not load {LEVEL}")

    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    report: dict[str, object] = {
        "level": LEVEL,
        "actor_count": len(actors),
        "player_starts": [],
        "terrain_candidates": [],
    }

    for actor in actors:
        label = actor.get_actor_label()
        record = {
            "label": label,
            "class": actor.get_class().get_name(),
            "location": vector(actor.get_actor_location()),
            "rotation": rotator(actor.get_actor_rotation()),
        }

        if isinstance(actor, unreal.PlayerStart):
            origin, extent = actor.get_actor_bounds(False, True)
            record["bounds_origin"] = vector(origin)
            record["bounds_extent"] = vector(extent)
            report["player_starts"].append(record)

        if "terrain" in label.lower() or "landscape" in label.lower():
            origin, extent = actor.get_actor_bounds(False, True)
            record["bounds_origin"] = vector(origin)
            record["bounds_extent"] = vector(extent)
            report["terrain_candidates"].append(record)

    unreal.log("TERRA_LEVEL_DIAGNOSTIC=" + json.dumps(report, sort_keys=True))


main()
