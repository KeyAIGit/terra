# DataSF: контуры зданий Сан-Франциско с лидарными высотами (ynuv-fyni,
# 177 тыс.) + реестр оценщика (wv5m-vpq2) с годом постройки каждого участка.
# Всё — открытый Socrata SODA API без ключа, страницами по $limit/$offset.
#
# Годы постройки — «машина времени» твина: фильтр year_built <= X де-строит
# город в прошлое. Ключ связи: footprints.mblr ('SF'+mapblklot) <-> assessor.

from __future__ import annotations

import json

from twin import schema
from twin.sources import common

NAME = "sfbuildings"
TITLE = "DataSF — здания СФ с лидарными высотами и годами постройки"
LICENSE = "PDDL/ODC (DataSF Open Data)"

FOOT_URL = "https://data.sfgov.org/resource/ynuv-fyni.json"
ROLL_URL = "https://data.sfgov.org/resource/wv5m-vpq2.json"
PAGE = 20_000
FOOT_PAGES = 10          # 177k / 20k
ROLL_PAGES = 13          # ~220k+ участков свежего года
ROLL_YEAR = 2025         # свежий closed_roll_year (числовой в SODA)


def _page(ctx, url: str, params: dict) -> list[dict]:
    r = ctx.session.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def _foot_records(rows: list[dict]) -> list[dict]:
    out = []
    for d in rows:
        shape = d.get("shape")
        if not shape or shape.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        coords = shape["coordinates"]
        rings = coords[0] if shape["type"] == "MultiPolygon" else coords
        if not rings or len(rings[0]) < 4:
            continue
        outer = rings[0]
        las = [p[1] for p in outer]; los = [p[0] for p in outer]
        h = common.to_float(d.get("hgt_median_m"))
        if h is None:
            pk = common.to_float(d.get("peak_1st_m"))
            gn = common.to_float(d.get("gnd_min_m"))
            h = (pk - gn) if (pk is not None and gn is not None) else None
        rec = schema.base_record("feature", FOOT_URL, LICENSE, "K")
        rec.update({
            "id": f"sfbld:{d.get('sf16_bldgid')}",
            "fclass": "building",
            "scene": "sf",
            "subclass": "citylidar",
            "name": None,
            "geometry": json.dumps({"type": "Polygon", "coordinates": [outer]}),
            "lat": sum(las) / len(las), "lon": sum(los) / len(los),
            "lat_min": min(las), "lon_min": min(los),
            "lat_max": max(las), "lon_max": max(los),
            "tags_json": json.dumps({
                "mapblklot": (d.get("mblr") or "")[2:] or None,
                "gnd_min_m": common.to_float(d.get("gnd_min_m")),
            }, ensure_ascii=False),
            "height_m": round(h, 1) if h is not None else None,
            "height_src": "lidar" if h is not None else "none",
        })
        out.append(rec)
    return out


def _roll_records(rows: list[dict]) -> list[dict]:
    out = []
    for d in rows:
        blk = d.get("parcel_number")
        yb = common.to_int(d.get("year_property_built"))
        if not blk:
            continue
        if yb is not None and not (1770 <= yb <= 2026):
            yb = None
        rec = schema.base_record("obs", ROLL_URL, LICENSE, "K")
        rec.update({
            "id": f"roll:{blk}",
            "station": "assessor",
            "t": ROLL_YEAR,
            "var": "year_built",
            "value": float(yb) if yb is not None else 0.0,
            "unit": "year",
            "scene": "sf",
            "text": d.get("use_definition"),
        })
        out.append(rec)
    return out


def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    total = 0

    for i in range(FOOT_PAGES):
        chunk = f"foot_{i:02d}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(90)
        rows = _page(ctx, FOOT_URL, {
            "$select": "sf16_bldgid,mblr,gnd_min_m,hgt_median_m,peak_1st_m,shape",
            "$order": "sf16_bldgid", "$limit": PAGE, "$offset": i * PAGE})
        recs = _foot_records(rows)
        files = ([common.write_one_shard("feature", recs, out_dir,
                                         f"{chunk}.parquet")] if recs else [])
        man.mark_chunk(NAME, chunk, rows=len(recs), files=files)
        total += len(recs)
        if len(rows) < PAGE:
            break

    for i in range(ROLL_PAGES):
        chunk = f"roll_{i:02d}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(60)
        rows = _page(ctx, ROLL_URL, {
            "$select": "parcel_number,year_property_built,use_definition",
            "$where": f"closed_roll_year={ROLL_YEAR}",
            "$order": "parcel_number", "$limit": PAGE, "$offset": i * PAGE})
        recs = _roll_records(rows)
        # один участок может повториться — оставляем первую запись чанка
        seen, uniq = set(), []
        for r in recs:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            uniq.append(r)
        files = ([common.write_one_shard("obs", uniq, out_dir,
                                         f"{chunk}.parquet")] if uniq else [])
        man.mark_chunk(NAME, chunk, rows=len(uniq), files=files)
        total += len(uniq)
        if len(rows) < PAGE:
            break

    return {"status": "done", "note": f"+{total} записей DataSF"}
