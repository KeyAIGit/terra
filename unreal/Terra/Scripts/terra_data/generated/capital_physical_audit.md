# Raflir capital: physical audit

## Verdict

The current `capital` export is a useful macro blockout, not a physically populated city at street-level fidelity.

- Source meta population: 8,367,729; requested comparison: 2,300,000.
- Terrain: 1.440 km²; building-layout bounding box: 0.299 km²; inferred wall enclosure: 0.127 km².
- 300 proxies imply 27,892 people/proxy at source population, or 7,667 at 2.3M.
- 255 house proxies provide about 45,356 m² estimated GFA: 184.5 people/m² at source population.
- OBB overlap pairs: 20 (2 non-compositional); road/building penetrations: 63.

## Streets and frontage

- House fronts within 10 m of a road edge: 209/255.
- House fronts simultaneously near, road-parallel and facing the road: 24/255.
- Market stalls simultaneously near, road-parallel and facing: 0/4.
- No square polygon exists. PlayerStart-as-proxy is 17.5 m from the nearest road edge.
- Gates: 2; market stalls: 4. Gate centers meet roads, while the market cluster lacks a direct square/access graph.

## Interpretation

Wall/tower and wall/gate overlaps may be intentional composition, but they need booleaned modular geometry. Other collisions, absent pedestrian/service graphs, and population ratios prevent a reality-level claim.

Audit digest: `sha256:8470679b3d12cdb4e5e2842b680e35a815a12120fb6de94213f59cb8d80d5717`
