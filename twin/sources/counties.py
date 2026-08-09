# Границы округов региона: Census Bureau cartographic boundary files
# (cb_2023, 1:500k) — без ключа. Фильтруем девять округов Залива по FIPS.
# Население ACS требует бесплатный ключ api.census.gov — до его появления
# кладём численность NULL и помечаем pending_urls.

from __future__ import annotations

import json
import os

from twin import regions, schema
from twin.sources import common

NAME = "counties"
TITLE = "Округа региона (Census cartographic boundaries cb_2023 500k)"
LICENSE = "Public Domain (US Census Bureau)"
URL = ("https://www2.census.gov/geo/tiger/GENZ2023/shp/"
       "cb_2023_us_county_500k.zip")
ACS_NOTE = ("население: https://api.census.gov/data/2023/acs/acs5"
            "?get=NAME,B01003_001E — требует бесплатный ключ")


def fetch(ctx) -> dict:
    import shapefile  # pyshp

    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    region = regions.REGIONS["bayarea"]
    chunk = "bayarea_counties"
    if man.chunk_done(NAME, chunk):
        return {"status": "done", "note": "уже собрано"}

    zpath = common.raw_path(NAME, "cb_2023_us_county_500k.zip")
    common.download(ctx, URL, zpath)

    import zipfile
    shp = common.raw_path(NAME, "counties.shp")
    dbf = common.raw_path(NAME, "counties.dbf")
    shx = common.raw_path(NAME, "counties.shx")
    with zipfile.ZipFile(zpath) as z:
        for suffix, dest in ((".shp", shp), (".dbf", dbf), (".shx", shx)):
            member = common.zip_member(zpath, suffix)
            with z.open(member) as f, open(dest, "wb") as g:
                g.write(f.read())

    sf = shapefile.Reader(shp)
    fields = [f[0] for f in sf.fields[1:]]
    want = set(region.counties_fips)
    records = []
    for sr in sf.iterShapeRecords():
        rec_d = dict(zip(fields, sr.record))
        fips = str(rec_d.get("STATEFP", "")) + str(rec_d.get("COUNTYFP", ""))
        if fips not in want:
            continue
        gj = sr.shape.__geo_interface__
        pts = [p for ring in _all_rings(gj) for p in ring]
        las = [p[1] for p in pts]; los = [p[0] for p in pts]
        rec = schema.base_record("feature", URL, LICENSE, "K")
        rec.update({
            "id": f"county:{fips}",
            "fclass": "county",
            "scene": None,
            "subclass": "county",
            "name": rec_d.get("NAME"),
            "geometry": json.dumps(gj),
            "lat": sum(las) / len(las), "lon": sum(los) / len(los),
            "lat_min": min(las), "lon_min": min(los),
            "lat_max": max(las), "lon_max": max(los),
            "tags_json": json.dumps({"fips": fips,
                                     "aland": rec_d.get("ALAND"),
                                     "population": None},
                                    ensure_ascii=False),
        })
        records.append(rec)
    if len(records) != len(want):
        return {"status": "failed",
                "note": f"найдено {len(records)} округов из {len(want)}"}

    shard = common.write_one_shard("feature", records, out_dir,
                                   "counties.parquet")
    man.mark_chunk(NAME, chunk, rows=len(records), files=[shard])
    man.set_pending_urls(NAME, [ACS_NOTE])
    common_drop_raw()
    return {"status": "done", "note": f"{len(records)} округов; {ACS_NOTE}"}


def _all_rings(gj: dict):
    if gj["type"] == "Polygon":
        return gj["coordinates"]
    if gj["type"] == "MultiPolygon":
        return [r for poly in gj["coordinates"] for r in poly]
    return []


def common_drop_raw() -> None:
    import shutil
    d = os.path.join(common.RAW_DIR, NAME)
    if os.path.isdir(d):
        shutil.rmtree(d)
