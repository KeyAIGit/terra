# D-PLACE / Ethnographic Atlas (EA): ~1300 обществ со структурными
# переменными культуры (Murdock; коды EA001..EA11x).
# Источник: github.com/D-PLACE/dplace-data (raw), лицензия CC-BY-4.0. Ярус K.
#
# Два стола:
#   polity_snapshot (общества): id, имя, координаты, фокусный год, glottocode
#   polity_snapshot (значения): длинный формат soc_id x переменная -> код+расшифровка

from __future__ import annotations

import csv
import io

from atlas import schema
from atlas.sources import common

NAME = "dplace"
TITLE = "D-PLACE: Ethnographic Atlas societies and variables"
LICENSE = "CC-BY-4.0"
BASE = "https://raw.githubusercontent.com/D-PLACE/dplace-data/master/datasets/EA/"
HOME = "https://d-place.org/"


def _read_csv(ctx: common.Ctx, fname: str) -> list[dict]:
    raw = common.download(ctx, BASE + fname, common.raw_path(NAME, fname))
    with open(raw, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    if not man.chunk_done(NAME, "societies"):
        ctx.check(30)
        rows = _read_csv(ctx, "societies.csv")
        records = []
        for r in rows:
            rec = schema.base_record("polity_snapshot", HOME + "societies/" + r["id"],
                                     LICENSE, "K")
            rec.update({
                "polity_id": f"ea:{r['id']}",
                "polity_name": r.get("pref_name_for_society") or r["id"],
                "year": common.to_int(r.get("main_focal_year")) or 0,  # фокусный год
                "lat": common.to_float(r.get("Lat")),
                "lon": common.to_float(r.get("Long")),
                "glottocode": r.get("glottocode") or None,
                "alt_names": r.get("alt_names_by_society") or None,
                "hraf_id": r.get("HRAF_name_ID") or None,
            })
            records.append(rec)
        paths, n = common.write_shards("polity_snapshot", records, out_dir, "polity_snapshot_societies")
        man.mark_chunk(NAME, "societies", rows=n, files=paths)
        print(f"    dplace: {n} обществ EA")

    if not man.chunk_done(NAME, "values"):
        ctx.check(60)
        variables = {v["id"]: v for v in _read_csv(ctx, "variables.csv")}
        codes = {}  # (var_id, code) -> имя кода
        for c in _read_csv(ctx, "codes.csv"):
            codes[(c["var_id"], c["code"])] = c.get("name") or c.get("description")
        soc_year = {}  # фокусный год общества — год снапшота значений
        for s in _read_csv(ctx, "societies.csv"):
            soc_year[s["id"]] = common.to_int(s.get("main_focal_year"))
        records = []
        for r in _read_csv(ctx, "data.csv"):
            var = variables.get(r["var_id"], {})
            rec = schema.base_record(
                "polity_snapshot", HOME + "societies/" + r["soc_id"], LICENSE, "K")
            rec.update({
                "polity_id": f"ea:{r['soc_id']}",
                "polity_name": None,
                "year": common.to_int(r.get("year")) or soc_year.get(r["soc_id"]) or 0,
                "var_id": r["var_id"],
                "var_title": var.get("title") or None,
                "var_category": var.get("category") or None,
                "code": r.get("code") or None,
                "code_label": codes.get((r["var_id"], r.get("code"))) or None,
                "sub_case": r.get("sub_case") or None,
                "references": (r.get("references") or None),
            })
            records.append(rec)
        paths, n = common.write_shards("polity_snapshot", records, out_dir, "polity_snapshot_values")
        man.mark_chunk(NAME, "values", rows=n, files=paths)
        print(f"    dplace: {n} значений переменных EA")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, "https://github.com/D-PLACE/dplace-data", LICENSE, TITLE,
            "Общества Ethnographic Atlas (координаты, фокусный год) и длинный "
            "формат значений переменных EA с расшифровкой кодов.")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "EA societies + values"}
