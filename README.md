# Terra World 0.4: Places and records

A published English browser explorer at https://keyaigit.github.io/terra/ . The simulation history remains the original terra-1 archive; this release changes presentation and navigation only.

## Explore

The atlas now draws gold settlement-cell markers and offers settlement search for the selected snapshot. Select a place to read its recorded population and people, then open that people's chronicle or biographies at an explicit cutoff year. Three destination links set both the place and the original walk's year. URLs preserve this context, for example `#atlas?year=-1500&city=Rik%C3%A3%CC%80%C5%BE%C3%A0val&polity=180`.

Only three places have walkable reconstructions. Other settlements are archive records, not newly generated game levels. A settlement absent from a requested snapshot is not backfilled from the future. Shared cells are drawn once and map clicks choose the most populous recorded settlement in the cell; the search can distinguish individual records.

In a walk, **Places** marks a landmark with a straight-line bearing and distance. **Jump** moves to a nearby landing position checked against existing collision and water constraints. The indicator is not a pathfinding route. **Guide** shows the settlement's recorded quantities, links it to the atlas, and lists recent events of its people, explicitly distinguished from town-specific events. The world pauses while a guide is open.

The scenery adds irregular feather-edged plazas and paths, window/door joinery, and a lightweight animated cloud layer. It remains stylized, not photorealistic. Existing buildings, street endpoints, terrain heights and historical data are preserved. Scene switching explicitly releases old scene resources. Touch controls and quality/pause settings from 0.3 remain available.

## Boundaries

There are 117 snapshots, 14,000 selected/truncated events and 5,060 notable-person records. Population is an aggregate simulation measure, not a count of autonomous AI agents. All eight featured portrait slots remain available in the full gallery. Historical filters hide the full featured gallery, exclude people born after the cutoff, and hide later deeds and death dates. Role, era and disposition fields are whole-life archive summaries, not a reconstruction of the person at the cutoff date.

The walks retain 34 / 30 / 23 reconstructed residents. Their dialogue is scripted. No paid generation, model calls, API-key collection, analytics or visitor tracking were added. Terra Atlas and the old Hugging Face Space remain unchanged. Original third-party licenses and source attribution still apply; no blanket ownership claim is made over reference data or upstream code.

## Build and tests

Run `node web/english-preview/build.mjs` with Node 24 or newer. The build checks original-archive and image SHA-256 hashes, JavaScript syntax, record counts and translation coverage. `dist/Terra_World_04.html` is the standalone offline edition. `site/` is the static self-hosted website including its data, images and download. Deploy the complete site directory, not just index.html.

Browser tests are in `tests/release04-desktop.mjs` and `tests/release04-mobile.mjs`. Install their Playwright dependency separately; set `TERRA_REPO` to the repository root and optionally `TERRA_QA` to a report directory. The tests use Chrome, including mobile touch emulation. QA_REPORT.json and release.json describe the exact verified build and tests. A physical iPhone/Safari, prolonged play, autonomous agents, multiplayer and changed simulation behavior are not claimed to be verified.

Previous published release: source 13c6f1bc59252149dd33fab1302518d32fe442d3 (0.3). Original English 0.2 source: 7fb112c6e33ed25e76a75f74ada9adf092f063d9. Keep these commits and the previous deployment for rollback. Feedback: https://github.com/KeyAIGit/terra/issues .
