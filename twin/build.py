# Компилятор сцены твина: twin/data/* -> twin/data/build/scene_<key>.json.gz
#
# Берёт рельеф (npz), объекты OSM (parquet) и погоду, проецирует в локальные
# метры сцены (x — восток, z — юг, y — вверх), квантует в дециметры и пакует
# один самодостаточный JSON для 3D-обозревателя (twin/view.py).
# Детерминизм: обход файлов и записей всюду отсортирован.
#
#   python3 -m twin.build sf

from __future__ import annotations

import glob
import gzip
import json
import math
import os
import sys

import numpy as np

from twin import regions, schema
from twin.state import DATA_DIR

BUILD_DIR = os.path.join(DATA_DIR, "build")

# здания: порог «крупного» (настоящий контур, а не коробка)
BIG_H = 25.0            # м высоты
BIG_AREA = 2000.0       # м² подошвы
SMALL_CAP = 260_000     # предохранитель на число мелких

# классы дорог: ширина в метрах (0 = не рисуем геометрией)
ROAD_W = {
    "motorway": 18.0, "motorway_link": 9.0, "trunk": 15.0, "trunk_link": 8.0,
    "primary": 12.0, "primary_link": 7.0, "secondary": 9.0,
    "secondary_link": 6.0, "tertiary": 7.0, "tertiary_link": 5.0,
    "residential": 5.5, "unclassified": 5.0, "living_street": 4.5,
    "service": 3.5, "pedestrian": 4.0, "footway": 1.8, "path": 1.5,
    "cycleway": 2.0, "steps": 1.8, "track": 2.5,
}

# цветовые классы зданий (индексы палитры в JS)
_B_COLOR = {
    "residential": 0, "house": 0, "apartments": 0, "detached": 0,
    "semidetached_house": 0, "bungalow": 0, "dormitory": 0,
    "commercial": 1, "retail": 1, "office": 1, "hotel": 1, "supermarket": 1,
    "industrial": 2, "warehouse": 2, "garage": 2, "garages": 2, "hangar": 2,
    "church": 3, "cathedral": 3, "chapel": 3, "temple": 3, "synagogue": 3,
    "mosque": 3, "civic": 3, "public": 3, "government": 3, "museum": 3,
    "school": 4, "university": 4, "college": 4, "kindergarten": 4,
    "hospital": 4,
}

M_PER_DEG_LAT = 111132.0


class Proj:
    """Локальная проекция сцены: метры от центра; x — восток, z — юг."""

    def __init__(self, sc: regions.Scene):
        self.lat0, self.lon0 = sc.center
        self.kx = math.cos(math.radians(self.lat0)) * 111320.0
        self.kz = M_PER_DEG_LAT

    def xz(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lon - self.lon0) * self.kx, (self.lat0 - lat) * self.kz)


class Ground:
    """Билинейная высота рельефа по широте-долготе."""

    def __init__(self, elev: np.ndarray, bbox):
        self.e = elev
        self.lat_min, self.lon_min, self.lat_max, self.lon_max = bbox
        self.rows, self.cols = elev.shape

    def at(self, lat: float, lon: float) -> float:
        fr = (self.lat_max - lat) / (self.lat_max - self.lat_min) * (self.rows - 1)
        fc = (lon - self.lon_min) / (self.lon_max - self.lon_min) * (self.cols - 1)
        r0 = min(max(int(fr), 0), self.rows - 2)
        c0 = min(max(int(fc), 0), self.cols - 2)
        tr, tc = fr - r0, fc - c0
        tr = min(max(tr, 0.0), 1.0); tc = min(max(tc, 0.0), 1.0)
        e = self.e
        return float(e[r0, c0] * (1 - tr) * (1 - tc) + e[r0 + 1, c0] * tr * (1 - tc)
                     + e[r0, c0 + 1] * (1 - tr) * tc + e[r0 + 1, c0 + 1] * tr * tc)


def _load_scene_dem(key: str):
    path = os.path.join(DATA_DIR, "dem", f"scene_{key}.npz")
    if not os.path.exists(path):
        raise FileNotFoundError(f"нет {path} — сначала python3 -m twin.ingest")
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    return z["elev"].astype(np.float32), tuple(meta["bbox"])


def _read_features(scene_key: str) -> list[dict]:
    import pyarrow.parquet as pq
    recs = []
    for src in ("osm", "sfbuildings"):
        for path in sorted(glob.glob(os.path.join(DATA_DIR, src, "*.parquet"))):
            if schema.table_kind(pq.ParquetFile(path).schema_arrow) != "feature":
                continue
            tbl = pq.read_table(path)
            for rec in tbl.to_pylist():
                if rec.get("scene") in (scene_key, None):
                    recs.append(rec)
    recs.sort(key=lambda r: r["id"])
    # дедупликация: один объект может попасть в два чанка-bbox
    seen, out = set(), []
    for r in recs:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append(r)
    return out


def _read_years() -> dict[str, tuple[int | None, str | None]]:
    """Реестр оценщика: mapblklot -> (год постройки, назначение участка)."""
    import pyarrow.parquet as pq
    out: dict[str, tuple[int | None, str | None]] = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "sfbuildings",
                                              "roll_*.parquet"))):
        if schema.table_kind(pq.ParquetFile(path).schema_arrow) != "obs":
            continue
        for rec in pq.read_table(path).to_pylist():
            blk = rec["id"].split(":", 1)[1]
            y = int(rec["value"]) if rec["value"] else None
            if blk not in out:
                out[blk] = (y, rec.get("text"))
    return out


# назначение участка (реестр оценщика) -> цветовой класс
def _use_color(use: str | None) -> int:
    u = (use or "").lower()
    if "residential" in u or "dwelling" in u or "apartment" in u:
        return 0
    if "commercial" in u or "office" in u or "hotel" in u or "shop" in u:
        return 1
    if "industrial" in u or "warehouse" in u or "garage" in u:
        return 2
    if "government" in u or "church" in u or "institution" in u:
        return 3
    if "school" in u or "hospital" in u:
        return 4
    return 5


def _rings(rec: dict) -> list[list[tuple[float, float]]]:
    gj = json.loads(rec["geometry"])
    if gj["type"] == "Polygon":
        return [[(la, lo) for lo, la in ring] for ring in gj["coordinates"]]
    if gj["type"] == "LineString":
        return [[(la, lo) for lo, la in gj["coordinates"]]]
    return []


def _area_m2(pts_xz: list[tuple[float, float]]) -> float:
    s = 0.0
    n = len(pts_xz)
    for i in range(n):
        x1, z1 = pts_xz[i]
        x2, z2 = pts_xz[(i + 1) % n]
        s += x1 * z2 - x2 * z1
    return abs(s) / 2.0


def _oriented_box(pts: list[tuple[float, float]]):
    """Прямоугольник по доминирующему ребру: центр, полуоси, угол (рад)."""
    best_len, ang = 0.0, 0.0
    for i in range(len(pts) - 1):
        dx = pts[i + 1][0] - pts[i][0]
        dz = pts[i + 1][1] - pts[i][1]
        l2 = dx * dx + dz * dz
        if l2 > best_len:
            best_len, ang = l2, math.atan2(dz, dx)
    ca, sa = math.cos(-ang), math.sin(-ang)
    us = [p[0] * ca - p[1] * sa for p in pts]
    vs = [p[0] * sa + p[1] * ca for p in pts]
    cu = (min(us) + max(us)) / 2
    cv = (min(vs) + max(vs)) / 2
    cx = cu * math.cos(ang) - cv * math.sin(ang)
    cz = cu * math.sin(ang) + cv * math.cos(ang)
    return cx, cz, (max(us) - min(us)) / 2, (max(vs) - min(vs)) / 2, ang


def _raster_fill(mask: np.ndarray, rings_rc: list[list[tuple[float, float]]],
                 value: int) -> None:
    """Скан-заливка полигона (кольца в координатах строк-столбцов растра)."""
    rows, cols = mask.shape
    if not rings_rc:
        return
    r_lo = max(0, int(min(r for ring in rings_rc for r, _ in ring)))
    r_hi = min(rows - 1, int(max(r for ring in rings_rc for r, _ in ring)) + 1)
    for r in range(r_lo, r_hi + 1):
        y = r + 0.5
        xs = []
        for ring in rings_rc:
            n = len(ring)
            for i in range(n - 1):
                r1, c1 = ring[i]
                r2, c2 = ring[i + 1]
                if (r1 <= y < r2) or (r2 <= y < r1):
                    t = (y - r1) / (r2 - r1)
                    xs.append(c1 + t * (c2 - c1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            c0 = max(0, int(math.ceil(xs[i] - 0.5)))
            c1 = min(cols - 1, int(math.floor(xs[i + 1] - 0.5)))
            if c1 >= c0:
                mask[r, c0:c1 + 1] = value


def _latest_weather(scene_key: str) -> dict:
    import pyarrow.parquet as pq
    out = {}
    paths = sorted(glob.glob(os.path.join(DATA_DIR, "weather", "*.parquet")))
    rows = []
    for path in paths:
        tbl = pq.read_table(path)
        rows.extend(r for r in tbl.to_pylist() if r.get("scene") == scene_key)
    if not rows:
        return out
    obs = [r for r in rows if r["station"] != "forecast"]
    obs.sort(key=lambda r: r["t"])
    for r in obs:
        if r["var"] == "temperature":
            out["temp_c"] = round(r["value"], 1)
        if r["var"] == "windSpeed":
            out["wind_kmh"] = round(r["value"], 1)
        if r.get("text"):
            out["text"] = r["text"]
        out["station"] = r["station"]
        out["t"] = r["t"]
    fc = [r for r in rows if r["station"] == "forecast"]
    fc.sort(key=lambda r: r["t"])
    if fc:
        out["forecast"] = fc[0].get("text")
    return out


def build_scene(key: str) -> str:
    sc = regions.scene(key)
    proj = Proj(sc)
    elev, dem_bbox = _load_scene_dem(key)
    # GLO-30 — поверхностная модель (DSM): в плотной застройке она вздута
    # крышами. Минимум-фильтр 3×3 (~90 м) прижимает к уровню улиц, лёгкое
    # сглаживание убирает ступени. Правильное решение — USGS 1 м DTM (фаза 2).
    from scipy.ndimage import gaussian_filter, minimum_filter
    elev = gaussian_filter(minimum_filter(elev, size=3), sigma=0.8)
    ground = Ground(elev, dem_bbox)
    feats = _read_features(key)

    lat_min, lon_min, lat_max, lon_max = dem_bbox
    rows, cols = elev.shape

    def to_rc(la, lo):
        return ((lat_max - la) / (lat_max - lat_min) * rows,
                (lo - lon_min) / (lon_max - lon_min) * cols)

    # ── классовый растр поверхности: 0 земля, 1 зелень, 2 песок, 3 вода ──
    surf = np.zeros((rows, cols), dtype=np.uint8)
    for rec in feats:
        if rec["fclass"] == "green":
            val = 2 if rec.get("subclass") in ("sand", "beach") else 1
            rr = [[to_rc(la, lo) for la, lo in ring] for ring in _rings(rec)]
            rr = [r for r in rr if len(r) >= 4 and r[0] == r[-1]]
            _raster_fill(surf, rr, val)
    for rec in feats:
        if rec["fclass"] == "water":
            rr = [[to_rc(la, lo) for la, lo in ring] for ring in _rings(rec)]
            rr = [r for r in rr if len(r) >= 4 and r[0] == r[-1]]
            _raster_fill(surf, rr, 3)
    surf[elev <= 0.0] = 3   # океан и залив

    # ── здания: именованные OSM (подписи) + городской лидар (масса) ──
    years = _read_years()
    named = [r for r in feats
             if r["fclass"] == "building" and r.get("subclass") != "citylidar"]
    # сетка-индекс bbox именованных зданий для дедупликации лидарных контуров
    CELL = 0.0005          # ~50 м
    named_grid: dict[tuple[int, int], list[dict]] = {}
    for r in named:
        for gy in range(int(r["lat_min"] / CELL), int(r["lat_max"] / CELL) + 1):
            for gx in range(int(r["lon_min"] / CELL) - 1,
                            int(r["lon_max"] / CELL) + 1):
                named_grid.setdefault((gy, gx), []).append(r)

    def covered_by_named(rec) -> bool:
        cell = (int(rec["lat"] / CELL), int(rec["lon"] / CELL))
        for r in named_grid.get(cell, []):
            if (r["lat_min"] - 1e-5 <= rec["lat"] <= r["lat_max"] + 1e-5 and
                    r["lon_min"] - 1e-5 <= rec["lon"] <= r["lon_max"] + 1e-5):
                return True
        return False

    big, small = [], []
    for rec in feats:
        if rec["fclass"] != "building":
            continue
        is_lidar = rec.get("subclass") == "citylidar"
        if is_lidar and covered_by_named(rec):
            continue
        rings = _rings(rec)
        if not rings or len(rings[0]) < 4 or rings[0][0] != rings[0][-1]:
            continue
        outer = [proj.xz(la, lo) for la, lo in rings[0][:-1]]
        if len(outer) < 3:
            continue
        area = _area_m2(outer)
        if area < 4.0:
            continue
        h = float(rec.get("height_m") or 5.0)
        g = ground.at(rec["lat"], rec["lon"])
        tags = json.loads(rec.get("tags_json") or "{}")
        year, use = None, None
        blk = tags.get("mapblklot")
        if blk and blk in years:
            year, use = years[blk]
        if is_lidar:
            cidx = _use_color(use)
        else:
            cidx = _B_COLOR.get(rec.get("subclass") or "", 5)
            sd = tags.get("start_date")
            if sd:
                for tok in str(sd).replace("-", " ").split():
                    if tok.isdigit() and len(tok) == 4:
                        year = int(tok)
                        break
        if h >= BIG_H or area >= BIG_AREA:
            entry = {
                "p": [[int(round(x * 10)), int(round(z * 10))] for x, z in outer],
                "h": int(round(h * 10)), "g": int(round(g * 10)), "c": cidx,
                "id": rec["id"],
            }
            if rec.get("name"):
                entry["n"] = rec["name"]
            if year:
                entry["y"] = year
            big.append(entry)
        elif len(small) < SMALL_CAP:
            cx, cz, hw, hd, ang = _oriented_box(outer)
            small.append([int(round(cx * 10)), int(round(cz * 10)),
                          max(1, int(round(hw * 10))), max(1, int(round(hd * 10))),
                          int(round(math.degrees(ang))) % 180,
                          int(round(h * 10)), int(round(g * 10)), cidx])

    # ── дороги ──
    roads = []
    for rec in feats:
        if rec["fclass"] != "road":
            continue
        w = ROAD_W.get(rec.get("subclass") or "", 0.0)
        if w <= 0.0:
            continue
        for line in _rings(rec):
            pts = [proj.xz(la, lo) for la, lo in line]
            if len(pts) < 2:
                continue
            roads.append({
                "w": int(round(w * 10)),
                "p": [[int(round(x * 10)), int(round(z * 10))] for x, z in pts],
            })

    # ── озёра как плоские полигоны на своей высоте ──
    lakes = []
    for rec in feats:
        if rec["fclass"] != "water":
            continue
        rings = _rings(rec)
        if not rings or len(rings[0]) < 4 or rings[0][0] != rings[0][-1]:
            continue
        g = ground.at(rec["lat"], rec["lon"])
        if g <= 1.0:
            continue        # залив и океан рисует водная гладь
        outer = [proj.xz(la, lo) for la, lo in rings[0][:-1]]
        lakes.append({
            "p": [[int(round(x * 10)), int(round(z * 10))] for x, z in outer],
            "g": int(round((g + 0.3) * 10)),
        })

    # ── POI: ближе к центру и с именем — вперёд ──
    pois = []
    for rec in feats:
        if rec["fclass"] != "poi" or not rec.get("name"):
            continue
        x, z = proj.xz(rec["lat"], rec["lon"])
        pois.append((x * x + z * z, rec["name"], rec.get("subclass") or "",
                     x, z))
    pois.sort(key=lambda p: (p[0], p[1]))
    poi_out = [[int(round(x * 10)), int(round(z * 10)), name, kind]
               for _, name, kind, x, z in pois[:400]]

    # ── рельеф: западный/северный край в локальных метрах ──
    x_w, z_n = proj.xz(lat_max, lon_min)
    x_e, z_s = proj.xz(lat_min, lon_max)
    terrain = {
        "x0": int(round(x_w * 10)), "z0": int(round(z_n * 10)),
        "dx": (x_e - x_w) / (cols - 1) * 10.0,
        "dz": (z_s - z_n) / (rows - 1) * 10.0,
        "nx": cols, "nz": rows,
        "elev": np.round(elev * 10).astype(np.int32).clip(-32000, 32000)
                  .astype(np.int16).flatten().tolist(),
        "surf": surf.flatten().tolist(),
    }

    wx = _latest_weather(key)
    head = {
        "key": key, "title": sc.title, "date": schema.today(),
        "center": list(sc.center), "bbox": list(sc.bbox),
        "utc_offset": sc.utc_offset,
        "counts": {"big": len(big), "small": len(small), "roads": len(roads),
                   "lakes": len(lakes), "pois": len(poi_out)},
        "weather": wx,
        "sources": [
            {"name": "Copernicus DEM GLO-30", "license": "ESA, свободно с атрибуцией"},
            {"name": "OpenStreetMap", "license": "ODbL-1.0"},
            {"name": "NOAA/NWS", "license": "Public Domain"},
            {"name": "US Census Bureau", "license": "Public Domain"},
        ],
    }

    payload = {"head": head, "terrain": terrain,
               "big": big, "small": small, "roads": roads,
               "lakes": lakes, "pois": poi_out}
    os.makedirs(BUILD_DIR, exist_ok=True)
    out = os.path.join(BUILD_DIR, f"scene_{key}.json.gz")
    raw = json.dumps(payload, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    with gzip.open(out, "wb", compresslevel=9) as f:
        f.write(raw)
    print(f"сцена {key}: зданий {len(big)}+{len(small)}, дорог {len(roads)}, "
          f"озёр {len(lakes)}, POI {len(poi_out)}; "
          f"json {len(raw)/1e6:.1f} МБ -> {os.path.getsize(out)/1e6:.1f} МБ gz")
    return out


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "sf"
    build_scene(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
