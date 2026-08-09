# Предсказания твина — и проверка их на честность.
#
# Правило одно: прогноз чего-то стоит, только если он записан ДО события и
# сверен ПОСЛЕ. Поэтому здесь два действия, а не одно:
#
#   python3 -m twin.forecast issue    # выпустить прогнозы с отметкой времени
#   python3 -m twin.forecast score    # сверить старые прогнозы с тем, что вышло
#   python3 -m twin.forecast show     # что сейчас предсказано и как мы стреляли
#
# Прогнозы бывают точечные (уровень воды, температура) и вероятностные
# (толчок магнитудой не ниже M за N дней). Первые оцениваем ошибкой, вторые —
# оценкой Бриера и калибровкой: если мы двадцать раз сказали «30 %», примерно
# шесть раз должно было случиться.

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import math
import os
import sys

from twin import regions, schema
from twin.state import DATA_DIR

FC_DIR = os.path.join(DATA_DIR, "forecast")

# Магнитуда, ниже которой каталог неполон: слабые толчки регистрируются не
# все, и подмешивать их в оценку b-значения нельзя.
M_COMPLETE = 1.5


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _iso(t: _dt.datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _parse(t: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(t.replace("Z", "+00:00"))


# ── сейсмика: закон Гутенберга — Рихтера ────────────────────────────────────
def b_value(mags: list[float], m_min: float = M_COMPLETE) -> tuple[float, int]:
    """Оценка b по Аки — максимум правдоподобия для усечённого показательного
    распределения. Возвращает (b, число использованных толчков).

    lg N(≥M) = a − b·M. Для Калифорнии b близко к 1: на каждую единицу
    магнитуды толчков становится примерно вдесятеро меньше.
    """
    use = [m for m in mags if m is not None and m >= m_min]
    n = len(use)
    if n < 20:
        return float("nan"), n
    mean = sum(use) / n
    if mean <= m_min:
        return float("nan"), n
    # поправка на дискретность каталога (магнитуды округлены до 0.01)
    return 1.0 / (math.log(10.0) * (mean - (m_min - 0.005))), n


def quake_probability(mags: list[float], days_observed: float,
                      target_mag: float, days_ahead: float) -> dict:
    """Вероятность хотя бы одного толчка магнитудой ≥ target за days_ahead.

    Скорость событий выше M_COMPLETE берём из наблюдённого каталога,
    экстраполируем к целевой магнитуде законом Гутенберга — Рихтера,
    дальше пуассоновский поток: P = 1 − exp(−λ·t).
    """
    b, n = b_value(mags)
    if not (n and b == b) or days_observed <= 0:      # b == b отсекает NaN
        return {"p": None, "note": "каталога не хватает для оценки"}
    rate_complete = n / days_observed                  # событий в сутки ≥ M_COMPLETE
    rate_target = rate_complete * 10.0 ** (-b * (target_mag - M_COMPLETE))
    lam = rate_target * days_ahead
    return {"p": 1.0 - math.exp(-lam), "b": b, "n": n,
            "rate_per_day": rate_target,
            # Поток считаем пуассоновским, то есть события независимы. Это
            # неправда: афтершоки идут роями, и на коротких сроках оценка
            # завышена. Не прячем — сверка прогнозов сама это покажет.
            "note": f"Гутенберг—Рихтер, b={b:.2f} по {n} толчкам; "
                    f"поток пуассоновский, афтершоки не расцеплены"}


# ── чтение того, что уже собрано ────────────────────────────────────────────
def _read_live_obs() -> list[dict]:
    import pyarrow.parquet as pq
    out = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "live", "*.parquet"))):
        pf = pq.ParquetFile(p)
        if schema.table_kind(pf.schema_arrow) != "obs":
            continue
        out.extend(pq.read_table(p).to_pylist())
    return out


def _read_quakes() -> list[dict]:
    import pyarrow.parquet as pq
    seen, out = set(), []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "live", "*.parquet"))):
        pf = pq.ParquetFile(p)
        if schema.table_kind(pf.schema_arrow) != "feature":
            continue
        for r in pq.read_table(p).to_pylist():
            if r["fclass"] != "quake" or r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append(json.loads(r["tags_json"]))
    return out


def _read_weather_fc() -> list[dict]:
    import pyarrow.parquet as pq
    out = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "weather", "*.parquet"))):
        pf = pq.ParquetFile(p)
        if schema.table_kind(pf.schema_arrow) != "obs":
            continue
        out.extend(pq.read_table(p).to_pylist())
    return out


# ── выпуск прогнозов ────────────────────────────────────────────────────────
def _fc_record(fid: str, kind: str, target: str, valid_at: str,
               method: str, scene: str, value=None, p=None,
               unit: str = "", note: str = "") -> dict:
    rec = schema.base_record("obs", "twin.forecast", "TERRA twin", "R")
    rec.update({
        "id": fid, "station": "forecast", "t": _iso(_now()),
        "var": f"fc:{kind}:{target}", "value": float(value if value is not None
                                                     else (p if p is not None else 0.0)),
        "unit": unit or ("вероятность" if kind == "prob" else ""),
        "scene": scene,
        "text": json.dumps({"kind": kind, "target": target, "valid_at": valid_at,
                            "method": method, "p": p, "value": value,
                            "note": note}, ensure_ascii=False, sort_keys=True),
    })
    return rec


def issue(scene_key: str = "sf") -> list[dict]:
    """Выпустить прогнозы на основе того, что уже собрано."""
    now = _now()
    out = []

    # 1. Прилив: гармонический прогноз NOAA на ближайшие полные и малые воды.
    obs = [o for o in _read_live_obs() if o.get("scene") == scene_key]
    hilo = sorted((o for o in obs if o["var"].startswith("tide_")),
                  key=lambda o: o["t"])
    for o in hilo:
        try:
            valid = _dt.datetime.strptime(o["t"], "%Y-%m-%d %H:%M").replace(
                tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
        if valid <= now:
            continue
        kindru = "полная" if o["var"].endswith("high") else "малая"
        out.append(_fc_record(
            f"fc:tide:{o['t']}", "point", "water_level", _iso(valid),
            "гармонический прогноз NOAA CO-OPS 9414290", scene_key,
            value=o["value"], unit="м",
            note=f"{kindru} вода"))

    # 2. Температура: почасовой прогноз NWS.
    for w in _read_weather_fc():
        if w.get("scene") != scene_key or w["var"] != "temperature_forecast":
            continue
        try:
            valid = _parse(w["t"])
        except ValueError:
            continue
        if valid <= now or (valid - now).total_seconds() > 3 * 86400:
            continue
        c = (w["value"] - 32) * 5 / 9 if w["unit"].upper().startswith("F") else w["value"]
        out.append(_fc_record(
            f"fc:temp:{w['t']}", "point", "temperature", _iso(valid),
            "прогноз NWS по сетке MTR", scene_key,
            value=round(c, 1), unit="°C", note=w.get("text") or ""))

    # 3. Сейсмика: вероятность ощутимого толчка — вероятностно и честно.
    qs = _read_quakes()
    mags = [q.get("mag") for q in qs if q.get("mag") is not None]
    times = sorted(q["t_iso"] for q in qs if q.get("t_iso"))
    if len(times) >= 2:
        span_days = max(1.0, (_parse(times[-1]) - _parse(times[0])).total_seconds() / 86400)
        for target_mag, horizon in ((3.0, 30), (4.0, 30), (5.0, 365)):
            r = quake_probability(mags, span_days, target_mag, horizon)
            if r["p"] is None:
                continue
            valid = now + _dt.timedelta(days=horizon)
            out.append(_fc_record(
                f"fc:quake:M{target_mag:.0f}:{horizon}d:{now.date()}", "prob",
                f"quake_M{target_mag:.0f}_{horizon}d", _iso(valid),
                r["note"], scene_key, p=round(r["p"], 4),
                note=f"скорость {r['rate_per_day']:.4f} соб/сут по каталогу "
                     f"за {span_days:.0f} сут"))

    # один срок — один прогноз: слепки живого слоя повторяют предсказания NOAA
    seen, uniq = set(), []
    for r in out:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    return uniq


def save(recs: list[dict]) -> str:
    from twin.sources import common
    if not recs:
        return ""
    os.makedirs(FC_DIR, exist_ok=True)
    stamp = _now().strftime("%Y%m%dT%H%M")
    return common.write_one_shard("obs", recs, FC_DIR, f"fc_{stamp}.parquet")


def _load_all() -> list[dict]:
    import pyarrow.parquet as pq
    out = []
    for p in sorted(glob.glob(os.path.join(FC_DIR, "*.parquet"))):
        for r in pq.read_table(p).to_pylist():
            meta = json.loads(r["text"])
            meta.update({"id": r["id"], "issued": r["t"], "unit": r["unit"]})
            out.append(meta)
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: (r["id"], r["issued"])):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    return uniq


# ── сверка с тем, что вышло ─────────────────────────────────────────────────
def score(scene_key: str = "sf") -> dict:
    now = _now()
    fcs = [f for f in _load_all() if _parse(f["valid_at"]) <= now]
    obs = _read_live_obs()
    levels = sorted(((o["t"], o["value"]) for o in obs if o["var"] == "water_level"),
                    key=lambda x: x[0])
    quakes = _read_quakes()

    rows, briers = [], []
    for f in fcs:
        valid = _parse(f["valid_at"])
        actual, err = None, None
        if f["target"] == "water_level" and levels:
            # ближайшее наблюдение к сроку прогноза, но не дальше часа
            best = min(levels, key=lambda x: abs(
                (_dt.datetime.strptime(x[0], "%Y-%m-%d %H:%M")
                 .replace(tzinfo=_dt.timezone.utc) - valid).total_seconds()))
            dt_min = abs((_dt.datetime.strptime(best[0], "%Y-%m-%d %H:%M")
                          .replace(tzinfo=_dt.timezone.utc) - valid).total_seconds()) / 60
            if dt_min <= 60:
                actual, err = best[1], best[1] - f["value"]
        elif f["target"].startswith("quake_M"):
            m_target = float(f["target"].split("_M")[1].split("_")[0])
            issued = _parse(f["issued"])
            hit = any(q.get("mag") is not None and q["mag"] >= m_target
                      and q.get("t_iso") and issued <= _parse(q["t_iso"]) <= valid
                      for q in quakes)
            actual = 1.0 if hit else 0.0
            if f.get("p") is not None:
                briers.append((f["p"] - actual) ** 2)
                err = f["p"] - actual
        if actual is not None:
            rows.append({"id": f["id"], "target": f["target"],
                         "valid_at": f["valid_at"],
                         "predicted": f.get("p") if f["kind"] == "prob" else f["value"],
                         "actual": actual, "error": err, "unit": f["unit"]})

    pts = [r for r in rows if r["error"] is not None and r["unit"] not in ("вероятность",)]
    summary = {
        "проверено": len(rows),
        "точечных": len(pts),
        "средняя_абс_ошибка": (round(sum(abs(r["error"]) for r in pts) / len(pts), 3)
                               if pts else None),
        "вероятностных": len(briers),
        "оценка_Бриера": round(sum(briers) / len(briers), 4) if briers else None,
        "ждут_срока": len([f for f in _load_all() if _parse(f["valid_at"]) > now]),
    }
    return {"summary": summary, "rows": rows}


def show() -> None:
    now = _now()
    all_fc = _load_all()
    pending = [f for f in all_fc if _parse(f["valid_at"]) > now]
    print(f"— прогнозов всего {len(all_fc)}, ждут срока {len(pending)} —")
    for f in sorted(pending, key=lambda f: f["valid_at"])[:12]:
        when = f["valid_at"][:16].replace("T", " ")
        if f["kind"] == "prob":
            print(f"  {when}  {f['target']:<22} {f['p']*100:5.1f} %   {f['method']}")
        else:
            print(f"  {when}  {f['target']:<22} {f['value']:6.2f} {f['unit']:<4} "
                  f"{f.get('note') or ''}")
    s = score()
    print("— как мы стреляли —")
    for k, v in s["summary"].items():
        print(f"  {k}: {v}")
    for r in s["rows"][-6:]:
        p, a = r["predicted"], r["actual"]
        print(f"  {r['valid_at'][:16]}  {r['target']:<22} "
              f"предсказано {p:.2f}, вышло {a:.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Прогнозы твина и их проверка")
    ap.add_argument("action", choices=("issue", "score", "show"))
    ap.add_argument("--scene", default="sf")
    args = ap.parse_args()
    if args.action == "issue":
        recs = issue(args.scene)
        path = save(recs)
        print(f"выпущено прогнозов: {len(recs)}" + (f" -> {path}" if path else ""))
        for r in recs[:8]:
            m = json.loads(r["text"])
            print(f"  {m['valid_at'][:16]}  {m['target']:<22} "
                  + (f"{m['p']*100:5.1f} %" if m["kind"] == "prob"
                     else f"{m['value']:6.2f} {r['unit']}"))
    elif args.action == "score":
        s = score(args.scene)
        print(json.dumps(s["summary"], ensure_ascii=False, indent=1))
        for r in s["rows"]:
            print(f"  {r['valid_at'][:16]}  {r['target']:<22} "
                  f"предсказано {r['predicted']:.2f}, вышло {r['actual']:.2f}, "
                  f"ошибка {r['error']:+.2f}" if r["error"] is not None else "")
    else:
        show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
