# HYDE 3.3 — модельные сетки населения и землепользования 10000 до н.э.–2023.
#
# Разведка (2026-08-02): исходный dataportaal.pbl.nl отвечает 302-редиректом
# на лендинг; РАБОЧЕЕ зеркало — Yoda-хранилище Утрехтского университета:
#   https://geo.public.data.uu.nl/vault-hyde/HYDE%203.3%5B1701183392%5D/
#     original/hyde33_c7_base_mrt2023/zip/<СРЕЗ>.zip
# (лендинг с DOI: https://public.yoda.uu.nl/geo/UU01/AEZZIT.html)
#
# Полный слой popc: все *_pop.zip срезы (10000BC..2023AD) -> Parquet-гриды
# (lon, lat, value) по popc (число людей на ячейку 5'); нулевые/NODATA опущены.
# Каждый срез — отдельный чанк slice_<файл> в манифесте: обрыв по бюджету
# продолжается с места (`--source hyde`). lu-срезы (землепользование) остаются
# в pending_urls до отдельного захода. Лицензия CC-BY-4.0.
# Ярус R: HYDE — модельная реконструкция, а не прямое наблюдение.

from __future__ import annotations

import os
import zipfile

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from atlas import schema
from atlas.sources import common
from atlas.state import DATA_DIR

NAME = "hyde"
TITLE = "HYDE 3.3 population grids (test slice 2000BC)"
LICENSE = "CC-BY-4.0"
DOI_PAGE = "https://public.yoda.uu.nl/geo/UU01/AEZZIT.html"
BASE = ("https://geo.public.data.uu.nl/vault-hyde/HYDE%203.3%5B1701183392%5D/"
        "original/hyde33_c7_base_mrt2023/zip/")
TEST_SLICE = "2000BC_pop.zip"
TEST_YEAR = -2000


def _slice_year(fname: str) -> int:
    """'10000BC_pop.zip' -> -10000; '0AD_pop.zip' -> 0; '2023AD_pop.zip' -> 2023."""
    base = fname.split("_", 1)[0]
    if base.endswith("BC"):
        return -int(base[:-2])
    if base.endswith("AD"):
        return int(base[:-2])
    raise ValueError(f"не разобран год среза: {fname}")


def _asc_to_grid(path: str):
    """ESRI ASCII grid -> (lon[], lat[], value[]) только ненулевых ячеек."""
    hdr = {}
    with open(path, "r") as f:
        for _ in range(6):
            k, v = f.readline().split()
            hdr[k.lower()] = float(v)
    ncols, nrows = int(hdr["ncols"]), int(hdr["nrows"])
    cell = hdr["cellsize"]
    x0 = hdr.get("xllcorner", -180.0)
    y0 = hdr.get("yllcorner", -90.0)
    nodata = hdr.get("nodata_value", -9999.0)
    arr = np.loadtxt(path, skiprows=6, dtype=np.float32)
    assert arr.shape == (nrows, ncols), f"форма {arr.shape} != {(nrows, ncols)}"
    mask = (arr != np.float32(nodata)) & (arr > 0)
    rr, cc = np.nonzero(mask)
    # центры ячеек; строка 0 ASC — верхняя (север)
    lon = (x0 + (cc + 0.5) * cell).astype(np.float64)
    lat = (y0 + (nrows - rr - 0.5) * cell).astype(np.float64)
    return lon, lat, arr[mask]


def _write_grid(out_dir: str, layer: str, year: int, lon, lat, val,
                src_url: str) -> str:
    """Грид -> parquet одной таблицей (константные колонки — словарно)."""
    n = len(val)
    tbl = pa.table({
        "layer": pa.array([layer] * n).dictionary_encode(),
        "year": pa.array(np.full(n, year, dtype=np.int32)),
        "lon": pa.array(lon),
        "lat": pa.array(lat),
        "value": pa.array(val),
        "source": pa.array([src_url] * n).dictionary_encode(),
        "license": pa.array([LICENSE] * n).dictionary_encode(),
        "tier": pa.array(["R"] * n).dictionary_encode(),
        "retrieved": pa.array([schema.today()] * n).dictionary_encode(),
    })
    meta = dict(tbl.schema.metadata or {})
    meta[schema.META_KIND_KEY] = b"grid_layer"
    meta[b"grid_cellsize_deg"] = b"0.0833333 (5 arcmin); omitted cells = 0/nodata"
    tbl = tbl.replace_schema_metadata(meta)
    fname = f"grid_{layer}_{'m' if year < 0 else ''}{abs(year)}.parquet"
    full = os.path.join(out_dir, fname)
    pq.write_table(tbl, full, compression="snappy")
    return os.path.relpath(full, DATA_DIR)


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    if not man.chunk_done(NAME, "test_slice"):
        ctx.check(90)
        url = BASE + TEST_SLICE
        zpath = common.download(ctx, url, common.raw_path(NAME, TEST_SLICE))
        ex_dir = common.raw_path(NAME, "asc")
        with zipfile.ZipFile(zpath) as z:
            z.extractall(ex_dir)
        # ищем popc_*.asc (population counts)
        asc = None
        for root, _, files in os.walk(ex_dir):
            for f in files:
                if f.lower().startswith("popc") and f.lower().endswith(".asc"):
                    asc = os.path.join(root, f)
        if asc is None:
            man.set_status(NAME, "failed", f"в {TEST_SLICE} нет popc_*.asc")
            return {"status": "failed", "note": "не найден popc в архиве"}
        ctx.check(60)
        lon, lat, val = _asc_to_grid(asc)
        rel = _write_grid(out_dir, "popc", TEST_YEAR, lon, lat, val, url)
        man.mark_chunk(NAME, "test_slice", rows=len(val), files=[rel],
                       note=os.path.basename(asc))
        print(f"    hyde: popc {TEST_YEAR} — {len(val)} населённых ячеек")

    # остальные срезы — в pending (URL-ы из листинга зеркала)
    if not man.chunk_done(NAME, "pending_urls"):
        ctx.check(30)
        pend = []
        try:
            import re
            html = ctx.session.get(BASE, timeout=40).text
            for m in re.finditer(r'href="([^"/]+\.zip)"', html):
                if m.group(1) != TEST_SLICE:
                    pend.append(BASE + m.group(1))
        except Exception as e:
            print(f"    hyde: листинг зеркала не прочитался: {str(e)[:80]}")
        man.set_pending_urls(NAME, sorted(pend))
        man.mark_chunk(NAME, "pending_urls", rows=0,  # метка, не данные
                       note=f"{len(pend)} срезов HYDE ждут закачки")
        print(f"    hyde: в pending {len(pend)} срезов")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, DOI_PAGE, LICENSE, TITLE,
            "Модельная сетка населения HYDE 3.3 (Utrecht Yoda mirror), 5 arcmin. "
            "Тестовый срез 2000 до н.э.: popc (людей на ячейку), нули опущены. "
            "Ярус R: модельная реконструкция.", tier="R")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    # --- полный слой popc: закачка отложенных *_pop.zip хронологически ---
    pend = man.src(NAME).get("pending_urls", [])
    pop_urls = sorted((u for u in pend if u.endswith("_pop.zip")),
                      key=lambda u: _slice_year(u.rsplit("/", 1)[1]))
    for url in pop_urls:
        fname = url.rsplit("/", 1)[1]
        if man.chunk_done(NAME, "slice_" + fname):
            continue
        ctx.check(120)  # скачать (~30-60 МБ) + распарсить грид
        year = _slice_year(fname)
        zpath = common.download(ctx, url, common.raw_path(NAME, fname))
        with zipfile.ZipFile(zpath) as z:
            member = None
            for n in z.namelist():
                b = os.path.basename(n).lower()
                if b.startswith("popc") and b.endswith(".asc"):
                    member = n
                    break
            if member is None:
                man.mark_chunk(NAME, "slice_" + fname, rows=0,
                               note="нет popc_*.asc — пропущен")
                common.drop_raw(NAME)
                continue
            ex_dir = common.raw_path(NAME, "asc")
            z.extract(member, ex_dir)
            asc = os.path.join(ex_dir, member)
        lon, lat, val = _asc_to_grid(asc)
        rel = _write_grid(out_dir, "popc", year, lon, lat, val, url)
        man.mark_chunk(NAME, "slice_" + fname, rows=len(val), files=[rel])
        common.drop_raw(NAME)
        print(f"    hyde: popc {year:+d} — {len(val)} населённых ячеек")

    common.drop_raw(NAME)
    n_done = 1 + sum(1 for u in pop_urls
                     if man.chunk_done(NAME, "slice_" + u.rsplit("/", 1)[1]))
    n_lu = sum(1 for u in pend if u.endswith("_lu.zip"))
    return {"status": "done",
            "note": f"popc {n_done}/{len(pop_urls) + 1} срезов; "
                    f"lu-срезы ({n_lu}) остаются в pending_urls"}
