# OpenStreetMap через Overpass API: ИМЕНОВАННЫЕ здания (подписи и высоты
# достопримечательностей), дороги, вода, зелень, POI для каждой сцены.
# Безымянную массовую застройку СФ даёт sfbuildings (DataSF, лидар) — поэтому
# Overpass нужен лишь на ~8 небольших запросов. Каждый чанк резюмируем и
# пишет свой parquet-шард. Лицензия ODbL. Ярус K.
#
# Зеркала Overpass чередуем при ошибках; между запросами — пауза вежливости.

from __future__ import annotations

import json
import time

from twin import regions, schema
from twin.sources import common

NAME = "osm"
TITLE = "OpenStreetMap (Overpass) — здания, дороги, вода, зелень, POI сцен"
LICENSE = "ODbL-1.0"

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
PAUSE_S = 2.0            # вежливая пауза между запросами
GRID_ROADS = 2           # сетка чанков дорог (2×2)

# теги, которые сохраняем в записи (остальное отбрасываем)
KEEP_TAGS = (
    "building", "building:levels", "height", "building:height", "roof:shape",
    "name", "addr:street", "addr:housenumber", "start_date", "amenity",
    "shop", "tourism", "leisure", "landuse", "natural", "water", "waterway",
    "highway", "lanes", "surface", "bridge", "tunnel", "layer", "oneway",
)

QUERIES = {
    "buildings": '(way["building"]["name"]({bbox}););out tags geom;',
    "roads": '(way["highway"]({bbox}););out tags geom;',
    "water": ('(way["natural"="water"]({bbox});'
              'relation["natural"="water"]({bbox});'
              'way["waterway"="riverbank"]({bbox});'
              'way["natural"="coastline"]({bbox}););out tags geom;'),
    "green": ('(way["leisure"~"park|garden|golf_course|pitch"]({bbox});'
              'way["landuse"~"grass|forest|recreation_ground|cemetery|meadow"]({bbox});'
              'way["natural"~"wood|scrub|sand|beach"]({bbox}););out tags geom;'),
    "pois": ('(node["name"]["amenity"]({bbox});'
             'node["name"]["shop"]({bbox});'
             'node["name"]["tourism"]({bbox}););out tags 4000;'),
}
FCLASS_OF = {"buildings": "building", "roads": "road", "water": "water",
             "green": "green", "pois": "poi"}


def _split(bbox, n) -> list[tuple[int, tuple]]:
    lat_min, lon_min, lat_max, lon_max = bbox
    dla, dlo = (lat_max - lat_min) / n, (lon_max - lon_min) / n
    out = []
    for i in range(n):
        for j in range(n):
            out.append((i * n + j,
                        (lat_min + i * dla, lon_min + j * dlo,
                         lat_min + (i + 1) * dla, lon_min + (j + 1) * dlo)))
    return out


def _query(ctx, ql: str) -> dict:
    """Запрос к Overpass с чередованием зеркал и повторами."""
    body = f"[out:json][timeout:60];{ql}"
    last = None
    for attempt in range(6):
        ctx.check(90)
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            r = ctx.session.post(url, data={"data": body}, timeout=90)
            if r.status_code in (429, 502, 504):
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except common.BudgetExceeded:
            raise
        except Exception as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass не ответил: {last}")


def _geometry(el: dict) -> tuple[str | None, tuple | None, tuple | None]:
    """GeoJSON-строка + centroid (lat, lon) + bbox из элемента Overpass."""
    if el["type"] == "node":
        la, lo = el.get("lat"), el.get("lon")
        if la is None:
            return None, None, None
        return (json.dumps({"type": "Point", "coordinates": [lo, la]}),
                (la, lo), (la, lo, la, lo))
    geom = el.get("geometry") or []
    pts = [(g["lat"], g["lon"]) for g in geom if g]
    if el["type"] == "relation":
        pts = []
        for m in el.get("members", []):
            pts.extend((g["lat"], g["lon"]) for g in (m.get("geometry") or []) if g)
    if len(pts) < 2:
        return None, None, None
    closed = pts[0] == pts[-1] and len(pts) >= 4
    coords = [[lo, la] for la, lo in pts]
    gj = {"type": "Polygon", "coordinates": [coords]} if closed else \
         {"type": "LineString", "coordinates": coords}
    las = [p[0] for p in pts]; los = [p[1] for p in pts]
    cen = (sum(las) / len(las), sum(los) / len(los))
    return json.dumps(gj), cen, (min(las), min(los), max(las), max(los))


def _records(data: dict, group: str, scene_key: str) -> list[dict]:
    out = []
    for el in data.get("elements", []):
        gj, cen, bb = _geometry(el)
        if gj is None:
            continue
        tags = el.get("tags", {}) or {}
        rec = schema.base_record("feature", "https://www.openstreetmap.org",
                                 LICENSE, "K")
        rec.update({
            "id": f"osm:{el['type']}/{el['id']}",
            "fclass": FCLASS_OF[group],
            "scene": scene_key,
            "subclass": tags.get("building") or tags.get("highway")
                        or tags.get("natural") or tags.get("leisure")
                        or tags.get("landuse") or tags.get("amenity")
                        or tags.get("shop") or tags.get("tourism") or "",
            "name": tags.get("name"),
            "geometry": gj,
            "lat": cen[0], "lon": cen[1],
            "lat_min": bb[0], "lon_min": bb[1],
            "lat_max": bb[2], "lon_max": bb[3],
            "tags_json": json.dumps(
                {k: v for k, v in tags.items() if k in KEEP_TAGS},
                ensure_ascii=False, sort_keys=True),
        })
        if group == "buildings":
            h, h_src = common.parse_height(tags)
            rec["height_m"] = round(h, 1)
            rec["height_src"] = h_src
        out.append(rec)
    return out


def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    total = 0
    for scene_key, sc in regions.SCENES.items():
        plan = ([("buildings", 0, sc.bbox)]
                + [("roads", i, bb) for i, bb in _split(sc.bbox, GRID_ROADS)]
                + [("water", 0, sc.bbox), ("green", 0, sc.bbox),
                   ("pois", 0, sc.bbox)])
        for group, idx, bb in plan:
            chunk = f"{scene_key}_{group}_{idx:02d}"
            if man.chunk_done(NAME, chunk):
                continue
            ctx.check(120)
            bbox_s = f"{bb[0]:.6f},{bb[1]:.6f},{bb[2]:.6f},{bb[3]:.6f}"
            data = _query(ctx, QUERIES[group].format(bbox=bbox_s))
            recs = _records(data, group, scene_key)
            files = []
            if recs:
                files = [common.write_one_shard(
                    "feature", recs, out_dir, f"{chunk}.parquet")]
            man.mark_chunk(NAME, chunk, rows=len(recs), files=files,
                           note=f"{group} bbox {idx}")
            total += len(recs)
            time.sleep(PAUSE_S)
    return {"status": "done", "note": f"+{total} объектов за прогон"}
