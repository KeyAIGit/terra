# TERRA Twin — a digital twin of the present, and a time machine out of it

*Strategy document, 2026-08. Status: phase 1 implemented (`twin/` package).*

## 1. What we are building

TERRA simulates a civilization from first principles. TERRA **Twin** attacks the
same goal from the opposite end: take a real territory, assemble a faithful
**simulation of the present** from real data — terrain, every building, every
street, live weather and sensors — then *de-build* it backwards through time
until the two ends of TERRA meet.

First region: the **San Francisco Bay Area** (9 counties), first scene: the
city of San Francisco. The choice is not sentimental: SF is arguably the best
*openly* instrumented city on Earth — the city itself publishes lidar-derived
3D building models, per-parcel construction years, and the region exposes live
transit, air, water, seismic and traffic feeds, almost all without any API key.

## 2. The reference landscape (who already does this)

The commercial category the user pointed at ("takes data from satellites,
planes, cars, thermal sensors and builds something close to Planet") splits
into five layers. For each there is an enterprise product — and a free,
redistributable emulation path that we take:

| Layer | State of the art (paid) | Our free path |
|---|---|---|
| Static 3D base | Google Photorealistic 3D Tiles, Blackshark.ai SYNTH3D | Blackshark's *recipe*, open data: city lidar footprints + OSM/Overture vectors + USGS 3DEP 1 m lidar + NAIP 60 cm imagery |
| Daily satellite pulse | Planet (3 m daily), EarthDaily, Albedo (10 cm + thermal VLEO) | Sentinel-2 (10 m, 2–5 days), Landsat 8/9 (incl. thermal), ECOSTRESS LST, GOES-18 (5 min) |
| Street level (car fleets) | Hivemapper/Bee Maps, Nexar CityStream | Mapillary (CC-BY-SA, dense SF coverage) |
| Live sensors | Enterprise city twins (Bentley, Esri — SFO runs one) | 511.org, NWS, USGS quakes, CO-OPS tides, adsb.lol aircraft, AIS ships, CAISO grid — SF's open sensor layer *beats* paid platforms |
| Ground photorealism | Gaussian splatting (Niantic Scaniverse), Matterport interiors | Self-captured splat "hero scenes"; interiors stay procedural (TERRA already fakes them from simulation data) |

What cannot be emulated for free: daily sub-meter optical, days-fresh street
imagery, meter-class thermal, interiors. Those are exactly what Planet,
Hivemapper, SatVu and Matterport charge for — and none is required for the
game.

**The proof-of-concept reference** (user-provided): Bilawal Sidhu's
*WorldView* "spy satellite simulator"
([spatialintelligence.ai](https://www.spatialintelligence.ai/p/i-built-a-spy-satellite-simulator))
— a weekend browser app layering live feeds (OpenSky/ADS-B aircraft,
CelesTrak satellite orbits, OSM traffic as particle systems, public CCTV
projected onto 3D city models) and sensor-style shaders (FLIR thermal, night
vision, CRT) over Google Photorealistic 3D Tiles. Every live layer he used
has a zero-key path in our inventory (adsb.lol, CelesTrak+SGP4, our own OSM
roads, Caltrans CWWP2 cams); the one paid piece is Google's mesh, which our
DataSF-lidar base replaces with redistributable data. His stated end-goal —
a continuously updating physical world model *queryable by AI agents* — is
exactly the twin-meets-TERRA-agents direction of this project.

## 3. Architecture (implemented)

`twin/` mirrors the atlas discipline: resumable manifest, chunked ingest,
Parquet with provenance (`source / license / tier / retrieved`), then a
deterministic scene compiler and a self-contained three.js viewer.

```
twin/
  regions.py      regions (bayarea) and scenes (sf) with bboxes
  state.py        manifest — same resume machinery as atlas/
  schema.py       kinds: feature (vector), grid (raster artifact), obs (sensor)
  sources/
    dem.py          Copernicus GLO-30 tiles -> region overview + 30 m scene crops
    osm.py          Overpass, chunked: buildings/roads/water/green/POIs
    sfbuildings.py  DataSF lidar footprints (177k, real heights) + assessor
                    year-built per parcel  <- the time machine key
    counties.py     Census cartographic boundaries, 9 counties
    weather.py      NOAA/NWS current observations + forecast
  ingest.py       driver: python3 -m twin.ingest --budget 1500
  doctor.py       schema validation + physical sanity (Twin Peaks elevation,
                  Transamerica Pyramid height, county count...)
  build.py        scene compiler -> scene_sf.json.gz (local meters, dm-quantized)
  view.py         -> twin_sf.html: embedded three.js, terrain mesh, extruded
                  landmark buildings, 150k+ instanced houses, roads, water,
                  live weather HUD, day-time slider, click-to-identify
```

Everything is tier **K** (known from source). The simulation remains the only
source of truth for *simulated* worlds; the twin is the only source of truth
for the *real* one. The two share the scene-compiler/viewer pattern
(`build_scene_data` ↔ `twin.build`), and later the UE5 export pipeline.

## 4. Data inventory

### Zero keys — implemented or ready to implement

| Source | What | Access |
|---|---|---|
| Copernicus GLO-30 | 30 m global DEM | `copernicus-dem-30m` S3, ~20 MB/tile ✅ |
| USGS 3DEP 1 m | 2023 SF lidar DEM, 4 tiles ~523 MB | `prd-tnm` S3, listable ✅ |
| USGS 3DEP EPT | full classified point cloud | `usgs-lidar-public` S3 (stream by octree node) |
| DataSF `ynuv-fyni` | 177k footprints, lidar ground+roof per building | Socrata, keyless ✅ implemented |
| DataSF `wv5m-vpq2` | assessor roll: year built + use per parcel | Socrata, keyless ✅ implemented |
| OSM Overpass | buildings (140k with heights), roads, water, POIs | keyless ✅ implemented |
| Overture Maps | conflated buildings/roads/places, whole Bay Area | GeoParquet on S3 / PMTiles range reads |
| NAIP 60 cm imagery | aerial texture, public domain | Planetary Computer STAC (anonymous SAS) |
| Sentinel-2 L2A | fresh 10 m color, 2–5 day revisit | `sentinel-cogs` S3 + Earth Search STAC ✅ probed |
| ESA WorldCover | 10 m land cover, one 88 MB COG covers the Bay | S3, keyless |
| NLCD annual | 30 m land cover 1985–2024 (urbanization playback) | MRLC direct download |
| TIGER TABBLOCK20 | census blocks **with POP20 population** — no API key needed | www2.census.gov, 368 MB for CA |
| NWS weather | observations + forecast | api.weather.gov ✅ implemented |
| USGS earthquakes | GeoJSON feed, 1-min refresh | keyless |
| NOAA CO-OPS | tides/currents at Golden Gate, 6-min | keyless |
| adsb.lol | live aircraft over the Bay, seconds-fresh | keyless |
| Caltrans CWWP2 | live freeway camera stills, District 4 | keyless |
| CAISO OASIS | grid demand/prices (city lights intensity) | keyless |
| CelesTrak | satellite TLEs (night-sky passes, SGP4 client-side) | keyless |
| BART API | real-time departures | public demo key works |
| USGS topoView | georeferenced historical topo quads 1884+ | TNM API, keyless |
| Sanborn maps (LoC) | building-level 1899–1950 fire-insurance maps | loc.gov JSON API, keyless |
| OpenHistoricalMap | date-tagged vectors (2,688 SF buildings with start_date) | own Overpass, keyless |
| David Rumsey | georeferenced 1849/1776 maps via IIIF/Allmaps | keyless (imagery CC BY-NC-SA — derive vectors, don't ship scans) |
| HYDE 3.3 | population grids 10,000 BC–2023 | already in atlas/ |

### Free key, instant signup — needs user action

| Source | Unlocks | Signup |
|---|---|---|
| **511.org** | GTFS-Realtime vehicle positions for *every* Bay Area operator (Muni, BART...), 15–30 s cadence, traffic events | name+email form, token by email, instant |
| **Census API** | current ACS demographics (beyond 2020 block counts) | instant email form |
| **aisstream.io** | live AIS ship positions (websocket) | GitHub sign-in |
| **OpenAQ** *or* **AirNow** | hourly air quality → haze/smog tint | instant |
| **NASA FIRMS** | wildfire hotspots | instant |
| NHGIS (IPUMS) | historical census per decade (people counts per era) | free account |
| Mapillary | street-level imagery API | free registration |

Mapillary is now optional rather than needed: **KartaView** turned out to serve
dashcam street imagery with position, heading and date over a keyless API
(CC BY-SA), and **Wikimedia Commons** `geosearch` returns geotagged building
views with author and licence, also keyless. Both are implemented in
`twin/sources/streetlevel.py` — see §4a.

### Billed key, user's account — implemented, awaiting a key

Google Maps Platform is the one place where the best imagery is genuinely
behind a paid key. All three products the user asked for are wired in and
switch on the moment a key is pasted into the page:

| Product | What it gives the twin | Endpoint |
|---|---|---|
| **Street View Static API** | photograph from the exact position and bearing the walker occupies — direct comparison against our geometry | `maps/api/streetview` |
| **Map Tiles API, 2D satellite** | the top-down view: Mercator tiles stitched into one canvas and laid on the terrain in place of NAIP | `createSession` → `v1/2dtiles/{z}/{x}/{y}` |
| **Map Tiles API, Photorealistic 3D Tiles** | the photorealistic walkthrough: Google's photogrammetry mesh streamed into our scene | `v1/3dtiles/root.json` |

Design decisions worth keeping:

- **Our own 3D Tiles traverser**, not Cesium. Pulling a second engine in for one
  layer costs more than the traversal: bounding volume → screen-space error →
  descend or load. Tiles arrive in ECEF and are moved into the scene by a single
  matrix (geocentric → east/up/south) built at the scene centre, so Google's
  mesh lands on our terrain and *our* sensors, sun and time-of-day still apply
  to it. `GLTFLoader`/`DRACOLoader` live in `examples/jsm` as ES modules;
  `twin/view.py` rewrites them into a classic script (each module in its own
  closure, or `const { Loader } = THREE` would be declared four times), and the
  Draco decoder is embedded as a `data:` URI.
- **The key belongs to the user, not to us.** It is typed into the page, kept in
  that browser's `localStorage`, and sent to exactly one host — Google.
  `twin.doctor` greps the sources and the compiled scene for anything shaped
  like `AIza…` and fails the build if it finds one.
- **Terms**: tiles are streamed, never cached to our repo, and the attribution
  string Google returns with the tileset is displayed on screen. Billing is the
  user's, so the panel links to Google's pricing page rather than hiding it.
- **Honest status**: written, syntax-checked and reasoned through, but **never
  executed** — we have no key. Failures surface in the panel in words instead of
  failing silently.

### Paid / restricted — not pursued

Planet, Hivemapper, Nexar, SatVu, Albedo, PeMS (manual approval,
anti-scraping). One special case: **SFEI historical ecology GIS** (the
pre-colonial Bay landscape) is free but its site 403-blocks our container's
proxy — needs a one-time user-side download.

## 4a. Photographs as ground truth (keyless, implemented)

The city is assembled from measurements, so the only honest way to ask whether
it resembles the real place is to stand where a camera stood, face the way it
faced, and look. That makes the *heading* the load-bearing field of a street
photograph — a frame without one cannot be compared to anything, and `doctor`
therefore requires a heading on ≥90% of frames and, in the compiled scene,
strictly inside [0, 360).

- **KartaView** (`api.kartaview.org`, images at `api.openstreetcam.org`):
  dashcam sequences, CC BY-SA 4.0, each frame carrying lat/lon, heading, date
  and contributor. A 450 m radius around downtown returns ~4000 frames, so
  thinning is mandatory: newest frame per 22 m cell at ingest, per 45 m in the
  scene.
- **Wikimedia Commons** `generator=geosearch` + `prop=imageinfo|coordinates`:
  geotagged views of named buildings, with author and licence for each.

Frames are never copied into our data — the scene carries the URL, the author
and the licence, and the page fetches the picture from the source. Two traps
found the hard way: KartaView serves images **without CORS** (fine in an
`<img>` panel, impossible as a WebGL texture), and Commons attaches coordinates
to only the first ten pages of a fifty-page generator result unless you ask for
`colimit=max`.

## 5. The time machine (present → past)

The de-building plan, layer by layer; tiers K/T/R as in the atlas:

- **2026 (K)** — the base twin. Already carries its own history: every parcel
  knows `year_property_built`.
- **1950 (K)** — *generated, not sourced*: filter buildings to
  `year_built <= 1950` (most pre-1950 stock still stands). Validate against
  Sanborn 1948–50 volumes and 1938–48 aerial photos (UCSB FrameFinder).
- **1906 (K/T)** — two states: post-fire (base twin minus everything inside
  DataSF's burn polygon `yk2r-b4e8`) and pre-quake — vectorize Sanborn
  1899–1900 sheets for the play-scene footprint only (a few blocks);
  terrain from the 1895/1899 USGS quads (pre-fill shoreline, ungraded hills).
- **1849 (T)** — Coast Survey charts and gold-rush plans via David Rumsey:
  the tiny Yerba Buena street grid, original waterline. Population from NHGIS.
- **1776 (T/R)** — Presidio + Mission Dolores as the only structures
  (Cañizares 1776 chart); landscape from SFEI ca.-1800 habitat mosaic.
- **Pre-colonial (R)** — SFEI historical ecology (tidal marsh, creeks,
  original shoreline = modern DEM minus fill), HYDE for regional population,
  Ohlone settlement sites from literature. This is where the twin meets the
  TERRA simulation: the de-built landscape becomes a world the simulator can
  inhabit.

## 5a. How current is "the present"? (three levels, honestly)

The twin is built, not streamed, so "live" needs defining. There are three
levels and we currently ship the first:

1. **Snapshot (today).** `twin.ingest --source live` writes a timestamped
   capture — aircraft where they were at that minute, the tide at that
   reading, satellites propagated around that epoch. `twin.build` bakes it
   into the scene and the HUD prints the stamp. Reopening the page a week
   later shows that week-old minute, correctly labelled. Aircraft and
   satellites keep *moving* from their captured state (dead reckoning and
   SGP4 ephemeris stay valid for tens of minutes either side), but the
   underlying capture does not refresh itself.
2. **Refreshed on a schedule.** The same three commands on a timer
   (`ingest --source live` → `build` → `view`) regenerate the page. Every
   source involved is keyless, so nothing blocks this; it needs a machine
   that runs the job and a place to put the result. Cheap: the live capture
   takes under two minutes, the rest of the data does not move.
3. **Live in the browser.** Feeds fetched by the page itself at view time.
   Only possible where the source sends permissive CORS headers — verified
   true for the Caltrans camera stills (which is why clicking a camera shows
   the road as of a minute ago even in an offline file) and worth checking
   per feed for the rest. This is the only level that is genuinely "always
   current", and it costs the page its offline self-sufficiency.

The right answer is probably 2 for the world (rebuild nightly) plus 3 for the
handful of feeds that allow it (cameras, weather, tide). Note that a page
published as an Artifact runs under a strict CSP that blocks *all* external
requests, so level 3 degrades to the snapshot there by design.

## 5b. Predicting forward — and being scored for it

The owner's goal is not only to reconstruct the past but to estimate what
happens next, with probabilities. The design principle here is the same one
that governs the time machine: **a forecast is worth nothing unless it is
recorded before the fact and scored after.** So `twin/forecast.py` has two
verbs, not one — `issue` writes dated, falsifiable predictions with a
timestamp, and `score` fetches what actually happened and grades them. Point
forecasts get mean absolute error; probabilistic ones get a Brier score and,
once there are enough, a calibration curve: if we said 30% twenty times, it
should have happened about six times.

Three predictors ship, all from data already ingested and all keyless:

- **Tide** — the harmonic prediction from NOAA CO-OPS 9414290. This is the
  loop's proving ground: a prediction issued now is scorable in hours against
  the station's own observation, so the whole issue→score machinery is
  validated end to end within a single day.
- **Temperature** — the NWS gridpoint forecast, converted to °C.
- **Seismicity** — a real estimate rather than a vibe. The Gutenberg–Richter
  law (log N = a − bM) is fitted to the USGS catalogue by Aki's
  maximum-likelihood estimator, the rate is extrapolated to the target
  magnitude, and a Poisson process gives P(at least one). On live Bay Area
  data this returns **b = 1.00**, the textbook California value, and
  P(M≥5 within a year) ≈ 43%, which sits inside USGS's own range.
  The stated caveat matters: a Poisson process assumes independence, and
  earthquakes cluster into aftershock sequences, so short horizons are
  overconfident. That limitation is written into the forecast's own method
  string rather than hidden — and the scoring loop will expose it in the
  Brier score, which is exactly what the loop is for. Declustering
  (Reasenberg) or ETAS is the honest next step.

What this framework buys later: the same issue→score discipline applies to
the interesting urban questions — where construction appears next (DataSF
permits are a genuine leading indicator: a filed permit is a stated intention
with a historical completion rate), population change, and inundation under
sea-level scenarios, which is deterministic given the DEM. Each is a
prediction the twin can be graded on, so the simulator earns credibility
instead of asserting it.

## 5c. People: synthetic, never real

The game layer wants a city you can walk through and talk to. The line drawn
here is deliberate and permanent:

- **Yes:** a synthetic population generated from public aggregate statistics
  — TIGER block populations (POP20, keyless), household size, age structure,
  occupation mix — assigned to real buildings by capacity and land use.
  Nobody in it corresponds to a real person; each resident is a draw from a
  distribution. This is ordinary practice in transport and epidemiological
  agent-based modelling, and it is also the better game: half a million
  plausible residents beat a handful of scraped names.
- **Yes:** institutions as institutions — agencies, budgets, transit
  operators, published policy — from open records.
- **No:** modelling identifiable real residents or named officials, or
  putting invented words in their mouths. That is profiling living people
  and fabricating their speech, the data for it is not open, and assembling
  it would be the wrong thing to do. Nothing about the game requires it.

TERRA's existing `agents.py` (traits, needs, beliefs, action choice) and
`play.py` (dialogue from recorded data) already provide the machinery; the
twin only needs to seed it from census distributions instead of simulation
history.

## 5d. Generative world models: appearance layer, not foundation (Aug 2026)

Asked whether Genie or Seedance could build this instead of a data pipeline
plus UE5, the answer from a survey of the field is unambiguous:

**No system in August 2026 generates an interactive 3D world that is
geometrically faithful to a real place.** These are autoregressive video
models with a context window; persistence and geographic fidelity are the
same limitation, and it has not been beaten.

- **Genie 3** (still current; no Genie 4) — 720p, 20–24 fps, a few minutes of
  interaction, memory of specific changes for about a minute. Since May 2026
  Project Genie can seed a world from a Google Maps pin. DeepMind's own words:
  *"currently unable to simulate real-world locations with perfect geographic
  accuracy"*; Google's own team: *"can't yet create a faithful reconstruction
  of a street."* The sharpest test is from the same author whose WorldView
  project prompted this whole direction: seeded in San Francisco, Genie put
  the Bay Bridge correctly beside the Ferry Building — and filled the back of
  the Palace of Fine Arts with **phantom houses where the Marina bay actually
  is**. Correct at the seed panorama, invented a block away. Output is video;
  no 3D export, no API, $200/mo tier.
- **Seedance 2.5** (released 31 Jul 2026) — real, and irrelevant as a
  substitute: video only, not interactive, no persistence, no 3D. 30 s native
  single-shot, up to 4K, multi-shot consistency. One useful hook: it accepts a
  **3D blockout to lock camera and composition** — i.e. render our greybox,
  let it skin the shot. Cinematics, not infrastructure.

**What can take our accurate geometry as input** — this is the real question,
and three systems answer it:

1. **NVIDIA Cosmos Transfer 2.5** — open weights (OpenMDW/Apache), generates
   photoreal video conditioned on depth, segmentation, LiDAR and HD maps from
   a simulation engine or real logs. Our geometry, its photorealism. Output
   is video.
2. **World Labs Marble** — "Chisel" blockout plus mesh import, and it is the
   only one that hands back a **reusable asset**: Gaussian splats (PLY/SPZ)
   and textured GLB. Since Jan 2026 assets are "roughly scaled and grounded to
   real-world units" — metric, though still not georeferenced. $20–95/mo.
3. **Tencent HY-World 2.0** — open source, exports 3DGS, meshes, point clouds,
   camera parameters, importable into Blender/UE/Isaac; its WorldMirror stage
   reconstructs real places from multi-view images or casual video. The
   self-hostable analogue to Marble.

None of the three knows what a latitude is. We supply the georeferencing —
which is precisely what this pipeline already produces.

**Two findings that change our planning:**

- **Gaussian splatting is production-ready and free to integrate.** NanoGS for
  UE5 (Mar 2026) gives Nanite-style LOD clusters for splats; XV3DGS renders
  splats and conventional geometry in one scene; three.js loaders exist, so
  splat "hero blocks" could land in our own viewer, not only in UE. Aerial →
  splat at city scale is a solved commercial path (DJI Terra outputs PLY and
  3D Tiles).
- **UE 5.8 (Jun 2026) is the final UE5 release**; UE6 early access is expected
  late 2027. More usefully, **PCG became production-ready in 5.7** — which is
  exactly the tool for instantiating tens of thousands of buildings from real
  footprints and heights. Our export already produces that input.

One architecture is worth watching: **Seoul World Model** (ECCV 2026,
research-only) does retrieval-augmented generation — given coordinates, it
retrieves nearby real street imagery and re-grounds continuously, achieving
multi-kilometre trajectories without drift. That is the missing step Google
skipped. If retrieval-grounding reaches a shipping product, this section needs
rewriting.

**Standing decision:** the accurate skeleton stays conventional — real data,
real coordinates, UE5 PCG for anything with collision. Generative models are
an appearance layer on top: Marble or HY-World for hero blocks exported as
splats, Cosmos Transfer for photoreal video out of the finished simulation,
Seedance for trailers. Where they genuinely earn their place is the layer with
no open data at all — **building interiors** — and the deep past, where
plausible reconstruction is the honest answer and tier R already says so.

## 6. Roadmap

1. **Done (this PR):** `twin/` pipeline + SF scene demo (`twin_sf.html`):
   real terrain, ~150k real buildings, streets, water, parks, live weather,
   day-cycle, click-to-identify. Offline tests + doctor.
2. **Precision pass:** scene buildings now come from DataSF lidar footprints
   (real heights for *every* building, not just OSM's 140k) with assessor years
   joined. ~~USGS 1 m DEM for the city core~~ — **done, and keyless**: USGS
   **3DEP Bare Earth** replaces Copernicus GLO-30 under the scene. This is a
   correctness fix, not a resolution one. GLO-30 is a *surface* model — it
   measures what the radar bounced off, which downtown is rooftops — so the
   ground was lifted by the height of the buildings standing on it, and the
   build had to shove it back down with a 3×3 minimum filter that also flattened
   the hills. 3DEP hands over ground with the built environment already
   subtracted, at 3.9 × 4.6 m, so the filter is gone. Two grids now exist for
   two different jobs: objects are *placed* on the full-resolution lidar, and
   the mesh we *draw* is resampled to ~24 m, because thirteen million vertices
   bought a 96 MB scene file and no visible detail. Verified: the scene's
   highest point is 287 m (Twin Peaks, 282 in life) and the financial district
   sits at 4.8 m where the surface model claimed 7.2.
   Still open: Overture for the other 8 counties.
3. ~~**Textures**~~ — **done for the base layer.** `twin/sources/imagery.py`
   pulls USDA **NAIP at 0.6 m/pixel** (public domain, keyless) as Planetary
   Computer mosaic tiles — z16, ~1000 tiles, stitched and cropped to the scene
   bbox, downscaled to a 4096 px JPEG. The terrain carries Mercator-correct
   UVs, because the tiles are EPSG:3857 while the DEM grid is uniform in
   latitude; ignoring that slides the photo tens of metres against the ground.
   Two rules keep it honest: the drawn road ribbons hide under the photo
   (the real streets are already in it), and travelling back in time switches
   the photo off with a note — it shows today's ground, and 1930 did not have
   these parking lots. Historical aerials (UCSB FrameFinder, 1938+) are the
   natural next layer for the past.
   Still open here: Sentinel-2 seasonal refresh, ESA WorldCover material
   masks, night lights from CAISO demand.
4. ~~**The living layer**~~ — **done, and it goes past the reference.**
   `twin/sources/live.py` bakes a timestamped snapshot of the present, all
   keyless: **aircraft** over the Bay (adsb.lol — ~250 contacts with type,
   flight level, heading, military flag), **satellites** (CelesTrak GP
   elements propagated through SGP4 in Python, then converted to the
   azimuth/elevation a viewer in San Francisco would actually see — so the
   passes arc across the sky dome, and sink below the horizon when they
   should), **earthquakes** (USGS, 30 days of Bay Area shocks), the
   **real tide** (NOAA CO-OPS station 9414290 — the bay surface in the twin
   sits at the water level measured at Fort Point), and **Caltrans freeway
   cameras**, whose stills carry `Access-Control-Allow-Origin: *` and so
   load live in the browser: clicking a camera in an offline HTML file shows
   the road as it is this minute.

   **Sensor modes** (keys 1–4): optical, night vision, thermal, CRT. The
   thermal channel is where we beat the reference outright. WorldView maps a
   FLIR palette onto rendered luminance; ours computes a **surface
   temperature** per vertex from the material's albedo and thermal inertia,
   the sun's angle of incidence, the stored heat of the day, and the
   building's own internal load by use class — with the air temperature
   coming from the live NOAA observation. So asphalt glows after dark
   because it really does, parks go cold because vegetation really cools
   fast, the bay stays flat because water really has enormous inertia, and
   industrial roofs run hotter than housing. The scale is printed in °C:
   ours is a measurement, not a colour ramp.

   Still to add here: traffic particles along the road graph, ships (AIS
   needs a free key), transit vehicles (511 key), air-quality haze.
5. ~~**Time machine v1**~~ — **done**: a year slider de-builds the city from
   2026 back to the 1790s. 165k buildings carry a construction year; the
   filter runs in the vertex shader (one uniform per slider move, geometry
   untouched), so 175k buildings re-date at frame rate. Named OSM landmarks
   inherit their year from the DataSF footprints they contain
   (point-in-polygon, not bbox — a neighbour's bbox would import the wrong
   date). Verified against reality: Transamerica Pyramid 1972, Salesforce
   Tower 2018, Coit Tower 1933, 555 California 1969.
   Two source caveats the UI states out loud rather than hides:
   the assessor writes **1900 as a placeholder for "old"** (14,628 parcels
   against 161 in 1901), and everything downtown carries **1906 or later**
   because the fire took the city — that layer needs Sanborn sheets.
   Buildings with no year at all (11k) are shown by default and can be
   switched off, so the player can see exactly how much is unknown.
   Next: the 1906 burn polygon, then 1849/1776/pre-colonial layers.
6. **People:** population per block (TIGER POP20) spawns agents; TERRA's
   agent/dialog machinery moves in — NPCs who *live in the real city*.
6a. ~~**Photographic ground truth**~~ — **done, keyless**: real street frames
   with camera headings (KartaView) and geotagged building views (Wikimedia
   Commons). *Stand here* puts the camera at the shot and turns it to the
   shot's bearing; *follow along* keeps the nearest same-facing frame beside
   you as you walk. This is the twin's first way of being **wrong in public**:
   any building we got too short, too tall or simply missing is now visible
   next to a photograph of the same corner. Next: score the mismatch instead
   of eyeballing it — silhouette overlap between the frame and our render.
6b. **Google layers** — **written, awaiting a key** (§4): Street View Static,
   2D satellite tiles, Photorealistic 3D Tiles. The skeleton stays ours;
   Google's imagery is an appearance layer on top of it, exactly as §5d
   concluded for generative models.
7. **UE5:** the twin scene compiler feeds the existing `export_ue` pipeline
   (terrain.obj + masks + buildings.json are format-compatible by design).

## 7. Design rules

- Same provenance discipline as the atlas: every record carries
  `source/license/tier/retrieved`; no binary blobs in git (twin/data is
  gitignored, ~reproducible from the manifest).
- Deterministic compile: sorted traversal everywhere; same inputs → same
  scene bytes.
- Respect licenses: ODbL for OSM-derived, PDDL for DataSF, public domain for
  federal; Google tiles and Rumsey scans are *not* baked into artifacts.
- Every user-visible surface is verified with Playwright screenshots.
- **Secrets never enter the repository, and it is checked rather than
  intended.** Ingest keys come from the environment or a gitignored
  `twin/.keys.json`; browser keys stay in the viewer's `localStorage`; a key is
  never sent through a conversation, because transcripts are written to disk and
  a leaked key can only be revoked, not recalled. `twin.doctor` greps the
  sources, the compiled scene and the built page for six shapes of secret and
  fails the build on a hit. See [twin_keys.md](twin_keys.md).
- **Keyless first.** A capability that needs a paid key is a capability we do
  not have yet. Of the sixteen providers worth wanting, fourteen cost nothing
  and need no payment card — and twice now the "paid" assumption turned out to
  be wrong on inspection: street-level imagery (KartaView, not Mapillary's
  token) and metre-scale bare-earth terrain (USGS 3DEP's open ImageServer, not
  OpenTopography's key). Check before budgeting.
