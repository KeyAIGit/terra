# Аэрофотоснимок города: NAIP (0.6 м/пиксель) через мозаичные тайлы
# Microsoft Planetary Computer. Без ключей и без SAS-токена — сервис
# подписывает запросы сам; из зависимостей только requests и Pillow.
#
# Съёмка NAIP — работа Министерства сельского хозяйства США (Farm Service
# Agency), общественное достояние; атрибуция обязательна из вежливости.
#
# Тайлы приходят в проекции Web Mercator (EPSG:3857) — обозреватель считает
# UV с поправкой Меркатора, иначе фотография сползёт относительно рельефа.

from __future__ import annotations

import io
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor

from twin import regions, schema
from twin.sources import common

NAME = "imagery"
TITLE = "NAIP — аэрофотосъёмка 0.6 м для сцен"
LICENSE = "Public Domain (USDA Farm Service Agency, NAIP)"
API = "https://planetarycomputer.microsoft.com/api/data/v1"
STAC_COLL = "naip"
YEAR_FROM, YEAR_TO = "2020-01-01T00:00:00Z", "2026-12-31T23:59:59Z"
ZOOM = 16                 # ~1.9 м/пиксель по сцене; дальше уменьшаем
OUT_WIDTH = 4096          # ширина итогового снимка
JPEG_Q = 86
WORKERS = 12
TILE = 256


def _lon2x(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * (1 << z)


def _lat2y(lat: float, z: int) -> float:
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * (1 << z)


def _register(ctx, bbox) -> str:
    """Мозаика по снимкам нужных лет; id — хеш запроса, повтор идемпотентен."""
    r = ctx.session.post(f"{API}/mosaic/register", json={
        "collections": [STAC_COLL],
        "bbox": [bbox[1], bbox[0], bbox[3], bbox[2]],
        "datetime": f"{YEAR_FROM}/{YEAR_TO}",
    }, timeout=90)
    r.raise_for_status()
    return r.json()["searchid"]


def _fetch_mosaic(ctx, bbox, zoom: int):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    sid = _register(ctx, bbox)
    lat_min, lon_min, lat_max, lon_max = bbox
    x0, x1 = math.floor(_lon2x(lon_min, zoom)), math.ceil(_lon2x(lon_max, zoom))
    y0, y1 = math.floor(_lat2y(lat_max, zoom)), math.ceil(_lat2y(lat_min, zoom))
    tiles = [(x, y) for x in range(x0, x1) for y in range(y0, y1)]
    url = (f"{API}/mosaic/tiles/{sid}/{{z}}/{{x}}/{{y}}.jpg"
           "?collection=naip&assets=image&asset_bidx=image%7C1,2,3")

    def one(t):
        x, y = t
        for attempt in range(3):
            try:
                r = ctx.session.get(url.format(z=zoom, x=x, y=y), timeout=90)
                if r.status_code == 200:
                    return x, y, r.content
                if r.status_code in (404, 204):
                    return x, y, None
            except Exception:
                pass
        return x, y, None

    canvas = Image.new("RGB", ((x1 - x0) * TILE, (y1 - y0) * TILE), (28, 34, 40))
    got = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for x, y, body in ex.map(one, tiles):
            if not body:
                continue
            canvas.paste(Image.open(io.BytesIO(body)).convert("RGB"),
                         ((x - x0) * TILE, (y - y0) * TILE))
            got += 1

    box = (round((_lon2x(lon_min, zoom) - x0) * TILE),
           round((_lat2y(lat_max, zoom) - y0) * TILE),
           round((_lon2x(lon_max, zoom) - x0) * TILE),
           round((_lat2y(lat_min, zoom) - y0) * TILE))
    crop = canvas.crop(box)
    if crop.width > OUT_WIDTH:
        h = round(OUT_WIDTH * crop.height / crop.width)
        crop = crop.resize((OUT_WIDTH, h), Image.LANCZOS)
    return crop, got, len(tiles)


def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    notes = []
    for key, sc in regions.SCENES.items():
        chunk = f"naip_{key}_z{ZOOM}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(240)
        img, got, total = _fetch_mosaic(ctx, sc.bbox, ZOOM)
        if got == 0:
            return {"status": "failed", "note": f"мозаика {key}: ни одного тайла"}
        fname = f"naip_{key}.jpg"
        path = os.path.join(out_dir, fname)
        img.save(path, "JPEG", quality=JPEG_Q, optimize=True)

        rec = schema.base_record("grid", f"{API}/mosaic", LICENSE, "K")
        rec.update({
            "id": f"naip:{key}", "layer": "aerial", "path": os.path.join(NAME, fname),
            "lat_min": sc.bbox[0], "lon_min": sc.bbox[1],
            "lat_max": sc.bbox[2], "lon_max": sc.bbox[3],
            "rows": img.height, "cols": img.width, "unit": "rgb",
            "min_v": 0.0, "max_v": 255.0,
            "note": json.dumps({"zoom": ZOOM, "tiles": f"{got}/{total}",
                                "crs": "EPSG:3857"}, ensure_ascii=False),
        })
        shard = common.write_one_shard("grid", [rec], out_dir,
                                       f"grid_naip_{key}.parquet")
        man.mark_chunk(NAME, chunk, rows=1, files=[shard],
                       note=f"{img.width}×{img.height}, тайлов {got}/{total}")
        notes.append(f"{key}: {img.width}×{img.height} из {got}/{total} тайлов, "
                     f"{os.path.getsize(path)/1e6:.1f} МБ")
    return {"status": "done", "note": "; ".join(notes) or "уже собрано"}
