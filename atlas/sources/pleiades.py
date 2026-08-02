# Pleiades — газеттир античного мира (~42 тыс. мест с координатами).
# Берём официальный CSV-дамп (лёгкий, ~7 МБ gz) вместо полного JSON (135 МБ):
# в нём есть всё нужное — id, имя, типы, координаты, точность, периоды.
# Лицензия: CC-BY 3.0. Ярус: K (каждое место опирается на источники Pleiades).

from __future__ import annotations

import csv
import gzip

from atlas import schema
from atlas.sources import common

NAME = "pleiades"
TITLE = "Pleiades gazetteer of ancient places"
LICENSE = "CC-BY-3.0"
URL = "https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz"


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    if not man.chunk_done(NAME, "places"):
        ctx.check(30)
        raw = common.download(ctx, URL, common.raw_path(NAME, "places.csv.gz"))
        records = []
        with gzip.open(raw, "rt", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                lat = common.to_float(row.get("reprLat"))
                lon = common.to_float(row.get("reprLong"))
                rec = schema.base_record(
                    "place", f"https://pleiades.stoa.org{row.get('path', '')}",
                    LICENSE, "K")
                rec.update({
                    "id": f"pleiades:{row['id']}",
                    "name": row.get("title") or f"pleiades:{row['id']}",
                    "lat": lat,
                    "lon": lon,
                    "place_types": row.get("featureTypes") or None,   # через запятую
                    "year_start": common.to_int(row.get("minDate")),  # годы, минус = до н.э.
                    "year_end": common.to_int(row.get("maxDate")),
                    "periods": row.get("timePeriodsKeys") or None,
                    "precision": row.get("locationPrecision") or None,
                    "description": (row.get("description") or None),
                })
                records.append(rec)
        paths, n = common.write_shards("place", records, out_dir, "place")
        man.mark_chunk(NAME, "places", rows=n, files=paths)
        print(f"    pleiades: {n} мест -> {len(paths)} шардов")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, "https://pleiades.stoa.org/", LICENSE, TITLE,
            "Полный дамп мест античного мира: id, имя, типы, координаты, "
            "точность локализации, временные периоды (minDate/maxDate).")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "полный дамп мест"}
