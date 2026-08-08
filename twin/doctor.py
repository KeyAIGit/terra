# Самопроверка твина: python3 -m twin.doctor [--examples]
#
# 1) сводка манифеста; 2) схема каждого parquet (провенанс, обязательные
# колонки); 3) физика: высоты рельефа против известных точек СФ, пирамида
# Трансамерика в данных, округов ровно девять. Жёсткие провалы — только для
# источников со статусом done; по partial — предупреждения.

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np

from twin import schema
from twin.state import DATA_DIR, Manifest

FAIL, WARN = "[x]", "[~]"
OK = "[v]"


def _check_dem(errors: list, warns: list) -> None:
    p = os.path.join(DATA_DIR, "dem", "scene_sf.npz")
    if not os.path.exists(p):
        errors.append("dem: нет scene_sf.npz")
        return
    z = np.load(p, allow_pickle=False)
    elev = z["elev"]
    bbox = json.loads(str(z["meta"]))["bbox"]
    lat_min, lon_min, lat_max, lon_max = bbox

    def at(la, lo):
        r = int((lat_max - la) / (lat_max - lat_min) * (elev.shape[0] - 1))
        c = int((lo - lon_min) / (lon_max - lon_min) * (elev.shape[1] - 1))
        return float(elev[r, c])

    tp = at(37.7544, -122.4477)      # Твин-Пикс (~282 м у вершины)
    if not (180 <= tp <= 320):
        errors.append(f"dem: Твин-Пикс {tp:.0f} м вне [180, 320]")
    else:
        print(f"{OK} dem: Твин-Пикс {tp:.0f} м")
    ocean = at(37.75, -122.52)       # океан у Оушен-Бич
    if ocean > 5:
        errors.append(f"dem: океан {ocean:.0f} м > 5 м")
    dtwn = at(37.7793, -122.4193)    # Сивик-центр (~15 м)
    if not (-2 <= dtwn <= 60):
        warns.append(f"dem: центр города {dtwn:.0f} м подозрителен")


def _read_kind(src: str, kind: str) -> list[dict]:
    import pyarrow.parquet as pq
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, src, "*.parquet"))):
        pf = pq.ParquetFile(path)
        if schema.table_kind(pf.schema_arrow) != kind:
            continue
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def _check_osm(errors: list, warns: list, done: bool) -> None:
    feats = _read_kind("osm", "feature")
    if not feats:
        (errors if done else warns).append("osm: нет объектов")
        return
    by = {}
    for f in feats:
        by.setdefault(f["fclass"], []).append(f)
    n_b = len({f["id"] for f in by.get("building", [])})
    n_r = len({f["id"] for f in by.get("road", [])})
    print(f"{OK} osm: именованных зданий {n_b}, дорог {n_r}, "
          f"воды {len(by.get('water', []))}, "
          f"зелени {len(by.get('green', []))}, POI {len(by.get('poi', []))}")
    if done and n_b < 1_000:
        errors.append(f"osm: слишком мало именованных зданий ({n_b} < 1000)")
    if done and n_r < 3_000:
        errors.append(f"osm: слишком мало дорог ({n_r} < 3000)")
    tower = [f for f in by.get("building", [])
             if (f.get("name") or "").startswith("Transamerica Pyramid")]
    if tower:
        h = tower[0].get("height_m") or 0
        if not (200 <= h <= 280):
            errors.append(f"osm: высота пирамиды Трансамерика {h} вне [200, 280]")
        else:
            print(f"{OK} osm: пирамида Трансамерика {h:.0f} м на месте")
    elif done:
        errors.append("osm: пирамида Трансамерика не найдена")


def _check_counties(errors: list, warns: list, done: bool) -> None:
    feats = _read_kind("counties", "feature")
    if not feats:
        (errors if done else warns).append("counties: нет округов")
        return
    names = sorted(f.get("name") or "" for f in feats)
    if len(feats) != 9:
        errors.append(f"counties: {len(feats)} округов вместо 9")
    elif "San Francisco" not in names:
        errors.append("counties: нет округа San Francisco")
    else:
        print(f"{OK} counties: 9 округов ({', '.join(names[:4])}…)")


def _check_weather(errors: list, warns: list, done: bool) -> None:
    obs = _read_kind("weather", "obs")
    if not obs:
        (errors if done else warns).append("weather: нет наблюдений")
        return
    temps = [o for o in obs if o["var"] == "temperature"]
    for t in temps:
        if not (-10 <= t["value"] <= 50):
            errors.append(f"weather: температура {t['value']} вне разумного")
    print(f"{OK} weather: {len(obs)} наблюдений, последняя точка {obs[-1]['t'][:10]}")


def _check_sfbuildings(errors: list, warns: list, done: bool) -> None:
    feats = _read_kind("sfbuildings", "feature")
    if not feats:
        (errors if done else warns).append("sfbuildings: нет контуров")
        return
    hs = [f["height_m"] for f in feats if f.get("height_m") is not None]
    med = float(np.median(hs)) if hs else 0
    print(f"{OK} sfbuildings: контуров {len(feats)}, медианная высота {med:.1f} м")
    if done and len(feats) < 150_000:
        errors.append(f"sfbuildings: {len(feats)} контуров < 150000")
    if hs and not (3 <= med <= 20):
        errors.append(f"sfbuildings: медианная высота {med:.1f} м подозрительна")
    rolls = _read_kind("sfbuildings", "obs")
    years = [r["value"] for r in rolls if r["value"] > 0]
    if years:
        my = float(np.median(years))
        print(f"{OK} sfbuildings: годов постройки {len(years)}, медиана {my:.0f}")
        if not (1890 <= my <= 1990):
            warns.append(f"sfbuildings: медианный год {my:.0f} странный")
        # оценщик ставит 1900 вместо «неизвестно»: у соседних годов записей
        # на порядок меньше. Это не ошибка сбора — это свойство источника,
        # и машина времени обязана про него говорить вслух.
        n1900 = sum(1 for y in years if y == 1900)
        n1901 = sum(1 for y in years if y == 1901)
        if n1900 > 10 * max(n1901, 1):
            print(f"{OK} sfbuildings: 1900 год — отметка «старое» "
                  f"({n1900} участков против {n1901} в 1901); учтено в подсказке сцены")


def _check_time_machine(errors: list, warns: list) -> None:
    """Собранная сцена: шкала лет и правдоподобие известных зданий."""
    import gzip
    path = os.path.join(DATA_DIR, "build", "scene_sf.json.gz")
    if not os.path.exists(path):
        warns.append("сцена не собрана — python3 -m twin.build sf")
        return
    with gzip.open(path, "rt", encoding="utf-8") as f:
        scene = json.load(f)
    tm = scene["head"].get("time_machine")
    if not tm:
        errors.append("в сцене нет шкалы времени")
        return
    print(f"{OK} машина времени: {tm['known']} зданий с годом, "
          f"{tm['unknown']} без, {tm.get('inferred', 0)} выведено; "
          f"шкала {tm['min']}–{tm['max']}")
    if tm["known"] < 100_000:
        errors.append(f"машина времени: годов всего {tm['known']} (< 100000)")
    if tm["unknown"] > tm["known"]:
        errors.append("машина времени: без года больше, чем с годом")

    # опорные здания: год в сцене против общеизвестного
    LANDMARKS = {"Transamerica Pyramid": 1972, "Salesforce Tower": 2018,
                 "Coit Tower": 1933, "555 California Street": 1969}
    named = {b.get("n"): b for b in scene["big"] if b.get("n")}
    for name, real in sorted(LANDMARKS.items()):
        b = named.get(name)
        if b is None:
            warns.append(f"машина времени: нет здания {name}")
            continue
        got = b.get("y")
        if got is None:
            warns.append(f"машина времени: у {name} нет года")
        elif abs(got - real) > 5:
            errors.append(f"машина времени: {name} датирован {got}, а построен {real}")
        else:
            print(f"{OK} машина времени: {name} — {got} (в жизни {real})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Самопроверка твина")
    ap.add_argument("--examples", action="store_true",
                    help="показать примеры записей")
    args = ap.parse_args()

    man = Manifest()
    print("— манифест —")
    for row in man.summary():
        print(f"  {row['source']:<12} {row['status']:<8} файлов {row['files']:<3} "
              f"строк {row['rows']:<8} {row['mb']} МБ"
              + (f"  ! {row['error']}" if row["error"] else ""))

    errors: list[str] = []
    warns: list[str] = []

    print("— схема parquet —")
    n_files = 0
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*", "*.parquet"))):
        errs = schema.validate_table(path)
        n_files += 1
        if errs:
            errors.append(f"{os.path.relpath(path, DATA_DIR)}: {errs[:2]}")
        if args.examples and not errs:
            import pyarrow.parquet as pq
            rec = pq.ParquetFile(path).read_row_group(0).slice(0, 1).to_pylist()[0]
            short = {k: (str(v)[:60] + "…" if isinstance(v, str) and len(str(v)) > 60
                         else v) for k, v in list(rec.items())[:8]}
            print(f"  {os.path.relpath(path, DATA_DIR)}: {short}")
    print(f"  проверено файлов: {n_files}")

    print("— физика —")
    st = {row["source"]: row["status"] for row in man.summary()}
    _check_dem(errors, warns)
    _check_osm(errors, warns, st.get("osm") == "done")
    _check_counties(errors, warns, st.get("counties") == "done")
    _check_weather(errors, warns, st.get("weather") == "done")
    _check_sfbuildings(errors, warns, st.get("sfbuildings") == "done")
    _check_time_machine(errors, warns)

    for w in warns:
        print(f"{WARN} {w}")
    for e in errors:
        print(f"{FAIL} {e}")
    if errors:
        print(f"итого: {len(errors)} провалов, {len(warns)} предупреждений")
        return 1
    print(f"итого: чисто ({len(warns)} предупреждений)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
