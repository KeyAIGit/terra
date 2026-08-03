# TERRA Unreal Engine project

This directory is the UE 5.8 client and editor-automation foundation for TERRA.
The simulation remains authoritative; Unreal consumes validated scene bundles and
turns them into a playable, streamed representation.

## Current baseline

- `TerraRuntime` provides Blueprint-visible scene/NPC contracts, a first-person
  Character, a GameMode, and a server-validated interaction interface.
- Unreal MCP and the Python Editor Script plugin are configured for local editor
  automation. The HTTP listener is explicitly restricted to `localhost`.
- The official experimental MetaHuman Generator toolset is enabled for bounded
  editor assistance. It does not replace 3D conforming, rigging, wardrobe,
  animation, or visual QA.
- The saved legacy blockout remains at `/Game/Terra/Maps/L_capital`.
- The accepted `terra-life` source package lives locally in `export_ue/`; the
  clean bridge validates it and writes only to the new `/Game/TerraLife`
  namespace. It never overwrites `/Game/Terra`.
- The first simulated-person look reference is in
  `Art/Characters/ja_scribe/`.

## First launch after pulling source changes

1. If the Unreal Editor is already open, save any dirty map or assets.
2. Close and reopen `Terra.uproject` once. UE must load/compile the new plugin
   set; do not force-quit the editor during this step.
3. Verify the local automation endpoint:

   ```bash
   python3 Scripts/unreal_mcp_client.py ping
   python3 Scripts/unreal_mcp_client.py list-tools
   ```

4. Validate the local simulation export and prepare a deterministic manifest:

   ```bash
   python3 Scripts/terra_data/terra_bridge.py validate --json
   python3 Scripts/terra_data/terra_bridge.py generate
   ```

   See `Scripts/terra_data/README.md` for the exact commands shipped with the
   bridge.

## Source-control boundaries

- Git: C++/Python source, config, docs, schemas, manifests, and small approved
  reference art.
- Git LFS with locking or Perforce: `.uasset`, `.umap`, and other Unreal binary
  packages.
- Hugging Face: immutable/versioned Atlas snapshots and the public data/demo
  surface, not transactional game state and not secrets.
- Runtime state: local save/event log initially; PostgreSQL/PostGIS only when a
  server world and spatial queries are actually required.

Never commit access tokens, API keys, handoff files containing credentials, raw
user voice/video, or licensed assets without distribution rights.

## Product documents

The product contract, architecture, and staged delivery gates live in the
repository's `docs/` directory:

- `TERRA_PRODUCT_SPEC_RU.md`
- `TERRA_ARCHITECTURE.md`
- `TERRA_ROADMAP.md`
