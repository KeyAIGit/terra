"""
TERRA — субагентность.

Люди здесь не статистика. У каждого симулируемого человека свои черты,
свои потребности, СВОЯ КАРТИНА МИРА (часто ошибочная), своя память, родня,
союзники и враги. Каждый год он выбирает, что делать, исходя из того, во что
верит — а не из того, как устроен мир на самом деле.

Общество не управляет людьми. Общество — это то, что получается,
когда тысячи таких выборов складываются.

Реализация: структура массивов (SoA) на numpy — чтобы десятки тысяч людей
жили одновременно быстро. «Заметные» люди дополнительно получают богатый
объект с именем, памятью и деяниями.
"""
from __future__ import annotations

import numpy as np

from .contracts import NEEDS, TRAITS

N_TRAIT = len(TRAITS)
N_NEED = len(NEEDS)
TI = {t: i for i, t in enumerate(TRAITS)}
NI = {n: i for i, n in enumerate(NEEDS)}

# ── роли ────────────────────────────────────────────────────────────────────
ROLES = ("commoner", "elder", "hunter", "farmer", "healer", "artisan",
         "priest", "warrior", "trader", "scribe", "chief", "rebel")
RI = {r: i for i, r in enumerate(ROLES)}
ROLE_RU = {
    "commoner": "общинник", "elder": "старейшина", "hunter": "охотник",
    "farmer": "земледелец", "healer": "знахарь", "artisan": "ремесленник",
    "priest": "жрец", "warrior": "воин", "trader": "торговец",
    "scribe": "писец", "chief": "вождь", "rebel": "смутьян",
}

# ── действия ────────────────────────────────────────────────────────────────
ACTIONS = (
    "subsist",     # добывать пищу привычным способом
    "intensify",   # работать тяжелее / вкладываться в урожай
    "store",       # запасать впрок
    "experiment",  # пробовать новое → изобретения
    "teach",       # передавать знание → удержание знаний
    "migrate",     # уйти на новое место
    "raid",        # напасть на соседей
    "defend",      # укрепляться
    "trade",       # обмен с соседями
    "build",       # строить общее
    "worship",     # обряд, смысл, сплочение
    "climb",       # добиваться статуса → иерархия
    "rebel",       # оспорить власть
    "care",        # заботиться о родне → выживание детей
)
AI = {a: i for i, a in enumerate(ACTIONS)}
N_ACT = len(ACTIONS)

# базовая доля действия в обычной жизни — до всякой мотивации.
# Без этого «набег» и «бунт» становятся рутиной, чего в живых обществах не бывает.
_PRIOR = np.zeros(N_ACT, dtype=np.float32)

# как черты влияют на склонность к действию (матрица N_ACT × N_TRAIT)
_W = np.zeros((N_ACT, N_TRAIT), dtype=np.float32)


def _w(act, **kw):
    for k, v in kw.items():
        _W[AI[act], TI[k]] = v


_w("subsist", diligence=0.8, patience=0.2)
_w("intensify", diligence=1.0, patience=0.9, ambition=0.3)
_w("store", patience=1.2, risk=-0.5, diligence=0.4)
_w("experiment", curiosity=1.6, risk=0.7, conformity=-0.9)
_w("teach", sociability=0.9, empathy=0.6, patience=0.5, ambition=0.2)
_w("migrate", risk=1.2, curiosity=0.6, conformity=-0.6, patience=-0.3)
_w("raid", aggression=1.5, risk=0.9, empathy=-1.0, ambition=0.5)
_w("defend", risk=-0.7, aggression=0.4, patience=0.5, sociability=0.3)
_w("trade", sociability=1.0, curiosity=0.5, patience=0.4, aggression=-0.4)
_w("build", patience=1.1, diligence=0.8, sociability=0.4, ambition=0.3)
_w("worship", piety=1.6, conformity=0.7, sociability=0.4)
_w("climb", ambition=1.6, sociability=0.6, empathy=-0.4, risk=0.3)
_w("rebel", ambition=0.9, aggression=0.8, conformity=-1.3, risk=0.8)
_w("care", empathy=1.4, sociability=0.5, patience=0.4, aggression=-0.5)

for _a, _p in (("subsist", 2.6), ("care", 1.1), ("intensify", 0.45), ("store", 0.15),
               ("teach", 0.15), ("worship", 0.15), ("defend", -0.15), ("trade", -0.6),
               ("build", -0.9), ("climb", -0.9), ("experiment", -1.15), ("migrate", -1.35),
               ("raid", -1.95), ("rebel", -2.4)):
    _PRIOR[AI[_a]] = _p

# ── убеждения (субъективная модель мира) ───────────────────────────────────
BELIEFS = (
    "elsewhere",   # «там лучше, чем здесь»
    "danger",      # «чужие опасны»
    "novelty",     # «новое работает»
    "trust",       # «своим можно верить»
    "authority",   # «власть законна»
    "divine",      # «мир управляется волей высших»
    "scarcity",    # «еды не хватит»
)
BI = {b: i for i, b in enumerate(BELIEFS)}
N_BELIEF = len(BELIEFS)


class Cohort:
    """Все живые симулируемые люди мира в одной структуре массивов."""

    __slots__ = ("cap", "n", "free", "aid", "polity", "born", "sex", "y", "x",
                 "alive", "traits", "needs", "belief", "prestige", "wealth",
                 "power", "health", "skill", "role", "mate", "kin_group",
                 "last_act", "valence", "children", "notable", "seed_counter")

    def __init__(self, cap: int = 60000):
        self.cap = cap
        self.n = 0
        self.free: list[int] = []
        z = np.zeros
        self.aid = z(cap, dtype=np.int64)
        self.polity = z(cap, dtype=np.int32) - 1
        self.born = z(cap, dtype=np.int32)
        self.sex = z(cap, dtype=np.int8)
        self.y = z(cap, dtype=np.int16)
        self.x = z(cap, dtype=np.int16)
        self.alive = z(cap, dtype=bool)
        self.traits = z((cap, N_TRAIT), dtype=np.float32)
        self.needs = z((cap, N_NEED), dtype=np.float32)
        self.belief = z((cap, N_BELIEF), dtype=np.float32)
        self.prestige = z(cap, dtype=np.float32)
        self.wealth = z(cap, dtype=np.float32)
        self.power = z(cap, dtype=np.float32)
        self.health = z(cap, dtype=np.float32)
        self.skill = z(cap, dtype=np.float32)
        self.role = z(cap, dtype=np.int8)
        self.mate = z(cap, dtype=np.int32) - 1
        self.kin_group = z(cap, dtype=np.int32)
        self.last_act = z(cap, dtype=np.int8)
        self.valence = z(cap, dtype=np.float32)   # накопленный настрой жизни
        self.children = z(cap, dtype=np.int16)
        self.notable = z(cap, dtype=bool)
        self.seed_counter = 0

    # ── создание и смерть ──
    def spawn(self, rng, polity: int, year: int, y: int, x: int,
              parents: tuple[int, int] | None = None, kin_group: int = 0) -> int:
        if self.free:
            i = self.free.pop()
        else:
            if self.n >= self.cap:
                raise RuntimeError("когорта переполнена")
            i = self.n
            self.n += 1
        self.seed_counter += 1
        self.aid[i] = self.seed_counter
        self.polity[i] = polity
        self.born[i] = year
        self.sex[i] = rng.integers(0, 2)
        self.y[i], self.x[i] = y, x
        self.alive[i] = True
        if parents is None:
            self.traits[i] = np.clip(rng.beta(3.2, 3.2, N_TRAIT), 0.02, 0.98)
        else:
            a, b = parents
            # наследование + развитие: половина от родителей, половина среда
            mid = 0.5 * (self.traits[a] + self.traits[b])
            self.traits[i] = np.clip(mid + rng.normal(0, 0.13, N_TRAIT), 0.02, 0.98)
        self.needs[i] = 0.25
        # дети наследуют картину мира родителей — так культура становится инерционной
        if parents is None:
            self.belief[i] = np.clip(rng.normal(0.5, 0.16, N_BELIEF), 0.03, 0.97)
        else:
            a, b = parents
            self.belief[i] = np.clip(
                0.5 * (self.belief[a] + self.belief[b]) + rng.normal(0, 0.09, N_BELIEF),
                0.03, 0.97)
        self.prestige[i] = 0.0
        self.wealth[i] = 0.0
        self.power[i] = 0.0
        self.health[i] = 1.0
        self.skill[i] = 0.05
        self.role[i] = RI["commoner"]
        self.mate[i] = -1
        self.kin_group[i] = kin_group
        self.valence[i] = 0.0
        self.children[i] = 0
        self.notable[i] = False
        return i

    def spawn_many(self, rng, polity: int, year: int, mothers: np.ndarray,
                   fathers: np.ndarray) -> np.ndarray:
        """Пакетное рождение — тот же расчёт, что и в spawn, но без цикла Python."""
        k = mothers.size
        if k == 0:
            return np.zeros(0, dtype=np.int64)
        slots = []
        while len(slots) < k and self.free:
            slots.append(self.free.pop())
        need = k - len(slots)
        if need > 0:
            if self.n + need > self.cap:
                need = max(0, self.cap - self.n)
                k = len(slots) + need
                if k == 0:
                    return np.zeros(0, dtype=np.int64)
                mothers, fathers = mothers[:k], fathers[:k]
            slots.extend(range(self.n, self.n + need))
            self.n += need
        i = np.array(slots[:k], dtype=np.int64)
        self.aid[i] = self.seed_counter + 1 + np.arange(k)
        self.seed_counter += k
        self.polity[i] = polity
        self.born[i] = year
        self.sex[i] = rng.integers(0, 2, k)
        self.y[i] = self.y[mothers]
        self.x[i] = self.x[mothers]
        self.alive[i] = True
        mid = 0.5 * (self.traits[mothers] + self.traits[fathers])
        self.traits[i] = np.clip(mid + rng.normal(0, 0.13, (k, N_TRAIT)), 0.02, 0.98)
        self.needs[i] = 0.25
        self.belief[i] = np.clip(
            0.5 * (self.belief[mothers] + self.belief[fathers])
            + rng.normal(0, 0.09, (k, N_BELIEF)), 0.03, 0.97)
        # дети наследуют долю достатка и почёта — так рождается сословие
        self.wealth[i] = 0.30 * self.wealth[fathers] + 0.15 * self.wealth[mothers]
        self.prestige[i] = 0.18 * (self.prestige[fathers] + self.prestige[mothers])
        self.power[i] = 0.0
        self.health[i] = 1.0
        self.skill[i] = 0.05
        self.role[i] = RI["commoner"]
        self.mate[i] = -1
        self.kin_group[i] = self.kin_group[mothers]
        self.valence[i] = 0.0
        self.children[i] = 0
        self.notable[i] = False
        np.add.at(self.children, mothers, 1)
        np.add.at(self.children, fathers, 1)
        return i

    def kill(self, i: int):
        self.alive[i] = False
        self.polity[i] = -1
        m = int(self.mate[i])
        if m >= 0 and self.mate[m] == i:
            self.mate[m] = -1
        self.mate[i] = -1
        self.free.append(int(i))

    def live_idx(self) -> np.ndarray:
        return np.flatnonzero(self.alive[: self.n])

    def of_polity(self, pid: int) -> np.ndarray:
        return np.flatnonzero(self.alive[: self.n] & (self.polity[: self.n] == pid))

    def age(self, idx, year: int) -> np.ndarray:
        return year - self.born[idx]


# ────────────────────────────────────────────────────────────────────────────
#  Восприятие: что человек ЗНАЕТ о своём положении
# ────────────────────────────────────────────────────────────────────────────
def update_needs(co: Cohort, idx, food_ratio: float, threat: float, cohesion: float,
                 meaning_supply: float, inequality: float, dt: float):
    """Потребности растут от дефицита. Богатые и знатные страдают меньше."""
    if idx.size == 0:
        return
    priv = np.clip(0.55 * co.wealth[idx] + 0.45 * co.power[idx], 0, 1)
    # еда: общий рацион, скорректированный привилегией и неравенством
    share = food_ratio * (1.0 - inequality * (0.85 - priv))
    hunger = np.clip(1.35 - share, 0, 1.6)
    co.needs[idx, NI["food"]] += (hunger - co.needs[idx, NI["food"]]) * min(1.0, 0.5 * dt)
    # безопасность
    fear = np.clip(threat * (1.25 - 0.5 * co.traits[idx, TI["risk"]]), 0, 1.5)
    co.needs[idx, NI["safety"]] += (fear - co.needs[idx, NI["safety"]]) * min(1.0, 0.45 * dt)
    # родня
    lonely = np.where(co.mate[idx] < 0, 0.45, 0.12) + 0.25 * (co.children[idx] == 0)
    lonely = lonely * (0.4 + co.traits[idx, TI["sociability"]])
    co.needs[idx, NI["kin"]] += (np.clip(lonely, 0, 1) - co.needs[idx, NI["kin"]]) * min(1.0, 0.3 * dt)
    # статус — относительный: страдает тот, кто амбициозен и внизу
    if idx.size > 1:
        rank = _rankpct(co.prestige[idx] + 0.5 * co.power[idx])
    else:
        rank = np.array([0.5], dtype=np.float32)
    st = np.clip(co.traits[idx, TI["ambition"]] * (1.0 - rank) * 1.3, 0, 1)
    co.needs[idx, NI["status"]] += (st - co.needs[idx, NI["status"]]) * min(1.0, 0.3 * dt)
    # смысл
    mn = np.clip(co.traits[idx, TI["piety"]] * (1.0 - meaning_supply)
                 + 0.3 * (1.0 - cohesion), 0, 1)
    co.needs[idx, NI["meaning"]] += (mn - co.needs[idx, NI["meaning"]]) * min(1.0, 0.25 * dt)
    np.clip(co.needs[idx], 0, 1.6, out=co.needs[idx])


def _rankpct(v: np.ndarray) -> np.ndarray:
    if v.size == 0:
        return v
    order = np.argsort(np.argsort(v))
    return (order / max(1, v.size - 1)).astype(np.float32)


# ────────────────────────────────────────────────────────────────────────────
#  Выбор действия — сердце субагентности
# ────────────────────────────────────────────────────────────────────────────
def choose_actions(rng, co: Cohort, idx, ctx: dict, temperature: float = 0.55) -> np.ndarray:
    """Каждый решает сам, исходя из своих черт, нужд и УБЕЖДЕНИЙ.

    Ключевое: в утилите стоят belief-переменные человека, а не истинное
    состояние мира. Люди мигрируют не туда, где лучше, а туда, где они
    ВЕРЯТ, что лучше. Ошибаться — их право.
    """
    if idx.size == 0:
        return np.zeros(0, dtype=np.int8)
    T = co.traits[idx]
    N = co.needs[idx]
    B = co.belief[idx]

    # базовая склонность из черт характера поверх обыденного распорядка жизни
    U = T @ _W.T + _PRIOR[None, :]                     # (k, N_ACT)

    hunger = N[:, NI["food"]]
    fear = N[:, NI["safety"]]
    status = N[:, NI["status"]]
    meaning = N[:, NI["meaning"]]
    kinneed = N[:, NI["kin"]]

    b_else = B[:, BI["elsewhere"]]
    b_dang = B[:, BI["danger"]]
    b_new = B[:, BI["novelty"]]
    b_auth = B[:, BI["authority"]]
    b_div = B[:, BI["divine"]]
    b_scar = B[:, BI["scarcity"]]

    surplus = ctx.get("surplus", 0.0)
    crowd = ctx.get("crowding", 0.0)        # 0..2, давление на землю
    frontier = ctx.get("frontier", 0.0)     # есть ли куда идти (объективно)
    hostility = ctx.get("hostility", 0.0)
    wealth_near = ctx.get("neighbor_wealth", 0.0)
    can_trade = ctx.get("trade_partners", 0.0)
    legitimacy = ctx.get("legitimacy", 0.5)
    ineq = ctx.get("inequality", 0.0)
    leisure = min(0.55, max(0.0, surplus * 1.5 + 0.07))

    U[:, AI["subsist"]] += 1.4 * hunger + 0.5
    U[:, AI["intensify"]] += 1.7 * hunger + 1.1 * b_scar - 0.5 * fear
    U[:, AI["store"]] += 1.5 * b_scar + 0.8 * hunger * (surplus > 0) - 0.3
    # изобретают сытые и любопытные — голодному не до опытов
    U[:, AI["experiment"]] += (2.2 * leisure * b_new + 1.5 * min(1.5, crowd) * b_new
                               + 0.4 * b_new - 2.1 * np.clip(hunger - 0.45, 0, 1))
    U[:, AI["teach"]] += 1.0 * leisure + 0.6 * co.skill[idx] + 0.5 * co.prestige[idx]
    U[:, AI["migrate"]] += 2.0 * b_else * (0.4 + crowd) + 1.6 * hunger * b_else \
        + 0.9 * fear * b_else - 1.2 * (1.0 - frontier) - 0.7 * co.wealth[idx]
    U[:, AI["raid"]] += 1.9 * hunger * (1.0 - b_dang) + 1.3 * wealth_near \
        + 0.9 * status - 1.1 * b_dang * 0.5
    U[:, AI["defend"]] += 2.0 * fear + 1.5 * b_dang * hostility + 0.6 * co.wealth[idx]
    U[:, AI["trade"]] += 1.6 * can_trade * (1.0 - b_dang) + 0.9 * surplus - 0.6 * hostility
    U[:, AI["build"]] += 1.4 * surplus + 0.8 * b_auth * legitimacy + 0.5 * meaning
    U[:, AI["worship"]] += 2.0 * meaning * b_div + 1.1 * fear * b_div + 0.5 * b_div
    U[:, AI["climb"]] += 2.2 * status + 1.0 * b_auth * surplus - 0.4 * fear
    U[:, AI["rebel"]] += 2.4 * status * (1.0 - b_auth) + 1.8 * hunger * ineq \
        + 1.4 * (1.0 - legitimacy) * (1.0 - b_auth) - 2.0 * b_auth
    U[:, AI["care"]] += 1.8 * kinneed + 0.9 * (co.children[idx] > 0)

    # возраст: старики учат и молятся, молодые рискуют
    age = ctx["year"] - co.born[idx]
    old = np.clip((age - 40) / 30.0, 0, 1)[:, None]
    young = np.clip((28 - age) / 20.0, 0, 1)[:, None]
    U[:, AI["teach"]] += 1.3 * old[:, 0]
    U[:, AI["worship"]] += 0.7 * old[:, 0]
    U[:, AI["migrate"]] += 0.8 * young[:, 0]
    U[:, AI["raid"]] += 1.0 * young[:, 0] * T[:, TI["aggression"]]
    U[:, AI["climb"]] += 0.6 * young[:, 0]

    # у кого нет власти — тот не строит и не правит
    U[:, AI["build"]] += 1.2 * co.power[idx]
    U[:, AI["rebel"]] -= 2.0 * co.power[idx]

    # запрещённые в данном обществе действия
    for a in ctx.get("blocked", ()):
        U[:, AI[a]] = -50.0

    # мягкий выбор: люди не оптимизаторы, они склонны
    U = U / max(0.05, temperature)
    U -= U.max(axis=1, keepdims=True)
    P = np.exp(U)
    P /= P.sum(axis=1, keepdims=True)
    c = (P.cumsum(axis=1) > rng.random((idx.size, 1))).argmax(axis=1)
    return c.astype(np.int8)


# ────────────────────────────────────────────────────────────────────────────
#  Обучение: опыт и подражание
# ────────────────────────────────────────────────────────────────────────────
def learn_from_outcome(co: Cohort, idx, acts, outcome: np.ndarray, dt: float):
    """Убеждения правятся личным опытом. Медленно и с перекосом к недавнему."""
    if idx.size == 0:
        return
    lr = np.clip(0.06 * dt * (1.4 - co.traits[idx, TI["conformity"]]), 0.01, 0.35)
    good = outcome > 0
    # «новое работает» правится только если человек пробовал новое
    tried = (acts == AI["experiment"]) | (acts == AI["migrate"]) | (acts == AI["trade"])
    d = np.where(good, 1.0, 0.0)
    co.belief[idx, BI["novelty"]] += np.where(tried, lr * (d - co.belief[idx, BI["novelty"]]), 0)
    # «там лучше» — растёт от голода и падает после неудачной попытки уйти
    moved = acts == AI["migrate"]
    co.belief[idx, BI["elsewhere"]] += np.where(
        moved, lr * (d - co.belief[idx, BI["elsewhere"]]),
        lr * 0.35 * (np.clip(co.needs[idx, NI["food"]], 0, 1) - co.belief[idx, BI["elsewhere"]]))
    # «чужие опасны» — от насилия
    co.belief[idx, BI["danger"]] += lr * 0.6 * (
        np.clip(co.needs[idx, NI["safety"]], 0, 1) - co.belief[idx, BI["danger"]])
    # «еды не хватит» — от голода, и это убеждение переживает изобилие
    co.belief[idx, BI["scarcity"]] += lr * 0.5 * (
        np.clip(co.needs[idx, NI["food"]], 0, 1) - co.belief[idx, BI["scarcity"]]) \
        * np.where(co.needs[idx, NI["food"]] > co.belief[idx, BI["scarcity"]], 1.6, 0.45)
    co.valence[idx] += 0.2 * dt * (outcome - co.valence[idx])
    np.clip(co.belief[idx], 0.02, 0.98, out=co.belief[idx])


def social_learning(rng, co: Cohort, idx, dt: float, openness: float = 1.0):
    """Престижное и конформное подражание — главный механизм культуры.

    Люди копируют убеждения у тех, кто выглядит успешным, а не у тех,
    кто прав. Отсюда и мода, и предрассудки, и живучие традиции.
    """
    if idx.size < 4:
        return
    B = co.belief[idx]
    conf = co.traits[idx, TI["conformity"]][:, None]
    strength = np.clip(0.16 * dt * openness, 0.0, 0.6)

    # модель для подражания: престиж + богатство + власть
    score = co.prestige[idx] + 0.6 * co.wealth[idx] + 0.8 * co.power[idx]
    top_k = max(1, idx.size // 8)
    elite = np.argsort(score)[-top_k:]
    elite_mean = B[elite].mean(axis=0)
    crowd_mean = B.mean(axis=0)

    # престижное смещение сильнее у амбициозных, конформное — у конформных
    amb = co.traits[idx, TI["ambition"]][:, None]
    target = (amb * elite_mean + (1.0 - amb) * crowd_mean)
    co.belief[idx] = np.clip(B + strength * conf * (target - B), 0.02, 0.98)

    # черты не наследуются подражанием, но навык — да
    sk_elite = co.skill[idx][elite].mean()
    co.skill[idx] += strength * 0.35 * conf[:, 0] * np.clip(sk_elite - co.skill[idx], 0, None)


def indoctrinate(co: Cohort, idx, values: dict, strength: float):
    """Институты давят на убеждения: жречество → divine, закон → authority."""
    if idx.size == 0:
        return
    conf = co.traits[idx, TI["conformity"]]
    for b, tgt in values.items():
        j = BI.get(b)
        if j is None:
            continue
        co.belief[idx, j] += strength * conf * (tgt - co.belief[idx, j])
    np.clip(co.belief[idx], 0.02, 0.98, out=co.belief[idx])


# ────────────────────────────────────────────────────────────────────────────
#  Жизненный цикл
# ────────────────────────────────────────────────────────────────────────────
def mortality(rng, co: Cohort, idx, year: int, food_ratio: float, violence: float,
              disease: float, health_tech: float, dt: float) -> np.ndarray:
    """Возвращает индексы умерших. Смертность реалистично высокая."""
    if idx.size == 0:
        return np.zeros(0, dtype=np.int64)
    age = year - co.born[idx]
    # ванна: младенцы и старики
    base = 0.055 * np.exp(-age / 3.2) + 0.0075 + 0.00022 * np.clip(age - 18, 0, None) ** 1.62
    starve = np.clip(1.05 - food_ratio, 0, 1.2) ** 2 * 0.22
    priv = np.clip(0.5 * co.wealth[idx] + 0.5 * co.power[idx], 0, 1)
    q = (base + starve * (1.0 - 0.65 * priv) + violence * (0.4 + 0.9 * (co.role[idx] == RI["warrior"]))
         + disease) * (1.0 - 0.45 * np.clip(health_tech, 0, 1)) / np.clip(co.health[idx], 0.25, 1.2)
    p = 1.0 - np.exp(-np.clip(q, 0, 3.0) * dt)
    dead = idx[rng.random(idx.size) < p]
    return dead


def pair_and_breed(rng, co: Cohort, idx, year: int, fertility_mod: float,
                   dt: float, kin_group_of=None) -> list[tuple[int, int, int]]:
    """Пары и дети. Возвращает [(child_i, mother, father)]."""
    born = []
    if idx.size < 2:
        return born
    age = year - co.born[idx]
    adult = idx[(age >= 15) & (age <= 60)]
    if adult.size < 2:
        return born
    single = adult[co.mate[adult] < 0]
    f = single[co.sex[single] == 0]
    m = single[co.sex[single] == 1]
    if f.size and m.size:
        # выбор партнёра не случаен: смотрят на престиж и достаток
        k = min(f.size, m.size)
        m_score = co.prestige[m] + 0.7 * co.wealth[m] + 0.5 * co.skill[m] + rng.normal(0, 0.4, m.size)
        f_score = co.prestige[f] + 0.4 * co.wealth[f] + rng.normal(0, 0.5, f.size)
        mm = m[np.argsort(-m_score)][:k]
        ff = f[np.argsort(-f_score)][:k]
        # ассортативность: верхние с верхними
        sel = rng.random(k) < 0.55 * dt
        for a, b in zip(ff[sel], mm[sel]):
            co.mate[a] = b
            co.mate[b] = a

    mothers = adult[(co.sex[adult] == 0) & (co.mate[adult] >= 0)]
    if mothers.size == 0:
        return born
    mage = year - co.born[mothers]
    fec = np.clip(1.0 - ((mage - 26) / 19.0) ** 2, 0, 1)
    rate = 0.235 * fec * fertility_mod * co.health[mothers]
    rate *= (1.0 - 0.30 * np.clip(co.needs[mothers, NI["food"]], 0, 1))
    rate *= (0.75 + 0.7 * co.traits[mothers, TI["empathy"]] * 0.5 + 0.35 * co.wealth[mothers])
    # за длинный такт женщина рожает несколько раз, а не один
    counts = np.minimum(rng.poisson(np.clip(rate, 0, 0.6) * dt), 3)
    mm = np.repeat(mothers, counts)
    if mm.size == 0:
        return born
    ff = co.mate[mm]
    ok = (ff >= 0) & co.alive[np.clip(ff, 0, None)]
    mm, ff = mm[ok], ff[ok].astype(np.int64)
    kids = co.spawn_many(rng, int(co.polity[mm[0]]) if mm.size else -1, year, mm, ff)
    for ch, mo, fa in zip(kids, mm[:kids.size], ff[:kids.size]):
        born.append((int(ch), int(mo), int(fa)))
    return born


def age_effects(co: Cohort, idx, year: int, dt: float):
    """Навык и здоровье с возрастом."""
    if idx.size == 0:
        return
    age = year - co.born[idx]
    learn_rate = np.clip(0.055 * dt * (0.35 + co.traits[idx, TI["diligence"]]), 0, 0.5)
    ceiling = np.clip(0.25 + 0.75 * co.traits[idx, TI["diligence"]], 0.2, 1.0)
    growing = age < 45
    co.skill[idx] += np.where(growing, learn_rate * (ceiling - co.skill[idx]), -0.004 * dt)
    np.clip(co.skill[idx], 0.0, 1.0, out=co.skill[idx])
    decline = np.clip((age - 45) / 45.0, 0, 1)
    co.health[idx] = np.clip(1.0 - 0.55 * decline, 0.2, 1.0)


# ────────────────────────────────────────────────────────────────────────────
#  Статус, богатство, власть
# ────────────────────────────────────────────────────────────────────────────
def update_standing(rng, co: Cohort, idx, acts, ctx: dict, dt: float):
    """Кто поднялся, кто разорился. Отсюда растёт неравенство."""
    if idx.size == 0:
        return
    surplus = ctx.get("surplus", 0.0)
    extract = ctx.get("surplus_extract", 0.0)      # насколько элита умеет изымать
    # доход
    income = (0.35 + 0.65 * co.skill[idx]) * (0.5 + surplus * 4.0) * 0.06 * dt
    income += 0.10 * dt * (acts == AI["intensify"]) * (0.4 + co.skill[idx])
    income += 0.16 * dt * (acts == AI["trade"]) * ctx.get("trade_partners", 0.0)
    income += 0.22 * dt * (acts == AI["raid"]) * ctx.get("raid_success", 0.0)
    # изъятие: власть имущие снимают с остальных
    if extract > 0 and idx.size > 3:
        pw = co.power[idx]
        pool = (income * extract * (1.0 - pw)).sum()
        income -= income * extract * (1.0 - pw)
        share = pw / max(1e-6, pw.sum()) if pw.sum() > 0 else np.zeros_like(pw)
        income += pool * share
    co.wealth[idx] = np.clip(co.wealth[idx] * (1 - 0.03 * dt) + income, 0, 4.0)

    # престиж: от умений, дел и щедрости
    dp = 0.0
    dp = (0.05 * dt * co.skill[idx]
          + 0.09 * dt * (acts == AI["teach"])
          + 0.11 * dt * (acts == AI["build"])
          + 0.13 * dt * (acts == AI["climb"]) * co.traits[idx, TI["sociability"]]
          + 0.10 * dt * (acts == AI["worship"]) * ctx.get("piety_pays", 0.3)
          + 0.14 * dt * (acts == AI["raid"]) * ctx.get("raid_success", 0.0)
          + 0.05 * dt * np.clip(co.wealth[idx], 0, 1) * ctx.get("wealth_prestige", 0.4))
    co.prestige[idx] = np.clip(co.prestige[idx] * (1 - 0.035 * dt) + dp, 0, 3.0)


def select_leaders(rng, co: Cohort, idx, form: str, year: int,
                   incumbent: int | None) -> int | None:
    """Кто получает власть — зависит от формы общества, а не от «лучшего»."""
    if idx.size == 0:
        return None
    age = year - co.born[idx]
    grown = idx[age >= 18]
    if grown.size == 0:
        return None
    p = co.prestige[grown]
    w = co.wealth[grown]
    a = co.traits[grown, TI["ambition"]]
    g = co.traits[grown, TI["aggression"]]
    s = co.skill[grown]

    if form in ("band",):
        score = 0.6 * p + 0.5 * s + 0.2 * co.traits[grown, TI["empathy"]]
    elif form in ("tribe",):
        score = 0.7 * p + 0.4 * s + 0.3 * a
    elif form in ("bigman",):
        score = 1.0 * p + 0.8 * w + 0.6 * a
    elif form in ("chiefdom", "kingdom", "empire"):
        # наследование: если есть правитель — сначала его дети
        if incumbent is not None and co.alive[incumbent]:
            heirs = grown[(co.kin_group[grown] == co.kin_group[incumbent])]
            if heirs.size and rng.random() < 0.72:
                hs = 0.6 * co.prestige[heirs] + 0.5 * co.wealth[heirs] \
                    + 0.4 * co.traits[heirs, TI["ambition"]] + rng.normal(0, 0.35, heirs.size)
                return int(heirs[int(np.argmax(hs))])
        score = 0.8 * w + 0.7 * p + 0.7 * a + 0.5 * g
    elif form in ("republic", "citystate", "confederation"):
        score = 0.9 * p + 0.6 * co.traits[grown, TI["sociability"]] + 0.5 * w + 0.3 * s
    else:
        score = p + w
    score = score + rng.normal(0, 0.45, grown.size)
    return int(grown[int(np.argmax(score))])


def assign_roles(rng, co: Cohort, idx, rep_effects: dict, form: str, leader: int | None):
    """Специализация появляется только там, где есть избыток."""
    if idx.size == 0:
        return
    co.role[idx] = RI["commoner"]
    spec = np.clip(rep_effects.get("complexity", 0.0) + rep_effects.get("admin", 0.0) * 0.5, 0, 2.0)
    n_spec = int(min(idx.size * 0.45, idx.size * 0.10 * (1 + spec)))
    if n_spec > 0:
        cur = co.traits[idx, TI["curiosity"]]
        pie = co.traits[idx, TI["piety"]]
        agg = co.traits[idx, TI["aggression"]]
        soc = co.traits[idx, TI["sociability"]]
        emp = co.traits[idx, TI["empathy"]]
        pools = [
            ("artisan", cur + co.skill[idx], rep_effects.get("labor", 0) > 0.1),
            ("priest", pie * 1.5, rep_effects.get("legitimacy", 0) > 0.15),
            ("warrior", agg * 1.4, rep_effects.get("military", 0) > 0.15),
            ("trader", soc * 1.2, rep_effects.get("trade", 0) > 0.1),
            ("scribe", cur * 1.3 + co.skill[idx], rep_effects.get("info", 0) > 0.3),
            ("healer", emp * 1.2, rep_effects.get("health", 0) > 0.1),
        ]
        active = [(r, sc) for r, sc, on in pools if on]
        if active:
            per = max(1, n_spec // len(active))
            taken = set()
            for r, sc in active:
                order = np.argsort(-(sc + rng.normal(0, 0.3, idx.size)))
                cnt = 0
                for j in order:
                    if int(idx[j]) in taken:
                        continue
                    co.role[idx[j]] = RI[r]
                    taken.add(int(idx[j]))
                    cnt += 1
                    if cnt >= per:
                        break
    # старейшины
    if leader is not None and co.alive[leader]:
        co.role[leader] = RI["chief"]


def apply_power(co: Cohort, idx, leader: int | None, form: str, complexity: float):
    """Распределение формальной власти."""
    if idx.size == 0:
        return
    co.power[idx] *= 0.55
    conc = {"band": 0.12, "tribe": 0.2, "bigman": 0.3, "chiefdom": 0.55,
            "citystate": 0.6, "kingdom": 0.75, "empire": 0.85,
            "republic": 0.45, "confederation": 0.4}.get(form, 0.3)
    if leader is not None and co.alive[leader]:
        co.power[leader] = conc
    # элита: жрецы, воины, писцы получают долю власти
    elite_roles = (RI["priest"], RI["warrior"], RI["scribe"], RI["elder"])
    m = np.isin(co.role[idx], elite_roles)
    co.power[idx[m]] = np.maximum(co.power[idx[m]], conc * (0.25 + 0.35 * complexity))
    np.clip(co.power[idx], 0, 1, out=co.power[idx])


def gini(v: np.ndarray) -> float:
    if v.size < 2:
        return 0.0
    x = np.sort(np.clip(v, 0, None)) + 1e-9
    n = x.size
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def notability(co: Cohort, idx, year: int) -> np.ndarray:
    """Кто попадёт в летопись."""
    if idx.size == 0:
        return np.zeros(0, dtype=np.int64)
    score = (co.prestige[idx] + 1.2 * co.power[idx] + 0.6 * co.wealth[idx]
             + 0.8 * co.skill[idx] * (co.role[idx] != RI["commoner"]))
    return idx[score > 1.25]
