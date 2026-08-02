# TERRA

**A civilization simulator with sub-agent people — and the beginnings of a game built on top of it.**

TERRA starts an Earth-like planet at 12,000 BCE — the moment when humans, fire and
language already exist, and nothing else does. From there, history is not a script
but an outcome. Every simulated person has their own personality traits, needs,
kinship ties and a *subjective, often wrong* picture of the world. Each year they
choose what to do. Peoples, chiefdoms, cities, religions, wars and empires are not
entities anyone placed on the map — they are what millions of such choices add up to.

Worlds are fully deterministic: the same seed reproduces the same history down to
the last personal name. So history can be **replayed**: roll back to any year,
change one parameter, and watch destinies diverge.

**Live demo:** https://bekzod25-terra-world.static.hf.space/
*(3D first-person walk, rotating globe, atlas & chronicle, portrait gallery — note:
in-world text and UI are currently in Russian)*

![Capital city](docs/play_capital_temple.jpg)
![Night village](docs/play_neo_nightfire.jpg)
![Globe](docs/globe_night.jpg)

---

## What emerges (not scripted)

- **No tech tree.** 123 pieces of knowledge are defined only by physical
  preconditions — affordances (cut, heat, store, count, record…), materials, biome,
  scale of a cohesive population, storable surplus. Discovery happens when a
  specific person with cognitive leisure stumbles onto a combination that works
  *here and now*. Bronze is skipped where there is no tin; farming may never appear
  without large-seeded wild grasses; writing is born only under accounting pressure
  in dense settlements.
- **Real dark ages.** A knowledge ceiling depends on the scale of the connected
  population. When a complex polity collapses (Tainter-style cost of complexity),
  cities empty, the ceiling drops, and skills literally crumble away — descendants
  can no longer do what their grandparents did.
- **Languages that branch.** Every culture has its own phonology; when a people
  splits, its language forks through 29 real sound laws. Personal names, ethnonyms,
  god names and city names are all generated from the living language.
- **People with biographies.** The world keeps a book of people: everyone who
  invented something, ruled, or decided at a crossroads is recorded with their
  name, lifespan, traits, beliefs and deeds.

Calibration against our own history (seed 1): population 2.2M at 11,000 BCE →
178M at 500 CE (Earth: ~3M → ~190M); planetary carrying capacity by subsistence
mode lands within real archaeological ranges.

## The game layer

`play.html` — a self-contained first-person walk (WASD + mouse) through three
scenes assembled *from simulation data*: an imperial capital in 500 CE (walls,
sanctuary, market), a Bronze Age river town with a ziggurat, a Neolithic village
at night by the fires. The inhabitants are the actual people from the world's
book of people; press **E** to talk — answers are generated from their recorded
traits, beliefs, gods and chronicle events. Paste an Anthropic API key into the
dialogue panel and NPCs converse freely in character (browser-side call,
`claude-haiku-4-5`).

## Unreal Engine 5 export

```bash
python3 -m terra.export_ue runs/terra-1
```

Produces, per scene: terrain meshes with baked color, PNG16 heightmaps and
material weightmaps, a building manifest (every footprint verified to sit on the
terrain within 30 cm), inhabitants with dialogue cards and patrol routes, 17
procedural proxy meshes (hut → ziggurat), plus `import_terra.py` for UE's built-in
Python that assembles the level in one run, and a step-by-step `README_UE.md`.
The road to photorealism from there is free within the Epic ecosystem
(Fab/Megascans materials, MetaHuman characters).

## Quick start

```bash
pip install numpy scipy pillow --break-system-packages
npm i three@0.185.1

python3 -m terra new --seed 1 --to 500 --name terra-1   # live 12,500 years (~1.5 h)
python3 -m terra doctor terra-1                         # physics self-check
python3 -m terra report terra-1                         # dashboard
python3 -m terra.play runs/terra-1                      # build the walkable game
python3 -m terra fork terra-1 --at -3000 --set climate_severity=1.8
python3 -m terra compare terra-1 terra-1-fork3000
python3 -m tests.test_terra --slow                      # 70+ checks incl. determinism
```

## Architecture

| layer | file | responsibility |
|---|---|---|
| L0 planet | `terra/world.py` | plate tectonics, 14,000-year climate history, rivers, ores, wild flora/fauna |
| L1 societies | `terra/society.py` | carrying capacity, soil balance, war, epidemics, institutions, collapse |
| L2 people | `terra/agents.py` | traits, needs, subjective beliefs, kinship, action choice, prestige imitation |
| cognition | `terra/knowledge.py` | 123 technologies as physical preconditions, no tree |
| languages | `terra/lang.py` | phonology, 29 sound laws, drift and branching |
| junctures | `terra/junctures.py` | pivotal decisions: heuristic / Anthropic API / file oracle |
| main loop | `terra/sim.py` | deterministic stepping, checkpoints, forking, book of people |
| game | `terra/play.py`, `terra/_play_js.py` | first-person scenes, NPC dialogue |
| UE bridge | `terra/export_ue.py`, `terra/ue/` | terrain/manifest export + UE editor-Python importer |
| viewers | `terra/globe.py`, `report.py`, `compact.py`, `gallery.py` | 3D globe, dashboard, light atlas, faces |
| atlas | `atlas/` | (early) real-history data pipeline: Wikidata, Pleiades, museum APIs |

Pure Python 3.11 + numpy/scipy/Pillow; three.js is inlined into self-contained
HTML files. The simulation is the single source of truth — visualizations only read.

## Honest limitations

- The simulation models an Earth-*like* planet, not Earth; an "Earth mode" fed by
  real datasets (HYDE, Pleiades) is planned in `atlas/`.
- One polity is an ethno-political unit of thousands–millions; named individuals
  are a weighted sample, not the full population.
- The browser game is stylized low-poly; photorealism is the UE5 path.
- In-world text and interfaces are currently Russian.

*Built by Fable (Claude, Anthropic) in a Cowork session; the human sets direction
and accounts, the model writes the world.*
