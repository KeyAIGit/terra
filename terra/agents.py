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

# ── прожитая жизнь: то, что копится в ОДНОМ человеке и умирает вместе с ним ──
#
# Знание цивилизации живёт в repertoire народа. Но народ — это не хранилище:
# всё, что «умеет общество», на деле держится в руках и головах живых людей.
# Здесь — их личный, невоспроизводимый капитал: чему научились руки, что
# запомнили глаза, что оставили на человеке голод, война и мор. Ничего из
# этого не наследуется автоматически. Либо мастер успел научить — либо с его
# смертью умение исчезает, даже если «в народе оно записано».
DOMAINS = ("forage", "farm", "craft", "war", "ritual",
           "trade", "letters", "heal", "build", "rule")
DI = {d: i for i, d in enumerate(DOMAINS)}
N_DOM = len(DOMAINS)
DOMAIN_RU = {
    "forage": "промысел", "farm": "земледелие", "craft": "ремесло", "war": "война",
    "ritual": "обряд", "trade": "торг", "letters": "счёт и письмо", "heal": "врачевание",
    "build": "строительство", "rule": "управление",
}

# какое действие какое умение упражняет (действие → [(домен, доля)])
ACT_PRACTICE: dict[str, tuple[tuple[str, float], ...]] = {
    # добывая пищу, человек попутно чинит и мастерит — отсюда и берутся руки,
    # способные однажды придумать новое
    "subsist": (("@subsist", 1.0), ("craft", 0.14)),
    "intensify": (("@subsist", 0.75), ("farm", 0.35)),
    "store": (("@subsist", 0.35), ("craft", 0.35)),
    "experiment": (("craft", 0.70), ("letters", 0.20)),
    "teach": (("@best", 0.45), ("ritual", 0.15)),
    "migrate": (("forage", 0.55),),
    "raid": (("war", 1.0),),
    "defend": (("war", 0.65), ("build", 0.25)),
    "trade": (("trade", 1.0), ("letters", 0.20)),
    "build": (("build", 1.0), ("craft", 0.30)),
    "worship": (("ritual", 1.0),),
    "climb": (("rule", 0.85), ("trade", 0.15)),
    "rebel": (("war", 0.5), ("rule", 0.5)),
    "care": (("heal", 0.85),),
}

# домены, которые слабеют с возрастом (тело), и те, что не слабеют (голова)
_DOM_PHYSICAL = np.zeros(N_DOM, dtype=np.float32)
for _d, _v in (("forage", 1.0), ("farm", 0.75), ("war", 1.25), ("build", 0.7),
               ("craft", 0.3), ("trade", 0.15)):
    _DOM_PHYSICAL[DI[_d]] = _v

# ── шрамы: пережитое, что остаётся на человеке до смерти ───────────────────
SCARS = ("hunger", "violence", "plague", "loss", "collapse", "glory")
SI = {s: i for i, s in enumerate(SCARS)}
N_SCAR = len(SCARS)
SCAR_RU = {
    "hunger": "голод", "violence": "насилие", "plague": "мор",
    "loss": "утрата близких", "collapse": "крушение порядка", "glory": "торжество",
}

N_MEM = 6            # сколько отдельных событий человек помнит поимённо
MEM_KINDS = ("none", "hunger", "violence", "plague", "loss", "collapse", "glory",
             "discovery", "birth", "power", "journey", "faith")
MI = {k: i for i, k in enumerate(MEM_KINDS)}
MEM_RU = {
    "hunger": "голодный год", "violence": "война", "plague": "мор",
    "loss": "смерть близкого", "collapse": "крушение державы", "glory": "торжество",
    "discovery": "открытие", "birth": "рождение ребёнка", "power": "власть",
    "journey": "уход с родных мест", "faith": "явление божества",
}


class Cohort:
    """Все живые симулируемые люди мира в одной структуре массивов."""

    __slots__ = ("cap", "n", "free", "aid", "polity", "born", "sex", "y", "x",
                 "alive", "traits", "needs", "belief", "prestige", "wealth",
                 "power", "health", "skill", "role", "mate", "kin_group",
                 "last_act", "valence", "children", "notable", "seed_counter",
                 # прожитая жизнь (умирает с человеком, если не передана)
                 "mastery", "lore", "scars", "mem_kind", "mem_year", "mem_val",
                 "mem_p", "taught", "teacher")

    # поля, добавленные позже: старые чекпоинты дозаполняются при загрузке
    _LATE = ("mastery", "lore", "scars", "mem_kind", "mem_year", "mem_val",
             "mem_p", "taught", "teacher")

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
        # ── прожитая жизнь ──
        self.mastery = z((cap, N_DOM), dtype=np.float32)   # чему научились руки
        self.lore = z(cap, dtype=np.float32)               # доля знания своего народа
        self.scars = z((cap, N_SCAR), dtype=np.float32)    # что оставило пережитое
        self.mem_kind = z((cap, N_MEM), dtype=np.int8)     # что человек помнит
        self.mem_year = z((cap, N_MEM), dtype=np.int32)
        self.mem_val = z((cap, N_MEM), dtype=np.float32)
        self.mem_p = z(cap, dtype=np.int8)                 # куда писать следующее
        self.taught = z(cap, dtype=np.int16)               # скольких успел научить
        self.teacher = z(cap, dtype=np.int32) - 1          # у кого учился

    # ── чекпоинты ──
    def __getstate__(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def __setstate__(self, st):
        # старые чекпоинты писались протоколом по умолчанию: (None, {слоты})
        if isinstance(st, tuple):
            st = st[1] or {}
        for k in self.__slots__:
            if k in st:
                setattr(self, k, st[k])
        # старые миры: полей прожитой жизни не было — заводим пустыми
        cap = st["cap"]
        for k in self._LATE:
            if k in st:
                continue
            if k == "mastery":
                v = np.zeros((cap, N_DOM), dtype=np.float32)
                v[:, DI["forage"]] = st["skill"]           # прежний общий навык
            elif k == "scars":
                v = np.zeros((cap, N_SCAR), dtype=np.float32)
            elif k == "mem_kind":
                v = np.zeros((cap, N_MEM), dtype=np.int8)
            elif k == "mem_year":
                v = np.zeros((cap, N_MEM), dtype=np.int32)
            elif k == "mem_val":
                v = np.zeros((cap, N_MEM), dtype=np.float32)
            elif k == "mem_p":
                v = np.zeros(cap, dtype=np.int8)
            elif k == "taught":
                v = np.zeros(cap, dtype=np.int16)
            elif k == "teacher":
                v = np.zeros(cap, dtype=np.int32) - 1
            else:                                          # lore
                v = np.full(cap, 0.35, dtype=np.float32)
            setattr(self, k, v)

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
        # человек рождается пустым: ни умения, ни знания, ни памяти
        self.mastery[i] = 0.0
        self.lore[i] = 0.0
        self.scars[i] = 0.0
        self.mem_kind[i] = 0
        self.mem_year[i] = 0
        self.mem_val[i] = 0.0
        self.mem_p[i] = 0
        self.taught[i] = 0
        self.teacher[i] = -1
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
        # ребёнок не наследует ни ремесла, ни памяти родителей — только их учат
        self.mastery[i] = 0.0
        self.lore[i] = 0.0
        self.scars[i] = 0.0
        self.mem_kind[i] = 0
        self.mem_year[i] = 0
        self.mem_val[i] = 0.0
        self.mem_p[i] = 0
        self.taught[i] = 0
        self.teacher[i] = -1
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

    # ── прожитое: человек выбирает не только по нужде, но и по памяти ──
    S = co.scars[idx]
    s_hun, s_vio = S[:, SI["hunger"]], S[:, SI["violence"]]
    s_pla, s_los = S[:, SI["plague"]], S[:, SI["loss"]]
    s_col, s_glo = S[:, SI["collapse"]], S[:, SI["glory"]]
    # переживший голод копит впрок даже в изобилии — до самой смерти
    U[:, AI["store"]] += 1.35 * s_hun
    U[:, AI["intensify"]] += 0.75 * s_hun
    U[:, AI["experiment"]] -= 0.45 * s_hun          # осторожность выученного голода
    # переживший войну укрепляется и не доверяет
    U[:, AI["defend"]] += 1.25 * s_vio
    U[:, AI["trade"]] -= 0.55 * s_vio
    U[:, AI["raid"]] += 0.45 * s_vio * T[:, TI["aggression"]]
    # мор гонит к богам и с места
    U[:, AI["worship"]] += 0.95 * s_pla
    U[:, AI["migrate"]] += 0.55 * s_pla
    # потерявший близких держится за родню
    U[:, AI["care"]] += 0.50 * s_los
    # видевший крушение державы не верит в порядок
    U[:, AI["build"]] -= 0.65 * s_col
    U[:, AI["rebel"]] += 0.55 * s_col
    U[:, AI["climb"]] -= 0.35 * s_col
    # знавший торжество тянется к нему снова
    U[:, AI["climb"]] += 0.85 * s_glo
    U[:, AI["build"]] += 0.35 * s_glo

    # Мастерство тянет человека к своему делу — но только тянет. Сделать этот
    # рычаг сильным нельзя: умение растёт от дела, а дело выбирается по умению,
    # и на масштабе народа такая петля сама себя разгоняет. Особенно война:
    # воюющие становятся лучшими воинами, потому воюют ещё охотнее — и один
    # народ съедает материк. Поэтому коэффициенты здесь намеренно скромные.
    M = co.mastery[idx]
    U[:, AI["intensify"]] += 0.30 * M[:, DI["farm"]]
    U[:, AI["experiment"]] += 0.55 * M[:, DI["craft"]] + 0.30 * co.lore[idx]
    U[:, AI["raid"]] += 0.22 * M[:, DI["war"]]
    U[:, AI["defend"]] += 0.25 * M[:, DI["war"]]
    U[:, AI["trade"]] += 0.35 * M[:, DI["trade"]]
    U[:, AI["build"]] += 0.35 * M[:, DI["build"]]
    U[:, AI["worship"]] += 0.30 * M[:, DI["ritual"]]
    U[:, AI["climb"]] += 0.25 * M[:, DI["rule"]]
    U[:, AI["care"]] += 0.25 * M[:, DI["heal"]]
    # мастеру есть что передать — и он это чувствует
    U[:, AI["teach"]] += 0.6 * M.max(axis=1) * np.clip(age / 45.0, 0.2, 1.4) + 0.35 * co.lore[idx]

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
    # чем больше человек пережил, тем неохотнее он пересматривает картину мира:
    # обжёгшийся не переучивается от одного удачного года
    hard = np.clip(co.scars[idx].sum(axis=1) * 0.28, 0, 0.75)
    lr = np.clip(0.06 * dt * (1.4 - co.traits[idx, TI["conformity"]]) * (1.0 - hard),
                 0.004, 0.35)
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
    # шрамы тянут убеждения на всю жизнь, независимо от того, как идут дела
    S = co.scars[idx]
    co.belief[idx, BI["scarcity"]] += lr * 0.9 * np.clip(S[:, SI["hunger"]] - co.belief[idx, BI["scarcity"]], 0, None)
    co.belief[idx, BI["danger"]] += lr * 0.9 * np.clip(S[:, SI["violence"]] - co.belief[idx, BI["danger"]], 0, None)
    co.belief[idx, BI["divine"]] += lr * 0.7 * np.clip(S[:, SI["plague"]] - co.belief[idx, BI["divine"]], 0, None)
    co.belief[idx, BI["authority"]] -= lr * 0.8 * S[:, SI["collapse"]]
    co.belief[idx, BI["trust"]] -= lr * 0.5 * S[:, SI["violence"]]
    # шрамы медленно бледнеют, но никогда не исчезают полностью
    co.scars[idx] = np.clip(S * (1.0 - 0.004 * dt), 0, 1.5)
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

    # черты не наследуются подражанием, а вот ремесло подсматривают —
    # но подсмотренное берётся много хуже, чем переданное из рук в руки
    M_elite = co.mastery[idx][elite].mean(axis=0)[None, :]
    co.mastery[idx] = np.clip(
        co.mastery[idx] + strength * 0.12 * conf * np.clip(M_elite - co.mastery[idx], 0, None),
        0, 1)
    co.skill[idx] = _overall(co.mastery[idx])


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
#  ПРОЖИТАЯ ЖИЗНЬ: личный капитал, который умирает вместе с человеком
# ────────────────────────────────────────────────────────────────────────────
def _act_domains(act_i: int, subsist_dom: int, best_dom: np.ndarray | None = None):
    """Раскладка действия по доменам умений. '@subsist' зависит от уклада народа."""
    out = []
    for dom, share in ACT_PRACTICE[ACTIONS[act_i]]:
        if dom == "@subsist":
            out.append((subsist_dom, share))
        elif dom == "@best":
            out.append((-1, share))            # -1 = «то, что человек знает лучше всего»
        else:
            out.append((DI[dom], share))
    return out


def _overall(M: np.ndarray) -> np.ndarray:
    """Общая умелость человека: главное дело плюс подспорье из соседних."""
    if M.size == 0:
        return np.zeros(M.shape[0], dtype=np.float32)
    top3 = np.sort(M, axis=1)[:, -3:]
    return np.clip(0.80 * top3[:, -1] + 0.20 * top3.mean(axis=1), 0, 1)


def practice(co: Cohort, idx, acts, year: int, dt: float,
             subsist_dom: int = 0, lore_supply: float = 0.5):
    """Умение растёт только от дела. Не от возраста и не от происхождения.

    Мастерство копится всю жизнь: молодые растут быстро, старики — медленно,
    но и теряют мало. Тело слабеет (война, промысел), голова — нет (обряд,
    письмо, управление): поэтому старики и становятся хранителями.
    Потолок мастерства ограничен тем, что вообще умеет цивилизация вокруг:
    нельзя стать великим кузнецом там, где никто не знает металла.
    """
    if idx.size == 0:
        return
    age = (year - co.born[idx]).astype(np.float32)
    T = co.traits[idx]
    dil, cur, pat = T[:, TI["diligence"]], T[:, TI["curiosity"]], T[:, TI["patience"]]

    # Чего вообще можно достичь в этом обществе и с этим характером.
    # Мастер своего дела к старости должен доходить почти до предела умения —
    # иначе в мире не бывает по-настоящему искусных рук, а без них не бывает
    # ни тонкого ремесла, ни изобретений.
    ceiling = np.clip((0.42 + 0.62 * dil + 0.24 * cur)
                      * (0.55 + 0.45 * np.clip(lore_supply, 0, 1))
                      * (0.75 + 0.25 * co.lore[idx]), 0.06, 1.0)[:, None]
    # Скорость обучения падает с возрастом, но не исчезает. Темп подобран так,
    # чтобы мастерство набиралось ДЕСЯТИЛЕТИЯМИ: в двадцать пять человек умеет
    # заметно меньше, чем в пятьдесят, — и это различие видно в его работе.
    plastic = np.clip(1.45 - age / 44.0, 0.30, 1.45)
    rate = (0.055 * dt * plastic * (0.45 + 0.75 * dil))[:, None]

    # что именно человек делал в этом такте
    prac = np.zeros((idx.size, N_DOM), dtype=np.float32)
    best = np.argmax(co.mastery[idx], axis=1)
    for a_i in range(N_ACT):
        sel = acts == a_i
        if not sel.any():
            continue
        for dom, share in _act_domains(a_i, subsist_dom):
            if dom < 0:                                   # «своё лучшее ремесло»
                np.add.at(prac, (np.flatnonzero(sel), best[sel]), share)
            else:
                prac[sel, dom] += share
    np.clip(prac, 0, 1.4, out=prac)

    M = co.mastery[idx]
    grow = rate * prac * np.clip(ceiling - M, 0, None)
    # что не упражняли — тихо ржавеет; руки помнят долго, поэтому темп мал
    rust = 0.008 * dt * (prac <= 0.02) * M * (1.35 - 0.5 * pat[:, None])
    # тело стареет: физические умения уходят после шестидесяти
    frail = np.clip((age - 58.0) / 34.0, 0, 1)[:, None] * _DOM_PHYSICAL[None, :]
    co.mastery[idx] = np.clip(M + grow - rust - 0.020 * dt * frail * M, 0.0, 1.0)

    # Сводный «навык» для остального кода — то, в чём человек хорош.
    # Считаем по лучшим трём делам, а не по всем десяти: человека судят по
    # тому, что он умеет, а не по тому, чего он не касался.
    co.skill[idx] = _overall(co.mastery[idx])


def absorb_lore(co: Cohort, idx, year: int, share: float, teaching: float, dt: float):
    """Сколько знания своего народа человек успел вобрать лично.

    В маленькой общине взрослый знает почти всё, что знает община. В большой
    культуре — лишь часть: знания стало больше, чем помещается в одну голову,
    и держится оно уже не памятью, а письмом, школами и цехами. Отсюда и
    хрупкость больших обществ: рушатся институты — и знание некому нести.

    `share` — какая доля общего знания вообще достижима одному человеку.
    """
    if idx.size == 0:
        return
    age = (year - co.born[idx]).astype(np.float32)
    plastic = np.clip(1.30 - age / 34.0, 0.14, 1.30)
    cur = co.traits[idx, TI["curiosity"]]
    conf = co.traits[idx, TI["conformity"]]
    rate = np.clip(0.055 * dt * plastic * (0.40 + 0.6 * cur + 0.4 * conf)
                   * (0.45 + 1.1 * np.clip(teaching, 0, 1)), 0, 0.7)
    tgt = float(np.clip(share, 0, 1))
    # без передачи знание тускнеет и в отдельной голове — но медленно
    fade = 0.0035 * dt * (1.0 - np.clip(teaching, 0, 1))
    co.lore[idx] = np.clip(co.lore[idx] + rate * (tgt - co.lore[idx]) - fade, 0, 1)


def apprentice(rng, co: Cohort, idx, acts, year: int, dt: float) -> int:
    """Передача из рук в руки — единственный мост между жизнью и культурой.

    Мастер, выбравший «учить», отдаёт часть своего умения молодым. Ничего
    не передаётся само: если поколение мастеров умерло, не успев научить,
    умение исчезает, даже если народ «в целом им владеет».
    Возвращает число состоявшихся передач.
    """
    if idx.size < 2:
        return 0
    # учит не только тот, кто «взялся учить»: половина передачи идёт через
    # обычную заботу о детях — рядом с матерью и отцом ребёнок и учится делу
    formal = acts == AI["teach"]
    caring = (acts == AI["care"]) & (co.children[idx] > 0)
    teachers = idx[formal | caring]
    if teachers.size == 0:
        return 0
    t_str = np.where(formal[formal | caring], 1.0, 0.45).astype(np.float32)
    age = year - co.born[idx]
    pupils = idx[(age >= 6) & (age <= 30)]
    if pupils.size == 0:
        return 0
    # ученик достаётся мастеру по кругу — детерминированно, без случайных пар
    order = np.argsort(co.mastery[pupils].max(axis=1))       # сперва самые неумелые
    pupils = pupils[order]
    k = min(pupils.size, teachers.size * 3)
    pupils = pupils[:k]
    pick = np.arange(k) % teachers.size
    tt = teachers[pick]

    Mt, Mp = co.mastery[tt], co.mastery[pupils]
    quality = (0.30 + 0.45 * co.traits[tt, TI["patience"]]
               + 0.35 * co.traits[tt, TI["sociability"]]
               + 0.25 * co.prestige[tt]) * t_str[pick]
    take = (0.22 + 0.55 * co.traits[pupils, TI["curiosity"]]
            + 0.30 * co.traits[pupils, TI["conformity"]])
    gain = np.clip(0.40 * dt * quality * take, 0, 0.9)[:, None]
    co.mastery[pupils] = np.clip(Mp + gain * np.clip(Mt - Mp, 0, None), 0, 1)
    # вместе с ремеслом переходит и доля знания народа
    lg = np.clip(0.35 * dt * quality * take, 0, 0.8)
    co.lore[pupils] = np.clip(co.lore[pupils]
                              + lg * np.clip(co.lore[tt] - co.lore[pupils], 0, None), 0, 1)
    co.teacher[pupils] = np.where(co.teacher[pupils] < 0, tt, co.teacher[pupils])
    np.add.at(co.taught, tt, 1)
    co.prestige[tt] += 0.012 * dt
    return int(k)


def imprint(co: Cohort, idx, kind: str, intensity: float, year: int,
            note_val: float | None = None):
    """Пережитое оставляет след на всю оставшуюся жизнь.

    Голод в детстве — и человек до старости копит впрок. Война — и он до
    смерти не верит чужим. Это не «параметр общества»: это личный опыт,
    который не передаётся детям и исчезает, когда поколение уходит.
    """
    if idx.size == 0 or intensity <= 0:
        return
    j = SI.get(kind)
    if j is not None:
        s = co.scars[idx, j]
        # чем свежее человек, тем глубже след: детская травма прочнее взрослой
        co.scars[idx, j] = np.clip(s + intensity * (1.0 - 0.55 * s), 0, 1.5)
    remember(co, idx, kind if kind in MI else "glory", year,
             note_val if note_val is not None else -intensity)


def remember(co: Cohort, idx, kind: str, year: int, val: float = 0.0):
    """Кольцо личной памяти: что человек будет помнить и о чём заговорит."""
    if idx.size == 0:
        return
    k = MI.get(kind)
    if not k:
        return
    p = co.mem_p[idx].astype(np.int64) % N_MEM
    co.mem_kind[idx, p] = k
    co.mem_year[idx, p] = year
    co.mem_val[idx, p] = val
    co.mem_p[idx] = ((p + 1) % N_MEM).astype(np.int8)


def scar_pressure(co: Cohort, idx) -> dict:
    """Как пережитое давит на выбор — читается в choose_actions."""
    S = co.scars[idx]
    return {
        "hunger": S[:, SI["hunger"]], "violence": S[:, SI["violence"]],
        "plague": S[:, SI["plague"]], "loss": S[:, SI["loss"]],
        "collapse": S[:, SI["collapse"]], "glory": S[:, SI["glory"]],
    }


def generation_grip(co: Cohort, idx, year: int) -> float:
    """Насколько крепко ЖИВОЕ поколение держит знание своего народа (0..1).

    Это и есть связка личного с общим: repertoire народа осыпается не по
    абстрактному «стрессу», а потому что умерли те, кто умел, и никто не
    успел перенять. Считается по доле знания у взрослых и по мастерству.
    """
    if idx.size == 0:
        return 0.0
    age = year - co.born[idx]
    adults = idx[age >= 14]
    if adults.size == 0:
        return float(np.clip(co.lore[idx].mean(), 0, 1))
    lore = float(co.lore[adults].mean())
    mast = float(co.mastery[adults].max(axis=1).mean())
    # старики — хранители: их доля повышает удержание
    elders = float((year - co.born[adults] >= 45).mean())
    return float(np.clip(0.55 * lore + 0.30 * mast + 0.15 * elders, 0, 1))


def life_story(co: Cohort, i: int, year: int) -> dict:
    """Что этот человек умеет, что пережил и что помнит — для летописи и NPC."""
    i = int(i)
    M = co.mastery[i]
    top = np.argsort(-M)[:3]
    crafts = [(DOMAINS[int(j)], round(float(M[j]), 2)) for j in top if M[j] > 0.12]
    sc = {SCARS[j]: round(float(v), 2) for j, v in enumerate(co.scars[i]) if v > 0.12}
    mem = []
    for s in range(N_MEM):
        k = int(co.mem_kind[i, s])
        if k:
            mem.append({"kind": MEM_KINDS[k], "year": int(co.mem_year[i, s]),
                        "val": round(float(co.mem_val[i, s]), 2)})
    mem.sort(key=lambda m: m["year"])
    return {"age": int(year - co.born[i]), "crafts": crafts, "scars": sc,
            "lore": round(float(co.lore[i]), 2), "memories": mem,
            "taught": int(co.taught[i]), "had_teacher": bool(co.teacher[i] >= 0)}


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
    """Здоровье с возрастом. Умение здесь НЕ растёт — только от дела (practice)."""
    if idx.size == 0:
        return
    age = year - co.born[idx]
    decline = np.clip((age - 45) / 45.0, 0, 1)
    # пережитый голод и мор укорачивают жизнь спустя десятилетия
    worn = np.clip(0.06 * co.scars[idx, SI["hunger"]] + 0.05 * co.scars[idx, SI["plague"]]
                   + 0.03 * co.scars[idx, SI["violence"]], 0, 0.10)
    co.health[idx] = np.clip(1.0 - 0.55 * decline - worn, 0.2, 1.0)


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
