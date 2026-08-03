# Terra Runtime

`TerraRuntime` is the asset-independent C++ foundation for Terra's first playable slice.

## Included

- versioned, Blueprint-visible NPC and scene records with explicit evidence authority;
- `UTerraNPCDataAsset` and `UTerraSceneDataAsset` authoring containers;
- `ITerraInteractable` for Blueprint or C++ actors;
- `UTerraInteractionComponent` with focus prompts and server-authoritative interaction;
- `ATerraFirstPersonCharacter` with keyboard, mouse, and gamepad controls;
- `ATerraGameModeBase`, which selects the first-person character as the default pawn.

The authority vocabulary is shared across simulation and runtime data: `Unknown`, `Known`,
`Typical`, `Reconstructed`, and `Simulated`.

## Project integration

1. Enable the **Terra Runtime** plugin in the Unreal Editor and restart the editor.
2. Set a map's GameMode Override to `TerraGameModeBase` (or derive a Blueprint from it).
3. Place a `PlayerStart` above collision-enabled terrain.
4. Implement `TerraInteractable` on an actor and override its three interface functions.
5. Bind UI to the character's interaction component event, `On Interaction Target Changed`,
   to show or hide its prompt.

The initial pawn intentionally binds physical keys without content-side Input Action assets:
WASD / left stick move, mouse / right stick look, Space / gamepad bottom jumps, Shift /
left-stick click sprints, hold C crouches, and E / gamepad left interacts.

## Tests

Development/editor builds expose smoke tests under `Terra.Runtime`:

- `Terra.Runtime.Data.SceneJsonRoundTrip`
- `Terra.Runtime.Gameplay.Defaults`

They verify JSON/save-style preservation of scene/NPC state and the default GameMode,
character, camera, replicated interaction component, and initial focus state.

Live collision tracing, client/server RPC execution, locomotion, and map spawn are intentionally
left to a PIE functional test after the plugin is enabled and a playable map is integrated.
