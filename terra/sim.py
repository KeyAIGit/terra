"""
TERRA — главный цикл.

Здесь планета, общества и люди соединяются в один мир, который идёт вперёд
сам по себе. Никакой сценарий не заложен: то, каким мир станет к концу прогона,
определяется географией, случаем и решениями конкретных людей.

Мир полностью детерминирован по сиду и конфигурации: тот же сид — та же история,
до последнего имени. Поэтому его можно ветвить: откатиться на любой год, поменять
один параметр — и посмотреть, как разойдутся судьбы.
"""
from __future__ import annotations

import base64
import gzip
import json
import math
import pickle
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import agents as ag
from . import junctures as jc
from . import knowledge as kn
from . import society as so
from . import world as wg
from .contracts import (
    BIOME_NAMES, ICE, LAKE, OCEAN, Event, Polity, Settlement,
)
from .lang import Lect

# ────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "seed": 1,
    "width": 180,
    "height": 90,
    "year_start": -12000,
    "year_end": 500,
    "seed_polities": 190,
    "start_pop_total": "auto",
    "cohort_cap": 90_000,
    "agent_target": 20,          # сколько человек симулируется в народе поимённо
    "snapshot_every": 100,
    "checkpoint_every": 500,
    "chronicle_min_weight": 1.6,
    "resolver": "heuristic",     # heuristic | api | oracle
    "resolver_model": "claude-3-5-haiku-latest",
    "resolver_budget": 400,
    "oracle_wait": 0.0,
    "innovation_rate": 1.0,
    "climate_severity": 1.0,
    "war_appetite": 1.0,
    "disease_severity": 1.0,
    "diffusion_rate": 1.0,
    "earth_like_layout": True,
    "max_polities": 460,
}

# шаг времени: в глубокой древности события редки, ближе к нам — гуще
DT_SCHEDULE = ((-12000, 10), (-7000, 5), (-2500, 2))

_JUNC_COOLDOWN = {"crisis": 260, "schism": 320, "contact": 60, "succession": 90,
                  "reform": 400, "expansion": 300, "innovation": 200}

_DOMAIN_RU = {"sky": "владыка неба", "storm": "податель гроз", "fertility": "мать урожая",
              "death": "страж мёртвых", "war": "бог битвы", "sun": "солнечный лик",
              "sea": "хозяин вод", "hearth": "хранитель очага", "craft": "покровитель ремесла",
              "wisdom": "податель разумения"}

GOD_DOMAINS = ("sky", "storm", "fertility", "death", "war", "sun", "sea",
               "hearth", "craft", "wisdom")


def dt_for(year: int) -> int:
    d = 10
    for y0, dd in DT_SCHEDULE:
        if year >= y0:
            d = dd
    return d


def yr(year: int) -> str:
    return f"{abs(year)} {'до н. э.' if year < 0 else 'н. э.'}"


# ────────────────────────────────────────────────────────────────────────────
class Sim:
    def __init__(self, config: dict | None = None, run_dir: Path | None = None,
                 world_obj=None):
        self.cfg = dict(DEFAULT_CONFIG)
        if config:
            self.cfg.update(config)
        self.run_id = self.cfg.get("run_id") or f"r{self.cfg['seed']}-{int(time.time())}"
        self.dir = Path(run_dir) if run_dir else Path("runs") / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)

        self.rng = np.random.default_rng(self.cfg["seed"] * 7919 + 13)
        self.prng = random.Random(self.cfg["seed"] * 104729 + 7)

        self.world = world_obj or wg.generate_world(
            self.cfg["seed"], self.cfg["width"], self.cfg["height"],
            {"earth_like_layout": self.cfg["earth_like_layout"]})
        self.grid = so.Grid(self.world)
        self.matfield = so.material_field(self.world)
        self.co = ag.Cohort(self.cfg["cohort_cap"])

        self.polities: dict[int, Polity] = {}
        self.reps: dict[int, kn.Repertoire] = {}
        self.lects: dict[int, Lect] = {}
        self.leaders: dict[int, int | None] = {}
        self.rep_weight: dict[int, float] = {}
        self.settlements: dict[int, Settlement] = {}
        self._next_pid = 0
        self._next_sid = 0

        self.year = self.cfg["year_start"]
        self.chronicle: list[Event] = []
        self.timeline: list[dict] = []
        self.snapshots: list[dict] = []
        self.resolver = jc.Resolver(self.cfg["resolver"], self.dir,
                                    self.cfg["resolver_model"],
                                    self.cfg["oracle_wait"], self.cfg["resolver_budget"])
        self._clim = None
        self._clim_year = None
        self._sea = {}
        self._sea_year = -10 ** 9
        self._mat_vecs = {}
        self.people: dict[int, dict] = {}
        self.routes: list = []
        self._names: dict[int, str] = {}
        self._land_links = None
        self._links_year = -10 ** 9
        self._pending_junctures: list[jc.Juncture] = []
        self._drift_year = self.cfg["year_start"]
        self.stats = {"discoveries": 0, "losses": 0, "wars": 0, "fissions": 0,
                      "extinctions": 0, "epidemics": 0, "collapses": 0, "junctures": 0}

    # ── климат ──
    def clim(self):
        if self._clim_year != self.year:
            self._clim = wg.climate_at(self.world, self.year)
            self._clim_year = self.year
        return self._clim

    # ── летопись ──
    def log(self, kind, text, weight=1.0, poly=None, person=None, y=None, x=None, **data):
        self.chronicle.append(Event(self.year, kind, text, poly, person, y, x, weight, data))

    # ────────────────────────────────────────────────────────────────────
    #  Заселение мира
    # ────────────────────────────────────────────────────────────────────
    def seed_world(self):
        w, g = self.world, self.grid
        clim = self.clim()
        H, W = w.height, w.width
        land = np.flatnonzero(g.land & (clim.biome.ravel() != ICE))
        if land.size == 0:
            raise RuntimeError("непригодная планета")
        rep0 = kn.starting_repertoire()
        q = so.cell_yield(w, g, clim, land, "forager", rep0) / np.maximum(g.area[land], 1)
        q = np.clip(q, 0, None)
        if q.sum() <= 0:
            q = np.ones_like(q)
        p = q / q.sum()
        n = self.cfg["seed_polities"]
        picks = self.rng.choice(land, size=min(n, land.size), replace=False,
                                p=p if p.size == land.size else None)
        world_k = float(so.cell_yield(w, g, clim, land, "forager", rep0).sum())
        cfg_total = self.cfg["start_pop_total"]
        total = world_k * 0.5 if cfg_total in (None, "auto") else float(cfg_total)
        self.cfg["_world_forager_capacity"] = round(world_k)
        weights = q[np.searchsorted(land, picks)] + 1e-9
        weights = weights / weights.sum()

        for k, c in enumerate(picks):
            lect = Lect.create(self.cfg["seed"] * 1000003 + k)
            pid = self._new_pid()
            name = lect.ethnonym(self.prng)
            poly = Polity(pid=pid, name=name, lect=lect.to_dict(),
                          color=_color(self.prng), born=self.year)
            poly.cells = {int(c)}
            g.owner[c] = pid
            poly.pop = max(60.0, float(total * weights[k]))
            poly.subsistence = "forager"
            poly.form = "band"
            poly.values = {"openness": self.prng.uniform(0.25, 0.85)}
            self.polities[pid] = poly
            self.reps[pid] = kn.starting_repertoire()
            self.lects[pid] = lect
            self.leaders[pid] = None
            y, x = divmod(int(c), W)
            self._populate(poly, y, x)
            # первые боги — из страха и непонятного
            for d in self.prng.sample(GOD_DOMAINS, 2):
                poly.gods.append({"name": lect.theonym(self.prng, d), "domain": d})
        # расселим стартовые народы на пару клеток
        for _ in range(3):
            for pid, poly in list(self.polities.items()):
                so.try_expand(self.rng, w, g, clim, poly, self.reps[pid], 1.0, 1)
        self.log("origin", f"{len(self.polities)} народов расселились по земле; "
                           f"всего людей около {int(sum(p.pop for p in self.polities.values())):,}"
                           .replace(",", " "), weight=5.0)

    def _new_pid(self) -> int:
        self._next_pid += 1
        return self._next_pid

    def _populate(self, poly: Polity, y: int, x: int):
        tgt = self._target_cohort(poly.pop)
        ids = []
        for _ in range(tgt):
            i = self.co.spawn(self.rng, poly.pid, self.year - int(self.rng.integers(0, 45)),
                              y, x, kin_group=int(self.rng.integers(0, 6)))
            # стартовое население — взрослое, а не младенцы
            ids.append(i)
        self.co.skill[ids] = np.clip(self.rng.beta(2, 3, len(ids)), 0.02, 0.9)
        poly.agent_ids = ids
        self.rep_weight[poly.pid] = poly.pop / max(1, len(ids))

    def _target_cohort(self, pop: float) -> int:
        return int(np.clip(9 + 7 * math.log10(max(pop, 10)), 12, self.cfg["agent_target"] * 2))

    # ────────────────────────────────────────────────────────────────────
    #  Один шаг мира
    # ────────────────────────────────────────────────────────────────────
    def step(self):
        dt = dt_for(self.year)
        w, g, co = self.world, self.grid, self.co
        clim = self.clim()
        if self.year - getattr(self, "_links_year", -10 ** 9) >= 30 or not getattr(self, "_land_links", None):
            self._land_links = so.contacts(w, g, self.polities)
            self._links_year = self.year
        land_links = self._land_links
        if self.year - self._sea_year >= 200:
            self._sea = so.sea_contacts(w, g, self.polities, self.reps)
            self._sea_year = self.year
        links = {}
        for pid in self.polities:
            d = dict(land_links.get(pid, {}))
            for k, v in self._sea.get(pid, {}).items():
                d[k] = max(d.get(k, 0.0), v)
            links[pid] = d
        mat_vecs = {pid: so.materials_vec(self.matfield, p)
                    for pid, p in self.polities.items() if p.dead is None and p.cells}
        goods = so.trade_goods(mat_vecs, self.polities, self.reps, links)
        self._mat_vecs = mat_vecs

        self._pending_junctures = []
        order = list(self.polities.keys())
        self.rng.shuffle(order)
        wars: list[tuple[int, int]] = []

        for pid in order:
            poly = self.polities.get(pid)
            if poly is None or poly.dead is not None:
                continue
            own = mat_vecs.get(pid)
            if own is None:
                continue
            tr = goods.get(pid)
            mats = own if tr is None else np.maximum(own, tr * 0.75)
            self._step_polity(poly, dt, clim, links.get(pid, {}), mats, wars)

        # ── речь меняется сама собой, поколение за поколением ──
        if self.year - getattr(self, "_drift_year", self.cfg["year_start"]) >= 700:
            self._drift_year = self.year
            span = 700
            for pid, poly in self.polities.items():
                if poly.dead is not None:
                    continue
                lect = self.lects.get(pid)
                if lect is None:
                    continue
                nl = lect.drift(self.prng, span)
                if nl is not None:
                    self.lects[pid] = nl
                poly.lect = self.lects[pid].to_dict()

        # ── торговые пути, какими их видит наблюдатель ──
        self.routes = []
        for a_id, nbs in links.items():
            for b_id, st in nbs.items():
                if a_id < b_id and st > 0.18:
                    self.routes.append([a_id, b_id, round(float(st), 3)])

        # ── межнародные дела ──
        self._resolve_junctures(co)
        self._do_wars(wars, dt)
        self._do_diffusion(links, dt)
        self._do_fission(dt)
        self._reap()

        self.year += dt

    # ── жизнь одного народа за такт ──
    def _step_polity(self, poly: Polity, dt: int, clim, nb: dict, mats,
                     wars: list):
        w, g, co = self.world, self.grid, self.co
        pid = poly.pid
        rep = self.reps[pid]
        idx = np.array([i for i in poly.agent_ids if co.alive[i] and co.polity[i] == pid],
                       dtype=np.int64)
        if idx.size == 0 or poly.pop < 12:
            self._extinct(poly, "вымер")
            return
        poly.agent_ids = list(map(int, idx))
        rw = self.rep_weight.get(pid, poly.pop / max(1, idx.size))

        # ── что даёт земля ──
        sed_now = float(so.MODE_SED[so.MODE_I[poly.subsistence]])
        biomes = so.biomes_of(clim, poly)
        K = so.capacity(w, g, clim, poly, rep)
        if K <= 0:
            self._extinct(poly, "земля перестала кормить")
            return

        # ── контекст решений ──
        crowding = float(np.clip(poly.pop / max(K, 1.0), 0, 3.0))
        hostility = sum(1.0 for o in nb if o in poly.at_war_with) / max(1, len(nb) or 1)
        nb_wealth = 0.0
        for o, s in nb.items():
            q = self.polities.get(o)
            if q and q.dead is None:
                nb_wealth = max(nb_wealth, s * min(1.0, q.pop / max(poly.pop, 1)) *
                                (0.3 + q.surplus * 4 + 0.4 * q.complexity))
        frontier = 1.0 if so.frontier_cells(w, g, poly, rep.effect("sea")) else 0.0
        threat = float(np.clip(0.25 * hostility + 0.35 * len(nb) / 6.0
                               + 0.4 * max(0.0, crowding - 1.0), 0, 1.4))
        meaning_supply = float(np.clip(0.25 + 0.5 * len(poly.gods) / 5.0
                                       + 0.6 * rep.effect("meaning"), 0, 1))
        blocked = []
        if not nb:
            blocked += ["raid", "trade"]
        if frontier < 0.5:
            blocked.append("migrate")

        ctx = {
            "year": self.year, "surplus": poly.surplus, "crowding": crowding,
            "frontier": frontier, "hostility": hostility, "neighbor_wealth": nb_wealth,
            "trade_partners": min(1.0, len(nb) / 3.0) * (0.4 + rep.effect("trade")),
            "legitimacy": poly.legitimacy, "inequality": poly.inequality,
            "surplus_extract": rep.effect("surplus_extract"),
            "raid_success": 0.35 + 0.3 * rep.effect("military"),
            "piety_pays": 0.2 + 0.6 * rep.effect("legitimacy"),
            "wealth_prestige": 0.25 + 0.6 * rep.effect("property"),
            "blocked": blocked,
        }

        # ── люди решают ──
        food_ratio_prev = float(np.clip(K / max(poly.pop, 1.0), 0.2, 2.0))
        ag.update_needs(co, idx, food_ratio_prev, threat, poly.cohesion, meaning_supply,
                        poly.inequality, dt)
        acts = ag.choose_actions(self.rng, co, idx, ctx)
        co.last_act[idx] = acts
        n = idx.size
        frac = np.bincount(acts, minlength=ag.N_ACT) / n

        # ── прожитая жизнь: руки учатся делу, старшие передают младшим ──
        # Умение здесь ничьё не «общее»: оно принадлежит человеку и уходит
        # с ним. Народ владеет знанием ровно настолько, насколько живые люди
        # успели его перенять.
        sub_dom = ag.DI["farm"] if poly.subsistence in ("horticulture", "agrarian",
                                                        "intensive", "pastoral") \
            else ag.DI["forage"]
        # Сколько знания народа вообще помещается в одну голову. В общине из
        # десятка умений взрослый знает всё; в державе со ста — лишь часть, и
        # держится остальное уже на письме, школах и цехах.
        head = 14.0 + 26.0 * rep.effect("info") + 34.0 * rep.effect("literacy") \
            + 10.0 * rep.effect("retention")
        lore_share = float(np.clip(head / max(8.0, rep.count()), 0.06, 1.0))
        # потолок мастерства: чему вообще можно выучиться в этом обществе
        craft_depth = float(np.clip(0.30 + 0.70 * min(1.0, rep.count() / 40.0), 0, 1))
        ag.practice(co, idx, acts, self.year, dt, sub_dom, craft_depth)
        ag.apprentice(self.rng, co, idx, acts, self.year, dt)
        ag.absorb_lore(co, idx, self.year, lore_share,
                       frac[ag.AI["teach"]] * 2.2 + frac[ag.AI["care"]] * 0.8
                       + 0.35 * rep.effect("literacy"), dt)

        # ── итог их решений для народа ──
        eff_int = frac[ag.AI["intensify"]]
        production = K * (1.0 + 0.42 * eff_int + 0.12 * frac[ag.AI["subsist"]]
                          - 0.10 * frac[ag.AI["raid"]] - 0.08 * frac[ag.AI["worship"]])
        # запасы
        cap_store = poly.pop * (0.12 + 0.9 * rep.effect("storage"))
        poly.food_stock = min(cap_store, poly.food_stock
                              + max(0.0, production - poly.pop) * (0.25 + frac[ag.AI["store"]]))
        avail = production + min(poly.food_stock, poly.pop * 0.5)
        food_ratio = float(np.clip(avail / max(poly.pop, 1.0), 0.15, 2.2))
        if food_ratio < 1.0:
            poly.food_stock = max(0.0, poly.food_stock - poly.pop * (1.0 - food_ratio) * 0.6)
        # голодный год оставляет след на каждом, кто его застал — навсегда
        if food_ratio < 0.96:
            ag.imprint(co, idx, "hunger", float(min(0.55, (0.96 - food_ratio) * 1.4)),
                       self.year)
        if hostility > 0.4:
            ag.imprint(co, idx, "violence", float(min(0.35, hostility * 0.35)), self.year)
        # Прибавочный продукт — не «незанятая ёмкость». Общество, упёршееся в
        # предел земли, живёт впроголодь, и по прежней мерке избытка у него ноль
        # всегда — а значит, никогда не появятся ни жрецы, ни цари.
        #
        # На деле избыток берётся из другого: пахарь производит заметно больше,
        # чем съедает сам, эту разницу можно хранить, и её есть кому изъять.
        # Поэтому избыток — это произведение производительности уклада,
        # хранимости пищи и способности верхов её отобрать, минус то,
        # что съедает содержание самой сложности.
        eff_mode = so.MODE_EFFICIENCY[so.MODE_I[poly.subsistence]]
        yield_gain = so._saturate(rep.effect("yield"), 0.95, 0.75) - 1.0
        storability = 0.14 + 0.86 * min(1.0, rep.effect("storage")) * (0.20 + 0.80 * sed_now)
        extract = float(np.clip(0.12 + rep.effect("surplus_extract"), 0, 1))
        gross = eff_mode * (1.0 + 0.55 * yield_gain) * storability * (0.32 + 0.68 * extract)
        cost = so.complexity_cost(poly, rep)
        hungry = max(0.0, 1.0 - food_ratio) * 1.6
        poly.surplus = float(np.clip(gross * (1.0 - hungry) - cost, 0, 0.6))

        # истощение земли — тихий убийца оседлых обществ
        cells = so.cells_arr(poly)
        if poly.subsistence in ("horticulture", "agrarian", "intensive"):
            so.soil_balance(w, g, cells, poly.pop, float(eff_int), rep, dt)
        else:
            g.depletion[cells] = np.clip(g.depletion[cells] - 0.0035 * dt, 0, 1)
        if poly.subsistence in ("forager", "complex_forager"):
            take = np.float32(np.clip(0.0016 * dt * poly.pop / max(g.area[cells].sum(), 1) * 900, 0, 0.05))
            g.fauna[cells] = np.clip(g.fauna[cells] - take + 0.0022 * dt, 0.12, 1.0)

        # ── болезни ──
        conn = min(1.0, len(nb) / 4.0) * (0.4 + rep.effect("trade"))
        load = so.pathogen_load(w, g, poly, rep, conn) * self.cfg["disease_severity"]
        plague = so.epidemic(self.rng, poly, load, dt)
        if plague > 0.06:
            poly.pop *= (1 - plague)
            self.stats["epidemics"] += 1
            self.log("epidemic", f"Мор прошёл по народу {poly.name}: погиб примерно "
                                 f"каждый {max(2, int(1/plague))}-й.", weight=2.4, poly=pid)
            kill = idx[self.rng.random(n) < plague]
            for i in kill:
                co.kill(int(i))
            idx = idx[co.alive[idx]]
            # выжившие помнят мор до конца дней
            ag.imprint(co, idx, "plague", float(min(0.7, plague * 3.0)), self.year)
            if idx.size < 3:
                self._extinct(poly, "вымер от мора")
                return

        # ── демография через людей ──
        violence = 0.006 * hostility + 0.010 * frac[ag.AI["raid"]] * self.cfg["war_appetite"]
        health_t = rep.effect("health")
        before = idx.size
        dead = ag.mortality(self.rng, co, idx, self.year, food_ratio, violence,
                            load * 0.006, health_t, dt)
        dead_kin = np.unique(co.kin_group[dead]) if dead.size else None
        dead_mates = co.mate[dead][co.mate[dead] >= 0] if dead.size else None
        for i in dead:
            self._on_death(poly, int(i))
            co.kill(int(i))
        idx = idx[co.alive[idx]]
        # смерть в семье — это личное горе, которое человек носит до конца
        if dead_kin is not None and idx.size:
            bereaved = idx[np.isin(co.kin_group[idx], dead_kin)]
            ag.imprint(co, bereaved, "loss", 0.16, self.year)
            if dead_mates is not None and dead_mates.size:
                widowed = dead_mates[co.alive[dead_mates]]
                ag.imprint(co, widowed, "loss", 0.34, self.year)
        ag.age_effects(co, idx, self.year, dt)
        fert = (1.0 + 0.4 * rep.effect("fertility")) * (0.6 + 0.5 * min(1.5, food_ratio))
        newborn = ag.pair_and_breed(self.rng, co, idx, self.year, fert, dt)
        for ch, mo, fa in newborn:
            poly.agent_ids.append(ch)
        idx = np.array([i for i in poly.agent_ids if co.alive[i]], dtype=np.int64)
        # душевые ставки рождений и смертей, наблюдённые в выборке
        b_rate = len(newborn) / max(1.0, before * dt)
        d_rate = len(dead) / max(1.0, before * dt)
        r = float(np.clip(b_rate - d_rate, -0.050, 0.011))
        poly.pop = float(np.clip(poly.pop * math.exp(r * dt), 0, K * 1.30 + 150))
        poly.agent_ids = list(map(int, idx))

        # ── обучение, статус, власть ──
        outcome = np.where(food_ratio > 1.0, 1.0, 0.0) * np.ones(idx.size)
        outcome = outcome + 0.4 * (co.wealth[idx] > co.wealth[idx].mean() if idx.size > 1 else 0)
        ag.learn_from_outcome(co, idx, co.last_act[idx], np.clip(outcome, 0, 1), dt)
        ag.social_learning(self.rng, co, idx, dt, poly.values.get("openness", 0.5) + 0.4)
        ag.update_standing(self.rng, co, idx, co.last_act[idx], ctx, dt)
        eff = {k: rep.effect(k) for k in ("complexity", "admin", "labor", "legitimacy",
                                          "military", "trade", "info", "health")}
        so.update_complexity(poly, rep, co)
        newform = so.pick_form(rep, poly, co)
        if newform != poly.form:
            old = poly.form
            poly.form = newform
            rank = ("band", "tribe", "bigman", "chiefdom", "citystate", "republic",
                    "confederation", "kingdom", "empire")
            up = rank.index(newform) > rank.index(old) if (old in rank and newform in rank) else True
            if up and poly.pop > 3000 and newform not in ("tribe",):
                self.log("form", f"{poly.name}: {so.FORM_RU.get(old, old)} → "
                                 f"{so.FORM_RU.get(newform, newform)} ({int(poly.pop):,} душ)"
                         .replace(",", " "), weight=2.6, poly=pid)
        ag.assign_roles(self.rng, co, idx, eff, poly.form, self.leaders.get(pid))
        lead = self.leaders.get(pid)
        if lead is None or not co.alive[lead] or co.polity[lead] != pid:
            newlead = ag.select_leaders(self.rng, co, idx, poly.form, self.year, lead)
            if newlead is not None and poly.form not in ("band",):
                self._enthrone(poly, newlead, lead)
            self.leaders[pid] = newlead
        ag.apply_power(co, idx, self.leaders.get(pid), poly.form, poly.complexity)
        poly.inequality = ag.gini(co.wealth[idx]) if idx.size > 3 else 0.0

        # институты давят на убеждения
        vals = {}
        if rep.effect("legitimacy") > 0.2:
            vals["authority"] = min(0.95, 0.5 + rep.effect("legitimacy"))
        if any(gd for gd in poly.gods) and rep.has("priesthood"):
            vals["divine"] = 0.8
        if rep.has("moralizing_god"):
            vals["trust"] = 0.8
        if vals:
            ag.indoctrinate(co, idx, vals, min(0.4, 0.08 * dt))

        # ── сплочённость и законность ──
        d_coh = (0.05 * frac[ag.AI["worship"]] + 0.04 * frac[ag.AI["build"]]
                 - 0.06 * frac[ag.AI["rebel"]] - 0.03 * poly.inequality
                 + 0.02 * rep.effect("cohesion")
                 - 0.010 * max(0, len(poly.cells) - 8) / (8.0 + 40.0 * rep.effect("admin")))
        d_coh -= 0.04 * poly.complexity * (1.0 - poly.legitimacy) + 0.02 * max(0.0, poly.inequality - 0.45)
        poly.cohesion = float(np.clip(
            poly.cohesion + d_coh * dt * 0.35 + 0.007 * dt * (0.60 - poly.cohesion), 0.03, 0.98))
        d_leg = (0.05 * (food_ratio - 1.0) + 0.03 * rep.effect("legitimacy")
                 - 0.10 * frac[ag.AI["rebel"]] - 0.05 * max(0.0, poly.inequality - 0.5)
                 + 0.03 * frac[ag.AI["build"]])
        d_leg -= 0.05 * poly.complexity + 0.06 * max(0.0, poly.inequality - 0.35)
        poly.legitimacy = float(np.clip(
            poly.legitimacy + d_leg * dt * 0.3 + 0.006 * dt * (0.55 - poly.legitimacy), 0.02, 0.98))

        # ── знания ──
        cold_press = float(np.clip((8.0 - clim.temp.ravel()[cells].mean()) / 22.0, 0, 1))
        seen = None
        for o in nb:
            r2 = self.reps.get(o)
            if r2 is not None:
                seen = r2.known.copy() if seen is None else (seen | r2.known)
        self._knowledge_step(poly, rep, idx, frac, mats, biomes, food_ratio, dt, K,
                             threat=threat, crowding=max(0.0, crowding - 0.7),
                             cold=cold_press, load=load, nbn=len(nb), seen=seen)

        # ── хозяйство и территория ──
        mode, _ = so.best_mode(w, g, clim, poly, rep)
        if mode != poly.subsistence:
            # переход к новому хозяйству занимает поколения: люди не бросают
            # привычный уклад из-за одного удачного года
            need = 360 if so.MODE_SED[so.MODE_I[mode]] > so.MODE_SED[so.MODE_I[poly.subsistence]] else 140
            cnt = poly.values.get("_mode_push", 0) + dt if poly.values.get("_mode_want") == mode else dt
            poly.values["_mode_want"] = mode
            poly.values["_mode_push"] = cnt
            if cnt >= need:
                old = poly.subsistence
                poly.subsistence = mode
                poly.values["_mode_push"] = 0
                self.log("mode", f"{poly.name} переходит: {so.MODE_RU[old]} → {so.MODE_RU[mode]}",
                         weight=3.4, poly=pid)
        else:
            poly.values["_mode_push"] = 0
        pressure = max(0.0, crowding - 0.72) * (0.6 + frac[ag.AI["migrate"]] * 2.2)
        if pressure > 0:
            got = so.try_expand(self.rng, w, g, clim, poly, rep, pressure, dt)
        if crowding < 0.35 and len(poly.cells) > 2 and poly.pop < K * 0.3:
            so.abandon(w, g, clim, poly, rep, 0.72)
        if len(poly.cells) > 2 and self.rng.random() < 0.35:
            so.absorb_enclaves(self.rng, w, g, self.polities, poly, dt)

        # ── боги и обрушение ──
        self._religion_step(poly, rep, frac, threat, food_ratio, dt)
        if self._maybe_collapse(poly, rep, food_ratio, dt):
            self._rebalance(poly)
            return

        # ── поселения ──
        self._settlements_step(poly, rep, clim, dt)

        # ── война: намерение ──
        raid_will = frac[ag.AI["raid"]] * self.cfg["war_appetite"]
        if nb and raid_will > 0.004:
            targets = [o for o in nb if self.polities.get(o) and self.polities[o].dead is None]
            if targets and self.rng.random() < min(0.45, raid_will * 1.6 * dt / 10):
                tgt = targets[int(self.rng.integers(0, len(targets)))]
                wars.append((pid, tgt))

        # ── развилки ──
        self._maybe_juncture(poly, rep, idx, food_ratio, crowding, nb, ctx, dt)

        # ── балансировка когорты ──
        self._rebalance(poly)

    # ────────────────────────────────────────────────────────────────────
    def _knowledge_step(self, poly, rep, idx, frac, mats, biomes, food_ratio, dt, K,
                        threat=0.0, crowding=0.0, cold=0.0, load=0.0, nbn=0, seen=None):
        co = self.co
        pid = poly.pid
        # чего этому народу сейчас не хватает — от этого зависит, что он изобретёт
        hunger = float(np.clip(1.15 - food_ratio, 0, 1))
        demand = kn.demand_vector({
            "food": 0.9 * hunger + 0.3 * crowding, "yield": 1.0 * hunger + 0.5 * crowding,
            "storage": 0.7 * hunger + 0.4 * poly.surplus, "famine_buffer": 0.8 * hunger,
            "marine_bonus": 0.5 * hunger, "military": 0.9 * threat, "defense": 0.8 * threat,
            "cold": 0.9 * cold, "health": 0.6 * load, "plague_resist": 0.5 * load,
            "admin": 0.7 * poly.complexity, "info": 0.5 * poly.complexity,
            "legitimacy": 0.5 * max(0.0, 0.55 - poly.legitimacy),
            "cohesion": 0.4 * max(0.0, 0.55 - poly.cohesion),
            "trade": 0.35 * min(1.0, nbn / 3.0), "trade_range": 0.3 * min(1.0, nbn / 3.0),
            "labor": 0.5 * poly.surplus, "sedentism": 0.4 * poly.surplus + 0.3 * crowding,
        })
        sed = so.MODE_SED[so.MODE_I[poly.subsistence]]
        tscale = so.tech_scale(poly, self.settlements)
        mask = kn.reachable_mask(rep, mats, tscale, poly.surplus, sed, biomes)
        n_exp = frac[ag.AI["experiment"]] * idx.size
        if n_exp > 0 and mask.any():
            # чем больше народ, тем больше попыток: масштаб населения — двигатель прогресса
            # число попыток растёт как корень из населения: больше голов — больше проб
            lam = (0.012 * frac[ag.AI["experiment"]] * math.sqrt(max(poly.pop, 1.0)) * dt
                   * self.cfg["innovation_rate"] * (1.0 + rep.effect("innovation"))
                   * (0.6 + 0.8 * poly.values.get("openness", 0.5)))
            tries = self.rng.poisson(min(40.0, lam))
            headroom = kn.carrying_knowledge(tscale, rep.count())
            found = 0
            # Знать, что вещь возможна, — половина изобретения. Народ, видевший
            # у соседей хлеб из посеянного зерна, доходит до земледелия сам,
            # даже если чужие семена у него не всходят. Так замысел переходит
            # через широты и горы, через которые не переходит сам обычай.
            hint = None
            if seen is not None:
                hint = (seen & ~rep.known)
                if not hint.any():
                    hint = None
            experimenters = idx[co.last_act[idx] == ag.AI["experiment"]]
            if experimenters.size == 0:
                # в выборке из двух десятков человек искателя может не оказаться,
                # хотя в народе их сотни — берём самых любопытных как их представителей
                experimenters = idx[np.argsort(-co.traits[idx, ag.TI["curiosity"]])[:3]]
            for _ in range(int(tries)):
                if experimenters.size == 0:
                    break
                who = int(experimenters[int(self.rng.integers(0, experimenters.size))])
                # Открывает не «общество», а конкретный человек — и тем вернее,
                # чем дольше он этим занимался и чем больше успел перенять.
                # Поэтому мастер на седьмом десятке стоит десятка юнцов.
                qual = float(0.16
                             + 0.55 * co.mastery[who, ag.DI["craft"]]
                             + 0.30 * co.lore[who]
                             + 0.38 * co.traits[who, ag.TI["curiosity"]]
                             + 0.12 * min(1.0, (self.year - co.born[who]) / 45.0))
                expo = 0.35 * rep.effect("info") + 0.25 * poly.values.get("openness", 0.5)
                tid = kn.attempt_discovery(self.rng, rep, mask, qual, expo, demand, headroom,
                                           hint=hint)
                if tid is None:
                    continue
                # Большой замысел не приходит готовым: его надо решиться довести,
                # а потом решить — открыть людям или придержать при себе.
                if kn.CATALOG[tid].difficulty >= 3.4 and poly.pop > 4000:
                    jid = jc.make_jid(self.run_id, self.year, "innovation", poly.pid,
                                      int(co.aid[who]))
                    j = jc.build(jid, self.year, "innovation", poly, who, co,
                                 self._name_of(poly, who),
                                 {"tech_name": kn.CATALOG[tid].name, "tech_tid": int(tid),
                                  "food_ratio": food_ratio,
                                  "role_ru": ag.ROLE_RU[ag.ROLES[int(co.role[who])]]})
                    self._pending_junctures.append(j)
                    break
                self._discover(poly, rep, tid, who)
                found += 1
                if found >= 2:      # общество не переваривает больше двух новшеств за такт
                    break
                headroom = kn.carrying_knowledge(tscale, rep.count())
                mask = kn.reachable_mask(rep, mats, tscale, poly.surplus, sed, biomes)

        # Знание народа держится не «само»: оно держится на живых людях.
        # Если поколение мастеров умерло, не успев научить, а молодые не
        # переняли — repertoire осыпается, сколько бы ни было записано.
        grip_gen = ag.generation_grip(co, idx, self.year)
        retention = (0.06 + 0.55 * grip_gen + frac[ag.AI["teach"]] * 1.3
                     + rep.effect("retention") + 0.35 * rep.effect("info"))
        kn.reinforce(rep, poly.pop, retention, dt)
        stress = float(np.clip((1.05 - food_ratio) * 1.6 + (1.0 - poly.cohesion) * 0.5
                               + 1.1 * max(0.0, 0.45 - grip_gen), 0, 2.5))
        if stress > 0.12 or tscale < 900:
            lost = kn.erode(self.rng, rep, stress, tscale, retention)
            for tid in lost:
                self.stats["losses"] += 1
                t = kn.CATALOG[tid]
                if t.difficulty >= 2.6:
                    self.log("loss", f"{poly.name} утратил умение: {t.name}.",
                             weight=2.2 + t.difficulty * 0.25, poly=pid)
        poly.known = set(int(t) for t in np.flatnonzero(rep.known))
        poly.literacy = float(np.clip(rep.effect("literacy"), 0, 1))

    def _discover(self, poly, rep, tid, who):
        co = self.co
        kn.learn(rep, tid, grip=0.4)
        rep.discovered_by[tid] = (self.year, int(co.aid[who]), None)
        self.stats["discoveries"] += 1
        t = kn.CATALOG[tid]
        co.prestige[who] += 0.35 + 0.22 * t.difficulty
        # открытие — это и личный опыт: рука мастера после него твёрже
        w1 = np.array([who], dtype=np.int64)
        co.mastery[who, ag.DI["craft"]] = min(1.0, co.mastery[who, ag.DI["craft"]] + 0.07)
        co.lore[who] = min(1.0, co.lore[who] + 0.05)
        ag.remember(co, w1, "discovery", self.year, 1.0)
        ag.imprint(co, w1, "glory", 0.25, self.year, note_val=1.0)
        if t.difficulty >= 2.0:
            lect = self.lects[poly.pid]
            nm = co.notable[who]
            name = self._name_of(poly, who)
            try:
                local = lect.word(t.key.split("_")[0]) if False else None
            except Exception:
                local = None
            self.log("discovery",
                     f"{name} из народа {poly.name} впервые {_verb(t)}: {t.name}.",
                     weight=1.6 + t.difficulty * 0.55, poly=poly.pid, person=int(co.aid[who]),
                     tech=t.key)
            co.notable[who] = True
            self._deed(poly, who, "discovery", f"впервые {_verb(t)}: {t.name}")

    # ────────────────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────────────────────
    #  Обрушение сложного общества
    # ────────────────────────────────────────────────────────────────────
    def _maybe_collapse(self, poly, rep, food_ratio, dt) -> bool:
        """Тёмные века начинаются здесь.

        Сложное общество живёт, пока изъятие покрывает содержание сложности.
        Когда перестаёт — рушится не постепенно, а разом: пустеют города,
        рассыпается власть, а вместе с городами исчезает и то знание,
        которое держалось только на них. Через век потомки не умеют того,
        что умели деды, и не понимают надписей на своих же камнях.
        """
        # Обрушение — событие эпохи, а не колебание. После него нужны века,
        # чтобы отстроить города, вернуть законность и снова накопить сложность.
        if self.year - poly.values.get("_last_collapse", -10 ** 9) < 450:
            return False
        risk = so.collapse_risk(poly, rep, food_ratio)
        if risk <= 0:
            poly.values["_strain"] = max(0.0, poly.values.get("_strain", 0.0) - 0.4 * dt)
            return False
        poly.values["_strain"] = poly.values.get("_strain", 0.0) + risk * dt
        p = 1.0 - math.exp(-0.0055 * risk * risk * dt)
        if self.rng.random() > p:
            return False

        co = self.co
        sev = float(np.clip(self.rng.beta(2.2, 2.6) * (0.35 + 0.45 * risk), 0.12, 0.65))
        before_tech = rep.count()
        pop_before = poly.pop
        poly.pop *= (1.0 - sev)
        poly.complexity *= (1.0 - 0.55 * sev)
        poly.legitimacy = max(0.03, poly.legitimacy * (1.0 - 0.7 * sev))
        poly.cohesion = max(0.05, poly.cohesion * (1.0 - 0.4 * sev))
        poly.surplus = 0.0
        poly.food_stock = 0.0
        rank = ("band", "tribe", "bigman", "chiefdom", "citystate", "republic",
                "confederation", "kingdom", "empire")
        if poly.form in rank:
            poly.form = rank[max(0, rank.index(poly.form) - (2 if sev > 0.4 else 1))]
        # города пустеют первыми — и уносят с собой книжное знание
        for sid in list(poly.settlements):
            st = self.settlements.get(sid)
            if st is None or st.destroyed:
                continue
            st.pop = int(st.pop * (1.0 - min(0.85, sev * 1.6)))
            if st.pop < 200:
                st.destroyed = self.year
                self.grid.settle[st.y * self.world.width + st.x] = -1
                poly.settlements.remove(sid)
        ts = so.tech_scale(poly, self.settlements)
        for _ in range(3):
            lost = kn.erode(self.rng, rep, 2.2 + 2.0 * sev, ts, 0.1)
            for tid in lost:
                self.stats["losses"] += 1
        gone = before_tech - rep.count()
        self.stats["collapses"] += 1
        poly.values["_strain"] = 0.0
        poly.values["_last_collapse"] = self.year
        idx = np.array(poly.agent_ids, dtype=np.int64)
        idx = idx[co.alive[idx]] if idx.size else idx
        if idx.size:
            drop = idx[self.rng.random(idx.size) < sev]
            for i in drop:
                self._on_death(poly, int(i))
                co.kill(int(i))
            poly.agent_ids = [int(i) for i in idx if co.alive[i]]
            # те, кто пережил крушение, до смерти не поверят в прочность порядка
            surv = np.array(poly.agent_ids, dtype=np.int64)
            if surv.size:
                ag.imprint(co, surv, "collapse", float(min(0.8, 0.35 + sev)), self.year)
            ag.indoctrinate(co, np.array(poly.agent_ids, dtype=np.int64),
                            {"authority": 0.15, "scarcity": 0.85}, 0.5)
        txt = (f"Держава {poly.name} обрушилась: из {int(pop_before):,} душ осталось "
               f"{int(poly.pop):,}".replace(",", " "))
        if gone > 0:
            txt += f", а вместе с городами утрачено {gone} умений"
        self.log("collapse", txt + ".", weight=4.2, poly=poly.pid,
                 severity=round(sev, 2), tech_lost=gone)
        if sev > 0.3:
            poly.values["_force_split"] = 1
        return True

    # ────────────────────────────────────────────────────────────────────
    #  Боги
    # ────────────────────────────────────────────────────────────────────
    def _religion_step(self, poly, rep, frac, threat, food_ratio, dt):
        """Пантеон не задан навсегда: боги рождаются из нужды и умирают от неё же."""
        if self.rng.random() > min(0.5, 0.0016 * dt * (1 + 3 * frac[ag.AI["worship"]])):
            return
        lect = self.lects.get(poly.pid)
        if lect is None:
            return
        have = {g["domain"] for g in poly.gods}
        # что сейчас болит, то и обожествляют
        want = []
        if threat > 0.5:
            want.append("war")
        if food_ratio < 0.95:
            want.append("fertility")
        if poly.subsistence in ("agrarian", "intensive", "horticulture"):
            want += ["sun", "storm"]
        if any(self.settlements.get(s) and self.settlements[s].port for s in poly.settlements):
            want.append("sea")
        if rep.effect("labor") > 0.4:
            want.append("craft")
        if rep.effect("info") > 0.4:
            want.append("wisdom")
        want = [d for d in want if d not in have] or [
            d for d in GOD_DOMAINS if d not in have]
        if want and len(poly.gods) < 9:
            d = want[int(self.rng.integers(0, len(want)))]
            nm = lect.theonym(self.prng, d)
            poly.gods.append({"name": nm, "domain": d, "born": self.year})
            if poly.pop > 20000:
                self.log("religion", f"У народа {poly.name} явился {nm} — "
                                     f"{_DOMAIN_RU.get(d, d)}.",
                         weight=1.5 + min(1.8, max(0.0, math.log10(max(10, poly.pop)) - 4.0)),
                         poly=poly.pid)
        # при большом масштабе многобожие свёртывается в одного высшего
        if rep.has("moralizing_god") and len(poly.gods) > 3 and self.rng.random() < 0.25:
            keep = poly.gods[0]
            merged = [g["name"] for g in poly.gods[1:4]]
            poly.gods = [keep] + poly.gods[4:]
            if poly.pop > 50000:
                self.log("religion",
                         f"В народе {poly.name} {', '.join(merged)} слились в {keep['name']}.",
                         weight=2.9, poly=poly.pid)

    def _settlements_step(self, poly, rep, clim, dt):
        w, g = self.world, self.grid
        share = so.urban_share(rep, poly)
        if share <= 0.01:
            return
        urban = poly.pop * share
        if not poly.settlements and urban > 320:
            cells = so.cells_arr(poly)
            score = (w.river.ravel()[cells] * 1.4 + w.soil.ravel()[cells]
                     + w.coastal.ravel()[cells] * 0.8
                     - w.ruggedness.ravel()[cells] * 0.6)
            c = int(cells[int(np.argmax(score))])
            if g.settle[c] < 0:
                self._next_sid += 1
                y, x = divmod(c, w.width)
                lect = self.lects[poly.pid]
                feats = []
                if w.river.ravel()[c] > 0.5:
                    feats.append("river")
                if w.coastal.ravel()[c]:
                    feats.append("sea")
                nm = lect.place_name(self.prng, "settlement", feats or None)
                s = Settlement(self._next_sid, nm, y, x, int(urban), poly.pid, self.year,
                               is_capital=True, port=bool(w.coastal.ravel()[c]))
                self.settlements[s.sid] = s
                g.settle[c] = s.sid
                poly.settlements.append(s.sid)
                poly.capital = s.sid
                self.log("city", f"Основан {nm} — первое постоянное поселение народа {poly.name}.",
                         weight=3.4, poly=poly.pid, y=y, x=x)
        # рост существующих: не поровну, а по рангу — так устроены все живые
        # системы расселения (столица много больше второго города)
        if poly.settlements:
            live = [sid for sid in poly.settlements
                    if self.settlements.get(sid) and not self.settlements[sid].destroyed]
            live.sort(key=lambda k: -self.settlements[k].pop)
            ranks = {sid: i + 1 for i, sid in enumerate(live)}
            norm = sum(1.0 / (r ** 0.95) for r in ranks.values()) or 1.0
            for sid in list(poly.settlements):
                s = self.settlements.get(sid)
                if s is None or s.destroyed:
                    continue
                old_tier = so.settlement_tier(s.pop)
                share = urban * (1.0 / (ranks.get(sid, len(live) + 1) ** 0.95)) / norm
                s.pop = int(0.72 * s.pop + 0.28 * share)
                nt = so.settlement_tier(s.pop)
                if nt != old_tier and s.pop > 1200:
                    self.log("city", f"{s.name} вырос: {old_tier} → {nt} ({s.pop:,} жителей)"
                             .replace(",", " "), weight=2.2, poly=poly.pid, y=s.y, x=s.x)
                if rep.has("city_wall") and s.walls < 0.5 and s.pop > 2500:
                    s.walls = 0.8
                    self.log("build", f"{s.name} обнесён стеной.", weight=2.0, poly=poly.pid)
                if rep.has("monumental") and len(s.monuments) < 2 and poly.surplus > 0.08 \
                        and self.rng.random() < 0.02 * dt:
                    lect = self.lects[poly.pid]
                    god = poly.gods[0]["name"] if poly.gods else s.name
                    s.monuments.append(god)
                    self.log("build", f"В городе {s.name} воздвигнуто святилище {god}.",
                             weight=2.8, poly=poly.pid, y=s.y, x=s.x)
            # новые города
            if len(poly.settlements) < 1 + int(poly.pop / 40000) and urban > 2500 \
                    and self.rng.random() < 0.05 * dt:
                cells = [c for c in sorted(poly.cells) if g.settle[c] < 0]
                if cells:
                    arr = np.array(cells)
                    score = w.river.ravel()[arr] + w.soil.ravel()[arr] + 0.6 * w.coastal.ravel()[arr]
                    c = int(arr[int(np.argmax(score))])
                    self._next_sid += 1
                    y, x = divmod(c, w.width)
                    nm = self.lects[poly.pid].place_name(self.prng, "settlement")
                    s = Settlement(self._next_sid, nm, y, x, int(urban * 0.2), poly.pid, self.year,
                                   port=bool(w.coastal.ravel()[c]))
                    self.settlements[s.sid] = s
                    g.settle[c] = s.sid
                    poly.settlements.append(s.sid)
                    self.log("city", f"Основан {nm} ({poly.name}).", weight=1.8,
                             poly=poly.pid, y=y, x=x)

    # ────────────────────────────────────────────────────────────────────
    def _maybe_juncture(self, poly, rep, idx, food_ratio, crowding, nb, ctx, dt):
        co = self.co
        if idx.size == 0:
            return
        cands = []
        lead = self.leaders.get(poly.pid)
        decider = lead if (lead is not None and co.alive[lead]) else int(
            idx[int(np.argmax(co.prestige[idx] + co.power[idx]))])

        if food_ratio < 0.86 and poly.pop > 240:
            cands.append(("crisis", decider, {
                "food_ratio": food_ratio, "mode_ru": so.MODE_RU[poly.subsistence],
                "sedentism": float(so.MODE_SED[so.MODE_I[poly.subsistence]]),
                "surplus_possible": max(0.0, 1.2 - crowding),
                "neighbor_wealth": ctx["neighbor_wealth"],
                "cause": "Урожай не задался третий год подряд." if poly.subsistence not in
                         ("forager", "complex_forager") else "Дичь ушла, а собирать нечего.",
                "role_ru": ag.ROLE_RU[ag.ROLES[int(co.role[decider])]],
            }))
        fp = so.fission_pressure(poly, rep, so.territorial_extent(self.world, poly))
        if fp > 1.0 and poly.pop > 900:
            # В безвластном обществе некому подавлять и некому карать: раскол
            # там решается только уходом. Принуждение требует аппарата.
            drop = [] if poly.form not in ("band", "tribe") else ["suppress", "purge"]
            cands.append(("schism", decider, {
                "cohesion": poly.cohesion, "legitimacy": poly.legitimacy,
                "cause": "Дальние роды перестали слать дары и слушать слово вождя."
                         if poly.form not in ("band", "tribe")
                         else "Дальние роды всё реже сходятся на общий обряд.",
                "role_ru": ag.ROLE_RU[ag.ROLES[int(co.role[decider])]],
                "drop_options": {"schism": drop},
            }))
        for o, s in nb.items():
            if o not in poly.neighbors_known and s > 0.12:
                q = self.polities.get(o)
                if q is None or q.dead is not None:
                    continue
                theirs = self.reps[o]
                extra = [kn.CATALOG[t].name for t in np.flatnonzero(theirs.known & ~rep.known)]
                cands.append(("contact", decider, {
                    "other_name": q.name, "other_pop": int(q.pop),
                    "other_mode": so.MODE_RU[q.subsistence],
                    "their_tech": ", ".join(extra[:3]) or "ничем особенным",
                    "danger": float(co.belief[decider, ag.BI["danger"]]),
                    "strength_ratio": float(poly.pop / max(q.pop, 1)),
                    "role_ru": ag.ROLE_RU[ag.ROLES[int(co.role[decider])]],
                    "other_pid": o,
                }))
                poly.neighbors_known[o] = 0.0
                break
        if poly.form in ("chiefdom", "kingdom", "empire", "citystate") and \
                (lead is None or not co.alive[lead]):
            cands.append(("succession", decider, {
                "predecessor": "прежний правитель", "claimants": int(min(5, 1 + idx.size // 8)),
                "cohesion": poly.cohesion, "legitimacy": poly.legitimacy,
                "role_ru": ag.ROLE_RU[ag.ROLES[int(co.role[decider])]],
            }))
        if poly.form not in ("band", "tribe") and (
                poly.pop > so.admin_limit(rep, poly.form) * 0.85
                or (poly.legitimacy < 0.28 and poly.pop > 5000)):
            drop = []
            if rep.affordances()[kn.AFF_IDX["record"]] < 0.55:
                drop.append("codify")     # нельзя записать закон, не умея писать
            if not poly.gods:
                drop.append("sacralize")
            cands.append(("reform", decider, {
                "literacy": poly.literacy,
                "role_ru": ag.ROLE_RU[ag.ROLES[int(co.role[decider])]],
                "drop_options": {"reform": drop},
            }))

        cool = poly.values.setdefault("_junc", {})
        for kind, who, extra in cands:
            if self.year - cool.get(kind, -10 ** 9) < _JUNC_COOLDOWN.get(kind, 200):
                continue
            if self.rng.random() > min(0.85, 0.16 * dt / 5 + 0.14):
                continue
            cool[kind] = self.year
            jid = jc.make_jid(self.run_id, self.year, kind, poly.pid, int(co.aid[who]))
            j = jc.build(jid, self.year, kind, poly, who, co, self._name_of(poly, who), extra)
            self._pending_junctures.append(j)

    def _resolve_junctures(self, co):
        if not self._pending_junctures:
            return
        self.resolver.resolve(self.rng, self._pending_junctures, co)
        for j in self._pending_junctures:
            self.stats["junctures"] += 1
            self._apply_resolution(j)
        self._pending_junctures = []

    def _apply_resolution(self, j):
        poly = self.polities.get(j.polity)
        if poly is None or poly.dead is not None:
            return
        co, rep = self.co, self.reps[j.polity]
        ch = j.resolution["choice"]
        who = j.person
        name = j.context.get("person_name", "?")
        deep = j.resolution.get("by") != "heuristic"
        wt = (1.3 + min(2.3, max(0.0, math.log10(max(10, poly.pop)) - 3.5) * 0.95)
              + (0.8 if deep else 0.0))
        jperson = int(co.aid[who]) if co.alive[who] else None
        if jperson is not None:
            co.notable[who] = True
            label = next((o["label"] for o in j.options if o["key"] == ch), ch)
            self._deed(poly, who, j.kind,
                       f"на развилке «{jc.KIND_RU.get(j.kind, j.kind)}» выбрал: {label}")

        if j.kind == "crisis":
            if ch == "migrate":
                poly.values["wander"] = poly.values.get("wander", 0) + 1
                idx = np.array(poly.agent_ids, dtype=np.int64)
                idx = idx[co.alive[idx]] if idx.size else idx
                if idx.size:
                    co.belief[idx, ag.BI["elsewhere"]] = np.clip(
                        co.belief[idx, ag.BI["elsewhere"]] + 0.22, 0, 0.98)
                self.log("decision", f"{name} увёл народ {poly.name} с истощённой земли.",
                         weight=wt, poly=poly.pid, person=jperson)
            elif ch == "raid":
                poly.values["martial"] = poly.values.get("martial", 0) + 1
                idx = np.array(poly.agent_ids, dtype=np.int64)
                idx = idx[co.alive[idx]]
                co.belief[idx, ag.BI["danger"]] = np.clip(co.belief[idx, ag.BI["danger"]] + 0.15, 0, .98)
                self.log("decision", f"{name} повёл народ {poly.name} за чужим хлебом.",
                         weight=wt, poly=poly.pid, person=jperson)
            elif ch == "sacrifice":
                poly.cohesion = min(1.0, poly.cohesion + 0.10)
                poly.legitimacy = min(1.0, poly.legitimacy + 0.06)
                idx = np.array(poly.agent_ids, dtype=np.int64)
                idx = idx[co.alive[idx]]
                if idx.size:
                    ag.indoctrinate(co, idx, {"divine": 0.9}, 0.35)
                self.log("decision", f"{name} принёс жертву, чтобы отвести беду от народа {poly.name}.",
                         weight=wt, poly=poly.pid, person=jperson)
            elif ch == "reform":
                poly.legitimacy = max(0.05, poly.legitimacy - 0.05)
                poly.complexity = max(0.0, poly.complexity - 0.10)
                poly.values["openness"] = min(1.0, poly.values.get("openness", 0.5) + 0.12)
                self.log("decision", f"{name} переменил порядок в народе {poly.name}.",
                         weight=wt, poly=poly.pid, person=jperson)
            elif ch == "intensify":
                cells = so.cells_arr(poly)
                self.grid.depletion[cells] = np.clip(self.grid.depletion[cells] + 0.05, 0, 0.95)
                poly.food_stock += poly.pop * 0.10
            else:
                poly.pop *= 0.97
        elif j.kind == "schism":
            if ch == "let_go":
                poly.values["_force_split"] = 1
            elif ch == "suppress":
                poly.pop *= 0.965
                poly.cohesion = min(1.0, poly.cohesion + 0.14)
                poly.legitimacy = max(0.03, poly.legitimacy - 0.08)
                self.log("decision", f"{name} усмирил недовольных силой ({poly.name}).",
                         weight=wt, poly=poly.pid, person=jperson)
            elif ch == "concede":
                poly.cohesion = min(1.0, poly.cohesion + 0.09)
                poly.complexity = max(0.0, poly.complexity - 0.08)
            elif ch == "purge":
                poly.pop *= 0.94
                poly.cohesion = min(1.0, poly.cohesion + 0.06)
                poly.legitimacy = max(0.02, poly.legitimacy - 0.16)
                self.log("decision", f"{name} истребил смутьянов в народе {poly.name}.",
                         weight=wt + 0.4, poly=poly.pid, person=jperson)
        elif j.kind == "contact":
            o = j.context.get("other_pid")
            q = self.polities.get(o) if o else None
            if q is None or q.dead is not None:
                return
            if ch == "trade":
                poly.neighbors_known[o] = 0.5
                q.neighbors_known[poly.pid] = 0.4
                poly.values["openness"] = min(1.0, poly.values.get("openness", 0.5) + 0.10)
                self.log("contact", f"{poly.name} и {q.name} завязали обмен.", weight=wt, poly=poly.pid)
            elif ch == "attack":
                poly.at_war_with.add(o)
                q.at_war_with.add(poly.pid)
                poly.neighbors_known[o] = -0.7
                q.neighbors_known[poly.pid] = -0.7
                self.log("contact", f"{poly.name} встретил {q.name} копьём.", weight=wt, poly=poly.pid)
            elif ch == "avoid":
                poly.neighbors_known[o] = -0.1
                poly.values["openness"] = max(0.05, poly.values.get("openness", 0.5) - 0.10)
            elif ch == "absorb":
                poly.neighbors_known[o] = 0.8
                q.neighbors_known[poly.pid] = 0.6
                if q.pop < poly.pop * 0.45 and self.rng.random() < 0.35:
                    self._merge(poly, q)
            elif ch == "tribute":
                if poly.pop > q.pop * 1.4:
                    q.tribute_to = poly.pid
                    self.log("contact", f"{q.name} обложен данью в пользу {poly.name}.",
                             weight=wt, poly=poly.pid)
                else:
                    poly.at_war_with.add(o)
                    q.at_war_with.add(poly.pid)
        elif j.kind == "succession":
            idx = np.array(poly.agent_ids, dtype=np.int64)
            idx = idx[self.co.alive[idx]]
            if idx.size == 0:
                return
            if ch == "heir":
                nl = ag.select_leaders(self.rng, co, idx, "kingdom", self.year, self.leaders.get(poly.pid))
            elif ch == "strongest":
                nl = int(idx[int(np.argmax(co.prestige[idx] + co.traits[idx, ag.TI["aggression"]]))])
                poly.legitimacy = max(0.03, poly.legitimacy - 0.10)
            elif ch == "council":
                nl = int(idx[int(np.argmax(co.prestige[idx] + co.traits[idx, ag.TI["sociability"]]))])
                poly.complexity = max(0.0, poly.complexity - 0.05)
                poly.legitimacy = min(1.0, poly.legitimacy + 0.08)
            elif ch == "priest":
                pr = idx[co.role[idx] == ag.RI["priest"]]
                nl = int(pr[0]) if pr.size else int(idx[0])
                poly.legitimacy = min(1.0, poly.legitimacy + 0.10)
            else:
                poly.values["_force_split"] = 1
                nl = int(idx[int(np.argmax(co.prestige[idx]))])
            self._enthrone(poly, nl, self.leaders.get(poly.pid))
            self.leaders[poly.pid] = nl
        elif j.kind == "innovation":
            tid = j.context.get("tech_tid")
            rep2 = self.reps.get(j.polity)
            if tid is None or rep2 is None or rep2.known[tid]:
                return
            t = kn.CATALOG[tid]
            if ch == "abandon":
                self.log("decision", f"{name} отступился от замысла: {t.name}.",
                         weight=max(1.4, wt - 0.8), poly=poly.pid, person=jperson)
                return
            grip = {"pursue": 0.55, "share": 0.75, "hoard": 0.28}.get(ch, 0.4)
            kn.learn(rep2, tid, grip=grip)
            rep2.discovered_by[tid] = (self.year, jperson, None)
            self.stats["discoveries"] += 1
            if co.alive[who]:
                co.prestige[who] += 0.4 + 0.25 * t.difficulty
                co.notable[who] = True
            if ch == "hoard":
                poly.values.setdefault("_secret", []).append(int(tid))
                poly.values["openness"] = max(0.05, poly.values.get("openness", 0.5) - 0.08)
                if co.alive[who]:
                    co.wealth[who] = min(4.0, co.wealth[who] + 0.5)
                verb = "утаил для своих"
            elif ch == "share":
                poly.values["openness"] = min(1.0, poly.values.get("openness", 0.5) + 0.10)
                verb = "открыл всем"
            else:
                verb = "довёл до конца"
            self.log("discovery", f"{name} из народа {poly.name} {verb} замысел: {t.name}.",
                     weight=1.8 + t.difficulty * 0.55, poly=poly.pid, person=jperson,
                     tech=t.key)
            self._deed(poly, who, "discovery", f"{verb} замысел: {t.name}")
        elif j.kind == "reform":
            if ch == "centralize":
                poly.complexity = min(1.0, poly.complexity + 0.10)
                poly.legitimacy = max(0.03, poly.legitimacy - 0.05)
                poly.cohesion = max(0.05, poly.cohesion - 0.04)
            elif ch == "distribute":
                poly.complexity = max(0.0, poly.complexity - 0.06)
                poly.legitimacy = min(1.0, poly.legitimacy + 0.10)
            elif ch == "codify":
                poly.legitimacy = min(1.0, poly.legitimacy + 0.14)
                poly.cohesion = min(1.0, poly.cohesion + 0.05)
                self.log("decision", f"{name} велел записать законы народа {poly.name}.",
                         weight=wt + 0.5, poly=poly.pid, person=jperson)
            elif ch == "sacralize":
                poly.legitimacy = min(1.0, poly.legitimacy + 0.16)
                poly.values["openness"] = max(0.05, poly.values.get("openness", 0.5) - 0.08)
                idx = np.array(poly.agent_ids, dtype=np.int64)
                idx = idx[co.alive[idx]]
                if idx.size:
                    ag.indoctrinate(co, idx, {"authority": 0.92, "divine": 0.88}, 0.4)
                if poly.gods:
                    self.log("decision", f"Власть в народе {poly.name} освящена именем "
                                         f"{poly.gods[0]['name']}.", weight=wt, poly=poly.pid)

    # ────────────────────────────────────────────────────────────────────
    def _do_wars(self, wars, dt):
        seen = set()
        for a_id, b_id in wars:
            key = tuple(sorted((a_id, b_id)))
            if key in seen:
                continue
            seen.add(key)
            a, b = self.polities.get(a_id), self.polities.get(b_id)
            if not a or not b or a.dead is not None or b.dead is not None:
                continue
            res = so.resolve_war(self.rng, self.world, self.grid, self.clim(),
                                 a, b, self.reps[a_id], self.reps[b_id], self.co, self.year, dt)
            self.stats["wars"] += 1
            W = self.polities[res["winner"]]
            L = self.polities[res["loser"]]
            for sid in res["sacked"]:
                s = self.settlements.get(sid)
                if s and not s.destroyed:
                    s.destroyed = self.year
                    self.grid.settle[s.y * self.world.width + s.x] = -1
                    if sid in L.settlements:
                        L.settlements.remove(sid)
                    self.log("war", f"{s.name} разграблен и сожжён.", weight=3.4,
                             poly=L.pid, y=s.y, x=s.x)
            if res.get("annexed") and L.cells:
                self._merge(W, L, conquest=True)
                self.log("war", f"{W.name} присоединил земли народа {L.name} к своей державе.",
                         weight=2.6 + min(2.2, max(0.0, math.log10(max(10, W.pop)) - 4.2)),
                         poly=W.pid)
                a.at_war_with.discard(b_id)
                b.at_war_with.discard(a_id)
                continue
            txt = f"{W.name} одолел {L.name}"
            if res["taken"]:
                txt += f", отняв {len(res['taken'])} земель"
            if res["tribute"]:
                txt += " и обложил данью"
            self.log("war", txt + ".",
                     weight=1.1 + min(2.9, max(0.0, math.log10(max(10, W.pop + L.pop)) - 3.4) * 0.95),
                     poly=W.pid)
            a.at_war_with.discard(b_id)
            b.at_war_with.discard(a_id)

    def _do_diffusion(self, links, dt):
        rate = self.cfg["diffusion_rate"]
        for pid, nb in links.items():
            poly = self.polities.get(pid)
            if poly is None or poly.dead is not None or not nb:
                continue
            rep = self.reps[pid]
            openness = poly.values.get("openness", 0.5)
            for o, s in nb.items():
                q = self.polities.get(o)
                if q is None or q.dead is not None:
                    continue
                rel = poly.neighbors_known.get(o, 0.0)
                contact = s * (0.4 + 0.6 * max(0.0, rel + 0.4)) * min(0.3, 0.0012 * dt * rate + 0.0012)
                if contact <= 0.0004:
                    continue
                mats = self._mat_vecs.get(pid)
                if mats is None:
                    continue
                sed = so.MODE_SED[so.MODE_I[poly.subsistence]]
                ts = so.tech_scale(poly, self.settlements)
                hr = kn.carrying_knowledge(ts, rep.count())
                if hr < 0.10:
                    continue
                secret = self.polities[o].values.get("_secret") if o in self.polities else None
                src_rep = self.reps[o]
                if secret:
                    src_rep = src_rep.copy()
                    for stid in secret:
                        src_rep.grip[stid] *= 0.18
                got = kn.diffuse(self.rng, rep, src_rep, contact * hr, 0.35 + openness,
                                 mats, ts, poly.surplus, sed,
                                 so.biomes_of(self.clim(), poly), max_items=2,
                                 eco_gap=self._eco_gap(poly, q))
                del src_rep
                for tid in got:
                    t = kn.CATALOG[tid]
                    if t.difficulty >= 3.0:
                        self.log("diffusion",
                                 f"{poly.name} перенял у народа {q.name}: {t.name}.",
                                 weight=1.7 + t.difficulty * 0.2, poly=pid, tech=t.key)

    def _eco_gap(self, a, b) -> float:
        """Насколько несхожи условия двух народов — по широте и по биому."""
        if not a.cells or not b.cells:
            return 1.0
        lat = self.world.latitude.ravel()
        la = float(np.mean([lat[c] for c in sorted(a.cells)[:24]]))
        lb = float(np.mean([lat[c] for c in sorted(b.cells)[:24]]))
        dlat = abs(la - lb) / 22.0
        ba = so.biomes_of(self.clim(), a)
        bb = so.biomes_of(self.clim(), b)
        share = len(ba & bb) / max(1, len(ba | bb))
        return float(min(2.5, dlat + 0.8 * (1.0 - share)))

    def _do_fission(self, dt):
        if len(self.polities) >= self.cfg["max_polities"]:
            return
        for pid in list(self.polities.keys()):
            poly = self.polities.get(pid)
            if poly is None or poly.dead is not None or len(poly.cells) < 2:
                continue
            rep = self.reps[pid]
            p = so.fission_pressure(poly, rep, so.territorial_extent(self.world, poly))
            forced = poly.values.pop("_force_split", 0)
            if not forced and self.rng.random() > 1 - math.exp(-0.035 * p * dt):
                continue
            if not forced and p < 0.55:
                continue
            sp = so.split_cells(self.world, poly, self.rng)
            if sp is None:
                continue
            keep, give = sp
            if len(give) < 1 or len(keep) < 1:
                continue
            npid = self._new_pid()
            gens = max(4, int(dt))
            child_lect = self.lects[pid].branch(self.prng, int(self.rng.integers(25, 90)))
            child = Polity(pid=npid, name=child_lect.ethnonym(self.prng),
                           lect=child_lect.to_dict(), color=_shift(poly.color, self.prng),
                           born=self.year, parent=pid)
            child.cells = give
            for c in give:
                self.grid.owner[c] = npid
            poly.cells = keep
            frac = len(give) / max(1, len(give) + len(keep))
            child.pop = poly.pop * frac
            poly.pop *= (1 - frac)
            child.subsistence = poly.subsistence
            child.form = "tribe" if poly.form in ("empire", "kingdom") else poly.form
            child.values = dict(poly.values)
            child.gods = [dict(g) for g in poly.gods]
            child.cohesion = min(1.0, poly.cohesion + 0.15)
            child.legitimacy = 0.5
            self.polities[npid] = child
            self.reps[npid] = self.reps[pid].copy()
            self.lects[npid] = child_lect
            self.leaders[npid] = None
            # переселяем часть людей
            co = self.co
            idx = np.array([i for i in poly.agent_ids if co.alive[i]], dtype=np.int64)
            if idx.size:
                take = idx[self.rng.random(idx.size) < frac]
                for i in take:
                    co.polity[i] = npid
                child.agent_ids = list(map(int, take))
                poly.agent_ids = [int(i) for i in idx if i not in set(map(int, take))]
            if not child.agent_ids:
                y, x = divmod(min(give), self.world.width)
                self._populate(child, y, x)
            self.rep_weight[npid] = child.pop / max(1, len(child.agent_ids))
            poly.cohesion = min(1.0, poly.cohesion + 0.10)
            self.stats["fissions"] += 1
            self.log("fission",
                     f"От народа {poly.name} отделился {child.name} "
                     f"({int(child.pop):,} душ).".replace(",", " "),
                     weight=0.8 + min(2.4, math.log10(max(10, child.pop)) / 1.6), poly=pid)

    def _merge(self, host, guest, conquest: bool = False):
        for c in sorted(guest.cells):
            self.grid.owner[c] = host.pid
            host.cells.add(c)
        guest.cells = set()
        host.pop += guest.pop
        for i in guest.agent_ids:
            if self.co.alive[i]:
                self.co.polity[i] = host.pid
                host.agent_ids.append(i)
        for sid in guest.settlements:
            s = self.settlements.get(sid)
            if s:
                s.culture = host.pid
                host.settlements.append(sid)
        rh, rg = self.reps[host.pid], self.reps[guest.pid]
        new = np.flatnonzero(rg.known & ~rh.known)
        rh.known |= rg.known
        rh.grip = np.maximum(rh.grip, rg.grip * 0.7)
        guest.dead = self.year
        # Язык покорённых не исчезает мгновенно: он оседает в языке победителей
        gl = self.lects.get(guest.pid)
        hl = self.lects.get(host.pid)
        if conquest and gl is not None and hl is not None and guest.pop > host.pop * 0.15:
            host.values["substrate"] = guest.name
        if conquest:
            host.cohesion = max(0.08, host.cohesion - 0.10)
            host.legitimacy = max(0.05, host.legitimacy - 0.04)
            host.complexity = min(1.0, host.complexity + 0.05)
        else:
            self.log("merge", f"{guest.name} влился в народ {host.name}.",
                     weight=2.6, poly=host.pid)

    def _extinct(self, poly, why):
        for c in sorted(poly.cells):
            self.grid.owner[c] = -1
        for i in poly.agent_ids:
            if self.co.alive[i]:
                self.co.kill(int(i))
        for sid in poly.settlements:
            s = self.settlements.get(sid)
            if s and not s.destroyed:
                s.destroyed = self.year
        poly.cells = set()
        poly.dead = self.year
        self.stats["extinctions"] += 1
        self.log("extinction", f"Народ {poly.name} {why}.",
                 weight=1.0 + min(2.6, max(0.0, math.log10(max(10, poly.pop)) - 3.2) * 0.95),
                 poly=poly.pid)

    def _reap(self):
        co = self.co
        for pid in list(self.polities):
            p = self.polities[pid]
            if p.dead is not None:
                continue
            # слот умершего мог достаться человеку другого народа — подчищаем
            p.agent_ids = [i for i in p.agent_ids
                           if co.alive[i] and int(co.polity[i]) == pid]
            if p.pop < 12 or not p.cells or not p.agent_ids:
                self._extinct(p, "исчез")

    # ────────────────────────────────────────────────────────────────────
    def _enthrone(self, poly, new_lead, old_lead):
        co = self.co
        if new_lead is None or not co.alive[new_lead]:
            return
        lect = self.lects[poly.pid]
        title = lect.title(self.prng, poly.form)
        name = self._name_of(poly, new_lead)
        co.role[new_lead] = ag.RI["chief"]
        co.prestige[new_lead] += 0.5
        if poly.form in ("chiefdom", "kingdom", "empire", "citystate", "republic") \
                and poly.pop > 1500:
            self.log("rule", f"{title} {name} встал во главе народа {poly.name}.",
                     weight=1.2 + min(2.4, max(0.0, math.log10(max(10, poly.pop)) - 3.6) * 0.9),
                     poly=poly.pid, person=int(co.aid[new_lead]))
            co.notable[new_lead] = True
            self._deed(poly, new_lead, "rule", f"{title} народа {poly.name}")

    def _remember(self, poly, i):
        """Занести человека в книгу мира: тела истлевают, записи остаются."""
        co = self.co
        aid = int(co.aid[i])
        rec = self.people.get(aid)
        if rec is None:
            rec = {
                "aid": aid, "name": self._name_of(poly, i), "polity": poly.pid,
                "polity_name": poly.name, "born": int(co.born[i]),
                "sex": int(co.sex[i]), "kin": int(co.kin_group[i]),
                "traits": {t: round(float(co.traits[i, k]), 2) for k, t in enumerate(ag.TRAITS)},
                "beliefs": {b: round(float(co.belief[i, k]), 2) for k, b in enumerate(ag.BELIEFS)},
                "deeds": [], "died": None, "role": ag.ROLES[int(co.role[i])],
                "era": kn.era_of(self.reps[poly.pid]),
                "mode": poly.subsistence, "form": poly.form,
            }
            self.people[aid] = rec
        rec["role"] = ag.ROLES[int(co.role[i])]
        rec["prestige"] = round(float(co.prestige[i]), 2)
        rec["power"] = round(float(co.power[i]), 2)
        rec["wealth"] = round(float(co.wealth[i]), 2)
        rec["last_seen"] = self.year
        return rec

    def _deed(self, poly, i, kind: str, text: str):
        rec = self._remember(poly, i)
        rec["deeds"].append({"year": self.year, "kind": kind, "text": text})

    def _name_of(self, poly, i) -> str:
        aid = int(self.co.aid[i])
        nm = self._names.get(aid)
        if nm is None:
            lect = self.lects.get(poly.pid)
            if lect is None:
                nm = f"№{aid}"
            else:
                nm = lect.person_name(self.prng, int(self.co.sex[i]),
                                      ag.ROLES[int(self.co.role[i])])
            self._names[aid] = nm
        return nm

    def _on_death(self, poly, i):
        co = self.co
        aid = int(co.aid[i])
        if aid in self.people:
            self.people[aid]["died"] = self.year
            self.people[aid]["age"] = self.year - int(co.born[i])
            self.people[aid]["life"] = ag.life_story(co, i, self.year)
        # Со смертью мастера, который никого не выучил, умение уходит по-настоящему:
        # у его народа больше нет ни одних рук, которые это умели.
        top = float(co.mastery[i].max())
        if top > 0.62 and int(co.taught[i]) == 0 and poly.pop > 400:
            dom = ag.DOMAINS[int(np.argmax(co.mastery[i]))]
            peers = np.array([j for j in poly.agent_ids
                              if co.alive[j] and j != i], dtype=np.int64)
            if peers.size and float(co.mastery[peers, ag.DI[dom]].max()) < top - 0.30:
                self.log("loss",
                         f"{self._name_of(poly, i)} умер, не передав своё "
                         f"мастерство ({ag.DOMAIN_RU[dom]}); в народе {poly.name} "
                         f"больше нет рук, которые это умели.",
                         weight=2.0 + 2.0 * top, poly=poly.pid, person=aid)
                # личное умение исчезло — общее знание в этой области слабеет
                rep = self.reps.get(poly.pid)
                if rep is not None:
                    kn.forget_domain(rep, dom, strength=0.35 * top)
        if not co.notable[i]:
            return
        age = self.year - int(co.born[i])
        if co.power[i] > 0.4 and poly.pop > 2000:
            self.log("death", f"{self._name_of(poly, i)} умер в {age} лет "
                              f"({so.FORM_RU.get(poly.form, poly.form)} {poly.name}).",
                     weight=1.8, poly=poly.pid, person=int(co.aid[i]))

    def _rebalance(self, poly):
        """Держим выборку людей нужного размера, не трогая численность народа."""
        co = self.co
        idx = np.array([i for i in poly.agent_ids if co.alive[i]], dtype=np.int64)
        tgt = self._target_cohort(poly.pop)
        if idx.size == 0:
            return
        if idx.size > tgt * 1.7:
            keep = self.rng.permutation(idx)[:tgt]
            drop = np.setdiff1d(idx, keep)
            for i in drop:
                co.kill(int(i))
            idx = keep
        elif idx.size < max(8, tgt * 0.55) and poly.pop > 60:
            need = int(tgt - idx.size)
            src = idx
            for _ in range(min(need, 40)):
                s = int(src[int(self.rng.integers(0, src.size))])
                try:
                    j = co.spawn(self.rng, poly.pid, int(co.born[s]), int(co.y[s]), int(co.x[s]),
                                 kin_group=int(co.kin_group[s]))
                except RuntimeError:
                    break
                co.traits[j] = np.clip(co.traits[s] + self.rng.normal(0, 0.07, ag.N_TRAIT), .02, .98)
                co.belief[j] = np.clip(co.belief[s] + self.rng.normal(0, 0.07, ag.N_BELIEF), .02, .98)
                co.skill[j] = co.skill[s] * 0.9
                co.wealth[j] = co.wealth[s] * 0.6
                idx = np.append(idx, j)
        poly.agent_ids = list(map(int, idx))
        self.rep_weight[poly.pid] = poly.pop / max(1, idx.size)

    # ────────────────────────────────────────────────────────────────────
    #  Прогон
    # ────────────────────────────────────────────────────────────────────
    def run(self, until: int | None = None, verbose: bool = True):
        end = until if until is not None else self.cfg["year_end"]
        t0 = time.time()
        next_snap = self.year
        next_ck = self.year + self.cfg["checkpoint_every"]
        while self.year < end:
            self.step()
            if self.year >= next_snap:
                self._snapshot()
                next_snap += self.cfg["snapshot_every"]
            if self.year >= next_ck:
                self.checkpoint()
                next_ck += self.cfg["checkpoint_every"]
            if verbose and self.year % 1000 < dt_for(self.year):
                alive = [p for p in self.polities.values() if p.dead is None]
                pop = sum(p.pop for p in alive)
                tech = max((self.reps[p.pid].count() for p in alive), default=0)
                print(f"  {yr(self.year):>14}  народов {len(alive):4d}  "
                      f"людей {pop/1e6:7.2f} млн  знаний до {tech:3d}  "
                      f"({time.time()-t0:5.1f} c)", flush=True)
        self._snapshot()
        self.checkpoint()
        self.flush()
        if verbose:
            print(f"  готово за {time.time()-t0:.1f} c")
        return self

    # ── запись ──
    def _snapshot(self):
        alive = [p for p in self.polities.values() if p.dead is None and p.cells]
        cm = np.full(self.world.height * self.world.width, -1, dtype=np.int16)
        for p in alive:
            for c in sorted(p.cells):
                cm[c] = p.pid % 32000
        pops = [p.pop for p in alive] or [0]
        modes = {}
        forms = {}
        for p in alive:
            modes[p.subsistence] = modes.get(p.subsistence, 0) + p.pop
            forms[p.form] = forms.get(p.form, 0) + p.pop
        best = max(alive, key=lambda p: self.reps[p.pid].count(), default=None)
        snap = {
            "year": self.year,
            "culture_map": base64.b64encode(cm.tobytes()).decode(),
            "polities": [{
                "pid": p.pid, "name": p.name, "color": p.color, "pop": int(p.pop),
                "mode": p.subsistence, "form": p.form, "cells": len(p.cells),
                "tech": self.reps[p.pid].count(), "complexity": round(p.complexity, 3),
                "ineq": round(p.inequality, 3), "coh": round(p.cohesion, 3),
                "era": kn.era_of(self.reps[p.pid]),
                "gods": [g["name"] for g in p.gods[:4]],
                "legit": round(p.legitimacy, 3), "surplus": round(p.surplus, 3),
                "capital": (self.settlements[p.capital].name
                            if p.capital in self.settlements else None),
            } for p in sorted(alive, key=lambda q: -q.pop)[:260]],
            "routes": self.routes[:1200],
            "settlements": [{"sid": s.sid, "name": s.name, "y": s.y, "x": s.x,
                             "pop": int(s.pop), "tier": so.settlement_tier(s.pop),
                             "culture": s.culture, "walls": round(s.walls, 2),
                             "mon": len(s.monuments)}
                            for s in self.settlements.values()
                            if not s.destroyed and s.pop > 250],
        }
        self.snapshots.append(snap)
        self.timeline.append({
            "year": self.year,
            "pop": float(sum(pops)),
            "polities": len(alive),
            "tech_max": int(max((self.reps[p.pid].count() for p in alive), default=0)),
            "tech_mean": float(np.mean([self.reps[p.pid].count() for p in alive]) if alive else 0),
            "cities": sum(1 for s in self.settlements.values() if not s.destroyed and s.pop > 1200),
            "largest_city": int(max((s.pop for s in self.settlements.values()
                                     if not s.destroyed), default=0)),
            "max_polity_pop": float(max(pops)),
            "complexity": float(np.mean([p.complexity for p in alive]) if alive else 0),
            "inequality": float(np.mean([p.inequality for p in alive]) if alive else 0),
            "literacy": float(np.mean([p.literacy for p in alive]) if alive else 0),
            "modes": {k: round(v) for k, v in modes.items()},
            "forms": {k: round(v) for k, v in forms.items()},
            "era": kn.era_of(self.reps[best.pid]) if best else "—",
            "gods": int(sum(len(p.gods) for p in alive)),
            "routes": len(self.routes),
            "people": len(self.people),
            **{f"n_{k}": v for k, v in self.stats.items()},
        })

    def flush(self):
        d = self.dir
        (d / "run.json").write_text(json.dumps({
            "run_id": self.run_id, "config": self.cfg, "year": self.year,
            "stats": self.stats, "resolver": self.resolver.stats,
            "n_polities_ever": self._next_pid,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        with (d / "chronicle.jsonl").open("w", encoding="utf-8") as f:
            for e in self.chronicle:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
        with (d / "timeline.jsonl").open("w", encoding="utf-8") as f:
            for t in self.timeline:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        with (d / "snapshots.jsonl").open("w", encoding="utf-8") as f:
            for s in self.snapshots:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        with (d / "people.jsonl").open("w", encoding="utf-8") as f:
            for aid, r in sorted(self.people.items()):
                if not r.get("deeds") and not r.get("died"):
                    continue
                rec = dict(r)
                p = self.polities.get(rec.get("polity"))
                if p is not None:
                    rec["polity_name"] = p.name
                    rec["polity_alive"] = p.dead is None
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        wg.save_world(self.world, str(d / "world"))
        # языки живых народов — чтобы можно было сравнивать родство
        langs = {}
        for pid, p in self.polities.items():
            if p.dead is None:
                langs[pid] = {"name": p.name, "parent": p.parent, "born": p.born,
                              "lect": self.lects[pid].to_dict()}
        with gzip.open(d / "lects.json.gz", "wt", encoding="utf-8") as f:
            json.dump(langs, f, ensure_ascii=False)

    def checkpoint(self) -> Path:
        d = self.dir / "checkpoints"
        d.mkdir(exist_ok=True)
        p = d / f"ck_{self.year}.pkl.gz"
        state = {
            "cfg": self.cfg, "run_id": self.run_id, "year": self.year,
            "rng": self.rng.bit_generator.state, "prng": self.prng.getstate(),
            "grid": self.grid, "co": self.co, "polities": self.polities,
            "reps": self.reps, "lects": {k: v.to_dict() for k, v in self.lects.items()},
            "leaders": self.leaders, "rep_weight": self.rep_weight,
            "settlements": self.settlements, "next_pid": self._next_pid,
            "next_sid": self._next_sid, "chronicle": self.chronicle,
            "timeline": self.timeline, "snapshots": self.snapshots,
            "stats": self.stats, "names": dict(self._names),
            "people": self.people, "routes": self.routes,
            "drift_year": self._drift_year, "links_year": self._links_year,
            "land_links": self._land_links, "sea": self._sea, "sea_year": self._sea_year,
        }
        with gzip.open(p, "wb") as f:
            pickle.dump(state, f, protocol=4)
        return p

    @classmethod
    def restore(cls, ck_path: str | Path, world_path: str | Path,
                overrides: dict | None = None, run_dir: Path | None = None,
                new_run_id: str | None = None) -> "Sim":
        with gzip.open(ck_path, "rb") as f:
            st = pickle.load(f)
        cfg = dict(st["cfg"])
        if overrides:
            cfg.update(overrides)
        w = wg.load_world(str(world_path))
        s = cls.__new__(cls)
        s.cfg = cfg
        s.run_id = new_run_id or st["run_id"]
        s.dir = Path(run_dir) if run_dir else Path("runs") / s.run_id
        s.dir.mkdir(parents=True, exist_ok=True)
        s.world = w
        s.rng = np.random.default_rng()
        s.rng.bit_generator.state = st["rng"]
        s.prng = random.Random()
        s.prng.setstate(st["prng"])
        s.grid = st["grid"]
        s.co = st["co"]
        s.polities = st["polities"]
        s.reps = st["reps"]
        s.lects = {k: Lect.from_dict(v) for k, v in st["lects"].items()}
        s.leaders = st["leaders"]
        s.rep_weight = st["rep_weight"]
        s.settlements = st["settlements"]
        s._next_pid = st["next_pid"]
        s._next_sid = st["next_sid"]
        s.chronicle = st["chronicle"]
        s.timeline = st["timeline"]
        s.snapshots = st["snapshots"]
        s.stats = st["stats"]
        s._names = st.get("names", {})
        s.year = st["year"]
        s._clim = None
        s._clim_year = None
        s._sea = st.get("sea", {})
        s._sea_year = st.get("sea_year", -10 ** 9)
        s._mat_vecs = {}
        s.people = st.get("people", {})
        s.routes = st.get("routes", [])
        s._land_links = st.get("land_links")
        s._drift_year = st.get("drift_year", st.get("year", s.year))
        s._links_year = st.get("links_year", -10 ** 9)
        s.matfield = so.material_field(w)
        s._pending_junctures = []
        s.resolver = jc.Resolver(cfg["resolver"], s.dir, cfg["resolver_model"],
                                 cfg["oracle_wait"], cfg["resolver_budget"])
        return s


# ────────────────────────────────────────────────────────────────────────────
def _color(prng: random.Random) -> str:
    h = prng.random()
    s = 0.45 + prng.random() * 0.35
    v = 0.55 + prng.random() * 0.35
    i = int(h * 6)
    f = h * 6 - i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def _shift(hexcol: str, prng: random.Random) -> str:
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    d = lambda v: max(20, min(235, v + prng.randint(-45, 45)))
    return "#%02x%02x%02x" % (d(r), d(g), d(b))


def _verb(t) -> str:
    return {"неолит": "додумался", "бронза": "измыслил", "железо": "измыслил",
            "античность": "постиг", "средневековье": "постиг",
            "новое время": "постиг"}.get(t.era_hint, "сделал")
