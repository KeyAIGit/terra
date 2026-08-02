# Реестр источников склада: порядок = приоритет обработки.
# Каждый модуль обязан дать: NAME, TITLE, LICENSE, fetch(ctx) -> dict
# со статусом ("done"/"partial"/"failed") и примечанием.

from atlas.sources import (
    pleiades,
    p3k14c,
    dplace,
    seshat,
    met,
    naturalearth,
    wikidata_rulers,
    hyde,
    astro,
    etopo,
    biosphere,
    osm_features,
)

# Порядок приоритета: лёгкое и целиком — раньше; тяжёлое/срезы — позже.
REGISTRY = [
    pleiades,
    p3k14c,
    dplace,
    seshat,
    met,
    naturalearth,
    wikidata_rulers,
    astro,
    etopo,
    biosphere,
    osm_features,
    hyde,
]

BY_NAME = {m.NAME: m for m in REGISTRY}
