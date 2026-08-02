# p3k14c — глобальная сводка радиоуглеродных дат (People 3000, Zenodo).
# Релиз 2025.07: https://doi.org/10.5281/zenodo.16394072 (zip с CSV).
# Каждая строка — лабораторная дата: прокси плотности заселения.
# Лицензия набора: CC-BY-4.0 (Bird et al. 2022, Scientific Data). Ярус: K.

from __future__ import annotations

import csv
import io
import zipfile

from atlas import schema
from atlas.sources import common

NAME = "p3k14c"
TITLE = "p3k14c: global archaeological radiocarbon dates"
LICENSE = "CC-BY-4.0"
DOI = "https://doi.org/10.5281/zenodo.16394072"
ZIP_URL = ("https://zenodo.org/api/records/16394072/files/"
           "people3k/p3k14c-2025.07.zip/content")


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    if not man.chunk_done(NAME, "dates"):
        ctx.check(60)
        raw = common.download(ctx, ZIP_URL, common.raw_path(NAME, "p3k14c.zip"))
        member = common.zip_member(raw, ".csv")  # самый крупный CSV = сами даты
        records = []
        with zipfile.ZipFile(raw) as z, z.open(member) as bf:
            tf = io.TextIOWrapper(bf, encoding="utf-8-sig", newline="")
            for row in csv.DictReader(tf):
                lat = common.to_float(row.get("Lat"))
                lon = common.to_float(row.get("Long"))
                rec = schema.base_record("event", DOI, LICENSE, "K")
                rec.update({
                    "id": f"p3k14c:{row.get('LabID', '').strip() or len(records)}",
                    "name": (row.get("SiteName") or "unknown site").strip(),
                    # калиброванного года нет в сводке; BP -> приблизительный
                    # календарный год: 1950 - age_bp (некалиброванно, честно помечаем)
                    "year_start": (1950 - common.to_int(row.get("Age"))
                                   if common.to_int(row.get("Age")) is not None else None),
                    "kind": "c14_date",
                    "lab_id": row.get("LabID"),
                    "age_bp": common.to_int(row.get("Age")),
                    "sd": common.to_int(row.get("Error")),
                    "lat": lat,
                    "lon": lon,
                    "site": row.get("SiteName") or None,
                    "country": row.get("Country") or None,
                    "continent": row.get("Continent") or None,
                    "material": row.get("Material") or None,
                    "method": row.get("Method") or None,
                    "note": "год = 1950 - age_bp, БЕЗ калибровки",
                })
                if rec["year_start"] is None:
                    rec["year_start"] = 0  # обязательное поле; страхуемся
                    rec["note"] = "нет возраста BP в источнике"
                records.append(rec)
        paths, n = common.write_shards("event", records, out_dir, "event")
        man.mark_chunk(NAME, "dates", rows=n, files=paths, note=member)
        print(f"    p3k14c: {n} радиоуглеродных дат -> {len(paths)} шардов")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, DOI, LICENSE, TITLE,
            "Радиоуглеродные даты (lab_id, age_bp, sd, координаты, памятник, "
            "страна) — прокси плотности заселения по эпохам.")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "релиз 2025.07"}
