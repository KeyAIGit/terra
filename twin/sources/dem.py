# Рельеф: Copernicus DEM GLO-30 (30 м) с открытого бакета AWS.
# Тайлы 1°×1°; отсутствующий тайл = океан (нулевые высоты). Продукты:
#   region_overview.npz — весь регион, даунсэмпл ×3 (~90 м)
#   scene_<key>.npz     — полный 30 м вырез под каждую сцену
# Плюс parquet kind=grid с описанием артефактов. Лицензия Copernicus
# разрешает свободное использование с указанием источника.

from __future__ import annotations

import json
import math
import os

import numpy as np

from twin import regions, schema
from twin.sources import common

NAME = "dem"
TITLE = "Copernicus DEM GLO-30 — рельеф региона и сцен"
LICENSE = "Copernicus DEM (ESA, свободное использование с атрибуцией)"
URL_T = ("https://copernicus-dem-30m.s3.amazonaws.com/"
         "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM/"
         "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM.tif")
N = 3600            # точек на градус в тайле
OVER_DS = 3         # даунсэмпл обзора региона (×3 → ~90 м)


def _tile_name(lat0: int, lon0: int) -> tuple[str, str]:
    la = f"{'N' if lat0 >= 0 else 'S'}{abs(lat0):02d}"
    lo = f"{'E' if lon0 >= 0 else 'W'}{abs(lon0):03d}"
    return la, lo


def _tiles_for(bbox) -> list[tuple[int, int]]:
    lat_min, lon_min, lat_max, lon_max = bbox
    out = []
    for lat0 in range(math.floor(lat_min), math.ceil(lat_max)):
        for lon0 in range(math.floor(lon_min), math.ceil(lon_max)):
            out.append((lat0, lon0))
    return out


def _fetch_tile(ctx, lat0: int, lon0: int) -> str | None:
    """Скачивает тайл в сырьё; None = тайла нет (океан)."""
    la, lo = _tile_name(lat0, lon0)
    dest = common.raw_path(NAME, f"{la}_{lo}.tif")
    if os.path.exists(dest):
        return dest
    miss = dest + ".missing"
    if os.path.exists(miss):
        return None
    url = URL_T.format(lat=la, lon=lo)
    r = ctx.session.head(url, timeout=30)
    if r.status_code == 404:
        open(miss, "w").close()
        return None
    common.download(ctx, url, dest)
    return dest


def _load_tile(path: str | None) -> np.ndarray:
    if path is None:
        return np.zeros((N, N), dtype=np.float32)
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    a = np.asarray(Image.open(path), dtype=np.float32)
    if a.shape != (N, N):
        raise ValueError(f"неожиданный размер тайла {path}: {a.shape}")
    return a


def crop_mosaic(bbox, tile_of) -> np.ndarray:
    """Вырез bbox из мозаики тайлов; tile_of(lat0, lon0) -> ndarray.

    Строка 0 результата — северный край bbox. Индекс от северного края
    тайла: row = (lat0 + 1 - lat) * N.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    rows = int(round((lat_max - lat_min) * N))
    cols = int(round((lon_max - lon_min) * N))
    out = np.zeros((rows, cols), dtype=np.float32)
    for lat0, lon0 in _tiles_for(bbox):
        tile = tile_of(lat0, lon0)
        # пересечение bbox с тайлом [lat0, lat0+1] × [lon0, lon0+1]
        la0, la1 = max(lat_min, lat0), min(lat_max, lat0 + 1)
        lo0, lo1 = max(lon_min, lon0), min(lon_max, lon0 + 1)
        if la1 <= la0 or lo1 <= lo0:
            continue
        # строки результата (0 = север bbox)
        r0 = int(round((lat_max - la1) * N))
        r1 = int(round((lat_max - la0) * N))
        c0 = int(round((lo0 - lon_min) * N))
        c1 = int(round((lo1 - lon_min) * N))
        # строки тайла (0 = север тайла lat0+1)
        tr0 = int(round((lat0 + 1 - la1) * N))
        tc0 = int(round((lo0 - lon0) * N))
        h, w = r1 - r0, c1 - c0
        out[r0:r0 + h, c0:c0 + w] = tile[tr0:tr0 + h, tc0:tc0 + w]
    return out


def _downsample(a: np.ndarray, k: int) -> np.ndarray:
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    return a[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def _grid_record(gid: str, layer: str, rel_path: str, bbox, arr) -> dict:
    rec = schema.base_record("grid", URL_T.split("{")[0], LICENSE, "K")
    rec.update({
        "id": gid, "layer": layer, "path": rel_path,
        "lat_min": bbox[0], "lon_min": bbox[1],
        "lat_max": bbox[2], "lon_max": bbox[3],
        "rows": int(arr.shape[0]), "cols": int(arr.shape[1]), "unit": "m",
        "min_v": float(arr.min()), "max_v": float(arr.max()),
    })
    return rec


def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    region = regions.REGIONS["bayarea"]
    cache: dict[tuple[int, int], np.ndarray] = {}

    def tile_of(lat0, lon0):
        if (lat0, lon0) not in cache:
            cache[(lat0, lon0)] = _load_tile(_fetch_tile(ctx, lat0, lon0))
        return cache[(lat0, lon0)]

    # 1. тайлы региона (каждый — чанк, докачиваемо)
    for lat0, lon0 in _tiles_for(region.bbox):
        la, lo = _tile_name(lat0, lon0)
        chunk = f"tile_{la}_{lo}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(60)
        path = _fetch_tile(ctx, lat0, lon0)
        man.mark_chunk(NAME, chunk, rows=0,
                       note="океан" if path is None else "скачан")

    records = []

    # 2. обзор региона ~90 м
    chunk = "region_overview"
    rel_npz = os.path.join(NAME, "region_overview.npz")
    if not man.chunk_done(NAME, chunk):
        ctx.check(120)
        full = crop_mosaic(region.bbox, tile_of)
        over = _downsample(full, OVER_DS).astype(np.float32)
        del full
        np.savez_compressed(os.path.join(out_dir, "region_overview.npz"),
                            elev=over,
                            meta=json.dumps({"bbox": region.bbox,
                                             "res_deg": OVER_DS / N}))
        rec = _grid_record("dem:region:bayarea", "elevation_overview",
                           rel_npz, region.bbox, over)
        shard = common.write_one_shard("grid", [rec], out_dir, "grid_overview.parquet")
        man.mark_chunk(NAME, chunk, rows=1, files=[shard])
        del over

    # 3. полные вырезы под сцены
    for key, sc in regions.SCENES.items():
        chunk = f"scene_{key}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(60)
        arr = crop_mosaic(sc.bbox, tile_of).astype(np.float32)
        fname = f"scene_{key}.npz"
        np.savez_compressed(os.path.join(out_dir, fname), elev=arr,
                            meta=json.dumps({"bbox": sc.bbox,
                                             "res_deg": 1.0 / N}))
        rec = _grid_record(f"dem:scene:{key}", "elevation",
                           os.path.join(NAME, fname), sc.bbox, arr)
        shard = common.write_one_shard("grid", [rec], out_dir,
                                       f"grid_scene_{key}.parquet")
        man.mark_chunk(NAME, chunk, rows=1, files=[shard])

    return {"status": "done",
            "note": f"тайлов {len(_tiles_for(region.bbox))}, сцен {len(regions.SCENES)}"}
