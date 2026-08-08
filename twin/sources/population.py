# Население кварталов: TIGER/Line TABBLOCK20 — границы переписных блоков
# с полем POP20 (людей по переписи 2020) и HOUSING20 (жилых единиц).
# Без ключа: API переписи с 2026 года требует регистрации, а шейп-файл — нет.
#
# Это АГРЕГАТЫ по кварталам, а не люди. Отдельные жители появляются позже
# (twin/people.py) как выборка из этих распределений: ни один синтетический
# житель не соответствует живому человеку, и соответствовать не должен.

from __future__ import annotations

import json
import os
import zipfile

from twin import regions, schema
from twin.sources import common

NAME = "population"
TITLE = "Переписные блоки с населением (TIGER TABBLOCK20)"
LICENSE = "Public Domain (US Census Bureau)"
URL = ("https://www2.census.gov/geo/tiger/TIGER2024/TABBLOCK20/"
       "tl_2024_06_tabblock20.zip")          # 06 = Калифорния


def fetch(ctx) -> dict:
    import shapefile  # pyshp

    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    region = regions.REGIONS["bayarea"]
    chunk = "bayarea_blocks"
    if man.chunk_done(NAME, chunk):
        return {"status": "done", "note": "уже собрано"}

    zpath = common.raw_path(NAME, "tabblock20_ca.zip")
    common.download(ctx, URL, zpath, timeout=180)

    paths = {}
    with zipfile.ZipFile(zpath) as z:
        for suffix in (".shp", ".dbf", ".shx"):
            member = common.zip_member(zpath, suffix)
            dest = common.raw_path(NAME, f"blocks{suffix}")
            with z.open(member) as f, open(dest, "wb") as g:
                g.write(f.read())
            paths[suffix] = dest

    want_counties = {f[2:] for f in region.counties_fips}   # без кода штата
    sf = shapefile.Reader(paths[".shp"])
    fields = [f[0] for f in sf.fields[1:]]
    records, n_people = [], 0
    for sr in sf.iterShapeRecords():
        d = dict(zip(fields, sr.record))
        if str(d.get("COUNTYFP20")) not in want_counties:
            continue
        pop = common.to_int(d.get("POP20")) or 0
        if pop <= 0:
            continue          # пустые кварталы: вода, парки, развязки
        gj = sr.shape.__geo_interface__
        rings = (gj["coordinates"] if gj["type"] == "Polygon"
                 else [r for poly in gj["coordinates"] for r in poly])
        pts = [p for ring in rings for p in ring]
        if not pts:
            continue
        las = [p[1] for p in pts]; los = [p[0] for p in pts]
        rec = schema.base_record("feature", URL, LICENSE, "K")
        rec.update({
            "id": f"blk:{d.get('GEOID20')}",
            "fclass": "census_block", "scene": None, "subclass": "block",
            "name": None,
            "geometry": json.dumps(gj),
            "lat": sum(las) / len(las), "lon": sum(los) / len(los),
            "lat_min": min(las), "lon_min": min(los),
            "lat_max": max(las), "lon_max": max(los),
            "tags_json": json.dumps({
                "pop20": pop,
                "housing20": common.to_int(d.get("HOUSING20")) or 0,
                "county": str(d.get("COUNTYFP20")),
                "aland": common.to_int(d.get("ALAND20")) or 0,
            }, ensure_ascii=False, sort_keys=True),
        })
        records.append(rec)
        n_people += pop

    if not records:
        return {"status": "failed", "note": "ни одного населённого квартала"}
    records.sort(key=lambda r: r["id"])
    shard = common.write_one_shard("feature", records, out_dir, "blocks.parquet")
    man.mark_chunk(NAME, chunk, rows=len(records), files=[shard])
    _drop_raw()
    return {"status": "done",
            "note": f"{len(records)} кварталов, {n_people:,} человек".replace(",", " ")}


def _drop_raw() -> None:
    import shutil
    d = os.path.join(common.RAW_DIR, NAME)
    if os.path.isdir(d):
        shutil.rmtree(d)
