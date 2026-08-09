# Синтетические жители: город, населённый правдоподобными людьми.
#
#   python3 -m twin.people sf [--sample 4000]
#
# Ни один житель не соответствует живому человеку. Мы берём ИЗМЕРЕННОЕ
# население переписного квартала (ярус K), расселяем его по реальным зданиям
# соразмерно их жилому объёму, и наделяем каждого чертами, вытянутыми из
# ТИПИЧНЫХ для места распределений (ярус T). Сам житель — реконструкция
# (ярус R): правдоподобная, проверяемая по сумме, но выдуманная поимённо.
#
# Детерминизм как во всей TERRA: сид берётся из номера квартала, поэтому один
# и тот же квартал всегда даёт одних и тех же людей.

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sys

from twin import regions, schema
from twin.state import DATA_DIR

OUT_DIR = os.path.join(DATA_DIR, "people")

# ── типичные распределения (ярус T) ─────────────────────────────────────────
# Источник: агрегаты переписи США и ACS по Сан-Франциско; здесь они записаны
# как округлённые доли — это ОПИСАНИЕ МЕСТА, а не данные о людях.
AGE_BANDS = (   # (от, до, доля)
    (0, 17, 0.13), (18, 24, 0.08), (25, 34, 0.21), (35, 44, 0.17),
    (45, 54, 0.13), (55, 64, 0.12), (65, 74, 0.09), (75, 95, 0.07),
)
HOUSEHOLD_SIZES = ((1, 0.39), (2, 0.31), (3, 0.14), (4, 0.10), (5, 0.04), (6, 0.02))
TENURE_OWNER = 0.38                     # доля собственников жилья в СФ
COMMUTE = (("пешком", 0.13), ("транспорт", 0.31), ("за рулём", 0.31),
           ("велосипед", 0.04), ("из дома", 0.21))
SECTORS = (("технологии", 0.19), ("здравоохранение", 0.13), ("торговля", 0.11),
           ("общепит", 0.09), ("финансы", 0.08), ("образование", 0.08),
           ("строительство", 0.06), ("транспорт", 0.05), ("госслужба", 0.05),
           ("искусство", 0.04), ("наука", 0.04), ("прочее", 0.08))
# Доля жилья в здании по назначению участка из реестра оценщика
RESIDENTIAL_SHARE = {0: 1.0, 1: 0.15, 2: 0.02, 3: 0.05, 4: 0.05, 5: 0.35}


def _pick(rnd: random.Random, table) -> str | int:
    r = rnd.random()
    acc = 0.0
    for value, w in table:
        acc += w
        if r <= acc:
            return value
    return table[-1][0]


def _age(rnd: random.Random) -> int:
    lo, hi, _ = None, None, None
    r = rnd.random()
    acc = 0.0
    for a, b, w in AGE_BANDS:
        acc += w
        if r <= acc:
            lo, hi = a, b
            break
    if lo is None:
        lo, hi = AGE_BANDS[-1][0], AGE_BANDS[-1][1]
    return rnd.randint(lo, hi)


def _read(src: str, kind: str) -> list[dict]:
    import pyarrow.parquet as pq
    out = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, src, "*.parquet"))):
        pf = pq.ParquetFile(p)
        if schema.table_kind(pf.schema_arrow) != kind:
            continue
        out.extend(pq.read_table(p).to_pylist())
    return out


def _bbox_of(gj: dict) -> tuple[float, float, float, float]:
    rings = (gj["coordinates"] if gj["type"] == "Polygon"
             else [r for poly in gj["coordinates"] for r in poly])
    pts = [p for ring in rings for p in ring]
    las = [p[1] for p in pts]; los = [p[0] for p in pts]
    return min(las), min(los), max(las), max(los)


def generate(scene_key: str = "sf", limit_blocks: int | None = None) -> dict:
    """Расселить население кварталов по зданиям сцены и породить жителей."""
    sc = regions.scene(scene_key)
    lat_min, lon_min, lat_max, lon_max = sc.bbox

    blocks = [b for b in _read("population", "feature")
              if b["fclass"] == "census_block"
              and lat_min <= b["lat"] <= lat_max
              and lon_min <= b["lon"] <= lon_max]
    blocks.sort(key=lambda b: b["id"])
    if limit_blocks:
        blocks = blocks[:limit_blocks]

    builds = [f for f in _read("sfbuildings", "feature") if f["fclass"] == "building"]
    # индекс зданий по ячейкам, чтобы не перебирать 177 тысяч на каждый квартал
    CELL = 0.002
    grid: dict[tuple[int, int], list[dict]] = {}
    for f in builds:
        grid.setdefault((int(f["lat"] / CELL), int(f["lon"] / CELL)), []).append(f)

    # назначение участка -> доля жилья
    from twin.build import _read_years, _use_color
    years = _read_years()

    people, housed, unhoused, n_blocks = [], 0, 0, 0
    for blk in blocks:
        tags = json.loads(blk["tags_json"])
        pop = int(tags.get("pop20") or 0)
        if pop <= 0:
            continue
        n_blocks += 1
        bb = _bbox_of(json.loads(blk["geometry"]))
        cand = []
        for gy in range(int(bb[0] / CELL), int(bb[2] / CELL) + 1):
            for gx in range(int(bb[1] / CELL), int(bb[3] / CELL) + 1):
                for f in grid.get((gy, gx), []):
                    if bb[0] <= f["lat"] <= bb[2] and bb[1] <= f["lon"] <= bb[3]:
                        cand.append(f)
        # вес здания: жилой объём = площадь основания × высота × доля жилья
        weighted = []
        for f in cand:
            h = float(f.get("height_m") or 5.0)
            blk_id = json.loads(f.get("tags_json") or "{}").get("mapblklot")
            use = years.get(blk_id, (None, None))[1] if blk_id else None
            share = RESIDENTIAL_SHARE.get(_use_color(use), 0.35)
            area = max(20.0, (f["lat_max"] - f["lat_min"]) * 111132.0
                       * (f["lon_max"] - f["lon_min"]) * 88000.0)
            w = area * max(h, 3.0) * share
            if w > 0:
                weighted.append((f, w))
        if not weighted:
            unhoused += pop
            continue

        rnd = random.Random(int(blk["id"].split(":")[1]) % (2 ** 31))
        total_w = sum(w for _f, w in weighted)
        left = pop
        for i, (f, w) in enumerate(weighted):
            share = pop * w / total_w
            n = left if i == len(weighted) - 1 else min(left, int(round(share)))
            left -= n
            while n > 0:
                size = min(n, int(_pick(rnd, HOUSEHOLD_SIZES)))
                owner = rnd.random() < TENURE_OWNER
                for _ in range(size):
                    age = _age(rnd)
                    people.append({
                        "block": blk["id"], "building": f["id"],
                        "lat": f["lat"], "lon": f["lon"],
                        "age": age,
                        "household": size,
                        "tenure": "собственник" if owner else "наниматель",
                        "commute": (_pick(rnd, COMMUTE) if 18 <= age < 70
                                    else "не ездит"),
                        "sector": (_pick(rnd, SECTORS) if 18 <= age < 70
                                   else ("учёба" if age < 18 else "на покое")),
                    })
                n -= size
                housed += size

    return {"people": people, "blocks": n_blocks,
            "housed": housed, "unhoused": unhoused}


def save(res: dict, scene_key: str, sample: int) -> str:
    from twin.sources import common
    rnd = random.Random(12345)
    ppl = res["people"]
    take = ppl if len(ppl) <= sample else rnd.sample(ppl, sample)
    take.sort(key=lambda p: (p["building"], p["age"]))
    recs = []
    for i, p in enumerate(take):
        rec = schema.base_record("feature", "twin.people", "TERRA twin", "R")
        rec.update({
            "id": f"syn:{scene_key}:{i:06d}",
            "fclass": "resident", "scene": scene_key, "subclass": "synthetic",
            "name": None,
            "geometry": json.dumps({"type": "Point",
                                    "coordinates": [p["lon"], p["lat"]]}),
            "lat": p["lat"], "lon": p["lon"],
            "lat_min": p["lat"], "lon_min": p["lon"],
            "lat_max": p["lat"], "lon_max": p["lon"],
            "tags_json": json.dumps({k: p[k] for k in
                                     ("age", "household", "tenure", "commute",
                                      "sector", "block", "building")},
                                    ensure_ascii=False, sort_keys=True),
        })
        recs.append(rec)
    os.makedirs(OUT_DIR, exist_ok=True)
    return common.write_one_shard("feature", recs, OUT_DIR,
                                  f"residents_{scene_key}.parquet")


def main() -> int:
    ap = argparse.ArgumentParser(description="Синтетические жители сцены")
    ap.add_argument("scene", nargs="?", default="sf")
    ap.add_argument("--sample", type=int, default=4000,
                    help="сколько жителей сохранить в файл сцены")
    args = ap.parse_args()
    res = generate(args.scene)
    ppl = res["people"]
    print(f"кварталов {res['blocks']}, расселено {res['housed']:,}".replace(",", " ")
          + (f", без жилья {res['unhoused']}" if res["unhoused"] else ""))
    if ppl:
        ages = sorted(p["age"] for p in ppl)
        med = ages[len(ages) // 2]
        adults = sum(1 for a in ages if a >= 18)
        print(f"медианный возраст {med}, взрослых {adults * 100 // len(ages)} %")
        path = save(res, args.scene, args.sample)
        print(f"выборка {min(len(ppl), args.sample)} человек -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
