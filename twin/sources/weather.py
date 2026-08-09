# Погода настоящего: NOAA/NWS api.weather.gov — без ключа.
# Для центра каждой сцены: текущее наблюдение ближайшей станции + прогноз.
# Каждый прогон обновляет слепок (чанк с датой) — твин дышит настоящим.

from __future__ import annotations

import datetime as _dt
import json

from twin import regions, schema
from twin.sources import common

NAME = "weather"
TITLE = "NOAA/NWS — текущая погода и прогноз для сцен"
LICENSE = "Public Domain (NOAA/NWS)"
API = "https://api.weather.gov"


def _get(ctx, url: str) -> dict:
    r = ctx.session.get(url, timeout=30,
                        headers={"Accept": "application/geo+json"})
    r.raise_for_status()
    return r.json()


def fetch(ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    today = _dt.date.today().isoformat()
    n_obs = 0
    for key, sc in regions.SCENES.items():
        chunk = f"{key}_{today}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(60)
        la, lo = sc.center
        point = _get(ctx, f"{API}/points/{la:.4f},{lo:.4f}")
        props = point["properties"]
        records = []

        # текущее наблюдение ближайшей станции
        stations = _get(ctx, props["observationStations"])
        st_feats = stations.get("features") or []
        if st_feats:
            st_id = st_feats[0]["properties"]["stationIdentifier"]
            obs = _get(ctx, f"{API}/stations/{st_id}/observations/latest")
            op = obs["properties"]
            for var in ("temperature", "windSpeed", "windDirection",
                        "relativeHumidity", "barometricPressure",
                        "visibility"):
                v = (op.get(var) or {}).get("value")
                if v is None:
                    continue
                rec = schema.base_record("obs", f"{API}/stations/{st_id}",
                                         LICENSE, "K")
                rec.update({"id": f"wx:{key}:{st_id}:{var}:{op['timestamp']}",
                            "station": st_id, "t": op["timestamp"],
                            "var": var, "value": float(v),
                            "unit": (op.get(var) or {}).get("unitCode", ""),
                            "scene": key,
                            "text": op.get("textDescription")})
                records.append(rec)

        # прогноз по периодам
        fc = _get(ctx, props["forecast"])
        for p in fc["properties"]["periods"][:8]:
            rec = schema.base_record("obs", props["forecast"], LICENSE, "K")
            rec.update({"id": f"fc:{key}:{p['number']}:{p['startTime']}",
                        "station": "forecast", "t": p["startTime"],
                        "var": "temperature_forecast",
                        "value": float(p["temperature"]),
                        "unit": p["temperatureUnit"],
                        "scene": key,
                        "text": f"{p['name']}: {p['shortForecast']}"})
            records.append(rec)

        files = []
        if records:
            files = [common.write_one_shard(
                "obs", records, out_dir, f"wx_{key}_{today}.parquet")]
        man.mark_chunk(NAME, chunk, rows=len(records), files=files)
        n_obs += len(records)
    return {"status": "done", "note": f"+{n_obs} наблюдений на {today}"}
