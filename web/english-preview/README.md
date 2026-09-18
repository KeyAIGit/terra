# Terra World 0.6: inhabited districts

Play at https://keyaigit.github.io/terra/ . Three new district routes are `#district/capital`, `#district/bronze` and `#district/neolithic`. The previous atlas, history, biographies and earlier settlement walks remain accessible.

## What is implemented

Each district contains five furnished, enterable interiors, working doors, actual window apertures, storage covers and work surfaces. The capital, Bronze Age riverside district and Neolithic clearing share the rendering and interaction system but have different architecture and surroundings. The global simulation and the original settlement export have not been regenerated or overwritten. These are authored neighborhoods, not full replacements of every archived city block.

Six reconstructed adult residents per district move between homes, work and meeting places. They open doors, perform short work animations, visit households and exchange scripted text. The player can open doors, enter homes, operate storage and work objects, and talk to nearby visible residents. Use E or the touch interaction button.

Their perception is geometric: distance, view direction, wall/window geometry and door state. It is not camera-image understanding. Each resident retains at most twelve local observations during the current visit. Dialogue quotes witnessed local actions; no language model or paid API is called. This is a rule-driven prototype, not general intelligence or an independently evolving civilization.

Small interiors admit one scheduled resident at a time. Household visits are queued so opposing residents do not jam doorways. Routes include open door-leaf footprints and swept collision checks; residents wait for a door to open fully before crossing. Replanning can move away from another resident without allowing body overlap. Player interactions and navigation are still prototypes, not a promise that all conceivable situations are solved.

## Visual scope and provenance

The districts use physically based surfaces, HDR illumination and selected models from Poly Haven. Head/neck geometry, required skin regions and hair use MakeHuman core assets. These particular assets are CC0; source files, transformations and checksums are recorded in `courtyard/ASSETS.json` and `THIRD_PARTY.md`. Application-library license notices are included. Unused body texture regions are masked out. Main district preview images are actual in-engine captures.

Character bodies, clothing, gait, lighting and the wider landscape still need artistic refinement. The result is not yet indistinguishable from filmed history. Original canonical counts remain 117 snapshots, 14,000 selected/truncated events and 5,060 notable-person records. Original aggregate population is not a count of autonomous agents. No new historical events are written from resident routines.

## Build, testing and hosting

Use Node 24 or newer. Run `npm ci` and `npm run build` from this directory. A pinned original-export cache can be supplied with `node build.mjs --cache=<directory>`. The complete offline edition is `dist/Terra_World_06.html`; the standalone district edition is `courtyard/dist/Terra_Courtyard.html`. The shared district runtime has about 41 MB of assets. Deploy the complete `site/` directory, including its assets and archives.

`npm test` runs navigation/perception unit checks, repeated traffic simulations, original archive browser regression, five-room interaction tests in all three eras, and full offline/touch district checks. The traffic tests use the actual captured district collision geometry and multiple timestep patterns; they do not establish unlimited-duration stability. `QA_REPORT.json` records actual results for the tested release. Physical iPhone/Safari, multiplayer, spoken dialogue, and whole-world photorealism are not claimed verified.

Hugging Face embeds the GitHub Pages application; it is not an independent copy of all game files. The old HF Space and Terra Atlas reference dataset are unchanged. Prior 0.5 source commit 5c46e761969bcd93b69618fc9bb2250b1d743482 and its published offline world remain available for rollback. This work does not modify the separate AIAvatar project.
