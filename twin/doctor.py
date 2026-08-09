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


def _check_bareearth(errors: list, warns: list, done: bool) -> None:
    """Голая земля 3DEP: она заменяет собой поверхностную модель, и если
    ошибётся — весь город встанет не на ту отметку."""
    p = os.path.join(DATA_DIR, "bareearth", "bare_sf.npz")
    if not os.path.exists(p):
        (errors if done else warns).append(
            "bareearth: нет bare_sf.npz — python3 -m twin.ingest --source bareearth")
        return
    z = np.load(p, allow_pickle=False)
    elev = z["elev"]
    meta = json.loads(str(z["meta"]))
    lat_min, lon_min, lat_max, lon_max = meta["bbox"]

    def at(la, lo):
        r = int((lat_max - la) / (lat_max - lat_min) * (elev.shape[0] - 1))
        c = int((lo - lon_min) / (lon_max - lon_min) * (elev.shape[1] - 1))
        return float(elev[r, c])

    step_m = (lat_max - lat_min) * 111_132.0 / elev.shape[0]
    print(f"{OK} bareearth: сетка {elev.shape[0]}×{elev.shape[1]}, "
          f"шаг ~{step_m:.1f} м, пропусков {meta.get('gaps', 0)}")
    if step_m > 10:
        errors.append(f"bareearth: шаг {step_m:.1f} м — не тоньше GLO-30, "
                      "смысла в подмене нет")
    peak = float(elev.max())
    # Твин-Пикс — высшая точка сцены, 282 м; лидар обязан её увидеть
    if not (250 <= peak <= 320):
        errors.append(f"bareearth: высшая точка {peak:.0f} м, а Твин-Пикс 282 м")
    else:
        print(f"{OK} bareearth: высшая точка {peak:.0f} м (Твин-Пикс, в жизни 282)")
    # главное отличие от модели поверхности: в деловом центре земля НИЗКАЯ,
    # потому что небоскрёбы вычтены
    fin = at(37.7935, -122.4010)
    if fin > 25:
        errors.append(f"bareearth: в деловом центре земля {fin:.0f} м — "
                      "похоже, это всё-таки крыши, а не земля")
    else:
        print(f"{OK} bareearth: деловой центр {fin:.1f} м — застройка вычтена")
    if meta.get("gaps", 0) > elev.size * 0.25:
        warns.append(f"bareearth: пропусков {meta['gaps']} — четверть сцены "
                     "не покрыта лидаром")


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


def _check_live(errors: list, warns: list, done: bool) -> None:
    """Живой слой: борта над Заливом, витки, толчки, прилив, камеры."""
    feats = _read_kind("live", "feature")
    obs = _read_kind("live", "obs")
    if not feats:
        (errors if done else warns).append("live: нет живых объектов")
        return
    by = {}
    for f in feats:
        by.setdefault(f["fclass"], []).append(f)
    n_air = len({f["id"] for f in by.get("aircraft", [])})
    n_sat = len({f["id"] for f in by.get("satellite", [])})
    n_q = len({f["id"] for f in by.get("quake", [])})
    n_cam = len({f["id"] for f in by.get("camera", [])})
    print(f"{OK} live: бортов {n_air}, витков {n_sat}, толчков {n_q}, камер {n_cam}")

    for f in by.get("aircraft", []):
        t = json.loads(f["tags_json"])
        alt = t.get("alt_ft") or 0
        if alt > 60000:
            errors.append(f"live: борт {t.get('callsign')} на {alt} футах — "
                          f"выше потолка гражданской и военной авиации")
        if (t.get("gs_kt") or 0) > 1200:
            errors.append(f"live: борт {t.get('callsign')} идёт "
                          f"{t.get('gs_kt')} узлов — быстрее любого самолёта")
    for f in by.get("satellite", []):
        t = json.loads(f["tags_json"])
        alts = t.get("alt_km") or []
        if alts and (min(alts) < 140 or max(alts) > 60000):
            errors.append(f"live: {f['name']} на высоте {min(alts):.0f}–"
                          f"{max(alts):.0f} км — вне разумных орбит")
        per = t.get("period_min")
        if per and not (80 <= per <= 1600):
            errors.append(f"live: у {f['name']} период {per} мин — не орбита")
    lev = [o for o in obs if o["var"] == "water_level"]
    if lev:
        v = lev[-1]["value"]
        if not (-1.0 <= v <= 3.5):
            errors.append(f"live: уровень воды {v} м вне диапазона залива")
        else:
            print(f"{OK} live: прилив {v:.2f} м (станция {lev[-1]['station']})")
    elif done:
        warns.append("live: нет уровня воды")


def _check_population(errors: list, warns: list, done: bool) -> None:
    """Кварталы переписи и синтетические жители: сходятся ли суммы."""
    blocks = _read_kind("population", "feature")
    if not blocks:
        (errors if done else warns).append("population: нет кварталов")
        return
    total = sum(json.loads(b["tags_json"]).get("pop20", 0) for b in blocks)
    print(f"{OK} population: {len(blocks)} кварталов, {total:,} человек по переписи"
          .replace(",", " "))
    # девять округов Залива по переписи 2020 — около 7.76 млн
    if not (6_500_000 <= total <= 8_500_000):
        errors.append(f"population: {total} человек — не похоже на Залив")

    res = _read_kind("people", "feature")
    if not res:
        warns.append("people: выборка жителей не построена "
                     "(python3 -m twin.people sf)")
        return
    ages = sorted(json.loads(r["tags_json"])["age"] for r in res)
    med = ages[len(ages) // 2]
    print(f"{OK} people: выборка {len(res)} жителей, медианный возраст {med}")
    # Сан-Франциско: медиана около 38 лет
    if not (30 <= med <= 46):
        errors.append(f"people: медианный возраст {med} не похож на город")
    if any(r["tier"] != "R" for r in res):
        errors.append("people: синтетический житель обязан быть яруса R")
    if any(r.get("name") for r in res):
        errors.append("people: у синтетического жителя не должно быть имени "
                      "живого человека")


def _check_streetlevel(errors: list, warns: list, done: bool) -> None:
    """Уличная съёмка: есть ли кадры, знают ли они свой курс и своего автора.

    Курс — не украшение: кадр без него нельзя поставить рядом с нашей
    геометрией, а ради этого съёмка и собиралась.
    """
    photos = _read_kind("streetlevel", "feature")
    if not photos:
        (errors if done else warns).append("streetlevel: нет уличных снимков")
        return
    kv = [p for p in photos if json.loads(p["tags_json"]).get("kind") == "kartaview"]
    wc = [p for p in photos if json.loads(p["tags_json"]).get("kind") == "commons"]
    with_h = [p for p in kv if json.loads(p["tags_json"]).get("heading") is not None]
    print(f"{OK} streetlevel: {len(kv)} кадров KartaView "
          f"({len(with_h)} с курсом), {len(wc)} видов Викисклада")

    if done and len(kv) < 5000:
        errors.append(f"streetlevel: {len(kv)} кадров — для города слишком мало")
    share = len(with_h) / max(1, len(kv))
    if share < 0.9:
        errors.append(f"streetlevel: курс известен лишь у {share:.0%} кадров — "
                      "сравнивать с геометрией будет нечем")
    # в сыром слепке 360.0 — это север: первоисточник округляет курс сам.
    # Строгая нормировка нужна там, где курс превращается в поворот камеры,
    # то есть в собранной сцене — она проверяется ниже.
    bad_h = [p for p in with_h
             if not (0 <= json.loads(p["tags_json"])["heading"] <= 360)]
    if bad_h:
        errors.append(f"streetlevel: у {len(bad_h)} кадров курс вне круга")
    no_url = [p for p in photos
              if not str(json.loads(p["tags_json"]).get("url", "")).startswith("http")]
    if no_url:
        errors.append(f"streetlevel: у {len(no_url)} кадров нет адреса снимка")
    # каждая фотография обязана нести автора и лицензию: это чужой труд
    no_lic = [p for p in photos if not p.get("license")]
    if no_lic:
        errors.append(f"streetlevel: у {len(no_lic)} кадров нет лицензии")
    # точка съёмки: сырой GPS регистратора ставит наблюдателя внутрь дома,
    # посаженная на дорогу — на проезжую часть, где машина и ехала
    on_road = [p for p in kv if json.loads(p["tags_json"]).get("place") == "road"]
    if kv:
        share_road = len(on_road) / len(kv)
        print(f"{OK} streetlevel: {share_road:.0%} кадров посажено на линию дороги")
        if share_road < 0.5:
            errors.append(f"streetlevel: на дорогу посажено лишь {share_road:.0%} "
                          "кадров — «встать сюда» будет заводить внутрь домов")
    anon = [p for p in kv if not json.loads(p["tags_json"]).get("author")]
    if anon:
        warns.append(f"streetlevel: у {len(anon)} кадров KartaView автор не указан")

    # съёмка — измерение, а не реконструкция
    if any(p["tier"] != "K" for p in photos):
        errors.append("streetlevel: снимок обязан быть яруса K")
    # снимки лежат у первоисточника; себе мы их не перекладываем
    kept = os.path.join(DATA_DIR, "streetlevel", "_raw")
    if os.path.isdir(kept):
        errors.append("streetlevel: кадры не должны храниться у нас — "
                      "везём только адрес")


SECRET_PATTERNS = (
    ("Google Maps", r"AIza[0-9A-Za-z_\-]{35}"),
    ("Anthropic", r"sk-ant-[A-Za-z0-9_\-]{24,}"),
    ("Hugging Face", r"hf_[A-Za-z0-9]{30,}"),
    ("GitHub", r"gh[pousr]_[A-Za-z0-9]{30,}"),
    ("Mapillary", r"MLY\|[0-9]+\|[a-f0-9]{28,}"),
    ("OpenAI", r"sk-[A-Za-z0-9]{40,}"),
)


def _check_secrets(errors: list, warns: list) -> None:
    """Ни один ключ не должен попасть в код, в сцену или в собранную страницу.

    Проверяем не только своё намерение, но и результат: обыскиваем исходники
    твина, скомпилированную сцену и готовый HTML. Заодно убеждаемся, что файл
    с ключами закрыт от git — забыть строчку в .gitignore легче лёгкого.
    """
    import re
    import subprocess
    from twin import keys as tkeys

    blobs: dict[str, str] = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in sorted(os.listdir(here)):
        if fn.endswith(".py"):
            with open(os.path.join(here, fn), encoding="utf-8") as f:
                blobs[f"twin/{fn}"] = f.read()
    src_dir = os.path.join(here, "sources")
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".py"):
            with open(os.path.join(src_dir, fn), encoding="utf-8") as f:
                blobs[f"twin/sources/{fn}"] = f.read()
    scene = os.path.join(DATA_DIR, "build", "scene_sf.json.gz")
    if os.path.exists(scene):
        import gzip
        with gzip.open(scene, "rb") as f:
            blobs["scene_sf.json.gz"] = f.read().decode("utf-8", "replace")
    page = os.path.join(DATA_DIR, "build", "twin_sf.html")
    if os.path.exists(page):
        with open(page, encoding="utf-8", errors="replace") as f:
            blobs["twin_sf.html"] = f.read()

    found = 0
    for who, pat in SECRET_PATTERNS:
        rx = re.compile(pat)
        for name, blob in blobs.items():
            if rx.search(blob):
                found += 1
                errors.append(f"секреты: в {name} лежит ключ {who} — "
                              "убрать немедленно и отозвать его у поставщика")
    if not found:
        print(f"{OK} секреты: в {len(blobs)} файлах твина ключей нет "
              f"(искали {len(SECRET_PATTERNS)} видов)")

    # файл с ключами не должен быть виден git ни при каких условиях
    if os.path.exists(tkeys.KEYS_FILE):
        try:
            r = subprocess.run(["git", "check-ignore", "-q", tkeys.KEYS_FILE],
                               cwd=os.path.dirname(here), timeout=20)
            if r.returncode != 0:
                errors.append("секреты: twin/.keys.json НЕ закрыт .gitignore")
            else:
                mode = oct(os.stat(tkeys.KEYS_FILE).st_mode & 0o777)
                print(f"{OK} секреты: twin/.keys.json закрыт .gitignore, права {mode}")
        except (OSError, subprocess.SubprocessError):
            warns.append("секреты: не удалось спросить git про .keys.json")

    from twin import _view_js
    if "localStorage" not in _view_js.APP_JS:
        warns.append("секреты: браузерный ключ больше не хранится в localStorage "
                     "— проверьте, куда он делся")
    free, total = tkeys.free_count()
    print(f"{OK} ключи: в реестре {total}, из них без платёжной карты {free} "
          f"(python3 -m twin.keys)")


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

    _check_scene_photos(scene, errors, warns)


def _check_scene_photos(scene: dict, errors: list, warns: list) -> None:
    """Съёмка в собранной сцене: курс становится поворотом камеры, значит
    обязан лежать строго внутри круга, а кадр — стоять на своей земле."""
    ph = scene.get("photos") or {}
    items = ph.get("items") or []
    if not items:
        warns.append("в сцене нет уличных снимков — python3 -m twin.build sf")
        return
    print(f"{OK} съёмка в сцене: {ph.get('n_street', 0)} кадров улиц, "
          f"{ph.get('n_land', 0)} видов мест")
    bad = [p for p in items if not (p[3] == -1 or 0 <= p[3] < 360)]
    if bad:
        errors.append(f"съёмка: у {len(bad)} кадров курс вне [0, 360)")
    # Курс обязателен для УЛИЧНЫХ кадров: только по ним встают в точку съёмки.
    # Виды Викисклада (kind=1) — метки места, у них курса нет и не должно быть.
    street = [p for p in items if p[4] == 0]
    blind = [p for p in street if p[3] < 0]
    if blind:
        errors.append(f"съёмка: {len(blind)} уличных кадров без курса — "
                      "по ним нельзя поверить геометрию")
    if len(street) < 2000:
        errors.append(f"съёмка: уличных кадров всего {len(street)} — "
                      "для города мало")

    # Рамка сцены НЕ симметрична: центр сцены задан отдельно от bbox и обычно
    # не совпадает с его серединой. Считаем углы через ту же проекцию.
    bb, p = scene["head"]["bbox"], scene["head"]["proj"]
    xs = [(bb[1] - p["lon0"]) * p["kx"], (bb[3] - p["lon0"]) * p["kx"]]
    zs = [(p["lat0"] - bb[0]) * p["kz"], (p["lat0"] - bb[2]) * p["kz"]]
    x0, x1 = min(xs) * 10 - 200, max(xs) * 10 + 200      # запас 20 м
    z0, z1 = min(zs) * 10 - 200, max(zs) * 10 + 200
    out = [q for q in items if not (x0 <= q[0] <= x1 and z0 <= q[1] <= z1)]
    if out:
        errors.append(f"съёмка: {len(out)} кадров вне рамки сцены")
    no_url = [q for q in items if not q[6]]
    if no_url:
        errors.append(f"съёмка: у {len(no_url)} кадров в сцене нет адреса")


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
    _check_bareearth(errors, warns, st.get("bareearth") == "done")
    _check_osm(errors, warns, st.get("osm") == "done")
    _check_counties(errors, warns, st.get("counties") == "done")
    _check_weather(errors, warns, st.get("weather") == "done")
    _check_sfbuildings(errors, warns, st.get("sfbuildings") == "done")
    _check_live(errors, warns, st.get("live") == "done")
    _check_population(errors, warns, st.get("population") == "done")
    _check_streetlevel(errors, warns, st.get("streetlevel") == "done")
    _check_secrets(errors, warns)
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
