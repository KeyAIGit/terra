# Регионы и сцены твина.
#
# Регион — крупная территория (данные среднего разрешения: рельеф-обзор,
# границы округов, население). Сцена — город/район для 3D-прогулки
# (полное разрешение: здания, дороги, вода, рельеф 30 м).
# bbox всюду: (lat_min, lon_min, lat_max, lon_max), WGS84.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    key: str
    title: str
    bbox: tuple[float, float, float, float]
    counties_fips: tuple[str, ...] = ()   # state+county FIPS для переписи


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    region: str
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]           # lat, lon — начало координат сцены
    utc_offset: float = -8.0              # для солнца по местному времени


# Девять округов Залива: SF 075, San Mateo 081, Santa Clara 085, Alameda 001,
# Contra Costa 013, Solano 095, Napa 055, Sonoma 097, Marin 041.
REGIONS = {
    "bayarea": Region(
        key="bayarea",
        title="Залив Сан-Франциско (9 округов)",
        bbox=(36.90, -123.60, 38.90, -121.20),
        counties_fips=("06075", "06081", "06085", "06001", "06013",
                       "06095", "06055", "06097", "06041"),
    ),
}

SCENES = {
    "sf": Scene(
        key="sf",
        title="Сан-Франциско, наши дни",
        region="bayarea",
        bbox=(37.703, -122.527, 37.836, -122.348),
        center=(37.7749, -122.4194),
    ),
}


def scene(key: str) -> Scene:
    if key not in SCENES:
        raise KeyError(f"нет сцены {key!r}; есть: {', '.join(SCENES)}")
    return SCENES[key]


def region_of(sc: Scene) -> Region:
    return REGIONS[sc.region]
