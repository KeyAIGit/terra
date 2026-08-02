# Подробности планеты, которых нет ни в одном «историческом» датасете:
# пещеры, вулканы, источники, водопады, ледники, солончаки, шахты, курганы,
# развалины и прочие места, вокруг которых люди селились, молились и добывали.
#
# Источник — OpenStreetMap через Overpass API. Это не «карта дорог»: для нашей
# задачи OSM ценен именно точечными объектами природы и следами древности.
# Пещера у реки в Дордони — это не абстракция «биом лес», это конкретное место,
# где человек жил 17 000 лет назад, и оно есть в OSM с координатами.
#
# Устройство: по каждому типу объектов — запрос широтными поясами (чтобы
# ответы Overpass оставались подъёмными), каждый пояс — отдельный чанк
# манифеста. Обрыв по бюджету продолжается ровно с недокачанного пояса.
#
# Ярус K: это наблюдение на местности (краудсорсинг с проверкой), а не модель.
# Лицензия ODbL 1.0 — производные обязаны сохранять ссылку на OSM.

from __future__ import annotations

import json
import time

from atlas import schema
from atlas.sources import common

NAME = "osm_features"
TITLE = "OpenStreetMap natural and archaeological point features"
LICENSE = "ODbL-1.0"
HOME = "https://www.openstreetmap.org/copyright"
API = "https://overpass-api.de/api/interpreter"

# (тег, значение, наш kind_of, по-русски)
FEATURES = [
    ("natural", "cave_entrance", "cave", "вход в пещеру"),
    ("natural", "volcano", "volcano", "вулкан"),
    ("natural", "spring", "spring", "источник"),
    ("natural", "hot_spring", "hot_spring", "горячий источник"),
    ("waterway", "waterfall", "waterfall", "водопад"),
    ("natural", "peak", "peak", "вершина"),
    ("natural", "glacier", "glacier", "ледник"),
    ("natural", "salt_pond", "salt_pond", "солончак"),
    ("historic", "archaeological_site", "archaeological_site", "археологический памятник"),
    ("historic", "ruins", "ruins", "развалины"),
    ("historic", "tomb", "tomb", "гробница"),
    ("historic", "megalith", "megalith", "мегалит"),
    ("man_made", "mineshaft", "mineshaft", "шахтный ствол"),
    ("man_made", "adit", "adit", "штольня"),
    ("landuse", "quarry", "quarry", "каменоломня"),
]

# широтные пояса: у экватора объектов больше, но пояса режем ровно
BANDS = [(-90, -30), (-30, 0), (0, 20), (20, 35), (35, 45), (45, 55), (55, 90)]


def _query(ctx, tag: str, val: str, lat0: int, lat1: int, tries: int = 3):
    q = (f'[out:json][timeout:240];node["{tag}"="{val}"]'
         f'({lat0},-180,{lat1},180);out body;')
    last = None
    for attempt in range(tries):
        ctx.check(120)
        try:
            r = ctx.session.post(API, data={"data": q}, timeout=300)
            if r.status_code in (429, 504):
                time.sleep(20 * (attempt + 1))
                last = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            return r.json().get("elements", [])
        except common.BudgetExceeded:
            raise
        except Exception as e:
            last = str(e)[:120]
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass не ответил: {last}")


def _emit(elements, kind_of: str, ru: str, tag: str, val: str) -> list[dict]:
    out = []
    today = schema.today()
    for el in elements:
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue
        t = el.get("tags", {}) or {}
        name = (t.get("name") or t.get("name:en") or t.get("alt_name")
                or f"{ru} #{el['id']}")
        # то, что реально пригодится сцене и симуляции
        extra = {k: t[k] for k in ("ele", "depth", "length", "site_type",
                                   "historic", "wikidata", "wikipedia",
                                   "start_date", "material", "resource")
                 if k in t}
        out.append({
            "source": f"https://www.openstreetmap.org/node/{el['id']}",
            "license": LICENSE, "tier": "K", "retrieved": today,
            "id": f"osm:node/{el['id']}", "name": str(name)[:200],
            "lat": float(lat), "lon": float(lon),
            "kind_of": kind_of, "kind_ru": ru,
            "osm_tag": f"{tag}={val}",
            "elevation_m": common.to_float(t.get("ele")),
            "wikidata": t.get("wikidata"),
            "tags": json.dumps(extra, ensure_ascii=False) if extra else None,
        })
    return out


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    total = 0
    done_all = True

    for tag, val, kind_of, ru in FEATURES:
        for (lat0, lat1) in BANDS:
            chunk = f"{val}_{lat0}_{lat1}"
            if man.chunk_done(NAME, chunk):
                continue
            if ctx.time_left() < 180:
                done_all = False
                break
            try:
                els = _query(ctx, tag, val, lat0, lat1)
            except common.BudgetExceeded:
                done_all = False
                break
            except Exception as e:
                man.mark_chunk(NAME, chunk, rows=0, note=f"не вышло: {str(e)[:90]}")
                continue
            recs = _emit(els, kind_of, ru, tag, val)
            if recs:
                p = common.write_one_shard("place", recs, out_dir,
                                           f"{val}_{lat0}_{lat1}.parquet")
                man.mark_chunk(NAME, chunk, rows=len(recs), files=[p])
            else:
                man.mark_chunk(NAME, chunk, rows=0, note="пусто в поясе")
            total += len(recs)
            print(f"    osm: {val} [{lat0}..{lat1}] — {len(recs)}")
        else:
            continue
        break

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, HOME, LICENSE, TITLE,
            "Точечные объекты OpenStreetMap, важные для жизни людей и сцен: "
            "входы в пещеры, вулканы, источники и горячие ключи, водопады, "
            "вершины, ледники, солончаки, каменоломни, шахты и штольни, "
            "археологические памятники, развалины, гробницы, мегалиты. "
            "Производные обязаны сохранять указание © участники OpenStreetMap.",
            tier="K")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    return {"status": "done" if done_all else "partial",
            "note": f"добавлено {total} объектов за заход"}
