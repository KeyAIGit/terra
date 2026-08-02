"""
TERRA — общие контракты данных.

Этот файл — единственный источник истины о том, как модули говорят друг с другом.
Ничего не импортирует из остальных модулей TERRA. Менять осторожно.

Три слоя мира:
  L0  среда      — numpy-поля планеты, климат по годам        (world.py)
  L1  общества   — народы, поселения, институты, знания       (society.py)
  L2  люди       — индивидуальные агенты с субагентностью     (agents.py)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ────────────────────────────────────────────────────────────────────────────
#  Биомы
# ────────────────────────────────────────────────────────────────────────────
OCEAN = 0
ICE = 1
TUNDRA = 2
BOREAL = 3
TEMPERATE_FOREST = 4
TEMPERATE_GRASSLAND = 5
MEDITERRANEAN = 6
DESERT = 7
XERIC_SHRUB = 8
SAVANNA = 9
TROPICAL_FOREST = 10
MONTANE = 11
WETLAND = 12
LAKE = 13

BIOME_NAMES = {
    OCEAN: "океан",
    ICE: "лёд",
    TUNDRA: "тундра",
    BOREAL: "тайга",
    TEMPERATE_FOREST: "широколиственный лес",
    TEMPERATE_GRASSLAND: "степь",
    MEDITERRANEAN: "средиземноморье",
    DESERT: "пустыня",
    XERIC_SHRUB: "полупустыня",
    SAVANNA: "саванна",
    TROPICAL_FOREST: "тропический лес",
    MONTANE: "горы",
    WETLAND: "болота",
    LAKE: "озеро",
}

BIOME_COLORS = {
    OCEAN: "#1b3a5c",
    ICE: "#e8f0f7",
    TUNDRA: "#9aa89b",
    BOREAL: "#2f5d3f",
    TEMPERATE_FOREST: "#3f7d3a",
    TEMPERATE_GRASSLAND: "#a8b45c",
    MEDITERRANEAN: "#8d9a48",
    DESERT: "#d8c48c",
    XERIC_SHRUB: "#bfae7c",
    SAVANNA: "#c2b45a",
    TROPICAL_FOREST: "#1f6b34",
    MONTANE: "#8b8378",
    WETLAND: "#4d7a6a",
    LAKE: "#2a5f8a",
}

WATER_BIOMES = (OCEAN, LAKE)

# ────────────────────────────────────────────────────────────────────────────
#  Материалы / ресурсы недр
# ────────────────────────────────────────────────────────────────────────────
ORE_KEYS = (
    "flint",      # кремень — режущая кромка, первая эпоха
    "obsidian",   # вулканическое стекло — острее, но редкое; ранняя дальняя торговля
    "clay",       # глина — керамика, кирпич, письмо
    "salt",       # соль — консервация, торговля, налог
    "stone",      # строительный камень
    "copper",     # медь — первый металл
    "tin",        # олово — редкое; без него нет бронзы
    "iron",       # железо — обильное, но требует высокой температуры
    "gold",       # золото — престиж и деньги
    "silver",
    "coal",
)

BIOTIC_KEYS = (
    "wild_grains",        # крупносеменные однолетние злаки — предпосылка земледелия
    "wild_pulses",        # бобовые — белок, азот в почве
    "wild_roots",         # корнеплоды/клубни — иной путь к земледелию
    "wild_fruit",
    "fauna_small",        # мелкая дичь
    "fauna_large",        # мегафауна: калорийно, но истощаемо
    "dom_herd",           # потенциал одомашнивания стадных (мясо, молоко, шерсть)
    "dom_draft",          # потенциал тягловых (плуг, повозка, кавалерия)
    "timber",
    "marine",             # рыба/моллюски — оседлость без земледелия
)


# ────────────────────────────────────────────────────────────────────────────
#  L0 — планета
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class World:
    """Статическая физика планеты. Все поля — numpy (H, W), если не сказано иное."""

    seed: int
    width: int
    height: int

    elevation: np.ndarray        # float32, метры, [-9000, 8900]
    is_land: np.ndarray          # bool
    plate_id: np.ndarray         # int16
    landmass_id: np.ndarray      # int16, -1 для воды
    latitude: np.ndarray         # float32, градусы, +90 (север) .. -90
    ruggedness: np.ndarray       # float32 0..1 — пересечённость, замедляет движение
    coastal: np.ndarray          # bool — суша, граничащая с океаном
    river: np.ndarray            # float32 0..1 — доступ к пресной проточной воде
    soil: np.ndarray             # float32 0..1 — плодородие
    base_temp: np.ndarray        # float32 °C, среднегодовая при нулевой климатической аномалии
    base_precip: np.ndarray      # float32 мм/год
    biome: np.ndarray            # int8
    ore: dict[str, np.ndarray]   # каждое поле float32 0..1
    biotic: dict[str, np.ndarray]  # каждое поле float32 0..1

    # производные характеристики материков
    landmass_axis: dict[int, float] = field(default_factory=dict)   # 1 = широтный, 0 = меридиональный
    landmass_area: dict[int, int] = field(default_factory=dict)
    landmass_name: dict[int, str] = field(default_factory=dict)

    # климатическая история: массивы длиной n_years, индексируются (year - year_start)
    year_start: int = -12000
    n_years: int = 14000
    global_temp_anom: np.ndarray | None = None    # float32, °C относительно базы
    global_precip_anom: np.ndarray | None = None  # float32, множитель ~0.7..1.3
    sea_level: np.ndarray | None = None           # float32, метры относительно современного

    # региональные шоки: список (year, kind, cy, cx, radius, severity)
    shocks: list[tuple] = field(default_factory=list)

    meta: dict[str, Any] = field(default_factory=dict)

    # ── удобные методы ──
    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def idx(self, y: int, x: int) -> int:
        return y * self.width + x

    def unidx(self, i: int) -> tuple[int, int]:
        return divmod(int(i), self.width)

    def wrap_x(self, x):
        return np.mod(x, self.width)

    def neighbors(self, y: int, x: int) -> list[tuple[int, int]]:
        """8-связность, тор по долготе, отражение по широте."""
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, (x + dx) % self.width
                if 0 <= ny < self.height:
                    out.append((ny, nx))
        return out


@dataclass
class Climate:
    """Климат конкретного года — то, что видят агенты."""
    year: int
    temp: np.ndarray      # float32 (H, W) °C
    precip: np.ndarray    # float32 (H, W) мм/год
    biome: np.ndarray     # int8 (H, W) — биом может смещаться со временем
    productivity: np.ndarray  # float32 (H, W) 0..~1.5 — первичная биопродуктивность


# ────────────────────────────────────────────────────────────────────────────
#  L1 — общества
# ────────────────────────────────────────────────────────────────────────────
SUBSISTENCE = (
    "forager",       # охота и собирательство, высокая мобильность
    "complex_forager",  # оседлые собиратели (рыба, орехи, дикие злаки)
    "horticulture",  # мотыжное земледелие / садоводство
    "pastoral",      # кочевое скотоводство
    "agrarian",      # пашенное земледелие
    "intensive",     # ирригация, севооборот, товарное хозяйство
)

POLITY_FORMS = (
    "band",          # 20–80 человек, эгалитарная группа
    "tribe",         # союз родов, лидерство без принуждения
    "bigman",        # престижная неформальная власть
    "chiefdom",      # наследственная иерархия, редистрибуция
    "citystate",
    "kingdom",
    "empire",
    "republic",
    "confederation",
)


@dataclass
class Settlement:
    sid: int
    name: str
    y: int
    x: int
    pop: int
    culture: int
    founded: int
    walls: float = 0.0
    monuments: list[str] = field(default_factory=list)
    is_capital: bool = False
    port: bool = False
    destroyed: int | None = None


@dataclass
class Polity:
    """Народ / политическое образование. Носитель культуры, знаний и институтов."""
    pid: int
    name: str
    lect: dict                        # сериализованный Lect
    color: str
    born: int
    parent: int | None = None

    cells: set = field(default_factory=set)         # индексы клеток (y*W+x)
    pop: float = 0.0
    subsistence: str = "forager"
    form: str = "band"

    known: set = field(default_factory=set)         # id освоенных знаний
    affordances: dict = field(default_factory=dict) # аффорданс -> лучший уровень 0..1
    institutions: dict = field(default_factory=dict)  # имя -> сила 0..1
    values: dict = field(default_factory=dict)      # культурные ценности -> -1..1
    gods: list = field(default_factory=list)

    # состояние
    food_stock: float = 0.0
    surplus: float = 0.0            # доля продовольствия сверх прожиточного
    inequality: float = 0.0         # 0..1, джини по домохозяйствам
    complexity: float = 0.0         # 0..1, число уровней иерархии / специализация
    legitimacy: float = 0.5
    cohesion: float = 0.7
    military: float = 0.0
    literacy: float = 0.0
    settlements: list = field(default_factory=list)  # sid
    capital: int | None = None

    neighbors_known: dict = field(default_factory=dict)   # pid -> отношение -1..1
    tribute_to: int | None = None
    at_war_with: set = field(default_factory=set)

    # люди
    agent_ids: list = field(default_factory=list)
    notables: list = field(default_factory=list)

    dead: int | None = None
    history: list = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
#  L2 — люди
# ────────────────────────────────────────────────────────────────────────────
TRAITS = (
    "curiosity",     # склонность пробовать новое → изобретения
    "risk",          # терпимость к риску → миграция, война, эксперимент
    "aggression",
    "sociability",   # размер и плотность связей
    "conformity",    # сила социального обучения
    "ambition",      # стремление к статусу → иерархия
    "patience",      # временное дисконтирование → запасы, посевы, стройка
    "empathy",       # круг морального внимания
    "piety",         # чувствительность к ритуалу и сверхъестественному
    "diligence",
)

NEEDS = ("food", "safety", "kin", "status", "meaning")


@dataclass
class Person:
    aid: int
    name: str
    polity: int
    born: int
    sex: int                      # 0 ж, 1 м
    traits: np.ndarray            # float32 len(TRAITS), 0..1
    y: int = 0
    x: int = 0

    needs: np.ndarray | None = None       # float32 len(NEEDS), 0 = удовлетворено, 1 = острая нужда
    skills: dict = field(default_factory=dict)   # знание -> владение 0..1
    beliefs: dict = field(default_factory=dict)  # субъективная модель мира
    memory: list = field(default_factory=list)   # эпизоды: (year, kind, valence, about)

    kin: set = field(default_factory=set)
    allies: set = field(default_factory=set)
    rivals: set = field(default_factory=set)
    mate: int | None = None
    children: list = field(default_factory=list)

    prestige: float = 0.0
    wealth: float = 0.0
    power: float = 0.0            # формальная власть 0..1
    role: str = "commoner"

    health: float = 1.0
    died: int | None = None
    cause: str | None = None
    deeds: list = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
#  Знание
# ────────────────────────────────────────────────────────────────────────────
AFFORDANCES = (
    "cut", "pierce", "bind", "heat", "contain", "ferment", "grind",
    "carry", "traction", "lever", "store", "signal", "count", "shelter",
    "float", "project", "armor", "irrigate", "smelt", "cure", "weave",
    "record", "measure", "propel", "predict", "organize",
)


@dataclass
class Tech:
    """Узел знания. Порядок открытия НЕ задан — задана только физика возможного."""
    tid: int
    key: str
    name: str
    era_hint: str                       # только для читаемости летописи
    gives: dict                         # аффорданс -> уровень 0..1
    needs_aff: dict                     # аффорданс -> минимальный уровень
    needs_mat: dict                     # материал/биотик -> минимальная доступность
    needs_biome: tuple = ()             # пусто = любой
    needs_pop: float = 0.0              # минимальная численность носителя
    needs_surplus: float = 0.0          # минимальный прибавочный продукт
    needs_sedentism: float = 0.0
    difficulty: float = 1.0             # сколько «когнитивных попыток» в среднем нужно
    effects: dict = field(default_factory=dict)  # прямые модификаторы общества
    lossy: float = 0.5                  # насколько легко забывается при коллапсе


# ────────────────────────────────────────────────────────────────────────────
#  Событие летописи
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class Event:
    year: int
    kind: str
    text: str
    polity: int | None = None
    person: int | None = None
    y: int | None = None
    x: int | None = None
    weight: float = 1.0      # значимость: 0..5, для фильтра летописи
    data: dict = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────────
#  Развилка для LLM-когниции
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class Juncture:
    """Момент, когда алгоритма мало и решает конкретный человек."""
    jid: str
    year: int
    kind: str                # crisis | succession | contact | innovation | schism | expansion | reform
    polity: int
    person: int
    situation: str           # текст на естественном языке — что видит человек
    options: list            # [{"key":..., "label":..., "consequence_hint":...}]
    context: dict            # машинные факты для эвристики
    resolution: dict | None = None   # {"choice":..., "reasoning":..., "by":"heuristic|api|oracle"}


SCHEMA_VERSION = 3
