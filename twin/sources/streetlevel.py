# Уличная съёмка твина: настоящие фотографии тех же улиц, БЕЗ ключей.
#
#   KartaView (бывш. OpenStreetCam) — съёмка с регистраторов, CC BY-SA 4.0:
#       точка, курс камеры, дата, кадр. Это открытый двойник Street View —
#       снято людьми, отдаётся без ключа и без запрета на использование.
#   Wikimedia Commons  — геопривязанные фотографии зданий и видов, свободные
#       лицензии; у каждой карточки автор и лицензия едут вместе со снимком.
#
# Зачем твину фотографии: это ПОВЕРКА. Наша геометрия построена из обмеров, и
# единственный честный способ узнать, похожа ли она на город, — встать в ту же
# точку, повернуться в ту же сторону и сравнить с кадром, снятым оттуда же.
# Поэтому у каждого снимка обязателен курс: без него сравнивать не с чем.
#
# Кадры НЕ скачиваются и не перекладываются к нам: в parquet едет только адрес,
# автор и лицензия, а картинку страница берёт с первоисточника.

from __future__ import annotations

import json
import math
import time

from twin import regions, schema
from twin.sources import common

NAME = "streetlevel"
TITLE = "Уличная съёмка: KartaView + Wikimedia Commons"
LICENSE = "KartaView CC BY-SA 4.0 / Wikimedia Commons (свободные лицензии)"

KV_URL = "https://api.kartaview.org/1.0/list/nearby-photos/"
KV_IMG_BASE = "https://api.openstreetcam.org/"
KV_RADIUS_M = 500          # радиус запроса
KV_STEP_M = 700            # шаг сетки: угол ячейки 495 м < радиуса — без дыр
KV_THIN_M = 22.0           # ближе этого по улице второй кадр не нужен
KV_MAX_PER_CELL = 4000     # предохранитель на случай сверхплотной ячейки
MATCH_MAX_M = 40.0         # дальше этого «посадка на дорогу» не заслуживает веры

COMMONS_URL = "https://commons.wikimedia.org/w/api.php"
COMMONS_STEP_M = 1800
COMMONS_RADIUS_M = 1200
COMMONS_LIMIT = 50         # потолок generator=geosearch с prop=imageinfo
COMMONS_THUMB_W = 800

PAUSE_S = 0.35

M_PER_DEG_LAT = 110_574.0


def _m_per_deg_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


def _grid(bbox, step_m: float) -> list[tuple[int, int, float, float]]:
    """Узлы сетки с шагом step_m: (строка, столбец, широта, долгота)."""
    la0, lo0, la1, lo1 = bbox
    dlat = step_m / M_PER_DEG_LAT
    out = []
    row = 0
    la = la0 + dlat / 2
    while la < la1 + dlat / 2:
        dlon = step_m / _m_per_deg_lon(la)
        col = 0
        lo = lo0 + dlon / 2
        while lo < lo1 + dlon / 2:
            out.append((row, col, la, lo))
            lo += dlon
            col += 1
        la += dlat
        row += 1
    return out


def _in_bbox(bbox, lat: float, lon: float) -> bool:
    return bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]


def _photo_record(rec_id: str, lat: float, lon: float, source: str, license: str,
                  scene: str, tags: dict, name: str | None = None) -> dict:
    rec = schema.base_record("feature", source, license, "K")
    rec.update({
        "id": rec_id, "fclass": "streetphoto", "scene": scene,
        "subclass": tags.get("kind", "photo"), "name": name,
        "geometry": json.dumps({"type": "Point", "coordinates": [lon, lat]}),
        "lat": lat, "lon": lon,
        "lat_min": lat, "lon_min": lon, "lat_max": lat, "lon_max": lon,
        "tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
    })
    return rec


# ── KartaView ───────────────────────────────────────────────────────────────
def _kv_heading(item: dict) -> float | None:
    """Курс камеры в градусах или None. У части кадров он не записан —
    такие снимку для поверки не годятся, но как метка места сойдут."""
    for key in ("heading", "headers"):
        v = item.get(key)
        if v in (None, "", "-1", -1):
            continue
        try:
            # округляем ДО приведения к кругу: иначе 359.97 округлится в 360.0
            # и уедет за круг уже после нормировки
            h = round(float(v), 1) % 360.0
        except (TypeError, ValueError):
            continue
        return h
    return None


def _kv_cell(ctx, lat: float, lon: float) -> list[dict]:
    r = ctx.session.post(KV_URL, data={"lat": lat, "lng": lon,
                                       "radius": KV_RADIUS_M}, timeout=90)
    r.raise_for_status()
    return (r.json().get("currentPageItems") or [])[:KV_MAX_PER_CELL]


def _kv_place(it: dict) -> tuple[float, float, str] | None:
    """Где стоял снимавший: (широта, долгота, откуда взято).

    У кадра две точки. Сырой GPS регистратора врёт на десятки метров (в самих
    записях бывает gps_accuracy 20 м) — с такой ошибкой «встать сюда» ставит
    наблюдателя внутрь соседнего дома. KartaView попутно сажает кадр на линию
    дороги (match_lat/match_lng) — это ровно то место, где едет машина, и
    именно оно нам нужно. Берём посаженную точку, если она рядом с сырой;
    если её нет или она уехала — честно возвращаемся к сырой.
    """
    try:
        lat = float(it["lat"]); lon = float(it["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    m_lat = common.to_float(it.get("match_lat"))
    m_lon = common.to_float(it.get("match_lng"))
    if m_lat and m_lon:
        d = math.hypot((m_lat - lat) * M_PER_DEG_LAT,
                       (m_lon - lon) * _m_per_deg_lon(lat))
        if d <= MATCH_MAX_M:
            return m_lat, m_lon, "road"
    return lat, lon, "gps"


def _kv_records(items: list[dict], bbox, scene: str) -> list[dict]:
    """Проредить кадры до одного на KV_THIN_M и превратить в записи.

    Прореживание — по ячейкам сетки: в каждой оставляем самый свежий кадр.
    Иначе на перекрёстке, где регистратор стоял в пробке, окажется полторы
    сотни одинаковых снимков одного бампера.
    """
    best: dict[tuple[int, int], tuple[int, dict]] = {}
    for it in items:
        place = _kv_place(it)
        if place is None:
            continue
        lat, lon, _ = place
        if not _in_bbox(bbox, lat, lon):
            continue
        cell = (int(round(lat * M_PER_DEG_LAT / KV_THIN_M)),
                int(round(lon * _m_per_deg_lon(lat) / KV_THIN_M)))
        ts = common.to_int(it.get("timestamp")) or 0
        prev = best.get(cell)
        if prev is None or ts > prev[0]:
            best[cell] = (ts, it)

    out = []
    for _, it in sorted(best.values(), key=lambda p: str(p[1].get("id"))):
        lat, lon, place_src = _kv_place(it)
        heading = _kv_heading(it)
        spherical = str(it.get("projection", "")).upper() != "PLANE"
        tags = {
            "kind": "kartaview",
            "heading": heading,
            "shot_date": (it.get("shot_date") or it.get("date_added") or "")[:10],
            "author": it.get("username") or "",
            "sequence": str(it.get("sequence_id") or ""),
            "spherical": spherical,
            "place": place_src,
            "url": KV_IMG_BASE + str(it.get("name") or ""),
            "thumb": KV_IMG_BASE + str(it.get("lth_name") or it.get("th_name") or ""),
            "page": f"https://kartaview.org/details/{it.get('sequence_id')}"
                    f"/{it.get('sequence_index')}",
        }
        out.append(_photo_record(f"kv_{it.get('id')}", lat, lon,
                                 "kartaview", "CC BY-SA 4.0", scene, tags))
    return out


# ── Wikimedia Commons ───────────────────────────────────────────────────────
def _strip_html(s: str) -> str:
    out, depth = [], 0
    for ch in s or "":
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())


def _commons_cell(ctx, lat: float, lon: float) -> dict:
    r = ctx.session.get(COMMONS_URL, params={
        "action": "query", "format": "json", "generator": "geosearch",
        "ggscoord": f"{lat}|{lon}", "ggsradius": str(COMMONS_RADIUS_M),
        "ggslimit": str(COMMONS_LIMIT), "ggsnamespace": "6",
        # coordinates обязателен: как генератор geosearch кладёт широту в
        # список, а не в страницы — без него у кадра не будет места.
        # colimit обязателен: по умолчанию координаты приезжают только к
        # первым десяти страницам из пятидесяти, и остальные кадры теряют место.
        "prop": "imageinfo|coordinates", "colimit": "max",
        "iiprop": "url|extmetadata",
        "iiurlwidth": str(COMMONS_THUMB_W),
        "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName|DateTimeOriginal",
    }, timeout=90)
    r.raise_for_status()
    return (r.json().get("query") or {}).get("pages") or {}


def _commons_records(pages: dict, bbox, scene: str) -> list[dict]:
    out = []
    for page in sorted(pages.values(), key=lambda p: p.get("pageid", 0)):
        coord = (page.get("coordinates") or [{}])[0]
        lat = common.to_float(coord.get("lat"))
        lon = common.to_float(coord.get("lon"))
        if lat is None or lon is None or not _in_bbox(bbox, lat, lon):
            continue
        ii = (page.get("imageinfo") or [{}])[0]
        thumb = ii.get("thumburl")
        if not thumb:
            continue
        em = ii.get("extmetadata") or {}

        def meta(key: str) -> str:
            return _strip_html(str((em.get(key) or {}).get("value") or ""))

        title = str(page.get("title") or "")
        tags = {
            "kind": "commons",
            "heading": None,
            "shot_date": meta("DateTimeOriginal")[:10],
            "author": meta("Artist"),
            "license": meta("LicenseShortName") or "см. страницу файла",
            "spherical": False,
            "url": ii.get("url") or thumb,
            "thumb": thumb,
            "page": ii.get("descriptionurl")
                    or ("https://commons.wikimedia.org/wiki/"
                        + title.replace(" ", "_")),
        }
        name = meta("ObjectName") or title[5:].rsplit(".", 1)[0].replace("_", " ")
        out.append(_photo_record(f"wc_{page.get('pageid')}", lat, lon,
                                 "wikimedia_commons", tags["license"], scene,
                                 tags, name=name[:180]))
    return out


# ── сбор ────────────────────────────────────────────────────────────────────
def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    total = 0
    for scene_key, sc in regions.SCENES.items():
        # KartaView — построчно: одна строка сетки = один чанк манифеста.
        nodes = _grid(sc.bbox, KV_STEP_M)
        rows = sorted({n[0] for n in nodes})
        for row in rows:
            chunk = f"{scene_key}_kv_{row:03d}"
            if man.chunk_done(NAME, chunk):
                continue
            ctx.check(90)
            items: list[dict] = []
            for _, _, la, lo in [n for n in nodes if n[0] == row]:
                items.extend(_kv_cell(ctx, la, lo))
                time.sleep(PAUSE_S)
            recs = _kv_records(items, sc.bbox, scene_key)
            files = []
            if recs:
                files = [common.write_one_shard("feature", recs, out_dir,
                                                f"{chunk}.parquet")]
            man.mark_chunk(NAME, chunk, rows=len(recs), files=files,
                           note=f"kartaview строка {row}")
            total += len(recs)

        # Commons — вся сцена одним чанком: узлов немного.
        chunk = f"{scene_key}_commons"
        if not man.chunk_done(NAME, chunk):
            ctx.check(90)
            pages: dict = {}
            for _, _, la, lo in _grid(sc.bbox, COMMONS_STEP_M):
                pages.update(_commons_cell(ctx, la, lo))
                time.sleep(PAUSE_S)
            recs = _commons_records(pages, sc.bbox, scene_key)
            files = []
            if recs:
                files = [common.write_one_shard("feature", recs, out_dir,
                                                f"{chunk}.parquet")]
            man.mark_chunk(NAME, chunk, rows=len(recs), files=files,
                           note="wikimedia commons")
            total += len(recs)

    return {"status": "done", "note": f"+{total} снимков за прогон"}
