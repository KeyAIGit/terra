# Terra World 0.5

Play: https://keyaigit.github.io/terra/ . The product title is **Terra World**, without a language suffix. The existing Hugging Face Space keeps its URL for compatibility and embeds this application.

## The new market courtyard

Enter the courtyard from the home page, or open `#courtyard`. This is a newly authored, walkable interpretation of Níhmīwū's market district at 500 CE. It has a covered stone arcade, detailed doors and shutters, a fountain, market stalls, fabric canopies and vegetation. The scene uses six physically based surface sets, four model sets and one captured HDR lighting environment. Asset sources, processing and hashes are recorded in `courtyard/ASSETS.json`; about 36 MB of runtime assets load on the first visit.

The surface maps control base color, normals, roughness and occlusion. Paving also uses sampled displacement. Selected models are packed GLBs with Meshopt compression; the tree was reduced before publication and its supplied leaf alpha was integrated into the material. Source textures are optimized WebP files, with lower texture resolution on touch devices. Poly Haven assets are CC0; applicable rendering-library license notices are included.

This is a step toward the photorealistic visual target, not a claim that the district or entire planet has achieved photorealism. The courtyard is new scenery, not a reconstruction uniquely implied by the simulation's data. It has no new AI residents. The three earlier settlement walks and their scripted residents remain available separately.

Desktop: drag to look, WASD to walk, Shift to move faster, P to pause, H to hide or restore the interface. Viewpoint, lighting and quality controls are in the upper corner. Touch devices have a movement joystick and drag-to-look; the photo-mode control is desktop-only. The information panel links back to the capital's actual atlas record.

## Preserved world

The terra-1 history and simulator were not changed or rerun. The archive still contains 117 snapshots, 14,000 selected/truncated events and 5,060 notable-person records. Aggregate population is not a count of autonomous AI agents. The original simulation grid and all historical identities remain unchanged. The earlier walks retain 34, 30 and 23 reconstructed residents.

All eight featured portrait slots remain; the previous illustrations remain interpretive. The home-page courtyard image is an actual in-engine screenshot, not an image-generation result. No paid generation, model calls, API keys, analytics or visitor tracking were added. The original reference dataset and legacy Hugging Face Space are unchanged.

## Build and verification

Use Node 24 or newer. In this directory, run `npm ci`, then `npm run build`. The courtyard uses bundled Three.js and local assets. The archived world exports are downloaded with pinned hashes, or supplied with `node build.mjs --cache=<original-export-cache>`. `site/` is the complete self-hosted website; deploy that whole directory. Runtime data do not depend on the original external CDN.

`dist/Terra_World_05.html` is the complete offline edition, including the courtyard. `courtyard/dist/Terra_Courtyard.html` is a standalone courtyard edition. The asset-heavy offline files are larger than the earlier world archive alone.

Run `npm test` for the archive and courtyard suites. Tests use Chrome, including offline mode and mobile touch emulation; they are not evidence of performance on a physical iPhone. QA_REPORT.json identifies the exact tested artifact. Prolonged play, physical Safari/iPhone compatibility, multiplayer and autonomous residents are not claimed tested.

Previous source release: f196f14677e0ff4614449745e88f896e5391aac8 (0.4), merged as f83305bcc0c93a7e7b1b72a4bb36983d9ed88e71. Keep the previous source and deployment commits for rollback.

Feedback: https://huggingface.co/spaces/Bekzod25/terra-world-english/discussions or https://github.com/KeyAIGit/terra/issues .
