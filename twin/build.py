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

# машина времени: границы шкалы, если реестр молчит
CITY_YEAR_MIN = 1850
CITY_YEAR_MAX = 2026
# год лидарной съёмки контуров DataSF (sf16_bldgid): чего в ней нет, а в OSM
# есть — построено позже
LIDAR_SURVEY_YEAR = 2016

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

# Шаг сетки, которую страница рисует. Лидар 3DEP тоньше на порядок, но рельеф
# на экране всё равно сглажен — вершины сверх этого шага только утяжеляют файл.
RENDER_STEP_M = 24.0


def _resample_to(a: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Пересчитать сетку на заданный размер, НЕ сдвигая рамку.

    Обрезать хвост по кратности нельзя: рамка рельефа задана по краям массива,
    и отброшенные строки увели бы весь город на десяток метров. Поэтому сперва
    сглаживаем по масштабу прореживания (иначе холмы пойдут ступенями от
    попадания шага в шаг), затем растягиваем края в края.
    """
    from scipy.ndimage import gaussian_filter, zoom
    if a.shape == (rows, cols):
        return a.astype(np.float32)
    ky, kx = a.shape[0] / rows, a.shape[1] / cols
    if ky > 1.2 or kx > 1.2:
        a = gaussian_filter(a, sigma=(max(0.6, ky * 0.5), max(0.6, kx * 0.5)))
    # mode="nearest" обязателен: по умолчанию zoom считает всё за краем нулём,
    # и от ошибки округления последний столбец выходит нулевым — по восточной
    # и южной кромке сцены встаёт обрыв в море там, где берег.
    return zoom(a, (rows / a.shape[0], cols / a.shape[1]),
                order=1, mode="nearest").astype(np.float32)


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
    """Рельеф сцены: голая земля 3DEP, если она собрана, иначе GLO-30.

    Возвращает (высоты, bbox, вид), где вид — "bare" или "surface". Разница
    не косметическая: GLO-30 меряет то, от чего отразился радар, то есть
    крыши, и в центре города «земля» у неё поднята на высоту застройки.
    """
    bare = os.path.join(DATA_DIR, "bareearth", f"bare_{key}.npz")
    if os.path.exists(bare):
        z = np.load(bare, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        return z["elev"].astype(np.float32), tuple(meta["bbox"]), "bare"
    path = os.path.join(DATA_DIR, "dem", f"scene_{key}.npz")
    if not os.path.exists(path):
        raise FileNotFoundError(f"нет {path} — сначала python3 -m twin.ingest")
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    return z["elev"].astype(np.float32), tuple(meta["bbox"]), "surface"


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


def _point_in_ring(la: float, lo: float, ring: list[tuple[float, float]]) -> bool:
    """Луч вправо по долготе: нечётное число пересечений — точка внутри."""
    inside = False
    n = len(ring)
    for i in range(n):
        la1, lo1 = ring[i]
        la2, lo2 = ring[(i + 1) % n]
        if (la1 > la) != (la2 > la):
            t = (la - la1) / (la2 - la1)
            if lo < lo1 + t * (lo2 - lo1):
                inside = not inside
    return inside


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


def _read_live(scene_key: str) -> dict:
    """Живой слой: борта, спутники, толчки, камеры, прилив — свежий слепок."""
    import pyarrow.parquet as pq
    feats: dict[str, list] = {}
    obs: list[dict] = []
    stamp = ""
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "live", "*.parquet"))):
        pf = pq.ParquetFile(path)
        kind = schema.table_kind(pf.schema_arrow)
        rows = pq.read_table(path).to_pylist()
        # имя чанка кончается меткой времени: берём только самый свежий слепок
        tag = os.path.basename(path).rsplit("_", 1)[-1].split(".")[0]
        stamp = max(stamp, tag)
        for r in rows:
            r["_stamp"] = tag
            if kind == "obs":
                obs.append(r)
            else:
                feats.setdefault(r["fclass"], []).append(r)
    seen_obs, uniq_obs = set(), []
    for r in sorted(obs, key=lambda r: (r["id"], r["_stamp"]), reverse=True):
        if r["id"] in seen_obs:
            continue
        seen_obs.add(r["id"])
        uniq_obs.append(r)
    obs = uniq_obs
    for k in feats:
        # борта/камеры/спутники — только свежий слепок; толчки копятся, но
        # один и тот же толчок приходит в каждом слепке, поэтому по id
        rows = [r for r in feats[k] if r["_stamp"] == stamp or k == "quake"]
        seen, uniq = set(), []
        for r in sorted(rows, key=lambda r: (r["id"], r["_stamp"]), reverse=True):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            uniq.append(r)
        uniq.sort(key=lambda r: r["id"])
        feats[k] = uniq
    return {"feats": feats, "obs": obs, "stamp": stamp}


def _sky_dir(lat0: float, lon0: float, lat: float, lon: float,
             alt_km: float) -> tuple[float, float]:
    """Азимут и высота над горизонтом спутника, как его видно из точки сцены.

    Плоская Земля тут не годится: аппарат за тысячу километров уходит под
    горизонт, и это должно быть видно.
    """
    R = 6371.0
    p = math.pi / 180.0
    # угловое расстояние по поверхности
    d_sigma = math.acos(max(-1.0, min(1.0,
        math.sin(lat0 * p) * math.sin(lat * p)
        + math.cos(lat0 * p) * math.cos(lat * p) * math.cos((lon - lon0) * p))))
    # высота над горизонтом из треугольника «центр Земли — наблюдатель — аппарат»
    rs = R + alt_km
    el = math.atan2(math.cos(d_sigma) - R / rs, math.sin(d_sigma))
    y = math.sin((lon - lon0) * p) * math.cos(lat * p)
    x = (math.cos(lat0 * p) * math.sin(lat * p)
         - math.sin(lat0 * p) * math.cos(lat * p) * math.cos((lon - lon0) * p))
    az = math.atan2(y, x)
    return math.degrees(az), math.degrees(el)


PHOTO_THIN_M = 45.0      # ближе этого второй уличный кадр не нужен
PHOTO_CAP = 9000         # потолок числа кадров в сцене
KV_BASE = "https://api.openstreetcam.org/"


def _thin_photos(rows: list[tuple[float, float, tuple]]) -> list[tuple]:
    """Один кадр на ячейку сетки; если кадров всё равно больше потолка —
    РАСТЯГИВАЕМ ячейку и повторяем.

    Обрезать отсортированный список нельзя: он отсортирован по месту, и
    обрезка выкинула бы целиком восточную половину города.
    """
    step = PHOTO_THIN_M
    for _ in range(12):
        best: dict[tuple[int, int], tuple] = {}
        for x, z, row in rows:
            cell = (int(round(x / step)), int(round(z / step)))
            prev = best.get(cell)
            # свежий кадр вытесняет старый; при равной дате — по адресу, чтобы
            # сборка оставалась детерминированной
            if prev is None or (row[8], row[5]) > (prev[8], prev[5]):
                best[cell] = row
        if len(best) <= PHOTO_CAP:
            return sorted(best.values(), key=lambda r: (r[0], r[1]))
        step *= max(1.15, math.sqrt(len(best) / PHOTO_CAP))
    return sorted(best.values(), key=lambda r: (r[0], r[1]))[:PHOTO_CAP]


def _street_photos(key: str, proj: "Proj", ground: "Ground") -> dict:
    """Уличные снимки сцены: место, курс камеры, адрес кадра, автор, лицензия.

    Кадры остаются у первоисточника — мы везём только адрес. Прореживаем до
    одного на PHOTO_THIN_M: пешеходу нужен ближайший кадр, а не все подряд.
    Снимки Commons (виды зданий, курса нет) не прореживаем — их немного, и
    каждый привязан к своему дому.
    """
    import pyarrow.parquet as pq
    rows: list[tuple[float, float, tuple]] = []
    landmarks: list[tuple] = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "streetlevel", "*.parquet"))):
        if schema.table_kind(pq.ParquetFile(path).schema_arrow) != "feature":
            continue
        for rec in pq.read_table(path).to_pylist():
            if rec.get("scene") != key or rec["fclass"] != "streetphoto":
                continue
            t = json.loads(rec["tags_json"])
            lat, lon = rec["lat"], rec["lon"]
            x, z = proj.xz(lat, lon)
            hdg = t.get("heading")
            row = (
                int(round(x * 10)), int(round(z * 10)),
                int(round(ground.at(lat, lon) * 10)),
                -1 if hdg is None else int(round(float(hdg))) % 360,
                0 if t.get("kind") == "kartaview" else 1,
                str(t.get("thumb") or "").replace(KV_BASE, ""),
                str(t.get("url") or "").replace(KV_BASE, ""),
                str(t.get("author") or "")[:60],
                str(t.get("shot_date") or "")[:10],
                str(rec.get("name") or "")[:90],
                str(t.get("license") or rec.get("license") or "")[:40],
                str(t.get("page") or ""),
            )
            if t.get("kind") != "kartaview":
                landmarks.append(row)
                continue
            rows.append((x, z, row))

    street = _thin_photos(rows)
    landmarks.sort(key=lambda r: (r[0], r[1], r[5]))
    return {
        "base": KV_BASE,
        "items": [list(r) for r in street + landmarks],
        "n_street": len(street), "n_land": len(landmarks),
        "note": "кадры лежат у первоисточника; у каждого автор и лицензия",
    }


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
    elev, dem_bbox, dem_kind = _load_scene_dem(key)
    from scipy.ndimage import gaussian_filter, minimum_filter
    if dem_kind == "bare":
        # 3DEP уже отдал землю без застройки, да ещё в четыре метра шага.
        # Минимум-фильтр тут ВРЕДЕН: он срезал бы настоящие гребни холмов —
        # а холмы и есть лицо этого города. Только лёгкое сглаживание, чтобы
        # снять шум лидара.
        elev = gaussian_filter(elev, sigma=1.2)
    else:
        # GLO-30 — поверхностная модель (DSM): в плотной застройке она вздута
        # крышами. Минимум-фильтр 3×3 (~90 м) прижимает к уровню улиц, лёгкое
        # сглаживание убирает ступени.
        elev = gaussian_filter(minimum_filter(elev, size=3), sigma=0.8)

    # Земля, на которую САДЯТСЯ объекты, берётся в полном разрешении лидара:
    # здание должно стоять на своей отметке, а не на средней по кварталу.
    ground = Ground(elev, dem_bbox)

    # Сетка, которую мы РИСУЕМ, — отдельная и грубее. Лидар даёт 4 метра, это
    # тринадцать миллионов вершин на сцену: страница на сто мегабайт ради
    # рельефа, который на экране всё равно сглажен. Прореживаем до шага,
    # который город переживал и раньше.
    h_m = (dem_bbox[2] - dem_bbox[0]) * M_PER_DEG_LAT
    w_m = (dem_bbox[3] - dem_bbox[1]) * math.cos(math.radians(proj.lat0)) * 111320.0
    want_rows = max(2, min(elev.shape[0], int(round(h_m / RENDER_STEP_M))))
    want_cols = max(2, min(elev.shape[1], int(round(w_m / RENDER_STEP_M))))
    elev = _resample_to(elev, want_rows, want_cols)
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

    # контуры именованных зданий для теста «точка внутри»: bbox соседа
    # захватывает чужие дома, а по многоугольнику наследование года честное
    named_ring = {}
    for r in named:
        rings = _rings(r)
        if rings and len(rings[0]) >= 4:
            named_ring[r["id"]] = rings[0]

    def covered_by_named(rec) -> dict | None:
        """Именованное здание OSM, накрывающее лидарный контур (или None)."""
        cell = (int(rec["lat"] / CELL), int(rec["lon"] / CELL))
        la, lo = rec["lat"], rec["lon"]
        for r in named_grid.get(cell, []):
            if not (r["lat_min"] - 1e-5 <= la <= r["lat_max"] + 1e-5 and
                    r["lon_min"] - 1e-5 <= lo <= r["lon_max"] + 1e-5):
                continue
            ring = named_ring.get(r["id"])
            if ring is None or _point_in_ring(la, lo, ring):
                return r
        return None

    # Предпроход: у именованных зданий OSM тега start_date почти нет, поэтому
    # год они наследуют от накрытых ими лидарных контуров (у тех есть участок
    # в реестре оценщика). Берём самый частый год — башня стоит на одном
    # участке, а разнобой соседних пристроек не должен перевесить.
    inherited: dict[str, dict[int, int]] = {}
    covered_n: dict[str, int] = {}
    for rec in feats:
        if rec["fclass"] != "building" or rec.get("subclass") != "citylidar":
            continue
        host = covered_by_named(rec)
        if host is None:
            continue
        covered_n[host["id"]] = covered_n.get(host["id"], 0) + 1
        blk = json.loads(rec.get("tags_json") or "{}").get("mapblklot")
        y = years.get(blk, (None, None))[0] if blk else None
        if y:
            inherited.setdefault(host["id"], {})
            inherited[host["id"]][y] = inherited[host["id"]].get(y, 0) + 1
    named_year = {k: max(sorted(v), key=lambda y: v[y])
                  for k, v in inherited.items()}
    # Здание, которого НЕТ в лидарной съёмке города, но которое есть в OSM
    # сегодня, построено после этой съёмки. Это уже вывод, а не факт из
    # источника — помечаем ярусом R, чтобы не выдавать за измерение.
    inferred_year = {r["id"]: LIDAR_SURVEY_YEAR + 1 for r in named
                     if r["id"] not in named_year and not covered_n.get(r["id"])}

    big, small = [], []
    for rec in feats:
        if rec["fclass"] != "building":
            continue
        is_lidar = rec.get("subclass") == "citylidar"
        if is_lidar and covered_by_named(rec) is not None:
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
        year, use, year_tier = None, None, "K"
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
            if not year:
                year = named_year.get(rec["id"])
            if not year and rec["id"] in inferred_year:
                year = inferred_year[rec["id"]]
                year_tier = "R"
        if h >= BIG_H or area >= BIG_AREA:
            pts = [[int(round(x * 10)), int(round(z * 10))] for x, z in outer]
            # после квантования соседние точки могут совпасть (в т.ч. первая
            # с последней) — JS-триангуляция такого не прощает
            pts = [p for i, p in enumerate(pts) if p != pts[i - 1]]
            if len(pts) < 3:
                continue
            entry = {
                "p": pts,
                "h": int(round(h * 10)), "g": int(round(g * 10)), "c": cidx,
                "id": rec["id"],
            }
            if rec.get("name"):
                entry["n"] = rec["name"]
            if year:
                entry["y"] = year
                if year_tier != "K":
                    entry["yt"] = year_tier   # год выведен, а не из источника
            big.append(entry)
        elif len(small) < SMALL_CAP:
            cx, cz, hw, hd, ang = _oriented_box(outer)
            small.append([int(round(cx * 10)), int(round(cz * 10)),
                          max(1, int(round(hw * 10))), max(1, int(round(hd * 10))),
                          int(round(math.degrees(ang))) % 180,
                          int(round(h * 10)), int(round(g * 10)), cidx,
                          int(year or 0)])   # 0 = год неизвестен

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

    # ── машина времени: сколько зданий стоит в каждый год ──
    all_years = [b["y"] for b in big if b.get("y")] + [s[8] for s in small if s[8]]
    n_unknown = (len(big) + len(small)) - len(all_years)
    decades = {}
    for y in all_years:
        decades[(y // 10) * 10] = decades.get((y // 10) * 10, 0) + 1
    time_machine = {
        "min": min(all_years) if all_years else CITY_YEAR_MIN,
        "max": max(all_years) if all_years else CITY_YEAR_MAX,
        "known": len(all_years),
        "unknown": n_unknown,
        "inferred": sum(1 for b in big if b.get("yt")),
        # оценщик ставит 1900 там, где настоящий год неизвестен: у соседних
        # годов на порядок меньше записей — это отметка «старое», не дата
        "placeholder_1900": sum(1 for y in all_years if y == 1900),
        "decades": {str(k): v for k, v in sorted(decades.items())},
        "burn_1906": "после пожара 1906 года центр отстроен заново — "
                     "у его зданий год постройки 1906 и позже",
    }

    # ── живой слой ──
    live = _read_live(key)
    lat0, lon0 = sc.center

    air = []
    for rec in live["feats"].get("aircraft", []):
        t = json.loads(rec["tags_json"])
        x, z = proj.xz(rec["lat"], rec["lon"])
        air.append({
            "x": round(x, 1), "z": round(z, 1),
            "alt": round((t.get("alt_ft") or 0) * 0.3048, 1),
            "hdg": round(t.get("track_deg") or 0, 1),
            "v": round((t.get("gs_kt") or 0) * 0.5144, 1),
            "cs": t.get("callsign") or rec["id"].split(":")[-1],
            "ty": t.get("type"), "mil": bool(t.get("military")),
            "gnd": bool(t.get("on_ground")),
        })
    air.sort(key=lambda a: a["cs"])

    sats = []
    for rec in live["feats"].get("satellite", []):
        t = json.loads(rec["tags_json"])
        coords = json.loads(rec["geometry"])["coordinates"]
        alts = t.get("alt_km") or []
        pts = []
        for i, (lo, la) in enumerate(coords):
            alt = alts[i] if i < len(alts) else 500.0
            az, el = _sky_dir(lat0, lon0, la, lo, alt)
            pts.append([round(az, 1), round(el, 1)] if el > -2 else None)
        if not any(p is not None and p[1] > 8 for p in pts):
            continue        # ниже восьми градусов — за крышами, не показываем
        sats.append({
            "n": rec["name"], "id": t.get("norad"),
            "p": pts, "t0": t.get("t0_iso"), "step": t.get("step_s"),
            "alt": round(sum(alts) / len(alts), 0) if alts else None,
            "per": t.get("period_min"),
        })
    sats.sort(key=lambda s: s["n"] or "")

    quakes = []
    for rec in live["feats"].get("quake", []):
        t = json.loads(rec["tags_json"])
        x, z = proj.xz(rec["lat"], rec["lon"])
        quakes.append({"x": round(x, 1), "z": round(z, 1),
                       "m": t.get("mag"), "d": t.get("depth_km"),
                       "pl": t.get("place"), "t": t.get("t_iso")})
    quakes.sort(key=lambda q: q["t"] or "", reverse=True)

    cams = []
    for rec in live["feats"].get("camera", []):
        t = json.loads(rec["tags_json"])
        x, z = proj.xz(rec["lat"], rec["lon"])
        cams.append({"x": round(x, 1), "z": round(z, 1),
                     "g": round(ground.at(rec["lat"], rec["lon"]), 1),
                     "n": rec["name"], "u": t.get("still_url"),
                     "r": t.get("route"), "d": t.get("direction")})
    cams.sort(key=lambda c: c["n"] or "")

    tide = {}
    tobs = [o for o in live["obs"] if o["var"] == "water_level"]
    if tobs:
        tobs.sort(key=lambda o: o["t"])
        tide = {"level_m": round(tobs[-1]["value"], 2), "t": tobs[-1]["t"],
                "station": tobs[-1]["station"]}
    hilo = sorted((o for o in live["obs"] if o["var"].startswith("tide_")),
                  key=lambda o: o["t"])
    if hilo:
        tide["next"] = [{"t": o["t"], "v": round(o["value"], 2),
                         "k": o["var"].split("_")[1]} for o in hilo]

    # аэрофотоснимок: сам файл кладёт в страницу view.py — JPEG уже сжат,
    # заворачивать его в gzip сцены бессмысленно
    aerial = None
    ap = os.path.join(DATA_DIR, "imagery", f"naip_{key}.jpg")
    if os.path.exists(ap):
        from PIL import Image
        with Image.open(ap) as im:
            aerial = {"path": os.path.relpath(ap, DATA_DIR),
                      "w": im.width, "h": im.height,
                      "bbox": list(sc.bbox),
                      "source": "USDA NAIP · Microsoft Planetary Computer"}

    photos = _street_photos(key, proj, ground)

    # ── синтетические жители: люди в городе, но ни один не настоящий ──
    residents = []
    import pyarrow.parquet as pq
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "people", "*.parquet"))):
        if schema.table_kind(pq.ParquetFile(path).schema_arrow) != "feature":
            continue
        for rec in pq.read_table(path).to_pylist():
            if rec.get("scene") != key or rec["fclass"] != "resident":
                continue
            t = json.loads(rec["tags_json"])
            x, z = proj.xz(rec["lat"], rec["lon"])
            residents.append([
                int(round(x * 10)), int(round(z * 10)),
                int(round(ground.at(rec["lat"], rec["lon"]) * 10)),
                t.get("age", 30), t.get("household", 1),
                t.get("tenure", ""), t.get("commute", ""), t.get("sector", ""),
            ])
    residents.sort(key=lambda r: (r[0], r[1], r[3]))

    wx = _latest_weather(key)
    head = {
        "key": key, "title": sc.title, "date": schema.today(),
        "center": list(sc.center), "bbox": list(sc.bbox),
        # проекция сцены наружу: обозревателю нужно уметь и обратно, из метров
        # в широту-долготу, — иначе не спросить Google про эту самую точку
        "proj": {"lat0": proj.lat0, "lon0": proj.lon0,
                 "kx": proj.kx, "kz": proj.kz},
        "utc_offset": sc.utc_offset,
        "counts": {"big": len(big), "small": len(small), "roads": len(roads),
                   "lakes": len(lakes), "pois": len(poi_out)},
        "weather": wx,
        "time_machine": time_machine,
        "aerial": aerial,
        "terrain_src": (
            {"kind": "bare", "name": "USGS 3DEP — голая земля",
             "note": "земля без застройки, шаг ~4 м"}
            if dem_kind == "bare" else
            {"kind": "surface", "name": "Copernicus GLO-30",
             "note": "модель поверхности: в центре города земля вздута крышами"}
        ),
        "people": {"n": len(residents),
                   "note": "синтетические жители: население квартала измерено "
                           "переписью, сам житель — реконструкция (ярус R); "
                           "никто из них не соответствует живому человеку"},
        "photos": {"street": photos["n_street"], "land": photos["n_land"],
                   "note": photos["note"]},
        "live": {"stamp": live["stamp"], "tide": tide,
                 "counts": {"aircraft": len(air), "sats": len(sats),
                            "quakes": len(quakes), "cams": len(cams)}},
        "sources": [
            ({"name": "USGS 3DEP (голая земля)", "license": "Public Domain"}
             if dem_kind == "bare" else
             {"name": "Copernicus DEM GLO-30", "license": "ESA, свободно с атрибуцией"}),
            {"name": "KartaView (уличная съёмка)", "license": "CC BY-SA 4.0"},
            {"name": "OpenStreetMap", "license": "ODbL-1.0"},
            {"name": "DataSF (лидар + реестр оценщика)", "license": "PDDL/ODC"},
            {"name": "NOAA/NWS", "license": "Public Domain"},
            {"name": "US Census Bureau", "license": "Public Domain"},
        ],
    }

    payload = {"head": head, "terrain": terrain,
               "big": big, "small": small, "roads": roads,
               "lakes": lakes, "pois": poi_out,
               "air": air, "sats": sats, "quakes": quakes, "cams": cams,
               "res": residents, "photos": photos}
    os.makedirs(BUILD_DIR, exist_ok=True)
    out = os.path.join(BUILD_DIR, f"scene_{key}.json.gz")
    raw = json.dumps(payload, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    with gzip.open(out, "wb", compresslevel=9) as f:
        f.write(raw)
    print(f"сцена {key}: зданий {len(big)}+{len(small)}, дорог {len(roads)}, "
          f"озёр {len(lakes)}, POI {len(poi_out)}; живое: бортов {len(air)}, "
          f"спутников {len(sats)}, толчков {len(quakes)}, камер {len(cams)}, "
          f"снимков улиц {photos['n_street']}+{photos['n_land']}"
          + (f", прилив {tide['level_m']} м" if tide else "") + "; "
          f"json {len(raw)/1e6:.1f} МБ -> {os.path.getsize(out)/1e6:.1f} МБ gz")
    return out


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "sf"
    build_scene(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
