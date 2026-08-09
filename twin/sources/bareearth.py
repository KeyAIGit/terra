# Голая земля: USGS 3DEP Bare Earth DEM. БЕЗ КЛЮЧА.
#
# Зачем, если рельеф уже есть. Copernicus GLO-30 — модель ПОВЕРХНОСТИ: она
# меряет то, от чего отразился радар, то есть крыши и кроны. В плотном центре
# города «земля» у неё поднята на высоту застройки, и здание, поставленное на
# такую отметку, взлетает на собственную крышу. В build.py против этого стоит
# костыль — минимум-фильтр 3×3. 3DEP отдаёт BARE EARTH: землю, из которой
# застройка уже вычтена, да ещё и с разрешением метра вместо тридцати.
#
# Сервис ArcGIS ImageServer отдаёт вырез любым размером до 2000×1600 за запрос
# (заявленный потолок 8000 не выдерживает: крупные вырезы отваливаются 500),
# поэтому сцену режем на плитки и сшиваем.

from __future__ import annotations

import json
import os

import numpy as np

from twin import regions, schema
from twin.sources import common

NAME = "bareearth"
TITLE = "USGS 3DEP — голая земля под городом"
LICENSE = "USGS 3DEP (общественное достояние)"

URL = ("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/"
       "ImageServer/exportImage")
TILE_W, TILE_H = 2000, 1600     # предел одного вырезa на практике
GRID_X, GRID_Y = 2, 2           # плиток по долготе и широте -> 4000×3200 на сцену
NODATA = -1e5                   # ниже этого — «данных нет»


def _fetch_tile(ctx, bbox) -> np.ndarray:
    """Один вырез голой земли; строка 0 — северный край."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    la0, lo0, la1, lo1 = bbox
    params = {
        "bbox": f"{lo0},{la0},{lo1},{la1}",
        "bboxSR": "4326", "imageSR": "4326",
        "size": f"{TILE_W},{TILE_H}",
        "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    r = ctx.session.get(URL, params=params, timeout=240)
    r.raise_for_status()
    if not r.content[:2] in (b"II", b"MM"):
        raise ValueError("3DEP вернул не TIFF: "
                         + r.content[:160].decode("utf-8", "replace"))
    import io
    a = np.asarray(Image.open(io.BytesIO(r.content)), dtype=np.float32)
    if a.shape != (TILE_H, TILE_W):
        raise ValueError(f"3DEP отдал {a.shape}, ждали {(TILE_H, TILE_W)}")
    return a


def _scene_grid(bbox):
    """Плитки сцены: (индекс, bbox). Режем ровно, без нахлёста."""
    la0, lo0, la1, lo1 = bbox
    dla = (la1 - la0) / GRID_Y
    dlo = (lo1 - lo0) / GRID_X
    out = []
    for iy in range(GRID_Y):          # 0 — северная полоса
        for ix in range(GRID_X):
            out.append(((iy, ix), (la1 - dla * (iy + 1), lo0 + dlo * ix,
                                   la1 - dla * iy, lo0 + dlo * (ix + 1))))
    return out


def _grid_record(gid: str, rel_path: str, bbox, arr) -> dict:
    rec = schema.base_record("grid", URL, LICENSE, "K")
    finite = arr[arr > NODATA]
    rec.update({
        "id": gid, "layer": "bare_earth", "path": rel_path,
        "lat_min": bbox[0], "lon_min": bbox[1],
        "lat_max": bbox[2], "lon_max": bbox[3],
        "rows": int(arr.shape[0]), "cols": int(arr.shape[1]), "unit": "m",
        "min_v": float(finite.min()) if finite.size else 0.0,
        "max_v": float(finite.max()) if finite.size else 0.0,
    })
    return rec


def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    made = []
    for key, sc in regions.SCENES.items():
        chunk = f"scene_{key}"
        if man.chunk_done(NAME, chunk):
            continue
        rows = TILE_H * GRID_Y
        cols = TILE_W * GRID_X
        full = np.full((rows, cols), NODATA, dtype=np.float32)
        for (iy, ix), bb in _scene_grid(sc.bbox):
            ctx.check(120)
            tile = _fetch_tile(ctx, bb)
            full[iy * TILE_H:(iy + 1) * TILE_H, ix * TILE_W:(ix + 1) * TILE_W] = tile

        # За городом 3DEP местами молчит; такие места — вода или вне съёмки.
        # Ставим ноль (уровень моря), а не оставляем дыру: иначе рельеф
        # провалится в бездну там, где просто нет лидара.
        gaps = int((full <= NODATA).sum())
        full[full <= NODATA] = 0.0

        path = os.path.join(out_dir, f"bare_{key}.npz")
        np.savez_compressed(
            path, elev=full.astype(np.float32),
            meta=json.dumps({"bbox": list(sc.bbox), "source": "USGS 3DEP",
                             "kind": "bare_earth", "gaps": gaps},
                            ensure_ascii=False))
        rec = _grid_record(f"bare:{key}", common.rel_data(path), sc.bbox, full)
        files = [common.write_one_shard("grid", [rec], out_dir,
                                        f"bare_{key}.parquet"),
                 common.rel_data(path)]
        man.mark_chunk(NAME, chunk, rows=1, files=files,
                       note=f"{rows}×{cols}, пропусков {gaps}")
        made.append(key)
    return {"status": "done",
            "note": f"голая земля собрана для сцен: {', '.join(made) or '—'}"}
