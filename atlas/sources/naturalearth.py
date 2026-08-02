# Natural Earth 10m: базовая география Земли (страны, города, реки, озёра).
# Zip-шейпы с naturalearth.s3.amazonaws.com; читаем pyshp (чистый Python —
# geopandas/fiona в контейнер не ставились, pyshp встал с pip без колёс C).
# Геометрию храним как GeoJSON-строку + bbox-колонки для фильтров.
# Лицензия: public domain. Ярус K (современная география).
#
# Фолбэк: если pyshp недоступен — оставляем сырые zip в data/naturalearth/raw_zip
# и помечаем источник partial (сырьё сохранено, парсинг позже).

from __future__ import annotations

import json
import os
import zipfile

from atlas import schema
from atlas.sources import common

NAME = "naturalearth"
TITLE = "Natural Earth 10m cultural + physical vectors"
LICENSE = "Public Domain (Natural Earth)"
S3 = "https://naturalearth.s3.amazonaws.com/"

# слой -> (путь на s3, тип места, атрибуты для представительной точки)
LAYERS = {
    "countries": ("10m_cultural/ne_10m_admin_0_countries.zip", "country"),
    "populated_places": ("10m_cultural/ne_10m_populated_places.zip", "city"),
    "rivers": ("10m_physical/ne_10m_rivers_lake_centerlines.zip", "river"),
    "lakes": ("10m_physical/ne_10m_lakes.zip", "lake"),
}

# какие атрибуты dbf тащим (без регистра)
KEEP_ATTRS = ["name", "name_en", "admin", "adm0name", "iso_a3", "continent",
              "pop_est", "pop_max", "featurecla", "scalerank", "label_x",
              "label_y", "latitude", "longitude"]


def _bbox_center(shp) -> tuple[float | None, float | None]:
    try:
        x1, y1, x2, y2 = shp.bbox
        return (y1 + y2) / 2.0, (x1 + x2) / 2.0
    except Exception:
        return None, None


def _clamp(v, lo, hi):
    return None if v is None else max(lo, min(hi, v))


def _layer_records(shp_dir: str, base: str, ptype: str, url: str) -> list[dict]:
    import shapefile  # pyshp
    rd = shapefile.Reader(os.path.join(shp_dir, base),
                          encoding="utf-8", encodingErrors="replace")
    fields = [f[0] for f in rd.fields[1:]]
    lower = {f.lower(): f for f in fields}
    records = []
    for i, sr in enumerate(rd.iterShapeRecords()):
        attrs = dict(zip(fields, sr.record))
        get = lambda k: attrs.get(lower.get(k, ""), None)
        # представительная точка: атрибуты слоя или центр bbox
        lat = common.to_float(get("latitude")) or common.to_float(get("label_y"))
        lon = common.to_float(get("longitude")) or common.to_float(get("label_x"))
        if lat is None or lon is None:
            lat, lon = _bbox_center(sr.shape)
        # у пары стран (Фиджи) bbox рвётся антимеридианом — прижимаем
        lat, lon = _clamp(lat, -90.0, 90.0), _clamp(lon, -180.0, 180.0)
        name = get("name_en") or get("name") or get("admin") or f"{ptype}_{i}"
        try:
            geom = json.dumps(sr.shape.__geo_interface__)
        except Exception:
            geom = None
        try:
            bx = list(sr.shape.bbox)
        except Exception:
            bx = [None] * 4
        rec = schema.base_record("place", url, LICENSE, "K")
        rec.update({
            "id": f"ne10m:{ptype}:{i}",
            "name": str(name),
            "lat": lat, "lon": lon,
            "place_types": ptype,
            "admin": (str(get("admin") or get("adm0name")) if (get("admin") or get("adm0name")) else None),
            "iso_a3": get("iso_a3") or None,
            "featurecla": get("featurecla") or None,
            "pop_est": common.to_float(get("pop_est")) or common.to_float(get("pop_max")),
            "minx": bx[0], "miny": bx[1], "maxx": bx[2], "maxy": bx[3],
            "geometry_geojson": geom,
        })
        records.append(rec)
    return records


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    try:
        import shapefile  # noqa: F401 — проверка гео-стека
        has_pyshp = True
    except ImportError:
        has_pyshp = False

    for layer, (relurl, ptype) in LAYERS.items():
        if man.chunk_done(NAME, layer):
            continue
        ctx.check(45)
        url = S3 + relurl
        zpath = common.download(ctx, url, common.raw_path(NAME, layer + ".zip"))
        if not has_pyshp:
            # гео-стек не встал: сохраняем сырьё рядом с данными, статус partial
            keep_dir = os.path.join(out_dir, "raw_zip")
            os.makedirs(keep_dir, exist_ok=True)
            os.replace(zpath, os.path.join(keep_dir, layer + ".zip"))
            man.set_status(NAME, "partial", "pyshp недоступен; zip сохранены")
            continue
        shp_dir = os.path.join(common.raw_path(NAME, ""), layer)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(shp_dir)
        base = common.zip_member(zpath, ".shp").rsplit("/", 1)[-1]
        records = _layer_records(shp_dir, base, ptype, url)
        paths, n = common.write_shards("place", records, out_dir,
                                      f"place_{layer}", rows_per_shard=50_000)
        man.mark_chunk(NAME, layer, rows=n, files=paths)
        print(f"    naturalearth: {layer} — {n} объектов")

    if has_pyshp and not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, "https://www.naturalearthdata.com/", LICENSE, TITLE,
            "Векторы 10m: страны, населённые пункты, реки, озёра; геометрия "
            "GeoJSON-строкой + bbox, представительная точка lat/lon.")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    if not has_pyshp:
        return {"status": "partial", "note": "гео-стека нет, сырые zip сохранены"}
    return {"status": "done", "note": "4 слоя 10m"}
