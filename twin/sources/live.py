# Живой слой твина: то, что движется прямо сейчас. Всё БЕЗ ключей.
#
#   самолёты   adsb.lol            — борта над Заливом, эшелон, курс, тип
#   спутники   CelesTrak + sgp4    — витки над городом на ±45 минут
#   толчки     USGS FDSN           — землетрясения Залива за месяц
#   прилив     NOAA CO-OPS 9414290 — реальный уровень воды в заливе
#   камеры     Caltrans CWWP2 D4   — дорожные камеры со свежим кадром
#
# Слепок пишется с отметкой времени: твин показывает НАСТОЯЩЕЕ, а не вообще.
# Спутники требуют pip install sgp4; без него источник честно скажет об этом
# и пропустит только спутники.

from __future__ import annotations

import datetime as _dt
import json
import math

from twin import regions, schema
from twin.sources import common

NAME = "live"
TITLE = "Живой слой: самолёты, спутники, толчки, прилив, камеры"
LICENSE = "ADS-B community (ODbL-like) / CelesTrak / USGS PD / NOAA PD / Caltrans PD"

ADSB_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
ADSB_RADIUS_NM = 120
CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?GROUP={g}&FORMAT=json"
# Группы: станции (МКС), яркие, метеорологические, научные и — к месту —
# аппараты Planet Labs и Spire, те самые «ежедневные снимки планеты».
SAT_GROUPS = ("stations", "visual", "weather", "science", "planet", "spire")
QUAKE_URL = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
             "&starttime={start}&minlatitude={la0}&maxlatitude={la1}"
             "&minlongitude={lo0}&maxlongitude={lo1}&minmagnitude=1.0&orderby=time")
TIDE_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
TIDE_STATION = "9414290"          # Сан-Франциско, Форт-Пойнт
CAM_URL = "https://cwwp2.dot.ca.gov/data/d4/cctv/cctvStatusD04.json"

SAT_WINDOW_MIN = 45               # ±минут вокруг слепка
SAT_STEP_S = 30                   # шаг витка
SAT_NEAR_KM = 1600                # насколько близко к городу должен пройти след
MAX_SATS = 60                     # столько самых близких оставляем


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _get(ctx, url: str, params: dict | None = None, timeout: int = 60):
    r = ctx.session.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r


def _point(rec_id: str, fclass: str, lat: float, lon: float, source: str,
           tags: dict, name: str | None = None, scene: str | None = None) -> dict:
    rec = schema.base_record("feature", source, LICENSE, "K")
    rec.update({
        "id": rec_id, "fclass": fclass, "scene": scene, "subclass": fclass,
        "name": name,
        "geometry": json.dumps({"type": "Point", "coordinates": [lon, lat]}),
        "lat": lat, "lon": lon,
        "lat_min": lat, "lon_min": lon, "lat_max": lat, "lon_max": lon,
        "tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
    })
    return rec


# ── самолёты ────────────────────────────────────────────────────────────────
def _aircraft(ctx, sc) -> list[dict]:
    la, lo = sc.center
    r = _get(ctx, ADSB_URL.format(lat=la, lon=lo, radius=ADSB_RADIUS_NM))
    d = r.json()
    ac = d.get("ac") or d.get("aircraft") or []
    out = []
    for a in ac:
        if a.get("lat") is None or a.get("lon") is None:
            continue
        alt = a.get("alt_baro")
        on_ground = (alt == "ground")
        alt_ft = 0 if on_ground else common.to_float(alt)
        if alt_ft is None:
            alt_ft = common.to_float(a.get("alt_geom")) or 0.0
        track = a.get("track")
        if track is None:
            track = a.get("true_heading") or a.get("mag_heading") or 0.0
        out.append(_point(
            f"ac:{a.get('hex')}", "aircraft", float(a["lat"]), float(a["lon"]),
            "https://api.adsb.lol", {
                "callsign": (a.get("flight") or "").strip() or None,
                "reg": a.get("r"), "type": a.get("t"),
                "alt_ft": alt_ft, "on_ground": on_ground,
                "gs_kt": common.to_float(a.get("gs")) or 0.0,
                "track_deg": float(track),
                "squawk": a.get("squawk"),
                "military": bool((a.get("dbFlags") or 0) & 1),
                "dist_nm": common.to_float(a.get("dst")),
            }, name=(a.get("flight") or "").strip() or a.get("hex")))
    return out


# ── спутники ────────────────────────────────────────────────────────────────
def _sat_tracks(ctx, sc) -> tuple[list[dict], str]:
    try:
        from sgp4.api import Satrec, jday
        from sgp4 import omm
    except ImportError:
        return [], "нет пакета sgp4 (pip install sgp4) — спутники пропущены"

    gp = []
    for g in SAT_GROUPS:
        ctx.check(30)
        try:
            body = _get(ctx, CELESTRAK.format(g=g)).json()
        except Exception as e:
            print(f"    группа {g} не отдалась: {e}")
            continue
        if isinstance(body, list):
            gp.extend(body)

    t0 = _now()
    steps = int(SAT_WINDOW_MIN * 60 * 2 / SAT_STEP_S) + 1
    times = [t0 + _dt.timedelta(seconds=(i * SAT_STEP_S - SAT_WINDOW_MIN * 60))
             for i in range(steps)]
    jds = [jday(t.year, t.month, t.day, t.hour, t.minute,
                t.second + t.microsecond * 1e-6) for t in times]
    lat0, lon0 = sc.center

    tracks = []
    seen = set()
    for el in gp:
        cat = el.get("NORAD_CAT_ID")
        if cat is None or cat in seen:
            continue
        seen.add(cat)
        try:
            sat = Satrec()
            omm.initialize(sat, el)
        except Exception:
            continue
        pts, best = [], 1e9
        for (jd, fr), t in zip(jds, times):
            e, r, _v = sat.sgp4(jd, fr)
            if e != 0:
                pts = []
                break
            la, lo, alt_km = _teme_to_geodetic(r, t)
            pts.append((round(lo, 3), round(la, 3), round(alt_km, 1)))
            best = min(best, _haversine_km(lat0, lon0, la, lo))
        if not pts or best > SAT_NEAR_KM:
            continue
        tracks.append((best, el, pts))

    tracks.sort(key=lambda x: x[0])
    out = []
    for best, el, pts in tracks[:MAX_SATS]:
        mid = pts[len(pts) // 2]
        rec = schema.base_record("feature", "https://celestrak.org", LICENSE, "K")
        rec.update({
            "id": f"sat:{el['NORAD_CAT_ID']}",
            "fclass": "satellite", "scene": sc.key, "subclass": "satellite",
            "name": el.get("OBJECT_NAME"),
            "geometry": json.dumps({
                "type": "LineString",
                "coordinates": [[p[0], p[1]] for p in pts]}),
            "lat": mid[1], "lon": mid[0],
            "lat_min": min(p[1] for p in pts), "lon_min": min(p[0] for p in pts),
            "lat_max": max(p[1] for p in pts), "lon_max": max(p[0] for p in pts),
            "tags_json": json.dumps({
                "norad": el["NORAD_CAT_ID"], "intl": el.get("OBJECT_ID"),
                "alt_km": [p[2] for p in pts],
                "t0_iso": times[0].isoformat().replace("+00:00", "Z"),
                "step_s": SAT_STEP_S,
                "closest_km": round(best, 1),
                "period_min": round(1440.0 / float(el["MEAN_MOTION"]), 1)
                              if el.get("MEAN_MOTION") else None,
            }, ensure_ascii=False, sort_keys=True),
        })
        out.append(rec)
    return out, f"{len(out)} аппаратов прошли рядом"


def _teme_to_geodetic(r_km, t: _dt.datetime) -> tuple[float, float, float]:
    """TEME -> широта/долгота/высота. Точности хватает для витка на глобусе."""
    x, y, z = r_km
    # Гринвичское звёздное время (упрощённая формула для эпохи J2000+)
    jd = (t - _dt.datetime(2000, 1, 1, 12, tzinfo=_dt.timezone.utc)).total_seconds() / 86400.0
    gmst = (280.46061837 + 360.98564736629 * jd) % 360.0
    g = math.radians(gmst)
    lon = math.degrees(math.atan2(y, x) - g)
    lon = (lon + 180.0) % 360.0 - 180.0
    rxy = math.hypot(x, y)
    lat = math.degrees(math.atan2(z, rxy))
    alt = math.sqrt(x * x + y * y + z * z) - 6371.0
    return lat, lon, alt


def _haversine_km(la1, lo1, la2, lo2) -> float:
    p = math.pi / 180
    a = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 12742 * math.asin(math.sqrt(max(0.0, a)))


# ── землетрясения ───────────────────────────────────────────────────────────
def _quakes(ctx, region) -> list[dict]:
    start = (_now() - _dt.timedelta(days=30)).date().isoformat()
    url = QUAKE_URL.format(start=start, la0=region.bbox[0], la1=region.bbox[2],
                           lo0=region.bbox[1], lo1=region.bbox[3])
    d = _get(ctx, url).json()
    out = []
    for f in d.get("features", []):
        c = f["geometry"]["coordinates"]
        p = f["properties"]
        t_ms = p.get("time")
        out.append(_point(
            f"eq:{f['id']}", "quake", float(c[1]), float(c[0]),
            "https://earthquake.usgs.gov", {
                "mag": p.get("mag"), "depth_km": float(c[2]) if len(c) > 2 else None,
                "place": p.get("place"),
                "t_iso": (_dt.datetime.fromtimestamp(t_ms / 1000, _dt.timezone.utc)
                          .isoformat().replace("+00:00", "Z")) if t_ms else None,
            }, name=p.get("title")))
    return out


# ── прилив ──────────────────────────────────────────────────────────────────
def _tide(ctx, sc) -> list[dict]:
    common_p = {"station": TIDE_STATION, "datum": "MLLW", "units": "metric",
                "time_zone": "gmt", "format": "json", "application": "terra-twin"}
    out = []
    d = _get(ctx, TIDE_URL, dict(common_p, date="latest", product="water_level")).json()
    if "error" in d:
        raise RuntimeError(f"CO-OPS: {d['error'].get('message')}")
    for row in d.get("data", []):
        rec = schema.base_record("obs", TIDE_URL, LICENSE, "K")
        rec.update({"id": f"tide:{TIDE_STATION}:{row['t']}", "station": TIDE_STATION,
                    "t": row["t"], "var": "water_level", "value": float(row["v"]),
                    "unit": "m", "scene": sc.key, "text": "наблюдение, MLLW"})
        out.append(rec)
    p = _get(ctx, TIDE_URL, dict(common_p, date="today", product="predictions",
                                 interval="hilo")).json()
    for row in p.get("predictions", []):
        rec = schema.base_record("obs", TIDE_URL, LICENSE, "K")
        rec.update({"id": f"tidep:{TIDE_STATION}:{row['t']}", "station": TIDE_STATION,
                    "t": row["t"], "var": "tide_" + ("high" if row["type"] == "H"
                                                     else "low"),
                    "value": float(row["v"]), "unit": "m", "scene": sc.key,
                    "text": "прогноз, MLLW"})
        out.append(rec)
    return out


# ── дорожные камеры ─────────────────────────────────────────────────────────
def _cameras(ctx, sc) -> list[dict]:
    d = _get(ctx, CAM_URL, timeout=120).json()
    lat_min, lon_min, lat_max, lon_max = sc.bbox
    out = []
    for item in d.get("data", []):
        c = item.get("cctv") or {}
        loc = c.get("location") or {}
        la = common.to_float(loc.get("latitude"))
        lo = common.to_float(loc.get("longitude"))
        if la is None or lo is None:
            continue
        if not (lat_min <= la <= lat_max and lon_min <= lo <= lon_max):
            continue
        if str(c.get("inService")).lower() != "true":
            continue
        img = ((c.get("imageData") or {}).get("static") or {}).get("currentImageURL")
        if not img:
            continue
        out.append(_point(
            f"cam:{c.get('index')}", "camera", la, lo,
            "https://cwwp2.dot.ca.gov", {
                "still_url": img,
                "stream_url": (c.get("imageData") or {}).get("streamingVideoURL"),
                "route": loc.get("route"), "direction": loc.get("direction"),
                "place": loc.get("nearbyPlace"),
            }, name=loc.get("locationName"), scene=sc.key))
    return out


# ── драйвер ─────────────────────────────────────────────────────────────────
def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    stamp = _now().strftime("%Y%m%dT%H%M")
    notes = []

    for scene_key, sc in regions.SCENES.items():
        region = regions.region_of(sc)
        jobs = [
            ("aircraft", "feature", lambda: _aircraft(ctx, sc)),
            ("quakes", "feature", lambda: _quakes(ctx, region)),
            ("tide", "obs", lambda: _tide(ctx, sc)),
            ("cameras", "feature", lambda: _cameras(ctx, sc)),
        ]
        for kind_name, kind, fn in jobs:
            chunk = f"{scene_key}_{kind_name}_{stamp}"
            if man.chunk_done(NAME, chunk):
                continue
            ctx.check(90)
            try:
                recs = fn()
            except Exception as e:
                notes.append(f"{kind_name}: {type(e).__name__} {e}")
                continue
            files = ([common.write_one_shard(kind, recs, out_dir,
                                             f"{chunk}.parquet")] if recs else [])
            man.mark_chunk(NAME, chunk, rows=len(recs), files=files)
            notes.append(f"{kind_name} {len(recs)}")

        chunk = f"{scene_key}_sats_{stamp}"
        if not man.chunk_done(NAME, chunk):
            ctx.check(180)
            try:
                recs, note = _sat_tracks(ctx, sc)
            except Exception as e:
                recs, note = [], f"{type(e).__name__}: {e}"
            files = ([common.write_one_shard("feature", recs, out_dir,
                                             f"{chunk}.parquet")] if recs else [])
            man.mark_chunk(NAME, chunk, rows=len(recs), files=files, note=note)
            notes.append(f"спутники: {note}")

    return {"status": "done", "note": "; ".join(notes) or "нечего обновлять"}
