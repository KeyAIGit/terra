# Реестр источников твина: порядок = приоритет обработки.
# Каждый модуль обязан дать: NAME, TITLE, LICENSE, fetch(ctx) -> dict
# со статусом ("done"/"partial"/"failed") и примечанием — как в атласе.

from twin.sources import (
    dem,
    bareearth,
    osm,
    counties,
    weather,
    sfbuildings,
    live,
    imagery,
    population,
    streetlevel,
)

REGISTRY = [
    dem,          # рельеф региона — фундамент всего
    bareearth,    # голая земля 3DEP под сценой: без крыш вместо земли
    counties,     # границы округов (лёгкие)
    weather,      # погода NOAA (мгновенно)
    live,         # живой слой: борта, спутники, толчки, прилив, камеры
    imagery,      # аэрофотоснимок под здания
    population,   # переписные кварталы с населением
    osm,          # здания/дороги/вода — самый долгий, чанками
    sfbuildings,  # городской лидар + годы постройки (машина времени)
    streetlevel,  # уличная съёмка: чем поверять геометрию — фотографией
]

BY_NAME = {m.NAME: m for m in REGISTRY}
