"""
TERRA — управление мирами.

    python -m terra new      --seed 1 --to 500          создать и прогнать мир
    python -m terra list                                 список прогонов
    python -m terra show     <run>                       что стало с миром
    python -m terra fork     <run> --at -3000 --set ...  ветвление истории
    python -m terra continue <run> --to 1500             продолжить прогон
    python -m terra report   <run>                       собрать HTML-дашборд
    python -m terra chronicle <run> --min 3.0            летопись мира
    python -m terra compare  <run> <run> ...             сравнить миры
    python -m terra oracle   <run>                       развилки, ждущие решения
    python -m terra doctor   [<run>]                     самопроверка мира
    python -m terra compact  <run>                       лёгкий обозреватель (~0.2 МБ)
"""
from __future__ import annotations

import argparse
import json
import sys
import pathlib
from pathlib import Path

RUNS = Path("runs")


def _fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def _yr(y: int) -> str:
    return f"{abs(int(y))} {'до н. э.' if y < 0 else 'н. э.'}"


def _ck_year(p: Path) -> int:
    return int(p.name.split("_", 1)[1].split(".", 1)[0])


def _load_run(run: str) -> tuple[Path, dict]:
    d = Path(run) if Path(run).exists() else RUNS / run
    if not (d / "run.json").exists():
        sys.exit(f"нет такого прогона: {run}")
    return d, json.loads((d / "run.json").read_text(encoding="utf-8"))


def _parse_set(pairs: list[str]) -> dict:
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


# ────────────────────────────────────────────────────────────────────────────
def cmd_new(a):
    from .sim import Sim
    cfg = {"seed": a.seed, "year_end": a.to}
    cfg.update(_parse_set(a.set))
    if a.name:
        cfg["run_id"] = a.name
    if a.resolver:
        cfg["resolver"] = a.resolver
    s = Sim(cfg)
    print(f"мир {s.run_id}: сид {s.cfg['seed']}, {_yr(s.cfg['year_start'])} → {_yr(s.cfg['year_end'])}")
    s.seed_world()
    print(f"ёмкость планеты для собирателей: {_fmt(s.cfg['_world_forager_capacity'])} человек")
    s.run()
    _summary(s)
    if not a.no_report:
        cmd_report(argparse.Namespace(run=str(s.dir), out=None))


def cmd_continue(a):
    from .sim import Sim
    d, meta = _load_run(a.run)
    cks = sorted((d / "checkpoints").glob("ck_*.pkl.gz"), key=_ck_year)
    if not cks:
        sys.exit("нет ни одной точки сохранения")
    s = Sim.restore(cks[-1], d / "world", _parse_set(a.set), run_dir=d)
    print(f"продолжаю {s.run_id} с {_yr(s.year)} до {_yr(a.to)}")
    s.cfg["year_end"] = a.to
    s.run(a.to)
    _summary(s)


def cmd_fork(a):
    from .sim import Sim
    d, meta = _load_run(a.run)
    cks = sorted((d / "checkpoints").glob("ck_*.pkl.gz"), key=_ck_year)
    if not cks:
        sys.exit("нет ни одной точки сохранения")
    at = a.at
    pick = min(cks, key=lambda p: abs(_ck_year(p) - at))
    y = _ck_year(pick)
    over = _parse_set(a.set)
    name = a.name or f"{meta['run_id']}-fork{y}"
    over["run_id"] = name
    s = Sim.restore(pick, d / "world", over, run_dir=RUNS / name, new_run_id=name)
    s.cfg["year_end"] = a.to if a.to is not None else meta["config"]["year_end"]
    from .contracts import Event
    s.chronicle.append(Event(s.year, "fork", f"История развилась заново от {_yr(y)}"
                             + (f"; изменено: {_parse_set(a.set)}" if a.set else ""),
                             None, None, None, None, 5.0, {}))
    print(f"ветвление {meta['run_id']} → {name} от {_yr(y)}"
          + (f", изменено: {_parse_set(a.set)}" if a.set else ""))
    s.run(s.cfg["year_end"])
    _summary(s)
    if not a.no_report:
        cmd_report(argparse.Namespace(run=str(s.dir), out=None))


def cmd_list(a):
    if not RUNS.exists():
        print("прогонов пока нет")
        return
    rows = []
    for d in sorted(RUNS.iterdir()):
        f = d / "run.json"
        if not f.exists():
            continue
        m = json.loads(f.read_text(encoding="utf-8"))
        tl = d / "timeline.jsonl"
        pop = polities = 0
        if tl.exists():
            lines = tl.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                pop, polities = last.get("pop", 0), last.get("polities", 0)
        rows.append((m["run_id"], m["config"]["seed"], m.get("year", 0), polities, pop,
                     m.get("stats", {}).get("discoveries", 0)))
    if not rows:
        print("прогонов пока нет")
        return
    print(f"{'мир':28s} {'сид':>4s} {'год':>14s} {'народов':>8s} {'людей':>14s} {'открытий':>9s}")
    for r in rows:
        print(f"{r[0]:28s} {r[1]:>4d} {_yr(r[2]):>14s} {r[3]:>8d} {_fmt(r[4]):>14s} {r[5]:>9d}")


def cmd_show(a):
    d, m = _load_run(a.run)
    print(f"мир {m['run_id']}  (сид {m['config']['seed']})")
    print(f"  дошёл до {_yr(m['year'])}, развилок разрешено {m['stats']['junctures']}"
          f" ({', '.join(f'{k}: {v}' for k, v in m['resolver'].items() if v)})")
    st = m["stats"]
    print(f"  открытий {st['discoveries']}, утрачено знаний {st['losses']}, войн {st['wars']},")
    print(f"  расколов {st['fissions']}, исчезло народов {st['extinctions']}, моров {st['epidemics']}")
    snaps = (d / "snapshots.jsonl")
    if snaps.exists():
        lines = snaps.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            last = json.loads(lines[-1])
            ps = last["polities"][:a.top]
            print(f"\n  крупнейшие народы на {_yr(last['year'])}:")
            print(f"  {'народ':22s} {'людей':>12s} {'хозяйство':22s} {'форма':18s} {'знаний':>7s}")
            from .society import FORM_RU, MODE_RU
            for p in ps:
                print(f"  {p['name'][:22]:22s} {_fmt(p['pop']):>12s} "
                      f"{MODE_RU.get(p['mode'], p['mode']):22s} "
                      f"{FORM_RU.get(p['form'], p['form']):18s} {p['tech']:>7d}")
            big = sorted(last["settlements"], key=lambda s: -s["pop"])[:a.top]
            if big:
                print(f"\n  крупнейшие города:")
                for s in big:
                    print(f"  {s['name'][:22]:22s} {_fmt(s['pop']):>12s}  {s['tier']}")


def cmd_chronicle(a):
    d, m = _load_run(a.run)
    f = d / "chronicle.jsonl"
    if not f.exists():
        sys.exit("летописи нет")
    kinds = set(a.kind) if a.kind else None
    n = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e["weight"] < a.min:
            continue
        if kinds and e["kind"] not in kinds:
            continue
        if a.since is not None and e["year"] < a.since:
            continue
        if a.until is not None and e["year"] > a.until:
            continue
        print(f"{_yr(e['year']):>16s}  {e['text']}")
        n += 1
        if a.limit and n >= a.limit:
            break
    if n == 0:
        print("(ничего не подошло под фильтр)")


def cmd_report(a):
    from .report import build_report
    d = Path(a.run) if Path(a.run).exists() else RUNS / a.run
    p = build_report(d, a.out)
    print(f"отчёт: {p}  ({p.stat().st_size/1e6:.1f} МБ)")


def cmd_compare(a):
    rows = []
    for r in a.runs:
        d, m = _load_run(r)
        tl = (d / "timeline.jsonl")
        last = {}
        if tl.exists():
            lines = tl.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
        rows.append((m["run_id"], m["config"]["seed"], last, m["stats"]))
    keys = [("pop", "людей", _fmt), ("polities", "народов", str),
            ("tech_max", "знаний макс", str), ("cities", "городов", str),
            ("largest_city", "крупнейший город", _fmt),
            ("complexity", "сложность", lambda v: f"{v:.2f}"),
            ("literacy", "письменность", lambda v: f"{v:.2f}"),
            ("era", "эпоха", str)]
    w = max(len(r[0]) for r in rows) + 2
    print(f"{'':22s}" + "".join(f"{r[0][:w-1]:>{w}s}" for r in rows))
    for k, label, fmt in keys:
        print(f"{label:22s}" + "".join(f"{fmt(r[2].get(k, 0)):>{w}s}" for r in rows))
    for k, label in (("discoveries", "открытий"), ("losses", "утрачено знаний"),
                     ("wars", "войн"), ("fissions", "расколов"),
                     ("extinctions", "исчезло народов"), ("epidemics", "моров")):
        print(f"{label:22s}" + "".join(f"{r[3].get(k, 0):>{w}d}" for r in rows))


def cmd_compact(a):
    from .compact import build_compact
    d = Path(a.run) if Path(a.run).exists() else RUNS / a.run
    p = build_compact(d, a.out, a.frames)
    print(f"лёгкий обозреватель: {p}  ({p.stat().st_size/1048576:.2f} МБ)")


def cmd_doctor(a):
    """Самопроверка: физика мира, каталог знаний, целостность прогона."""
    import numpy as np
    from . import knowledge as kn, society as so, world as wg
    from .contracts import AFFORDANCES
    ok = True

    print("── каталог знаний ─────────────────────────────────")
    print(f"  знаний: {kn.N_TECH}, стартовых: {len(kn.STARTING)}")
    gm = np.zeros(len(AFFORDANCES))
    for t in kn.CATALOG:
        for aff, v in t.gives.items():
            gm[kn.AFF_IDX[aff]] = max(gm[kn.AFF_IDX[aff]], v)
    dead = sorted({t.key for t in kn.CATALOG
                   for aff, v in t.needs_aff.items() if gm[kn.AFF_IDX[aff]] < v})
    if dead:
        ok = False
        print(f"  ✗ требуют недостижимого: {dead}")
    else:
        print("  ✓ нет требований, которых никто не даёт")
    rich = {k: 0.9 for k in kn.MAT_KEYS}
    r = kn.starting_repertoire()
    for _ in range(400):
        m = kn.reachable_mask(r, rich, 1e7, 0.6, 1.0, set(range(14)))
        if not m.any():
            break
        for tid in np.flatnonzero(m):
            kn.learn(r, int(tid), 1.0)
    unreach = [t.key for t in kn.CATALOG if not r.known[t.tid]]
    if unreach:
        ok = False
        print(f"  ✗ недостижимо даже на щедрой планете: {unreach}")
    else:
        print("  ✓ весь каталог раскрывается из палеолита")
    print(f"  потолок знаний: община 200 чел. → {kn.knowledge_ceiling(200):.0f}, "
          f"город 25 000 → {kn.knowledge_ceiling(25000):.0f}, "
          f"держава 1 млн → {kn.knowledge_ceiling(1e6):.0f}")

    print("\n── планета ────────────────────────────────────────")
    w = wg.generate_world(a.seed, 180, 90)
    g = so.Grid(w)
    c = wg.climate_at(w, -4000)
    land = np.flatnonzero(g.land)
    area = g.area[land].sum()
    print(f"  суша {area/1e6:.1f} млн км², {w.is_land.mean():.1%} поверхности")
    ref = {"forager": (1e6, 1.2e7, "верхний палеолит 4–8 млн"),
           "agrarian": (1.0e8, 4.0e8, "мир около 1 г. н. э. 200–250 млн"),
           "intensive": (3.0e8, 1.2e9, "мир около 1700 г. 600–700 млн")}
    for m in so.MODES:
        cap = float(so.cell_yield(w, g, c, land, m, kn.starting_repertoire()).sum())
        note = ""
        if m in ref:
            lo, hi, txt = ref[m]
            good = lo <= cap <= hi
            ok = ok and good
            note = f"  {'✓' if good else '✗'} {txt}"
        print(f"  {so.MODE_RU[m]:24s} {cap/1e6:8.1f} млн ({cap/area:6.2f} чел/км²){note}")
    tin = float((w.ore["tin"][w.is_land] > 0.3).mean())
    draft = float((w.biotic["dom_draft"][w.is_land] > 0.4).mean())
    print(f"  олово: {tin:.2%} суши, тягловые животные: {draft:.1%} суши")

    if a.run:
        print("\n── прогон ─────────────────────────────────────────")
        d, m = _load_run(a.run)
        for f in ("run.json", "chronicle.jsonl", "timeline.jsonl", "snapshots.jsonl",
                  "world.npz", "people.jsonl", "lects.json.gz"):
            e = (d / f).exists()
            ok = ok and (e or f in ("people.jsonl", "lects.json.gz"))
            print(f"  {'✓' if e else '·'} {f}")
        tl = [json.loads(l) for l in (d / "timeline.jsonl").read_text(
            encoding="utf-8").splitlines() if l.strip()]
        if tl:
            print(f"  кадров: {len(tl)}, {_yr(tl[0]['year'])} → {_yr(tl[-1]['year'])}")
            print(f"  население: " + ", ".join(
                f"{_yr(t['year'])} {t['pop']/1e6:.1f} млн"
                for t in tl[::max(1, len(tl) // 6)][:7]))
            neg = [t["year"] for t in tl if t["pop"] < 0 or t["polities"] < 0]
            if neg:
                ok = False
                print(f"  ✗ отрицательные величины в годах {neg[:5]}")
    print("\n" + ("ВСЁ В ПОРЯДКЕ" if ok else "ЕСТЬ ЗАМЕЧАНИЯ — см. пометки ✗"))
    if not ok:
        sys.exit(1)


def cmd_oracle(a):
    d, m = _load_run(a.run)
    f = d / "oracle" / "pending.jsonl"
    if not f.exists():
        print("развилок в очереди нет")
        return
    res = d / "oracle" / "resolved.jsonl"
    done = set()
    if res.exists():
        for line in res.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["jid"])
    n = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        j = json.loads(line)
        if j["jid"] in done:
            continue
        print(f"\n── {j['jid']}  [{j['kind']}]  {_yr(j['year'])}")
        print(f"   {j['situation']}")
        for o in j["options"]:
            print(f"     {o['key']:12s} {o['label']} — {o['consequence_hint']}")
        n += 1
        if a.limit and n >= a.limit:
            break
    print(f"\nждут решения: {n}")
    print(f"чтобы ответить, допиши строки в {res}:")
    print('  {"jid": "...", "choice": "...", "reasoning": "..."}')


def _summary(s):
    alive = [p for p in s.polities.values() if p.dead is None]
    pop = sum(p.pop for p in alive)
    print(f"\n{_yr(s.year)}: народов {len(alive)}, людей {_fmt(pop)}")
    print(f"  {s.stats}")


# ────────────────────────────────────────────────────────────────────────────
def cmd_multiverse(a):
    """Реестр вселенных: что в них совпало, а что разошлось."""
    from . import multiverse as mv
    root = a.runs
    out = a.out or str(pathlib.Path(root) / "multiverse.html")
    unis = mv.scan(root)
    if not unis:
        print(f"в {root} нет прогонов")
        return
    print(f"вселенных: {len(unis)}")
    for u in unis:
        print(f"  {u['name']:<18} сид {str(u['seed']):<4} "
              f"до {mv._fmt_year(u['year_now']):<14} {mv._fmt_pop(u['pop_now']):>9}  "
              f"знаний {u['tech_max']:>3}  крушений {u['stats']['collapses']}")
    if len(unis) >= 2:
        d = mv.divergence(unis[0], unis[1])
        gap = d["mean_gap"]
        print(f"\n{d['a']} против {d['b']}: "
              + (f"вехи расходятся в среднем на {gap:.0f} лет" if gap
                 else "общих вех нет")
              + f", знаний {d['tech_delta']:+d}")
    page = mv.build_multiverse(root, out)
    js = mv.registry_json(root, str(pathlib.Path(out).with_suffix(".json")))
    print(f"\nстраница: {page}\nреестр: {js}")


def main(argv=None):
    ap = argparse.ArgumentParser("terra", description="итеративный симулятор цивилизации")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="создать и прогнать новый мир")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--to", type=int, default=500, help="до какого года")
    p.add_argument("--name", help="имя прогона")
    p.add_argument("--resolver", choices=["heuristic", "api", "oracle"])
    p.add_argument("--set", nargs="*", help="параметры вида ключ=значение")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(f=cmd_new)

    p = sub.add_parser("continue", help="продолжить прогон с последней точки")
    p.add_argument("run")
    p.add_argument("--to", type=int, required=True)
    p.add_argument("--set", nargs="*")
    p.set_defaults(f=cmd_continue)

    p = sub.add_parser("fork", help="переиграть историю от выбранного года")
    p.add_argument("run")
    p.add_argument("--at", type=int, required=True, help="год ветвления")
    p.add_argument("--to", type=int)
    p.add_argument("--name")
    p.add_argument("--set", nargs="*", help="что изменить в этом мире")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(f=cmd_fork)

    p = sub.add_parser("list", help="список миров")
    p.set_defaults(f=cmd_list)

    p = sub.add_parser("show", help="итог мира")
    p.add_argument("run")
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(f=cmd_show)

    p = sub.add_parser("chronicle", help="летопись мира")
    p.add_argument("run")
    p.add_argument("--min", type=float, default=2.6, help="минимальная значимость")
    p.add_argument("--kind", nargs="*")
    p.add_argument("--since", type=int)
    p.add_argument("--until", type=int)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(f=cmd_chronicle)

    p = sub.add_parser("report", help="собрать HTML-дашборд")
    p.add_argument("run")
    p.add_argument("--out")
    p.set_defaults(f=cmd_report)

    p = sub.add_parser("compare", help="сравнить миры")
    p.add_argument("runs", nargs="+")
    p.set_defaults(f=cmd_compare)

    p = sub.add_parser("compact", help="лёгкий обозреватель (открывается везде)")
    p.add_argument("run")
    p.add_argument("-o", "--out")
    p.add_argument("--frames", type=int, default=46)
    p.set_defaults(f=cmd_compact)

    p = sub.add_parser("doctor", help="самопроверка физики мира и прогона")
    p.add_argument("run", nargs="?")
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(f=cmd_doctor)

    p = sub.add_parser("oracle", help="развилки, ждущие внешнего решения")
    p.add_argument("run")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(f=cmd_oracle)

    p = sub.add_parser("multiverse", help="обзор всех вселенных и их расхождений")
    p.add_argument("--runs", default="runs")
    p.add_argument("-o", "--out", default=None)
    p.set_defaults(f=cmd_multiverse)

    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
