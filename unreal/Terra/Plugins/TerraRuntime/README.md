# Terra Runtime

`TerraRuntime` is the asset-independent C++ foundation for Terra's first playable slice.

## Included

- versioned, Blueprint-visible NPC and scene records with explicit evidence authority;
- `UTerraNPCDataAsset` and `UTerraSceneDataAsset` authoring containers;
- `ITerraInteractable` for Blueprint or C++ actors;
- `UTerraInteractionComponent` with focus prompts and server-authoritative interaction;
- `ATerraFirstPersonCharacter` with keyboard, mouse, and gamepad controls;
- `ATerraGameModeBase`, which selects the first-person character as the default pawn;
- an always-visible `BLOCKOUT` disclosure HUD for honest prototype captures;
- `ATerraPreviewGameMode`, an asset-free ground/camera/collision test pad;
- `ATerraRealitySliceGameMode`, a separate data-driven 200 x 200 m ground-level
  ward with streets, alleys, building masses, façades, courtyards, market stalls,
  well, walls, and a physically open gate.

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

Initial possession resets pitch and roll, retains PlayerStart yaw, and briefly suppresses mouse
input while a standalone window captures the pointer. Spawn diagnostics log the pawn, camera,
capsule bottom, and both simple and complex floor hits. A large simple/complex height mismatch
means the imported terrain needs complex-as-simple or a dedicated walkable collision mesh.

## Honest runtime preview

Launch the engine's empty Entry map with the opt-in preview GameMode:

```text
UnrealEditor Terra.uproject "/Engine/Maps/Entry?game=/Script/TerraRuntime.TerraPreviewGameMode" -game -windowed -ResX=1280 -ResY=720
```

This creates a flat collision pad, two scale markers, simple sky lighting, a safe PlayerStart,
and a visible `TERRA — reality slice prototype / STATUS: BLOCKOUT` overlay. It validates engine
plumbing only; it does not present the legacy random proxy city as finished simulation content.

## Ground-level spatial prototype

Launch the audited procedural ward independently of `/Game/Terra` and `L_capital`:

```text
UnrealEditor Terra.uproject "/Engine/Maps/Entry?game=/Script/TerraRuntime.TerraRealitySliceGameMode" -game -windowed -ResX=1280 -ResY=720 -NoSplash -log
```

For Pixel Streaming, append:

```text
-AudioMixer -PixelStreamingConnectionURL=ws://127.0.0.1:8888 -RenderOffScreen -ForceRes
```

The default source is
`Scripts/terra_data/generated/reality_slice_capital_runtime_v1.json`. An explicit
adapter or compatible rich-layout file can be supplied with
`-TerraRealitySliceLayout=/absolute/path/layout.json`; invalid/missing data falls
back to a deterministic embedded ward.

Runtime loading removes the audited source XY anchor and deliberately flattens
terrain samples onto a z=0 engineering datum. Ground-contact masses are snapped
to that datum while façade and roof elevations are preserved relative to their
building base. This makes collision coherent without claiming terrain fidelity.
PlayerStart is capsule-checked against rotated collision boxes and road footprints;
an unsafe source position is moved deterministically to nearby pedestrian ground.
The gate is rendered as two collision piers plus a non-colliding lintel with at
least 6 m of open passage—never as a solid box across the avenue.

The result is a **spatial prototype / blockout**, not a photoreal scene and not a
reality-equivalent simulation. Its purpose is to validate scale, route readability,
ground-level navigation, collision, and the JSON-to-Unreal runtime contract.

## Tests

Development/editor builds expose smoke tests under `Terra.Runtime`:

- `Terra.Runtime.Data.SceneJsonRoundTrip`
- `Terra.Runtime.Gameplay.Defaults`
- `Terra.Runtime.Gameplay.GroundLevelPreview`
- `Terra.Runtime.RealitySlice.LayoutContract`
- `Terra.Runtime.RealitySlice.GroundNavigation`

They verify JSON/save-style preservation of scene/NPC state and the default GameMode,
character, camera, blockout disclosure, replicated interaction component, initial focus state,
initial view stabilization, preview spawn clearance, and a real runtime floor collision trace.
The reality-slice tests additionally verify source counts and anchoring, flat-datum
normalization, unsafe-spawn relocation, fallback validity, gate passage/pier collision,
and capsule clearance along the main avenue.
