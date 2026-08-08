"""
TERRA-Твин — офлайн-проверки (без сети): схема, проекция, геометрия,
мозаика рельефа, разбор высот OSM.

Запуск:  cd terra && python3 -m tests.test_twin
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twin import build as tb  # noqa: E402
from twin import regions, schema  # noqa: E402
from twin.sources import common as tc  # noqa: E402
from twin.sources.dem import _downsample, crop_mosaic  # noqa: E402

_FAILS: list[str] = []
_RUN = 0


def check(name: str, cond, detail: str = ""):
    global _RUN
    _RUN += 1
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        _FAILS.append(name)


def section(t):
    print(f"\n── {t} " + "─" * max(0, 58 - len(t)))


def test_schema():
    section("схема твина")
    rec = schema.base_record("feature", "https://osm.org", "ODbL-1.0", "K")
    rec.update({"id": "osm:way/1", "fclass": "building", "geometry": "{}",
                "lat": 37.7, "lon": -122.4, "lat_min": 37.7, "lon_min": -122.5,
                "lat_max": 37.8, "lon_max": -122.3})
    check("валидная запись проходит", schema.validate_record("feature", rec) == [])
    bad = dict(rec)
    bad["tier"] = "X"
    check("чужой tier ловится", schema.validate_record("feature", bad) != [])
    bad2 = dict(rec)
    del bad2["geometry"]
    check("пропавшее поле ловится", schema.validate_record("feature", bad2) != [])
    bad3 = dict(rec)
    bad3["lat"] = 91.0
    check("широта 91 ловится", schema.validate_record("feature", bad3) != [])
    try:
        schema.base_record("nonsense", "x", "y", "K")
        check("неизвестный kind отвергается", False)
    except ValueError:
        check("неизвестный kind отвергается", True)


def test_heights():
    section("высоты OSM")
    h, s = tc.parse_height({"height": "25"})
    check("height=25 → 25 м", abs(h - 25) < 0.01 and s == "height")
    h, s = tc.parse_height({"height": "25 m"})
    check("'25 m' понимается", abs(h - 25) < 0.01)
    h, s = tc.parse_height({"height": "82 ft"})
    check("футы переводятся", abs(h - 24.99) < 0.05, f"{h}")
    h, s = tc.parse_height({"building:levels": "10"})
    check("10 этажей → 32 м", abs(h - 32.0) < 0.01 and s == "levels")
    h, s = tc.parse_height({})
    check("без данных — дефолт", h == tc.DEFAULT_H and s == "default")
    h, s = tc.parse_height({"height": "мусор", "building:levels": "3"})
    check("мусор в height → этажи", s == "levels")


def test_projection():
    section("проекция сцены")
    sc = regions.scene("sf")
    proj = tb.Proj(sc)
    x, z = proj.xz(*sc.center)
    check("центр в нуле", abs(x) < 0.01 and abs(z) < 0.01)
    x, z = proj.xz(sc.center[0], sc.center[1] + 0.01)
    check("0.01° на восток ≈ 880 м", 850 < x < 910 and abs(z) < 0.01, f"{x:.0f}")
    x, z = proj.xz(sc.center[0] + 0.01, sc.center[1])
    check("0.01° на север → z<0", abs(z + 1111) < 15 and abs(x) < 0.01, f"{z:.0f}")


def test_geometry():
    section("геометрия зданий")
    sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    check("площадь квадрата 10×10", abs(tb._area_m2(sq) - 100.0) < 1e-6)
    cx, cz, hw, hd, ang = tb._oriented_box(sq)
    check("бокс квадрата: центр (5,5)", abs(cx - 5) < 0.01 and abs(cz - 5) < 0.01)
    check("бокс квадрата: полуоси 5×5", abs(hw - 5) < 0.01 and abs(hd - 5) < 0.01)
    a = math.radians(30)
    rot = [(math.cos(a) * x - math.sin(a) * z, math.sin(a) * x + math.cos(a) * z)
           for x, z in [(-6.0, -2.0), (6.0, -2.0), (6.0, 2.0), (-6.0, 2.0)]]
    cx, cz, hw, hd, ang = tb._oriented_box(rot)
    dims = sorted([hw, hd])
    check("повёрнутый прямоугольник 12×4 восстановлен",
          abs(dims[0] - 2) < 0.05 and abs(dims[1] - 6) < 0.05,
          f"{dims}")
    check("центр повёрнутого в нуле", abs(cx) < 0.01 and abs(cz) < 0.01)


def test_raster_fill():
    section("скан-заливка полигонов")
    m = np.zeros((10, 10), dtype=np.uint8)
    ring = [(2.0, 2.0), (2.0, 8.0), (8.0, 8.0), (8.0, 2.0), (2.0, 2.0)]
    tb._raster_fill(m, [ring], 1)
    check("квадрат заполнен", m[3:7, 3:7].all() and m.sum() == 36, f"{m.sum()}")
    check("вне квадрата пусто", m[0, 0] == 0 and m[9, 9] == 0)


def test_ground():
    section("рельеф: билинейная выборка")
    elev = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    g = tb.Ground(elev, (37.0, -123.0, 38.0, -122.0))
    check("угол северо-запад", abs(g.at(38.0, -123.0) - 0.0) < 0.01)
    check("угол юго-восток", abs(g.at(37.0, -122.0) - 30.0) < 0.01)
    check("середина усредняется", abs(g.at(37.5, -122.5) - 15.0) < 0.01)


def test_mosaic():
    section("мозаика DEM")
    def tile_of(lat0, lon0):
        return np.full((3600, 3600), float(lat0 * 1000 - lon0), dtype=np.float32)
    crop = crop_mosaic((37.5, -123.5, 38.5, -122.5), tile_of)
    check("размер выреза 1°×1°", crop.shape == (3600, 3600), f"{crop.shape}")
    check("северо-запад из тайла N38 W124",
          abs(float(crop[0, 0]) - (38 * 1000 + 124)) < 0.01, f"{crop[0,0]}")
    check("юго-восток из тайла N37 W123",
          abs(float(crop[-1, -1]) - (37 * 1000 + 123)) < 0.01, f"{crop[-1,-1]}")
    d = _downsample(np.arange(16, dtype=np.float32).reshape(4, 4), 2)
    check("даунсэмпл усредняет", d.shape == (2, 2) and abs(d[0, 0] - 2.5) < 0.01)


def test_point_in_ring():
    section("точка внутри контура")
    sq = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
    check("центр внутри", tb._point_in_ring(5.0, 5.0, sq))
    check("снаружи справа", not tb._point_in_ring(5.0, 15.0, sq))
    check("снаружи сверху", not tb._point_in_ring(15.0, 5.0, sq))
    check("снаружи слева", not tb._point_in_ring(5.0, -1.0, sq))
    # П-образный контур: точка в вырезе снаружи, хотя внутри bbox
    u = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 6.0),
         (4.0, 6.0), (4.0, 4.0), (10.0, 4.0), (10.0, 0.0)]
    check("вырез буквы П — снаружи", not tb._point_in_ring(7.0, 5.0, u))
    check("тело буквы П — внутри", tb._point_in_ring(2.0, 5.0, u))


def test_time_machine():
    section("машина времени")
    check("год лидарной съёмки задан", 2000 < tb.LIDAR_SURVEY_YEAR < 2030)
    check("границы шкалы разумны",
          tb.CITY_YEAR_MIN < 1900 < tb.CITY_YEAR_MAX)
    # назначение участка -> цветовой класс
    check("жильё -> класс 0", tb._use_color("Single Family Residential") == 0)
    check("контора -> класс 1", tb._use_color("Commercial Retail") == 1)
    check("склад -> класс 2", tb._use_color("Industrial") == 2)
    check("пусто -> прочее", tb._use_color(None) == 5)


def test_sky_dir():
    section("небо: азимут и высота спутника")
    # прямо над головой — высота 90°
    az, el = tb._sky_dir(37.77, -122.42, 37.77, -122.42, 500.0)
    check("зенит даёт 90°", abs(el - 90) < 0.5, f"{el:.1f}")
    # на север от наблюдателя — азимут около 0
    az, el = tb._sky_dir(37.0, -122.0, 40.0, -122.0, 500.0)
    check("север — азимут ≈ 0", abs(az) < 1.0, f"{az:.1f}")
    check("в трёхстах км высота меньше зенита", 0 < el < 60, f"{el:.1f}")
    # на восток
    az, el = tb._sky_dir(37.0, -122.0, 37.0, -119.0, 500.0)
    check("восток — азимут ≈ 90", abs(az - 90) < 2.0, f"{az:.1f}")
    # далёкий аппарат уходит под горизонт
    az, el = tb._sky_dir(37.0, -122.0, 10.0, -122.0, 500.0)
    check("за три тысячи км — под горизонтом", el < 0, f"{el:.1f}")
    # чем выше орбита, тем дольше виден
    _, el_low = tb._sky_dir(37.0, -122.0, 41.0, -122.0, 400.0)
    _, el_high = tb._sky_dir(37.0, -122.0, 41.0, -122.0, 20000.0)
    check("высокая орбита видна лучше", el_high > el_low,
          f"{el_low:.1f} vs {el_high:.1f}")


def test_forecast():
    section("прогнозы и их проверка")
    from twin import forecast as fc

    # каталог с ЗАДАННЫМ b: проверяем, что оценка его возвращает
    import random as _r
    rnd = _r.Random(7)
    for true_b in (0.8, 1.0, 1.3):
        mags = [fc.M_COMPLETE - math.log10(rnd.random()) / true_b
                for _ in range(6000)]
        got, n = fc.b_value(mags)
        check(f"b={true_b} восстанавливается", abs(got - true_b) < 0.06,
              f"вышло {got:.3f} по {n}")

    check("на пустом каталоге b не выдумывается",
          fc.b_value([]) [0] != fc.b_value([])[0])   # NaN != NaN

    # вероятность растёт со сроком и падает с магнитудой
    mags = [fc.M_COMPLETE - math.log10(rnd.random()) / 1.0 for _ in range(2000)]
    p30 = fc.quake_probability(mags, 365, 4.0, 30)["p"]
    p90 = fc.quake_probability(mags, 365, 4.0, 90)["p"]
    p5 = fc.quake_probability(mags, 365, 5.0, 30)["p"]
    check("дольше срок — выше вероятность", p90 > p30, f"{p30:.3f} vs {p90:.3f}")
    check("выше магнитуда — ниже вероятность", p5 < p30, f"{p5:.3f} vs {p30:.3f}")
    check("вероятность в пределах [0,1]", 0 <= p30 <= 1 and 0 <= p90 <= 1)
    check("редкий толчок за год реже чем наверняка",
          fc.quake_probability(mags, 365, 7.0, 365)["p"] < 0.5)
    check("скудный каталог не даёт прогноза",
          fc.quake_probability([1.6, 2.0], 30, 4.0, 30)["p"] is None)


def test_people():
    section("синтетические жители")
    from twin import people as tp
    import random as _r
    rnd = _r.Random(3)
    # доли распределений должны складываться в единицу
    for name, tbl in (("возраст", [(a, b, w) for a, b, w in tp.AGE_BANDS]),
                      ("домохозяйства", tp.HOUSEHOLD_SIZES),
                      ("поездки", tp.COMMUTE), ("занятость", tp.SECTORS)):
        w = sum(t[-1] for t in tbl)
        check(f"доли {name} дают 1.0", abs(w - 1.0) < 0.02, f"{w:.3f}")
    ages = [tp._age(rnd) for _ in range(20000)]
    med = sorted(ages)[len(ages) // 2]
    check("медианный возраст выборки как в городе", 33 <= med <= 44, f"{med}")
    check("возраст в разумных границах", 0 <= min(ages) and max(ages) <= 95)
    kids = sum(1 for a in ages if a < 18) / len(ages)
    check("детей около 13 %", 0.10 <= kids <= 0.16, f"{kids:.3f}")
    # выбор из таблицы устойчив к сиду: тот же сид — тот же человек
    a = [tp._pick(_r.Random(9), tp.SECTORS) for _ in range(5)]
    b = [tp._pick(_r.Random(9), tp.SECTORS) for _ in range(5)]
    check("выбор детерминирован сидом", a == b)
    check("жилая доля жилого дома выше складской",
          tp.RESIDENTIAL_SHARE[0] > tp.RESIDENTIAL_SHARE[2])


def test_regions():
    section("регионы")
    sc = regions.scene("sf")
    r = regions.region_of(sc)
    check("сцена внутри региона",
          r.bbox[0] <= sc.bbox[0] and sc.bbox[2] <= r.bbox[2]
          and r.bbox[1] <= sc.bbox[1] and sc.bbox[3] <= r.bbox[3])
    check("девять округов", len(r.counties_fips) == 9)
    try:
        regions.scene("nope")
        check("чужая сцена отвергается", False)
    except KeyError:
        check("чужая сцена отвергается", True)


def main():
    print("TERRA-Твин — проверки\n" + "=" * 64)
    test_schema()
    test_heights()
    test_projection()
    test_geometry()
    test_raster_fill()
    test_ground()
    test_mosaic()
    test_point_in_ring()
    test_time_machine()
    test_sky_dir()
    test_forecast()
    test_people()
    test_regions()
    print("\n" + "=" * 64)
    if _FAILS:
        print(f"ПРОВАЛЕНО {len(_FAILS)} из {_RUN}:")
        for f in _FAILS:
            print("   ·", f)
        sys.exit(1)
    print(f"все {_RUN} проверок пройдены")


if __name__ == "__main__":
    main()
