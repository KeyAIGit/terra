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

### Paid / restricted — explicitly not needed

Google Photorealistic 3D Tiles (streaming only, no baking, billing account),
Planet, Hivemapper, Nexar, SatVu, Albedo, PeMS (manual approval, anti-scraping).
One special case: **SFEI historical ecology GIS** (the pre-colonial Bay
landscape) is free but its site 403-blocks our container's proxy — needs a
one-time user-side download.

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

## 6. Roadmap

1. **Done (this PR):** `twin/` pipeline + SF scene demo (`twin_sf.html`):
   real terrain, ~150k real buildings, streets, water, parks, live weather,
   day-cycle, click-to-identify. Offline tests + doctor.
2. **Precision pass:** switch scene buildings to DataSF lidar footprints
   (real heights for *every* building, not just OSM's 140k), join assessor
   years; USGS 1 m DEM for the city core; Overture for the other 8 counties.
3. **Textures:** NAIP orthophoto ground texture + Sentinel-2 seasonal
   refresh; ESA WorldCover material masks; night lights from CAISO demand.
4. **The living layer** (WorldView-style, all zero-key unless noted):
   synthesized traffic as particle flow along the road graph; planes
   (adsb.lol), ships (AIS — key), transit vehicles (511 — key), tides,
   quakes, air-quality haze; satellite passes overhead (CelesTrak TLE +
   SGP4 client-side); Caltrans freeway-camera billboards; sensor view
   modes (thermal / night-vision shaders) as a game aesthetic.
5. **Time machine v1:** year slider 2026→1906 driven by assessor years +
   burn polygon; then 1849/1776/pre-colonial layers.
6. **People:** population per block (TIGER POP20) spawns agents; TERRA's
   agent/dialog machinery moves in — NPCs who *live in the real city*.
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
