# Terra World 0.3: English browser release

A fictional world explorer with an English atlas, chronicle, biographies and three walkable settlements. The published application is intended for https://keyaigit.github.io/terra/ . The separate Hugging Face Space remains the old version until its owner grants a working publication method.

## What changed from 0.2

The walk has separate plaster, masonry, timber, roof-tile and thatch treatments; terrain-following streets and a paved capital square; denser canopies; household baskets, grinding stones, benches and market produce; animated cloth; and reconstructed residents with individual heads and animated limbs. Added canopy counts are 135 / 210 / 65 and added prop primitive counts are 823 / 318 / 306 for capital / bronze / neolithic. These counts describe rendering detail, not newly simulated historical facts.

Touchscreen controls include a left movement joystick, drag-to-look, Meet and Map buttons. Landscape mode keeps controls within the viewport. A pause button stops time and resident motion, and auto/balanced/high quality options adjust resolution and shadows. The initial position is close to the settlement center. Touch compatibility-click handling prevents a newly opened dialog being immediately closed by the same tap.

The hosted edition serves the preserved archives and artwork from its own site. It does not depend on the old temporary CDN at runtime. The standalone `Terra_World_03.html` includes the same data and artwork and runs offline. Download it from `downloads/Terra_World_03.html` on the published site or build it locally.

## Preserved content and limits

The terra-1 engine, history, names, dates and settlement coordinates are unchanged. There are 117 archived snapshots, 14,000 selected event records and 5,060 notable-person records. The event export is explicitly truncated. The simulation grid remains 180 by 90. Its roughly 178 million people is an aggregate model quantity, not 178 million independently simulated agents.

All eight featured portrait slots are populated; most archived people have no portrait. Generated art is interpretive and is not an in-engine screenshot. The walk has 34 / 30 / 23 reconstructed residents. Chronologically invalid archival appearances remain excluded, while their biographies remain available. Dialogue is scripted, with no AI API calls, key collection or analytics. No new paid generation was used in this release.

This remains a stylized browser prototype. No photorealism, autonomous agents, multiplayer, physical-phone performance measurement, Safari-device compatibility or long-duration stability claim is made. Tests use desktop Chrome and Chrome mobile/touch emulation, not an actual iPhone. The engine was not rerun or retested because it was not modified.

## Build and verification

With Node 24 or newer, run `node web/english-preview/build.mjs`. The build verifies SHA-256 hashes of the three immutable original exports and the artwork. It checks JavaScript syntax, archive record counts and translation coverage. Outputs are `dist/` (standalone) and `site/` (self-hosted static files). Both generated directories are ignored by the code branch. Deploy the contents of `site/`, including `data/` and `assets/`, to the repository's gh-pages branch.

`QA_REPORT.json` contains actual browser results. `RELEASE.json` identifies the tested standalone file. `BUILD_MANIFEST.json` in dist records hashes. `ASSETS_MANIFEST.json` records artwork provenance. `tests/` contains the browser-test sources; pass an optional base URL to the published-site smoke test. Original 0.2 remains available through Git commit 7fb112c6e33ed25e76a75f74ada9adf092f063d9. The original HF datasets and Space are not overwritten.

Source: https://github.com/KeyAIGit/terra . Feedback: https://github.com/KeyAIGit/terra/issues . Reference data: https://huggingface.co/datasets/Bekzod25/terra-atlas . Preserve upstream code and data licenses; this package makes no blanket ownership claim over third-party reference datasets.
