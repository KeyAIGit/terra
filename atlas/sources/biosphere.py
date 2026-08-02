# Живое: кто вообще населяет эту планету и где.
#
# Человек 12 000 до н. э. живёт не «в биоме», а среди конкретных зверей,
# птиц, рыб и трав: одних он ест, другими лечится, третьих боится, четвёртых
# приручит через пять тысяч лет. Чтобы сцены и хозяйство были нашими, а не
# похожими, нужен настоящий список видов и настоящая карта их местообитаний.
#
# Слои:
#   taxa       — таксономический костяк GBIF: принятые виды с царством, типом,
#                классом, отрядом и семейством (кто вообще есть на Земле);
#   ecoregions — RESOLVE Ecoregions 2017: 846 экорегионов и 14 биомов,
#                полигоны с площадью и охранным статусом (где что живёт).
#
# Ярусы: taxa — K (номенклатура), ecoregions — K (карта, сведённая экспертами).
# Дальше по плану: ареалы отдельных видов (PHYLACINE — «естественные» ареалы
# млекопитающих без человека, ровно наш случай) и археозоология по стоянкам.

from __future__ import annotations

import gzip
import io
import json
import os
import zipfile

from atlas import schema
from atlas.sources import common

NAME = "biosphere"
TITLE = "Life on Earth: GBIF backbone taxa + RESOLVE Ecoregions 2017"
LICENSE = "CC-BY-4.0 (GBIF backbone), CC-BY-4.0 (RESOLVE Ecoregions 2017)"
HOME = "https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"

GBIF_URL = "https://hosted-datasets.gbif.org/datasets/backbone/current/simple.txt.gz"
GBIF_SRC = "GBIF Secretariat: GBIF Backbone Taxonomy (Checklist dataset)"
GBIF_LIC = "CC-BY-4.0"

ECO_URL = "https://storage.googleapis.com/teow2016/Ecoregions2017.zip"
ECO_SRC = ("Dinerstein et al. 2017, BioScience 67(6): «An Ecoregion-Based Approach "
           "to Protecting Half the Terrestrial Realm» (RESOLVE Ecoregions 2017)")
ECO_LIC = "CC-BY-4.0"

# Колонки simple.txt (backbone GBIF, tab-separated, без заголовка), 30 штук:
# id, parent_key, basionym_key, is_synonym, status, rank, nom_status,
# constituent_key, origin, source_taxon_key, kingdom_key, phylum_key,
# class_key, order_key, family_key, genus_key, species_key, name_id,
# scientific_name, canonical_name, genus_or_above, specific_epithet, …
# ВАЖНО: вышестоящие таксоны здесь — КЛЮЧИ, а не имена; имена приходится
# собирать первым проходом по тому же файлу.
_C_ID, _C_STATUS, _C_RANK = 0, 4, 5
_C_KINGDOM, _C_PHYLUM, _C_CLASS = 10, 11, 12
_C_ORDER, _C_FAMILY, _C_GENUS = 13, 14, 15
_C_SCIENTIFIC, _C_CANONICAL = 18, 19
_HIGHER_RANKS = {"KINGDOM", "PHYLUM", "CLASS", "ORDER", "FAMILY", "GENUS"}

# Что нам вообще интересно: то, с чем человек сталкивается.
_KINGDOMS = {"Animalia", "Plantae", "Fungi"}
# Классы, которые важны для сцен и хозяйства (остальное — по требованию)
_KEEP_CLASSES = {
    "Mammalia", "Aves", "Reptilia", "Amphibia", "Insecta", "Arachnida",
    "Actinopterygii", "Chondrichthyes", "Bivalvia", "Gastropoda", "Malacostraca",
    "Magnoliopsida", "Liliopsida", "Pinopsida", "Polypodiopsida", "Agaricomycetes",
}


def _taxa_chunk(ctx, man, out_dir) -> None:
    """Костяк видов. Потоково: файл 0.5 ГБ не разворачиваем в память."""
    if man.chunk_done(NAME, "taxa"):
        return
    ctx.check(300)
    path = common.download(ctx, GBIF_URL, common.raw_path(NAME, "simple.txt.gz"))
    recs: list[dict] = []
    shard = 0
    files: list[str] = []
    total = 0
    today = schema.today()

    def flush():
        nonlocal recs, shard, total
        if not recs:
            return
        p = common.write_one_shard("taxon", recs, out_dir,
                                   f"taxa_{shard:04d}.parquet")
        files.append(p)
        total += len(recs)
        shard += 1
        recs = []

    # проход 1: имена вышестоящих таксонов по их ключам
    names: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) < 20 or c[_C_RANK] not in _HIGHER_RANKS:
                continue
            if c[_C_STATUS] != "ACCEPTED":
                continue
            nm = c[_C_CANONICAL] or c[_C_SCIENTIFIC]
            if nm and nm != "\\N":
                names[c[_C_ID]] = nm
    ctx.check(120)
    print(f"    biosphere: имён вышестоящих таксонов {len(names)}")

    def nm(key: str):
        return names.get(key) if key and key != "\\N" else None

    # проход 2: сами виды с разрешёнными именами
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) < 20:
                continue
            if c[_C_STATUS] != "ACCEPTED" or c[_C_RANK] != "SPECIES":
                continue
            kingdom = nm(c[_C_KINGDOM])
            if kingdom not in _KINGDOMS:
                continue
            klass = nm(c[_C_CLASS])
            if klass and klass not in _KEEP_CLASSES:
                continue
            name = c[_C_CANONICAL] or c[_C_SCIENTIFIC]
            if not name or name == "\\N":
                continue
            recs.append({
                "source": GBIF_SRC, "license": GBIF_LIC, "tier": "K",
                "retrieved": today,
                "id": f"gbif:{c[_C_ID]}", "name": name, "rank": "species",
                "kingdom": kingdom, "phylum": nm(c[_C_PHYLUM]),
                "class": klass, "order": nm(c[_C_ORDER]),
                "family": nm(c[_C_FAMILY]), "genus": nm(c[_C_GENUS]),
                "scientific_name": (c[_C_SCIENTIFIC]
                                    if c[_C_SCIENTIFIC] != "\\N" else None),
            })
            if len(recs) >= 400_000:
                flush()
                ctx.check(60)
    flush()
    man.mark_chunk(NAME, "taxa", rows=total, files=files,
                   note="принятые виды GBIF: звери, птицы, рыбы, насекомые, растения, грибы")
    print(f"    biosphere: видов {total}")
    common.drop_raw(NAME)


def _ecoregions_chunk(ctx, man, out_dir) -> None:
    """846 экорегионов и 14 биомов — карта того, где какая жизнь."""
    if man.chunk_done(NAME, "ecoregions"):
        return
    ctx.check(200)
    import shapefile        # pyshp

    zpath = common.download(ctx, ECO_URL, common.raw_path(NAME, "eco.zip"))
    ex = common.raw_path(NAME, "eco")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(ex)
    shp = None
    for root, _, fs in os.walk(ex):
        for fn in fs:
            if fn.lower().endswith(".shp"):
                shp = os.path.join(root, fn)
    if shp is None:
        man.mark_chunk(NAME, "ecoregions", rows=0, note="в архиве нет .shp")
        return

    # dbf экорегионов — в latin-1 («Alto Paraná»), не в utf-8
    r = shapefile.Reader(shp, encoding="latin-1", encodingErrors="replace")
    fields = [f[0] for f in r.fields[1:]]
    recs = []
    today = schema.today()
    for sr in r.iterShapeRecords():
        d = dict(zip(fields, sr.record))
        bbox = list(sr.shape.bbox) if sr.shape.bbox else [None] * 4
        lon = (bbox[0] + bbox[2]) / 2 if bbox[0] is not None else None
        lat = (bbox[1] + bbox[3]) / 2 if bbox[1] is not None else None
        rec = schema.base_record("place", ECO_SRC, ECO_LIC, "K")
        rec.update({
            "id": f"eco:{d.get('ECO_ID')}",
            "name": str(d.get("ECO_NAME") or "?"),
            "lat": lat, "lon": lon,
            "kind_of": "ecoregion",
            "biome": str(d.get("BIOME_NAME") or ""),
            "biome_num": common.to_float(d.get("BIOME_NUM")),
            "realm": str(d.get("REALM") or ""),
            "area_km2": common.to_float(d.get("SHAPE_AREA")),
            "nnh": common.to_float(d.get("NNH")),       # статус сохранности
            "bbox": json.dumps([round(float(b), 4) for b in bbox]
                               if bbox[0] is not None else []),
            "n_parts": len(sr.shape.parts),
        })
        recs.append(rec)
    p = common.write_one_shard("place", recs, out_dir, "ecoregions_0000.parquet")
    man.mark_chunk(NAME, "ecoregions", rows=len(recs), files=[p],
                   note="RESOLVE Ecoregions 2017: экорегион, биом, царство жизни, площадь")
    print(f"    biosphere: экорегионов {len(recs)}")
    common.drop_raw(NAME)


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    _ecoregions_chunk(ctx, man, out_dir)     # лёгкое и сразу полезное
    _taxa_chunk(ctx, man, out_dir)           # тяжёлое, режется на шарды

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, HOME, LICENSE, TITLE,
            "Живое на планете: принятые виды таксономического костяка GBIF "
            "(звери, птицы, рептилии, рыбы, насекомые, растения, грибы) и карта "
            "экорегионов RESOLVE 2017 (846 экорегионов, 14 биомов). Нужно для "
            "охоты, собирательства, одомашнивания и наполнения сцен.", tier="K")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "виды GBIF + экорегионы RESOLVE"}
