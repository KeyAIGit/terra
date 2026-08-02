"""
TERRA — проверки.

Запуск:  cd terra && python3 -m tests.test_terra
Быстрые проверки идут первыми; те, что гоняют мир, помечены как медленные
и включаются флагом --slow.
"""
from __future__ import annotations

import gzip
import json
import math
import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terra import agents as ag  # noqa: E402
from terra import knowledge as kn  # noqa: E402
from terra import society as so  # noqa: E402
from terra import world as wg  # noqa: E402
from terra.contracts import AFFORDANCES, ICE, OCEAN  # noqa: E402
from terra.lang import Lect  # noqa: E402

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


# ────────────────────────────────────────────────────────────────────────────
def test_world():
    section("планета")
    t0 = time.time()
    w = wg.generate_world(11, 120, 60)
    check("генерация укладывается в 25 с", time.time() - t0 < 25, f"{time.time()-t0:.1f} с")
    land = w.is_land.mean()
    check("доля суши 22–38 %", 0.22 <= land <= 0.38, f"{land:.1%}")
    check("высоты в разумных пределах",
          -9000 < w.elevation.min() < -1000 and 2000 < w.elevation.max() < 9000,
          f"{w.elevation.min():.0f}…{w.elevation.max():.0f}")
    check("вода не считается сушей", not (w.is_land & (w.biome == OCEAN)).any())
    check("климатическая история заполнена",
          w.global_temp_anom is not None and len(w.global_temp_anom) == w.n_years)
    check("дегляциация: в начале холоднее, чем в середине голоцена",
          w.global_temp_anom[0] < w.global_temp_anom[6000] - 1.5,
          f"{w.global_temp_anom[0]:.1f} → {w.global_temp_anom[6000]:.1f}")
    tin = (w.ore["tin"][w.is_land] > 0.3).mean()
    check("олово редкое (<4 % суши)", tin < 0.04, f"{tin:.2%}")
    iron = (w.ore["iron"][w.is_land] > 0.3).mean()
    check("железо обильнее олова", iron > tin * 3, f"железо {iron:.1%}")
    c1 = wg.climate_at(w, -9000)
    c2 = wg.climate_at(w, -9000)
    check("климат детерминирован", np.array_equal(c1.temp, c2.temp))
    check("продуктивность неотрицательна и ограничена",
          c1.productivity.min() >= 0 and c1.productivity.max() < 3)
    check("на льду ничего не растёт",
          float(c1.productivity[c1.biome == ICE].max() if (c1.biome == ICE).any() else 0) < 0.15)
    w2 = wg.generate_world(11, 120, 60)
    check("тот же сид — тот же мир", np.array_equal(w.elevation, w2.elevation))
    w3 = wg.generate_world(12, 120, 60)
    check("другой сид — другой мир", not np.array_equal(w.elevation, w3.elevation))
    with tempfile.TemporaryDirectory() as d:
        p = wg.save_world(w, str(Path(d) / "w"))
        w4 = wg.load_world(str(Path(d) / "w"))
        check("мир переживает запись и чтение",
              np.array_equal(w.elevation, w4.elevation) and np.array_equal(w.biome, w4.biome))
    return w


def test_knowledge():
    section("познание")
    check("каталог непустой", kn.N_TECH > 80, str(kn.N_TECH))
    keys = [t.key for t in kn.CATALOG]
    check("ключи знаний уникальны", len(keys) == len(set(keys)))
    bad = [t.key for t in kn.CATALOG
           for a in list(t.gives) + list(t.needs_aff) if a not in AFFORDANCES]
    check("все аффордансы существуют", not bad, str(bad[:4]))
    rep = kn.starting_repertoire()
    check("стартовый набор — палеолит", rep.count() == len(kn.STARTING))
    check("кэш эффектов совпадает с прямым счётом",
          abs(rep.effect("food") - sum(kn.CATALOG[t].effects.get("food", 0)
                                       * min(1.0, 0.35 + rep.grip[t])
                                       for t in np.flatnonzero(rep.known))) < 1e-4)

    rich = {k: 0.9 for k in kn.MAT_KEYS}
    poor = dict(rich)
    poor["tin"] = 0.0
    m_rich = kn.reachable_mask(rep, rich, 1e6, 0.5, 1.0, {4, 5, 6})
    m_poor = kn.reachable_mask(rep, poor, 1e6, 0.5, 1.0, {4, 5, 6})
    check("без сырья достижимо не больше, чем с сырьём", m_poor.sum() <= m_rich.sum())

    # тупики в графе аффордансов: знание, требующее того, чего никто не даёт
    gives_max = np.zeros(len(AFFORDANCES))
    for t in kn.CATALOG:
        for a, v in t.gives.items():
            gives_max[kn.AFF_IDX[a]] = max(gives_max[kn.AFF_IDX[a]], v)
    dead = [t.key for t in kn.CATALOG
            for a, v in t.needs_aff.items() if gives_max[kn.AFF_IDX[a]] < v]
    check("нет знаний с недостижимыми требованиями", not dead, str(sorted(set(dead))[:5]))

    # достижимость всего каталога из палеолита при щедрой планете
    r = kn.starting_repertoire()
    # 5·10⁷ — масштаб связного населения, при котором в принципе возможно всё,
    # вплоть до вычислительных машин: их не построить в общине на тысячу душ
    for _ in range(400):
        m = kn.reachable_mask(r, rich, 5e7, 0.6, 1.0, set(range(14)))
        if not m.any():
            break
        for tid in np.flatnonzero(m):
            kn.learn(r, int(tid), 1.0)
    unreach = [t.key for t in kn.CATALOG if not r.known[t.tid]]
    check("весь каталог достижим на щедрой планете", not unreach, str(unreach[:6]))

    # индустриальный потолок: механизированное хозяйство должно давать
    # порядок «наших» восьми миллиардов, а не бесконечность
    import terra.society as _so
    check("механизированное хозяйство кормит на порядок больше пашенного",
          _so.MODE_DENSITY[_so.MODE_I["mechanized"]]
          > 8 * _so.MODE_DENSITY[_so.MODE_I["agrarian"]])
    check("но не бесконечно: не больше 25 крат пашенного",
          _so.MODE_DENSITY[_so.MODE_I["mechanized"]]
          < 25 * _so.MODE_DENSITY[_so.MODE_I["agrarian"]])
    # путь к машинному разуму существует, но требует масштаба целой цивилизации
    _ai = kn.BY_KEY.get("artificial_mind")
    check("искусственный разум требует масштаба в миллионы душ",
          _ai is not None and _ai.needs_pop >= 1e6,
          f"нужно {_ai.needs_pop:,.0f}" if _ai else "нет такого знания")

    ceil_small = kn.knowledge_ceiling(200)
    ceil_big = kn.knowledge_ceiling(200000)
    check("потолок знаний растёт с масштабом", 20 < ceil_small < 45 < ceil_big,
          f"{ceil_small:.0f} → {ceil_big:.0f}")
    check("у общины потолок ниже полного каталога", ceil_small < kn.N_TECH)

    # забвение при обрушении масштаба
    r2 = kn.starting_repertoire()
    for tid in np.flatnonzero(kn.reachable_mask(r2, rich, 1e6, 0.5, 1.0, {5, 6}))[:20]:
        kn.learn(r2, int(tid), 0.5)
    before = r2.count()
    rng = np.random.default_rng(3)
    for _ in range(60):
        kn.erode(rng, r2, 2.5, 120, 0.1)
    check("при обрушении масштаба знания теряются", r2.count() < before,
          f"{before} → {r2.count()}")


def test_agents():
    section("люди")
    rng = np.random.default_rng(7)
    co = ag.Cohort(4000)
    ids = [co.spawn(rng, 1, -5000, 10, 10) for _ in range(300)]
    idx = np.array(ids)
    check("все живы после рождения", co.alive[idx].all())
    check("черты в пределах 0..1",
          co.traits[idx].min() >= 0 and co.traits[idx].max() <= 1)
    check("убеждения у людей разные", co.belief[idx].std(axis=0).mean() > 0.05)

    ctx = {"year": -5000, "surplus": 0.0, "crowding": 0.5, "frontier": 1.0,
           "hostility": 0.0, "neighbor_wealth": 0.0, "trade_partners": 0.0,
           "legitimacy": 0.5, "inequality": 0.0}
    acts = ag.choose_actions(rng, co, idx, ctx)
    frac = np.bincount(acts, minlength=ag.N_ACT) / idx.size
    check("в мирный сытый год большинство просто добывает еду",
          frac[ag.AI["subsist"]] > 0.5, f"{frac[ag.AI['subsist']]:.2f}")
    check("набег и бунт — редкость",
          frac[ag.AI["raid"]] < 0.06 and frac[ag.AI["rebel"]] < 0.04,
          f"набег {frac[ag.AI['raid']]:.3f}, бунт {frac[ag.AI['rebel']]:.3f}")

    co.needs[idx, ag.NI["food"]] = 1.0
    hungry = ag.choose_actions(rng, co, idx, dict(ctx, crowding=1.6))
    fh = np.bincount(hungry, minlength=ag.N_ACT) / idx.size
    check("голод и теснота гонят людей с места",
          fh[ag.AI["migrate"]] > frac[ag.AI["migrate"]],
          f"{frac[ag.AI['migrate']]:.3f} → {fh[ag.AI['migrate']]:.3f}")
    check("голод поднимает набеги", fh[ag.AI["raid"]] >= frac[ag.AI["raid"]])

    # престижное подражание сближает убеждения
    spread0 = float(co.belief[idx].std(axis=0).mean())
    co.prestige[idx[:10]] = 3.0
    for _ in range(30):
        ag.social_learning(rng, co, idx, 5.0)
    spread1 = float(co.belief[idx].std(axis=0).mean())
    check("подражание сближает картины мира", spread1 < spread0,
          f"{spread0:.3f} → {spread1:.3f}")

    check("неравенство считается", 0 <= ag.gini(co.wealth[idx]) <= 1)
    n0 = int(co.alive[:co.n].sum())
    for i in ids[:50]:
        co.kill(i)
    check("смерть освобождает место", int(co.alive[:co.n].sum()) == n0 - 50)
    new = co.spawn(rng, 1, -4990, 10, 10)
    check("место переиспользуется", new in ids[:50])


def test_society(w):
    section("общество")
    g = so.Grid(w)
    c = wg.climate_at(w, -4000)
    rep = kn.starting_repertoire()
    land = np.flatnonzero(g.land)
    caps = {m: float(so.cell_yield(w, g, c, land, m, rep).sum()) for m in so.MODES}
    check("собиратели: планета кормит 1–12 млн", 1e6 < caps["forager"] < 1.2e7,
          f"{caps['forager']/1e6:.1f} млн")
    check("пашня кормит на порядок больше собирательства",
          caps["agrarian"] > caps["forager"] * 8, f"{caps['agrarian']/1e6:.0f} млн")
    check("ирригация — верх доиндустриального предела",
          caps["intensive"] > caps["agrarian"], f"{caps['intensive']/1e6:.0f} млн")
    check("доиндустриальный потолок ниже полутора миллиардов",
          caps["intensive"] < 1.5e9)
    ar = so.arable_fraction(w, land, c.productivity.ravel()[land],
                            w.river.ravel()[land], w.soil.ravel()[land])
    check("пашня — малая доля земли", 0.02 < ar.mean() < 0.25, f"{ar.mean():.1%}")
    check("пашня нигде не больше 45 %", ar.max() <= 0.43, f"{ar.max():.2f}")

    from terra.contracts import Polity
    p = Polity(pid=1, name="Проба", lect={}, color="#fff", born=-4000)
    p.cells = {int(land[0]), int(land[1])}
    p.pop = 5000
    check("без избытка иерархия не заводится",
          so.pick_form(rep, p, ag.Cohort(10)) in ("band", "tribe"))
    p.surplus = 0.25
    p.complexity = 0.7
    p.legitimacy = 0.1
    p.cohesion = 0.2
    p.pop = 200000
    check("обрушение грозит истощённой сложной державе",
          so.collapse_risk(p, rep, 0.75) > 0)
    p.complexity = 0.05
    check("простому обществу обрушаться нечему",
          so.collapse_risk(p, rep, 0.75) == 0)


def test_lang():
    section("языки")
    a = Lect.create(101)
    b = Lect.create(101)
    check("тот же сид — тот же язык", a.to_dict() == b.to_dict())
    rng = random.Random(5)
    kid = a.branch(rng, 80)
    grand = kid.branch(random.Random(6), 80)
    d1 = a.distance(kid)
    d2 = a.distance(grand)
    check("дочерний язык отошёл, но не оторвался", 0.02 < d1 < 0.75, f"{d1:.2f}")
    check("внук дальше от предка, чем сын", d2 >= d1 - 0.02, f"{d1:.2f} → {d2:.2f}")
    other = Lect.create(999)
    check("неродственный язык дальше родственного", a.distance(other) > d1,
          f"чужой {a.distance(other):.2f} против своего {d1:.2f}")
    j = a.to_dict()
    a2 = Lect.from_dict(json.loads(json.dumps(j)))
    check("язык переживает JSON", a2.to_dict() == j)
    nm = [a.person_name(random.Random(i), i % 2) for i in range(40)]
    check("имена непустые и произносимые",
          all(2 <= len(x) <= 30 for x in nm), str([x for x in nm if len(x) < 2][:3]))
    check("имена разные", len(set(nm)) > 20, str(len(set(nm))))


def test_sim_short():
    section("мир (короткий прогон)")
    from terra.sim import Sim
    cfg = {"seed": 42, "seed_polities": 45, "width": 120, "height": 60,
           "snapshot_every": 10 ** 9, "checkpoint_every": 10 ** 9}
    with tempfile.TemporaryDirectory() as d:
        s = Sim(dict(cfg), run_dir=Path(d) / "a")
        s.seed_world()
        p0 = sum(p.pop for p in s.polities.values())
        for _ in range(30):
            s.step()
        alive = [p for p in s.polities.values() if p.dead is None]
        check("мир не вымер", len(alive) > 5, str(len(alive)))
        pop = sum(p.pop for p in alive)
        check("население не взорвалось и не схлопнулось",
              p0 * 0.2 < pop < p0 * 6, f"{p0/1e6:.2f} → {pop/1e6:.2f} млн")
        check("территории не пересекаются", _no_overlap(s))
        check("владения совпадают с картой владельцев", _grid_consistent(s))
        check("у каждого народа есть люди",
              all(any(s.co.alive[i] for i in p.agent_ids) for p in alive))
        check("люди приписаны своему народу",
              all(all(s.co.polity[i] == p.pid for i in p.agent_ids if s.co.alive[i])
                  for p in alive))
        s._snapshot()
        s.flush()
        for f in ("run.json", "chronicle.jsonl", "timeline.jsonl", "snapshots.jsonl",
                  "people.jsonl", "lects.json.gz", "world.npz"):
            check(f"записан {f}", (Path(d) / "a" / f).exists())
        snap = json.loads((Path(d) / "a" / "snapshots.jsonl").read_text(
            encoding="utf-8").splitlines()[-1])
        check("в снимке есть карта владений и народы",
              "culture_map" in snap and snap["polities"])
        with gzip.open(Path(d) / "a" / "lects.json.gz", "rt", encoding="utf-8") as fh:
            lects = json.load(fh)
        check("языки живых народов сохранены", len(lects) == len(alive))
        ck = s.checkpoint()
        s2 = Sim.restore(ck, Path(d) / "a" / "world", run_dir=Path(d) / "b",
                         new_run_id="b")
        check("восстановление даёт тот же год", s2.year == s.year)
        check("восстановление даёт те же народы",
              sorted(p.pid for p in s2.polities.values() if p.dead is None)
              == sorted(p.pid for p in alive))
        for _ in range(5):
            s.step()
            s2.step()
        check("продолжение из точки сохранения идёт тем же путём",
              _fingerprint(s) == _fingerprint(s2))


def test_determinism():
    section("детерминизм")
    from terra.sim import Sim
    def run(seed, steps=22):
        with tempfile.TemporaryDirectory() as d:
            s = Sim({"seed": seed, "seed_polities": 40, "width": 120, "height": 60,
                     "snapshot_every": 10 ** 9, "checkpoint_every": 10 ** 9},
                    run_dir=Path(d) / "r")
            s.seed_world()
            for _ in range(steps):
                s.step()
            return _fingerprint(s)
    a, b, c = run(3), run(3), run(4)
    check("тот же сид — та же история до последнего имени", a == b)
    check("другой сид — другая история", a != c)


def _fingerprint(s) -> str:
    import hashlib
    alive = sorted((p.pid, p.name, round(p.pop, 2), p.subsistence, p.form,
                    s.reps[p.pid].count(), len(p.cells))
                   for p in s.polities.values() if p.dead is None)
    ev = [(e.year, e.kind, e.text) for e in s.chronicle]
    return hashlib.blake2b(json.dumps([alive, ev], ensure_ascii=False).encode(),
                           digest_size=12).hexdigest()


def _no_overlap(s) -> bool:
    seen = {}
    for p in s.polities.values():
        if p.dead is not None:
            continue
        for c in p.cells:
            if c in seen:
                return False
            seen[c] = p.pid
    return True


def _grid_consistent(s) -> bool:
    for p in s.polities.values():
        if p.dead is not None:
            continue
        for c in p.cells:
            if int(s.grid.owner[c]) != p.pid:
                return False
    return True


# ────────────────────────────────────────────────────────────────────────────
def main():
    slow = "--slow" in sys.argv
    t0 = time.time()
    print("TERRA — проверки\n" + "=" * 64)
    w = test_world()
    test_knowledge()
    test_agents()
    test_society(w)
    test_lang()
    test_sim_short()
    if slow:
        test_determinism()
    else:
        print("\n(проверка детерминизма пропущена; запусти с --slow)")
    print("\n" + "=" * 64)
    if _FAILS:
        print(f"ПРОВАЛЕНО {len(_FAILS)} из {_RUN} за {time.time()-t0:.0f} с:")
        for f in _FAILS:
            print("   ·", f)
        sys.exit(1)
    print(f"все {_RUN} проверок пройдены за {time.time()-t0:.0f} с")


if __name__ == "__main__":
    main()
