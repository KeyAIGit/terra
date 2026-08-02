# Метрополитен-музей (Met Open Access): метаданные ~490 тыс. объектов, CC0.
# CSV лежит в Git LFS, поэтому качаем через media.githubusercontent.com
# (raw.githubusercontent отдаёт только LFS-указатель на 134 байта).
#
# ТОЛЬКО метаданные, без картинок. Прямых URL изображений в CSV нет —
# честно даём link (страница объекта) и api_url (public API, поле
# primaryImage там). Ярус K, лицензия CC0-1.0.
#
# Резюмируемость: CSV читается pandas-чанками по 60 тыс. строк; каждый чанк
# -> именованный шард artifact_NNNN.parquet, факт записи — в манифесте.
# Прерванный прогон переигрывает только парсинг (секунды), не запись.

from __future__ import annotations

import os

import pandas as pd

from atlas import schema
from atlas.sources import common

NAME = "met"
TITLE = "The Metropolitan Museum of Art Open Access"
LICENSE = "CC0-1.0"
CSV_URL = ("https://media.githubusercontent.com/media/metmuseum/openaccess/"
           "master/MetObjects.csv")
CHUNK_ROWS = 60_000

# Колонки CSV -> наши имена (латиницей, snake_case).
KEEP = {
    "Object ID": "object_id",
    "Object Number": "accession_number",
    "Is Public Domain": "is_public_domain",
    "Is Highlight": "is_highlight",
    "Department": "department",
    "Object Name": "object_name",
    "Title": "title",
    "Culture": "culture",
    "Period": "period",
    "Dynasty": "dynasty",
    "Reign": "reign",
    "Object Date": "date_text",
    "Object Begin Date": "year_start",
    "Object End Date": "year_end",
    "Medium": "medium",
    "Classification": "classification",
    "Country": "country",
    "Region": "region",
    "Excavation": "excavation",
    "Link Resource": "link",
    "Artist Display Name": "artist",
    "Object Wikidata URL": "wikidata_url",
}


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    raw = common.raw_path(NAME, "MetObjects.csv")

    done_all = man.chunk_done(NAME, "all_shards")
    if not done_all:
        ctx.check(60)
        common.download(ctx, CSV_URL, raw)  # ~318 МБ, докачивается Range'ом
        ctx.check(45)

        reader = pd.read_csv(
            raw, dtype=str, chunksize=CHUNK_ROWS, keep_default_na=False,
            on_bad_lines="skip", low_memory=True, engine="c")
        total = 0
        for i, df in enumerate(reader):
            chunk_id = f"shard_{i:04d}"
            total += len(df)
            if man.chunk_done(NAME, chunk_id):
                continue  # уже записан прошлым прогоном
            ctx.check(30)
            records = []
            for row in df.itertuples(index=False):
                d = dict(zip(df.columns, row))
                oid = d.get("Object ID") or ""
                if not oid.strip().isdigit():
                    continue  # битая строка
                rec = schema.base_record(
                    "artifact",
                    d.get("Link Resource")
                    or f"https://www.metmuseum.org/art/collection/search/{oid}",
                    LICENSE, "K")
                for src_col, name in KEEP.items():
                    v = d.get(src_col, "")
                    v = v.strip() if isinstance(v, str) else v
                    rec[name] = v if v != "" else None
                rec["id"] = f"met:{oid.strip()}"
                rec["title"] = rec.get("title") or rec.get("object_name") or f"met:{oid}"
                rec["year_start"] = common.to_int(rec.get("year_start"))
                rec["year_end"] = common.to_int(rec.get("year_end"))
                rec["is_public_domain"] = (d.get("Is Public Domain") == "True")
                rec["is_highlight"] = (d.get("Is Highlight") == "True")
                # прямого image url в CSV нет; primaryImage отдаёт этот API
                rec["api_url"] = ("https://collectionapi.metmuseum.org/"
                                  f"public/collection/v1/objects/{oid.strip()}")
                records.append(rec)
            if not records:
                man.mark_chunk(NAME, chunk_id, rows=0)
                continue
            rel = common.write_one_shard("artifact", records, out_dir,
                                         f"artifact_{i:04d}.parquet")
            man.mark_chunk(NAME, chunk_id, rows=len(records), files=[rel])
            print(f"    met: шард {i:04d} ({len(records)} объектов)")
        # rows=0: метка завершения, строки уже посчитаны пошардово
        man.mark_chunk(NAME, "all_shards", rows=0, note=f"всего строк CSV: {total}")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, "https://github.com/metmuseum/openaccess", LICENSE,
            TITLE,
            "Метаданные объектов Met (CC0): датировки begin/end year, культура, "
            "материал, классификация; image URL — через api_url (primaryImage).")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)  # 318 МБ сырья больше не нужны
    return {"status": "done", "note": "только метаданные, без картинок"}
