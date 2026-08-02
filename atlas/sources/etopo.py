# Рельеф Земли: ETOPO 2022 (NOAA NCEI) — высоты суши и глубины океана.
#
# Это фундамент режима «настоящая Земля»: по нему строятся ландшафты UE,
# береговые линии, водоразделы и проходимость. Без реального рельефа любая
# «наша история» остаётся историей похожей планеты, а не нашей.
#
# Что берём:
#   surface 60" (1 угловая минута) — полный шар, ~112 МБ netCDF-4. Хранится
#     ЦЕЛИКОМ как исходный файл (его же кладём на HF) — это канонический вид.
#   grid_10m — производная сетка 10′ (2160×1080) в parquet: быстрый слой для
#     карт, климата и первых прикидок; 2.3 млн ячеек.
#   Более высокое разрешение (30″, 15″) — отдельными чанками по мере надобности:
#     30″ весит ~450 МБ, 15″ — 1.8 ГБ; ссылки лежат в pending_urls.
#
# Ярус K: это измерение (спутниковая альтиметрия + промеры + LiDAR),
# а не реконструкция. Лицензия: работа правительства США, общественное достояние.

from __future__ import annotations

import os

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from atlas import schema
from atlas.sources import common
from atlas.state import DATA_DIR

NAME = "etopo"
TITLE = "ETOPO 2022 global relief (surface elevation and bathymetry)"
LICENSE = "public-domain-gov (US Government work, NOAA NCEI)"
HOME = "https://www.ncei.noaa.gov/products/etopo-global-relief-model"
DOI = "https://doi.org/10.25921/fd45-gt74"

BASE = "https://www.ngdc.noaa.gov/thredds/fileServer/global/ETOPO2022/"
F60 = BASE + "60s/60s_surface_elev_netcdf/ETOPO_2022_v1_60s_N90W180_surface.nc"
PENDING = [
    BASE + "30s/30s_surface_elev_netcdf/ETOPO_2022_v1_30s_N90W180_surface.nc",
    BASE + "30s/30s_bed_elev_netcdf/ETOPO_2022_v1_30s_N90W180_bed.nc",
    BASE + "15s/15s_surface_elev_netcdf/ETOPO_2022_v1_15s_N90W180_surface.nc",
]


def _read_nc(path: str):
    """ETOPO netCDF-4 = HDF5; читаем без netCDF4, одним h5py."""
    import h5py
    with h5py.File(path, "r") as h:
        zname = "z" if "z" in h else next(
            k for k in h if getattr(h[k], "ndim", 0) == 2)
        z = h[zname]
        lat = np.asarray(h["lat"][:], dtype=np.float64)
        lon = np.asarray(h["lon"][:], dtype=np.float64)
        arr = np.asarray(z[:], dtype=np.float32)
    return lat, lon, arr


def _coarse_grid(lat, lon, arr, factor: int):
    """Огрубление усреднением блоками factor×factor (высоты — среднее)."""
    ny, nx = arr.shape
    ny2, nx2 = ny // factor, nx // factor
    a = arr[: ny2 * factor, : nx2 * factor].reshape(ny2, factor, nx2, factor)
    z = a.mean(axis=(1, 3))
    la = lat[: ny2 * factor].reshape(ny2, factor).mean(axis=1)
    lo = lon[: nx2 * factor].reshape(nx2, factor).mean(axis=1)
    return la, lo, z


def _write_grid(out_dir: str, layer: str, la, lo, z, src_url: str,
                fname: str) -> tuple[str, int]:
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    n = z.size
    tbl = pa.table({
        "layer": pa.array([layer] * n).dictionary_encode(),
        "year": pa.array(np.full(n, 2022, dtype=np.int32)),
        "lon": pa.array(LO.ravel().astype(np.float64)),
        "lat": pa.array(LA.ravel().astype(np.float64)),
        "value": pa.array(z.ravel().astype(np.float32)),
        "source": pa.array([src_url] * n).dictionary_encode(),
        "license": pa.array([LICENSE] * n).dictionary_encode(),
        "tier": pa.array(["K"] * n).dictionary_encode(),
        "retrieved": pa.array([schema.today()] * n).dictionary_encode(),
    })
    meta = dict(tbl.schema.metadata or {})
    meta[schema.META_KIND_KEY] = b"grid_layer"
    meta[b"units"] = b"metres above mean sea level (negative = below)"
    tbl = tbl.replace_schema_metadata(meta)
    full = os.path.join(out_dir, fname)
    pq.write_table(tbl, full, compression="zstd")
    return os.path.relpath(full, DATA_DIR), n


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    # 1) полный файл 60" — хранится как есть (канонический вид рельефа)
    keep = os.path.join(out_dir, "ETOPO_2022_v1_60s_surface.nc")
    if not man.chunk_done(NAME, "nc60"):
        ctx.check(240)
        if not os.path.exists(keep):
            tmp = common.download(ctx, F60, common.raw_path(NAME, "etopo60.nc"))
            os.replace(tmp, keep)
        mb = os.path.getsize(keep) / 1e6
        man.mark_chunk(NAME, "nc60", rows=0,
                       files=[os.path.relpath(keep, DATA_DIR)],
                       note=f"исходный netCDF 60″ ({mb:.0f} МБ), 21600×10800")
        print(f"    etopo: 60″ netCDF сохранён ({mb:.0f} МБ)")

    # 2) производные сетки для быстрой работы
    for tag, factor, fname in (("grid_10m", 10, "grid_elev_10m.parquet"),
                               ("grid_5m", 5, "grid_elev_5m.parquet")):
        if man.chunk_done(NAME, tag):
            continue
        ctx.check(150)
        lat, lon, arr = _read_nc(keep)
        la, lo, z = _coarse_grid(lat, lon, arr, factor)
        rel, n = _write_grid(out_dir, "elevation", la, lo, z, F60, fname)
        man.mark_chunk(NAME, tag, rows=n, files=[rel],
                       note=f"высота/глубина, шаг {factor}′, {z.shape[0]}×{z.shape[1]}")
        print(f"    etopo: {tag} — {n} ячеек ({z.shape[0]}×{z.shape[1]})")
        del arr, z

    if not man.chunk_done(NAME, "pending_urls"):
        man.set_pending_urls(NAME, PENDING)
        man.mark_chunk(NAME, "pending_urls", rows=0,
                       note="30″ (surface, bed) и 15″ — качать под конкретные сцены")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, DOI, LICENSE, TITLE,
            "ETOPO 2022 — глобальная модель рельефа NOAA: высоты суши и глубины "
            "океана в одной сетке (60″ целиком + производные 10′ и 5′). Основа "
            "режима «настоящая Земля»: береговые линии, водоразделы, проходимость, "
            "ландшафты для UE. Ярус K — измерение, не реконструкция.", tier="K")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "60″ целиком + сетки 10′ и 5′; 30″/15″ в pending"}
