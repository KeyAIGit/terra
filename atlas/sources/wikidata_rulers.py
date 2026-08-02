# Wikidata SPARQL: первый вертикальный срез «Междуречье −2500…−500».
# Правители месопотамских царств (должности «царь X»), их даты правления,
# царства и координаты столиц. Небольшие постраничные запросы с паузами,
# User-Agent TERRA-atlas/0.1. Лицензия данных Wikidata: CC0-1.0. Ярус K
# (записи опираются на источники Wikidata; хронология — среднеассирийская
# условность, это свойство источника, не наша выдумка).
#
# ЗАГЛУШКА-ПЛАН (НЕ выполняется сейчас): полный слой «все люди с датой
# рождения до 1500 г.» — это дамп-масштаб, см. GLOBAL_PERSONS_PLAN ниже.

from __future__ import annotations

import re
import time

from atlas import schema
from atlas.sources import common

NAME = "wikidata_rulers"
TITLE = "Wikidata: rulers of Mesopotamia, -2500..-500"
LICENSE = "CC0-1.0"
ENDPOINT = "https://query.wikidata.org/sparql"
WINDOW = (-2500, -500)
PAUSE = 1.5  # пауза между запросами, сек

# Должности ищем по названию через mwapi (устойчивее, чем зашитые QID).
# Принимаем и синонимы главы: «ruler of Elam» на запрос «King of Elam»
# (в Wikidata титулы называются по-разному), но ЧАСТЬ-МЕСТО обязана
# совпасть точно — иначе поиск «King of Ur» приносит «king of Urartu».
POSITION_TERMS = [
    "King of Assyria", "King of Babylon", "King of Sumer", "King of Akkad",
    "King of Ur", "King of Uruk", "King of Lagash", "King of Kish",
    "King of Isin", "King of Larsa", "King of Elam", "King of Mari",
    "King of Eshnunna", "King of the Universe", "King of Sumer and Akkad",
    "King of Babylonia", "King of Mitanni", "King of Urartu",
]

HEAD_WORDS = r"(king|queen|ruler|monarch|governor|ensi|lugal)s?"


def _label_fits(term: str, label: str) -> bool:
    """Подпись найденного пункта соответствует искомому титулу?"""
    if label.lower() == term.lower():
        return True
    if " of " not in term or " of " not in label:
        return False
    place = term.lower().split(" of ", 1)[1].removeprefix("the ").strip()
    return bool(re.fullmatch(
        HEAD_WORDS + r" of (the )?" + re.escape(place), label.lower()))

# План полного слоя персон (дамп-масштаб; не тянуть SPARQL'ем).
GLOBAL_PERSONS_PLAN = {
    "goal": "все люди Wikidata с датой рождения до 1500 г. (~4-6 млн)",
    "why_not_sparql": "WDQS режет тяжёлые выборки (timeout 60с); "
                      "полный проход = сотни тысяч страниц запросов",
    "how": [
        "скачать дамп https://dumps.wikimedia.org/wikidatawiki/entities/"
        "latest-all.json.bz2 (~90 ГБ сжатых) НЕ в этом контейнере, либо",
        "фильтрованный поток: качать bz2 чанками и стримить bz2->json построчно, "
        "отбирая P31=Q5 c P569<1500 — укладывается в диск, но не в 40-мин окна; "
        "нужен резюмируемый оффсет по байтам дампа",
        "либо HF-датасеты производных Wikidata (например, wikidata5m/humans) "
        "как временная замена",
    ],
    "estimated_output": "3-8 ГБ parquet (персоны с датами/местами/ролями)",
}


def _sparql(ctx: common.Ctx, query: str, retries: int = 3) -> list[dict]:
    """Один SPARQL-запрос с паузой и повторами; результат — bindings."""
    for attempt in range(retries):
        ctx.check(20)
        r = ctx.session.get(
            ENDPOINT, params={"query": query, "format": "json"}, timeout=70)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        time.sleep(PAUSE)
        return r.json()["results"]["bindings"]
    raise RuntimeError(f"SPARQL не ответил после {retries} попыток")


def _v(b: dict, key: str):
    return b.get(key, {}).get("value")


def _year(iso: str | None):
    """'-0604-01-01T00:00:00Z' -> -604; None -> None."""
    if not iso:
        return None
    m = re.match(r"^([+-]?\d{1,6})-", iso)
    return int(m.group(1)) if m else None


def _qid(uri: str | None):
    return uri.rsplit("/", 1)[-1] if uri else None


def _find_positions(ctx: common.Ctx) -> dict[str, str]:
    """Поиск QID должностей по названиям через mwapi; фильтр «это должность»."""
    found: dict[str, str] = {}  # qid -> подпись
    for term in POSITION_TERMS:
        q = f"""
        SELECT ?item ?itemLabel WHERE {{
          SERVICE wikibase:mwapi {{
            bd:serviceParam wikibase:endpoint "www.wikidata.org";
                            wikibase:api "EntitySearch";
                            mwapi:search "{term}"; mwapi:language "en".
            ?item wikibase:apiOutputItem mwapi:item.
          }}
          ?item wdt:P31/wdt:P279* ?cls .
          VALUES ?cls {{ wd:Q4164871 wd:Q116 wd:Q355567 }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }} LIMIT 5"""
        try:
            for b in _sparql(ctx, q):
                qid = _qid(_v(b, "item"))
                label = _v(b, "itemLabel") or qid
                # глава может зваться иначе (ruler/ensi), место — точно
                if _label_fits(term, label):
                    found[qid] = label
        except common.BudgetExceeded:
            raise
        except Exception as e:
            print(f"    wikidata: поиск '{term}' не удался: {str(e)[:80]}")
    return found


def _holders(ctx: common.Ctx, pos_qid: str, pos_label: str) -> list[dict]:
    """Держатели должности с датами правления/жизни."""
    q = f"""
    SELECT ?p ?pLabel ?birth ?death ?start ?end WHERE {{
      ?p p:P39 ?st . ?st ps:P39 wd:{pos_qid} .
      OPTIONAL {{ ?st pq:P580 ?start }} OPTIONAL {{ ?st pq:P582 ?end }}
      OPTIONAL {{ ?p wdt:P569 ?birth }} OPTIONAL {{ ?p wdt:P570 ?death }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ru". }}
    }} LIMIT 2000"""
    out = []
    for b in _sparql(ctx, q):
        qid = _qid(_v(b, "p"))
        ys, ye = _year(_v(b, "start")), _year(_v(b, "end"))
        yb, yd = _year(_v(b, "birth")), _year(_v(b, "death"))
        years = [y for y in (ys, ye, yb, yd) if y is not None]
        # пересечение с окном среза; бездатные держатели древних титулов — оставляем
        in_window = (not years) or (min(years) <= WINDOW[1] and max(years) >= WINDOW[0])
        if not in_window:
            continue
        rec = schema.base_record(
            "person", f"https://www.wikidata.org/wiki/{qid}", LICENSE, "K")
        rec.update({
            "id": f"wikidata:{qid}",
            "name": _v(b, "pLabel") or qid,
            "birth_year": yb, "death_year": yd,
            "reign_start": ys, "reign_end": ye,
            "position": pos_label,
            "position_qid": pos_qid,
            "undated": not years,
        })
        out.append(rec)
    return out


def _polity_capitals(ctx: common.Ctx, pos_qids: list[str]) -> list[dict]:
    """Царства должностей (P1001) и координаты их столиц (P36 -> P625)."""
    values = " ".join(f"wd:{q}" for q in pos_qids)
    q = f"""
    SELECT ?pos ?polity ?polityLabel ?cap ?capLabel ?coord WHERE {{
      VALUES ?pos {{ {values} }}
      ?pos wdt:P1001 ?polity .
      OPTIONAL {{ ?polity wdt:P36 ?cap . OPTIONAL {{ ?cap wdt:P625 ?coord }} }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ru". }}
    }}"""
    seen, out = set(), []
    for b in _sparql(ctx, q):
        cap_qid = _qid(_v(b, "cap"))
        if not cap_qid or cap_qid in seen:
            continue
        seen.add(cap_qid)
        lat = lon = None
        coord = _v(b, "coord")  # 'Point(lon lat)'
        m = re.match(r"Point\(([-0-9.]+) ([-0-9.]+)\)", coord or "")
        if m:
            lon, lat = float(m.group(1)), float(m.group(2))
        rec = schema.base_record(
            "place", f"https://www.wikidata.org/wiki/{cap_qid}", LICENSE, "K")
        rec.update({
            "id": f"wikidata:{cap_qid}",
            "name": _v(b, "capLabel") or cap_qid,
            "lat": lat, "lon": lon,
            "place_types": "capital",
            "polity_qid": _qid(_v(b, "polity")),
            "polity_name": _v(b, "polityLabel"),
        })
        out.append(rec)
    return out


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)
    state = man.src(NAME)

    # 1) поиск должностей (QID не зашиваем — ищем по названиям)
    if not man.chunk_done(NAME, "positions"):
        positions = _find_positions(ctx)
        if not positions:
            man.set_status(NAME, "failed", "mwapi не нашёл ни одной должности")
            return {"status": "failed", "note": "должности не найдены"}
        state["positions"] = positions
        # rows=0: чанк-метка, parquet пишет persons_parquet
        man.mark_chunk(NAME, "positions", rows=0,
                       note=", ".join(sorted(positions.values()))[:300])
        print(f"    wikidata: найдено должностей: {len(positions)}")
    positions: dict = state.get("positions", {})

    # 2) держатели каждой должности (чанк = должность)
    persons: list[dict] = []
    for pos_qid, pos_label in sorted(positions.items()):
        chunk = f"holders_{pos_qid}"
        if man.chunk_done(NAME, chunk):
            continue
        ctx.check(40)
        rows = _holders(ctx, pos_qid, pos_label)
        persons.extend(rows)
        man.mark_chunk(NAME, chunk, rows=0,  # метка; строки считает persons_parquet
                       note=f"{pos_label}: {len(rows)} в окне")
        print(f"    wikidata: {pos_label} — {len(rows)} правителей в окне")
    if persons:
        # дедупликация: один человек может держать несколько титулов — оставляем
        # все титулы (это разные записи-факты), но выкидываем полные дубли
        uniq = {(r["id"], r["position_qid"], r["reign_start"], r["reign_end"]): r
                for r in persons}
        paths, n = common.write_shards("person", list(uniq.values()), out_dir,
                                       "person_rulers")
        man.mark_chunk(NAME, "persons_parquet", rows=n, files=paths)
        print(f"    wikidata: записано {n} записей правителей")

    # 3) царства и столицы с координатами
    if positions and not man.chunk_done(NAME, "capitals"):
        ctx.check(40)
        caps = _polity_capitals(ctx, list(positions.keys()))
        if caps:
            paths, n = common.write_shards("place", caps, out_dir, "place_capitals")
            man.mark_chunk(NAME, "capitals", rows=n, files=paths)
            print(f"    wikidata: {n} столиц царств")
        else:
            man.mark_chunk(NAME, "capitals", rows=0, note="координат не нашлось")

    # 4) план полного слоя персон — только регистрация, БЕЗ выполнения
    if not man.chunk_done(NAME, "global_persons_plan"):
        man.set_pending_urls(NAME, [
            "https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.bz2",
        ])
        state["global_persons_plan"] = GLOBAL_PERSONS_PLAN
        man.mark_chunk(NAME, "global_persons_plan", rows=0,
                       note="дамп-масштаб, отдельный этап")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, "https://www.wikidata.org/", LICENSE, TITLE,
            "Срез: правители Междуречья −2500…−500 (должности, даты правления) "
            "+ столицы царств с координатами. Полный слой персон — в плане.")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    return {"status": "done", "note": "срез Междуречья; полный слой персон — план"}
