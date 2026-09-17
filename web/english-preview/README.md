# Terra World: English Preview 0.2

## Run

Open **Terra_World_English_Preview.html** in a current desktop Chrome or Edge browser. No installation, server, account, API key or internet connection is required for this standalone edition. The optional Online Preview fetches the three original archives on demand.

Explore the home page, Atlas, Chronicle and People. Choose **Enter the world** for the walk. Click inside the scene, drag to look, use WASD to walk, Shift to run, E to meet a resident, M for the local map and Esc to close a dialogue. The top toolbar selects a settlement, a landmark or the time of day.

## What changed

The previous separate pages are integrated into one English interface. There are three preserved walkable settlements, a globe and flat map with 117 snapshots, a searchable translation of 14,000 selected event records, and 5,060 notable-person records. All eight featured portrait slots now have images; four existing illustrations were retained and four were generated with Higgsfield z_image. Three environment illustrations were also generated. Every artwork is explicitly interpretive, not an in-engine screenshot or evidence about a real historical person.

The walk now includes a textured masonry treatment, a curved capital gateway, additional architectural details, pottery, fabric awnings and instanced grasses. Its terrain, coordinates, broad layout and simulation history remain the original terra-1 export.

The original scenes incorrectly placed several archived people outside their lifetimes. The adapter excludes those 25 archival appearances without deleting their biographies. The scenes contain 34, 30 and 23 explicitly reconstructed residents. Their dialogue is scripted and does not call an AI service.

## Verification and limits

QA_REPORT.json records the actual desktop-Chrome verification of the standalone build, including all three walks, movement, lighting, landmark navigation, dialogue, gallery, search, timeline, mobile layout and zero network requests with the browser offline. BUILD_MANIFEST.json records source and artifact hashes. The build also checks JavaScript syntax, original-source integrity, record counts and translation coverage.

This is still a stylized browser prototype. It is not a photorealistic game, a new world-simulation run, or a population of autonomous AI agents. The 178 million population figure is an aggregate model quantity. The event export is explicitly truncated. The simulation grid remains 180 by 90; the larger display texture adds no simulation resolution. Mobile browsing was checked; touchscreen movement in the 3D walk is not implemented. Other browsers, long-duration play and multiplayer were not verified.

The historical-reference dataset Terra Atlas is separate and unchanged. Its 181M-row counter is not this game's story size. No analytics, paid NPC calls or browser API-key collection were added.

## Source, provenance and publication

Source: https://github.com/KeyAIGit/terra/tree/terra-world-english-preview-20260917/web/english-preview
Original Space: https://huggingface.co/spaces/Bekzod25/terra-world
Feedback: https://huggingface.co/spaces/Bekzod25/terra-world/discussions
The original Space and datasets were not overwritten: the connected Hugging Face write and create-PR actions returned Forbidden. The preview is prepared on a separate GitHub branch. Preserve the upstream code and asset licenses; this package makes no blanket ownership or licensing claim over external reference data.

Build: Node 24 or newer, run `node web/english-preview/build.mjs`. The build downloads only the three pinned original browser archives, not the 181M-row reference dataset. Original archive hashes are verified before their code is used. Generated artwork provenance and optimized-file hashes are in ASSETS_MANIFEST.json.
