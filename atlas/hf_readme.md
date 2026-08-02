---
license: other
license_name: mixed-open
license_link: https://github.com/KeyAIGit/terra
language:
- en
- ru
pretty_name: TERRA Atlas of Historical Data
size_categories:
- 100K<n<1M
tags:
- history
- archaeology
- geography
- gazetteer
- radiocarbon
---

# TERRA Atlas of Historical Data

A warehouse of **normalized extracts from open historical datasets** for the
TERRA civilization-simulation project (an epoch-travel game aiming at
historically honest scenes). This is *not* a scrape of the web: every record
comes from a published open dataset and carries provenance.

## Record contract

Every row in every parquet file has four mandatory provenance fields:

| field | meaning |
|---|---|
| `source` | URL or stable identifier of the origin record/dataset |
| `license` | license of the origin dataset (see per-source table below) |
| `tier` | confidence tier: **K** = known from a source (document, find, database record); **T** = typical for the epoch/place (norms, no direct record); **R** = reconstruction / model output, honestly flagged |
| `retrieved` | ISO date the record was fetched |

Record kinds (stored in parquet key-value metadata `terra_atlas_kind`):
`person`, `place`, `polity_snapshot`, `event`, `artifact`, `grid_layer`,
`source` (dataset-level provenance row).

Layout: `data/<source>/<kind>_*.parquet` (snappy, shards ≤ 256 MB).
`manifest.json` documents per-source status, chunk checksums and sizes.

## Sources

| source | what | kinds | license | tier |
|---|---|---|---|---|
| `pleiades` | ~42k places of the ancient world: coordinates, feature types, time periods, location precision | place | CC-BY-3.0 | K |
| `p3k14c` | ~180k archaeological radiocarbon dates (lab id, age BP, sd, coordinates, site, country) — settlement-density proxy. Year field is `1950 − age_bp`, **uncalibrated** | event | CC-BY-4.0 | K |
| `dplace` | D-PLACE Ethnographic Atlas: ~1.3k societies (coordinates, focal year) + long-format variable values with code labels | polity_snapshot | CC-BY-4.0 | K |
| `seshat` | Seshat Databank, official Equinox packaged data (Zenodo mirror 10.5281/zenodo.6629022) | polity_snapshot | AGPL-3.0 per Zenodo record; Seshat site states CC-BY-NC-SA-4.0 — **do not ship without checking** | K |
| `met` | The Met Open Access: ~490k object metadata rows (title, begin/end year, culture, medium, public-domain flag). No images; `api_url` returns `primaryImage` | artifact | CC0-1.0 | K |
| `naturalearth` | Natural Earth 10m vectors: countries, populated places, rivers, lakes; geometry as GeoJSON strings + bbox + representative point | place | Public Domain | K |
| `wikidata_rulers` | First vertical slice “Mesopotamia −2500…−500”: rulers (reign dates, positions) and kingdom capitals with coordinates. Full pre-1500 persons layer is registered as a dump-scale plan, not fetched | person, place | CC0-1.0 | K |
| `hyde` | HYDE 3.3 (Utrecht University mirror): test slice — population-count grid (`popc`) for 2000 BC, 5 arcmin, zero cells omitted; remaining slices listed as pending URLs in the manifest | grid_layer | CC-BY-4.0 | **R** (model reconstruction) |

## Honest-uncertainty policy

The atlas marks, rather than hides, how much is actually known: prehistory has
no names or conversations — its ceiling is archaeology (tier K for material
finds), everything else is T/R by definition. Model grids (HYDE) are tier R
even though they are the best available estimates. Downstream consumers (scene
compilers, NPC dossiers) must show provenance, e.g. “source: Pleiades 912985”
vs “reconstruction by analogy”.

## Reproduction

Collection pipeline (resumable, disk- and time-budgeted) lives in the TERRA
repo: `atlas/` package — `python3 -m atlas.ingest --budget 1500`, then
`python3 -m atlas.doctor`, then `HF_TOKEN=... python3 -m atlas.upload_hf`.

## Licenses

Each record carries its origin license; the compilation adds no restrictions.
For shipping inside a game use only CC0 / Public Domain / CC-BY rows (mind
CC-BY attribution) and exclude `seshat` until its terms are clarified.
