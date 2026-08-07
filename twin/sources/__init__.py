# Реестр источников твина: порядок = приоритет обработки.
# Каждый модуль обязан дать: NAME, TITLE, LICENSE, fetch(ctx) -> dict
# со статусом ("done"/"partial"/"failed") и примечанием — как в атласе.

from twin.sources import (
    dem,
    osm,
    counties,
    weather,
    sfbuildings,
)

REGISTRY = [
    dem,          # рельеф — фундамент всего
    counties,     # границы округов (лёгкие)
    weather,      # погода NOAA (мгновенно)
    osm,          # здания/дороги/вода — самый долгий, чанками
    sfbuildings,  # городской лидар + годы постройки (машина времени)
]

BY_NAME = {m.NAME: m for m in REGISTRY}
