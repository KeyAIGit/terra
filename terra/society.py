"""
TERRA — общество.

Слой между планетой и людьми. Здесь ничего не «решается сверху»: народы
растут, делятся, воюют, торгуют и рушатся как следствие того, что выбрали
конкретные люди из agents.py, помноженного на то, что позволяет география.

Ключевые механизмы, дающие правдоподобие:
  • несущая способность зависит от способа хозяйства, климата ЭТОГО года и знаний
  • истощение почв — медленная мина под всеми оседлыми обществами
  • деление народа при превышении управляемого масштаба → языки ветвятся
  • издержки сложности (Тэйнтер): чем сложнее общество, тем дороже его держать
  • эпидемии как плата за плотность и скот
  • забвение знаний при коллапсе — настоящие «тёмные века»
"""
from __future__ import annotations

import math

import numpy as np

from . import agents as ag
from . import knowledge as kn
from .contracts import (
    BOREAL, DESERT, ICE, LAKE, MEDITERRANEAN, MONTANE, OCEAN, SAVANNA,
    TEMPERATE_FOREST, TEMPERATE_GRASSLAND, TROPICAL_FOREST, TUNDRA, WETLAND,
    XERIC_SHRUB, Polity, Settlement,
)

EARTH_R = 6371.0

# ── пригодность биома для способа хозяйства ────────────────────────────────
BIOME_MODE = {
    #                    forag c_forag hortic pastor agrar intens mechan
    ICE:                 (0.03, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00),
    TUNDRA:              (0.18, 0.10, 0.02, 0.22, 0.02, 0.00, 0.03),
    BOREAL:              (0.30, 0.22, 0.10, 0.15, 0.12, 0.05, 0.20),
    TEMPERATE_FOREST:    (0.55, 0.55, 0.62, 0.32, 0.80, 0.85, 0.95),
    TEMPERATE_GRASSLAND: (0.48, 0.42, 0.55, 0.95, 0.85, 0.90, 1.00),
    MEDITERRANEAN:       (0.52, 0.62, 0.80, 0.55, 0.92, 0.95, 0.92),
    DESERT:              (0.08, 0.05, 0.04, 0.20, 0.05, 0.30, 0.35),
    XERIC_SHRUB:         (0.22, 0.16, 0.18, 0.60, 0.28, 0.55, 0.60),
    SAVANNA:             (0.62, 0.45, 0.55, 0.85, 0.62, 0.70, 0.72),
    TROPICAL_FOREST:     (0.50, 0.42, 0.72, 0.10, 0.40, 0.50, 0.55),
    MONTANE:             (0.25, 0.18, 0.28, 0.45, 0.22, 0.35, 0.30),
    WETLAND:             (0.55, 0.75, 0.45, 0.10, 0.42, 0.75, 0.70),
    LAKE:                (0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
    OCEAN:               (0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
}
MODES = ("forager", "complex_forager", "horticulture", "pastoral", "agrarian",
         "intensive", "mechanized")
MODE_I = {m: i for i, m in enumerate(MODES)}
# Для присваивающих и скотоводческих способов — человек на км² ВСЕЙ земли.
# Для земледельческих — человек на км² ПАХОТНОЙ земли, а пашня это малая доля
# любой территории. Без этого различия мир кормит миллиарды уже в неолите.
# Механизированное хозяйство — не «ещё лучше пашня»: это другая физика.
# Азот берут из воздуха, работу — из нефти, сорт выводят нарочно.
# Один работник кормит десятки, и плотность на гектар пашни растёт втрое.
MODE_DENSITY = np.array([0.085, 0.30, 20.0, 1.1, 62.0, 145.0, 1100.0],
                        dtype=np.float32)
FARMING = (2, 4, 5, 6)
MODE_SED = np.array([0.05, 0.55, 0.75, 0.20, 0.90, 0.97, 0.99], dtype=np.float32)
MODE_MOBILITY = np.array([1.0, 0.55, 0.30, 0.95, 0.18, 0.10, 0.06], dtype=np.float32)
# насколько производитель этого уклада даёт больше, чем съедает сам:
# именно из этой разницы и берутся жрецы, воины, писцы и цари
MODE_EFFICIENCY = np.array([0.030, 0.085, 0.19, 0.11, 0.36, 0.46, 0.93],
                           dtype=np.float32)
MODE_RU = {"forager": "охотники-собиратели", "complex_forager": "оседлые собиратели",
           "horticulture": "мотыжное земледелие", "pastoral": "скотоводы",
           "agrarian": "пашенное земледелие", "intensive": "ирригационное хозяйство",
           "mechanized": "механизированное хозяйство"}
FORM_RU = {"band": "община", "tribe": "племя", "bigman": "вождество бигменов",
           "chiefdom": "вождество", "citystate": "город-государство",
           "kingdom": "царство", "empire": "держава", "republic": "республика",
           "confederation": "союз"}


_SUIT = np.zeros((7, 16), dtype=np.float32)
for _bi, _row in BIOME_MODE.items():
    for _mi, _v in enumerate(_row):
        _SUIT[_mi, _bi] = _v


class Grid:
    """Изменяемое состояние клеток мира."""

    def __init__(self, world):
        h, w = world.height, world.width
        self.owner = np.full(h * w, -1, dtype=np.int32)
        self.depletion = np.zeros(h * w, dtype=np.float32)   # истощение почв 0..1
        self.deforest = np.zeros(h * w, dtype=np.float32)
        self.pop = np.zeros(h * w, dtype=np.float32)
        self.fauna = np.ones(h * w, dtype=np.float32)        # запас дичи, истощается
        self.area = _cell_area(world).ravel()
        self.land = world.is_land.ravel()
        self.settle = np.full(h * w, -1, dtype=np.int32)


def _cell_area(world) -> np.ndarray:
    dlat = 180.0 / world.height
    dlon = 360.0 / world.width
    lat = world.latitude
    return (np.abs(np.deg2rad(dlat) * EARTH_R
                   * np.deg2rad(dlon) * EARTH_R * np.cos(np.deg2rad(lat)))).astype(np.float32)


# ────────────────────────────────────────────────────────────────────────────
#  Продуктивность земли
# ────────────────────────────────────────────────────────────────────────────
def cell_yield(world, grid: Grid, clim, cells: np.ndarray, mode: str,
               rep: kn.Repertoire) -> np.ndarray:
    """Сколько людей прокормит каждая клетка при данном хозяйстве и знаниях."""
    if cells.size == 0:
        return np.zeros(0, dtype=np.float32)
    mi = MODE_I[mode]
    b = clim.biome.ravel()[cells]
    suit = _SUIT[mi][b]
    prod = clim.productivity.ravel()[cells]
    soil = world.soil.ravel()[cells]
    river = world.river.ravel()[cells]
    area = grid.area[cells]

    dens = MODE_DENSITY[mi] * suit
    if mode in ("forager", "complex_forager"):
        fauna = world.biotic["fauna_large"].ravel()[cells] * grid.fauna[cells]
        small = world.biotic["fauna_small"].ravel()[cells]
        marine = world.biotic["marine"].ravel()[cells]
        grain = world.biotic["wild_grains"].ravel()[cells]
        roots = world.biotic["wild_roots"].ravel()[cells]
        base = 0.35 + 0.9 * fauna + 0.5 * small + 0.35 * roots
        base += marine * (1.6 if mode == "complex_forager" else 0.7) * (
            1.0 + rep.effect("marine_bonus"))
        base += grain * (1.3 if rep.has("wild_harvest") else 0.35)
        dens = dens * base * prod
    elif mode == "pastoral":
        herd = world.biotic["dom_herd"].ravel()[cells]
        dens = dens * (0.25 + 1.5 * herd) * prod * (0.6 + 0.5 * (1 - soil))
    else:
        depl = 1.0 - 0.55 * grid.depletion[cells]
        water = 0.55 + 0.75 * river if mode == "intensive" else 0.8 + 0.35 * river
        arable = arable_fraction(world, cells, prod, river, soil)
        if mode == "intensive":
            arable = np.minimum(0.52, arable * (1.0 + 0.9 * river))
        dens = dens * arable * depl * water * prod
        dens *= _saturate(rep.effect("yield"), 0.95, 0.75)
        if mode in ("agrarian", "intensive"):
            dens *= _saturate(rep.effect("soil_restore"), 0.35, 1.0)
    dens *= _saturate(rep.effect("food"), 0.55, 0.9)
    if int(clim.biome.ravel()[cells][0]) == MONTANE if cells.size else False:
        pass
    mont = (b == MONTANE)
    if mont.any() and rep.effect("montane_bonus"):
        dens[mont] *= (1.0 + rep.effect("montane_bonus"))
    return np.clip(dens, 0, None) * area


def _saturate(x: float, gain: float, half: float) -> float:
    """Насыщающая отдача: десять улучшений плуга не дают десятикратного урожая."""
    x = max(0.0, float(x))
    return 1.0 + gain * x / (half + x)


def arable_fraction(world, cells, prod, river, soil) -> np.ndarray:
    """Какая доля клетки вообще может быть распахана.

    Склоны, камень, болота, сушь и мерзлота вычитаются. В лучшей пойме это
    около 40%, в обычном ландшафте 8–20%, в горах и пустыне почти ноль.
    Именно этот множитель держит доиндустриальный мир в сотнях миллионов,
    а не в миллиардах.
    """
    rug = world.ruggedness.ravel()[cells]
    a = 0.46 * (soil ** 1.15) * (1.0 - 0.80 * rug) * np.clip(0.25 + 0.95 * prod, 0, 1.25)
    a = a * (0.72 + 0.55 * river)
    return np.clip(a, 0.0, 0.42).astype(np.float32)


def capacity(world, grid, clim, poly: Polity, rep: kn.Repertoire) -> float:
    cells = cells_arr(poly)
    if cells.size == 0:
        return 0.0
    return float(cell_yield(world, grid, clim, cells, poly.subsistence, rep).sum())


def best_mode(world, grid, clim, poly: Polity, rep: kn.Repertoire) -> tuple[str, float]:
    """Народ переходит к тому хозяйству, что кормит лучше — но не мгновенно."""
    cells = cells_arr(poly)
    if cells.size == 0:
        return poly.subsistence, 0.0
    avail = kn.available_modes(rep)
    best, bk = poly.subsistence, capacity(world, grid, clim, poly, rep)
    for m in avail:
        if m == poly.subsistence:
            continue
        k = float(cell_yield(world, grid, clim, cells, m, rep).sum())
        # переход стоит: люди держатся привычного
        if k > bk * 1.22:
            best, bk = m, k
    return best, bk


# ────────────────────────────────────────────────────────────────────────────
#  Материалы, доступные народу
# ────────────────────────────────────────────────────────────────────────────
def material_field(world) -> np.ndarray:
    """Матрица (len(MAT_KEYS), H*W): что где лежит. Считается один раз на мир."""
    out = np.zeros((len(kn.MAT_KEYS), world.height * world.width), dtype=np.float32)
    for i, k in enumerate(kn.MAT_KEYS):
        if k in world.ore:
            out[i] = world.ore[k].ravel()
        elif k in world.biotic:
            out[i] = world.biotic[k].ravel()
        elif k == "river":
            out[i] = world.river.ravel()
        elif k == "soil":
            out[i] = world.soil.ravel()
    return out


def materials_vec(matfield: np.ndarray, poly: Polity) -> np.ndarray:
    if not poly.cells:
        return np.zeros(matfield.shape[0], dtype=np.float32)
    cells = cells_arr(poly)
    return matfield[:, cells].max(axis=1)


def materials_of(world, grid, poly: Polity, trade_reach: dict) -> dict:
    cells = cells_arr(poly)
    out = {}
    if cells.size == 0:
        return {k: 0.0 for k in kn.MAT_KEYS}
    for k in kn.MAT_KEYS:
        if k in world.ore:
            v = float(world.ore[k].ravel()[cells].max())
        elif k in world.biotic:
            v = float(world.biotic[k].ravel()[cells].max())
        elif k == "river":
            v = float(world.river.ravel()[cells].max())
        elif k == "soil":
            v = float(world.soil.ravel()[cells].max())
        else:
            v = 0.0
        # торговля приносит то, чего нет дома — но слабее, чем своё
        v = max(v, trade_reach.get(k, 0.0) * 0.75)
        out[k] = v
    return out


def biomes_of(clim, poly: Polity) -> set:
    if not poly.cells:
        return set()
    cells = cells_arr(poly)
    return set(int(v) for v in np.unique(clim.biome.ravel()[cells]))


# ────────────────────────────────────────────────────────────────────────────
#  Расширение и миграция территории
# ────────────────────────────────────────────────────────────────────────────
def frontier_cells(world, grid: Grid, poly: Polity, sea_range: float) -> list[int]:
    """Куда народ физически может шагнуть."""
    W = world.width
    H = world.height
    out = []
    seen = set()
    for c in sorted(poly.cells):
        y, x = divmod(c, W)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, (x + dx) % W
                if not (0 <= ny < H):
                    continue
                nc = ny * W + nx
                if nc in seen or nc in poly.cells:
                    continue
                seen.add(nc)
                if grid.land[nc]:
                    out.append(nc)
                elif sea_range > 0.35:
                    # переправа: ищем сушу за водой в пределах дальности
                    for r in range(2, int(2 + sea_range * 4)):
                        yy, xx = y + dy * r, (x + dx * r) % W
                        if 0 <= yy < H and grid.land[yy * W + xx]:
                            cc = yy * W + xx
                            if cc not in poly.cells:
                                out.append(cc)
                            break
    return out


def cells_arr(poly) -> np.ndarray:
    """Клетки народа в устойчивом порядке.

    Множество Python обходится в порядке, зависящем от истории вставок,
    а после записи на диск и чтения обратно история другая. Любой обход
    множества клеток обязан быть отсортирован — иначе мир, продолженный
    с точки сохранения, разойдётся с самим собой.
    """
    if not poly.cells:
        return np.zeros(0, dtype=np.int64)
    return np.sort(np.fromiter(poly.cells, dtype=np.int64, count=len(poly.cells)))


def own_neighbor_count(world, grid, poly, cells: np.ndarray) -> np.ndarray:
    """Сколько соседних клеток уже свои — мера связности."""
    if cells.size == 0:
        return np.zeros(0, dtype=np.float32)
    out = np.zeros(cells.size, dtype=np.float32)
    for i, c in enumerate(cells):
        out[i] = sum(1 for nc in _neigh(world, int(c)) if nc in poly.cells)
    return out


def try_expand(rng, world, grid, clim, poly, rep, pressure: float, dt: float) -> list[int]:
    """Экспансия: занимаем то, что кажется годным. Занятое чужими — только войной.

    Земли прирастают к своим: клетка, окружённая своими, притягательнее
    выгодного, но оторванного куска. Иначе владения выходят лоскутными,
    чего в живых политиях не бывает — их держат дороги, гонцы и родня.
    """
    if pressure <= 0 or not poly.cells:
        return []
    sea = rep.effect("sea") + 0.4 * rep.affordances()[kn.AFF_IDX["float"]]
    cand = frontier_cells(world, grid, poly, sea)
    cand = [c for c in cand if grid.owner[c] < 0 and grid.land[c]]
    if not cand:
        return []
    arr = np.array(sorted(set(cand)), dtype=np.int64)
    y = cell_yield(world, grid, clim, arr, poly.subsistence, rep)
    rug = world.ruggedness.ravel()[arr]
    score = y / np.maximum(grid.area[arr], 1.0) * (1.0 - 0.55 * rug)
    score = score * (1.0 + 0.45 * own_neighbor_count(world, grid, poly, arr))
    score = score * (1.0 + 0.35 * rng.random(arr.size))
    n = int(min(arr.size, max(0, rng.poisson(pressure * dt * 0.55))))
    if n == 0:
        return []
    order = np.argsort(-score)[:n]
    got = []
    for j in order:
        if score[j] <= 1e-9:
            continue
        c = int(arr[j])
        poly.cells.add(c)
        grid.owner[c] = poly.pid
        got.append(c)
    return got


def absorb_enclaves(rng, world, grid, polities, poly, dt: float) -> list[int]:
    """Чужой клочок, со всех сторон окружённый нами, рано или поздно станет нашим.

    Так лоскутные границы со временем сглаживаются, а на карте появляются
    сплошные державы, а не мозаика.
    """
    if len(poly.cells) < 3:
        return []
    seen: dict[int, int] = {}
    for c in sorted(poly.cells):
        for nc in _neigh(world, c):
            o = int(grid.owner[nc])
            if o >= 0 and o != poly.pid:
                seen[nc] = seen.get(nc, 0) + 1
    got = []
    for nc, k in sorted(seen.items()):
        if k < 6:
            continue
        o = int(grid.owner[nc])
        q = polities.get(o)
        if q is None or q.dead is not None or len(q.cells) <= 1:
            continue
        if poly.pop < q.pop * 1.15:
            continue
        if rng.random() > min(0.5, 0.02 * dt * (k - 5)):
            continue
        q.cells.discard(nc)
        poly.cells.add(nc)
        grid.owner[nc] = poly.pid
        got.append(nc)
    return got


def abandon(world, grid, clim, poly, rep, keep_ratio: float) -> list[int]:
    """Отступление с земель, которые больше не кормят.

    Уходят с окраин, а не из середины: сначала бросают оторванные и бедные углы.
    """
    if len(poly.cells) <= 1:
        return []
    cells = cells_arr(poly)
    y = cell_yield(world, grid, clim, cells, poly.subsistence, rep)
    y = y / np.maximum(grid.area[cells], 1.0)
    y = y * (1.0 + 0.35 * own_neighbor_count(world, grid, poly, cells))
    keep = max(1, int(len(cells) * keep_ratio))
    order = np.argsort(-y)
    drop = cells[order[keep:]]
    lost = []
    for c in drop:
        if grid.settle[c] >= 0:
            continue
        poly.cells.discard(int(c))
        grid.owner[c] = -1
        lost.append(int(c))
    return lost


# ────────────────────────────────────────────────────────────────────────────
#  Военное дело
# ────────────────────────────────────────────────────────────────────────────
def military_strength(poly: Polity, rep: kn.Repertoire, co: ag.Cohort) -> float:
    idx = np.array(poly.agent_ids, dtype=np.int64)
    idx = idx[co.alive[idx]] if idx.size else idx
    warriors = float((co.role[idx] == ag.RI["warrior"]).mean()) if idx.size else 0.0
    aggr = float(co.traits[idx, ag.TI["aggression"]].mean()) if idx.size else 0.5
    base = math.sqrt(max(poly.pop, 1.0))
    tech = 1.0 + rep.effect("military")
    return base * tech * (0.55 + 0.9 * warriors) * (0.65 + 0.7 * aggr) * (0.5 + 0.8 * poly.cohesion)


def resolve_war(rng, world, grid, clim, a: Polity, b: Polity, ra, rb, co, year: int,
                dt: float) -> dict:
    """Один военный сезон. Возвращает описание исхода."""
    sa = military_strength(a, ra, co)
    sb = military_strength(b, rb, co) * (1.0 + 0.6 * rb.effect("defense"))
    # оборона в горах и за стенами
    bc = cells_arr(b)
    if bc.size:
        sb *= 1.0 + 0.45 * float(world.ruggedness.ravel()[bc].mean())
    sa *= (1.0 + 0.25 * rng.normal())
    sb *= (1.0 + 0.25 * rng.normal())
    total = sa + sb + 1e-6
    p_a = sa / total
    win_a = rng.random() < p_a
    intensity = min(0.16, 0.05 * dt) * (1.0 + 0.5 * min(sa, sb) / max(sa, sb, 1e-6))
    a.pop *= (1 - intensity * (0.55 if win_a else 1.0))
    b.pop *= (1 - intensity * (1.0 if win_a else 0.55))
    res = {"winner": a.pid if win_a else b.pid, "loser": b.pid if win_a else a.pid,
           "intensity": intensity, "taken": [], "tribute": False, "sacked": [],
           "annexed": False}
    W, L = (a, b) if win_a else (b, a)
    RW = ra if win_a else rb
    # добыча: земля, дань или разграбление
    if L.cells and rng.random() < 0.55:
        lc = cells_arr(L)
        border = [int(c) for c in lc if any(
            (nc in W.cells) for nc in _neigh(world, int(c)))]
        if border:
            n = max(1, int(len(border) * min(0.5, 0.10 + 0.35 * (p_a if win_a else 1 - p_a))))
            for c in rng.permutation(border)[:n]:
                L.cells.discard(int(c))
                W.cells.add(int(c))
                grid.owner[c] = W.pid
                res["taken"].append(int(c))
    if RW.effect("surplus_extract") > 0.25 and rng.random() < 0.4:
        L.tribute_to = W.pid
        res["tribute"] = True
    # Победитель, способный управлять чужими, забирает побеждённого целиком.
    # Без этого мир навсегда остаётся россыпью мелких народов: державы
    # растут не приращением клеток по одной, а поглощением соседей.
    if (L.pop < W.pop * 0.35 and len(L.cells) <= max(3, len(W.cells)) and
            RW.effect("admin") > 0.35 and W.pop > 20_000):
        p_annex = min(0.55, 0.12 + 0.30 * RW.effect("admin")
                      + 0.25 * (1.0 - L.pop / max(W.pop, 1.0)))
        if rng.random() < p_annex:
            res["annexed"] = True
    for sid in list(L.settlements):
        if rng.random() < 0.10 + 0.20 * intensity:
            res["sacked"].append(sid)
    W.legitimacy = min(1.0, W.legitimacy + 0.10)
    L.legitimacy = max(0.0, L.legitimacy - 0.14)
    L.cohesion = max(0.05, L.cohesion - 0.08)
    return res


def _neigh(world, c: int) -> list[int]:
    W, H = world.width, world.height
    y, x = divmod(c, W)
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, (x + dx) % W
            if 0 <= ny < H:
                out.append(ny * W + nx)
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Болезни
# ────────────────────────────────────────────────────────────────────────────
def pathogen_load(world, grid, poly: Polity, rep: kn.Repertoire, connectivity: float) -> float:
    if not poly.cells:
        return 0.0
    cells = cells_arr(poly)
    dens = poly.pop / max(1.0, grid.area[cells].sum())
    herd = float(world.biotic["dom_herd"].ravel()[cells].max()) if rep.has("herding") else 0.0
    wet = float((world.biotic["marine"].ravel()[cells] > 0.3).mean())
    load = (0.35 * math.log10(1 + dens * 90) + 0.5 * herd + 0.25 * connectivity + 0.12 * wet)
    load *= (1.0 - 0.55 * min(1.0, rep.effect("health") + rep.effect("plague_resist")))
    return float(max(0.0, load))


def epidemic(rng, poly: Polity, load: float, dt: float) -> float:
    """Возвращает долю потерь. Эпидемии редки, но выкашивают."""
    if load < 0.30:
        return 0.0
    p = 1.0 - math.exp(-0.0011 * (load - 0.25) ** 2 * dt)
    if rng.random() < p:
        return float(np.clip(rng.beta(2.0, 5.0) * 0.55 * (0.5 + load), 0.02, 0.5))
    return 0.0


# ────────────────────────────────────────────────────────────────────────────
#  Сложность и её цена (Тэйнтер)
# ────────────────────────────────────────────────────────────────────────────
def complexity_cost(poly: Polity, rep: kn.Repertoire) -> float:
    """Доля продукта, уходящая на содержание самой сложности."""
    c = poly.complexity
    scale = math.log10(max(poly.pop, 10)) / 5.0
    admin = 1.0 + rep.effect("admin")
    base = 0.055 * c + 0.18 * c * c + 0.05 * scale
    return float(base / admin)


def tech_scale(poly: Polity, settlements: dict) -> float:
    """Сколько людей реально взаимодействуют достаточно плотно, чтобы держать знание.

    Письменность рождается в городе, а не в трёх миллионах разбросанных пахарей.
    """
    sed = float(MODE_SED[MODE_I[poly.subsistence]])
    biggest = 0
    for sid in poly.settlements:
        st = settlements.get(sid)
        if st is not None and not st.destroyed:
            biggest = max(biggest, st.pop)
    return float(max(biggest * 4.0, poly.pop * 0.12 * (0.30 + sed)))


def soil_balance(world, grid, cells: np.ndarray, pop: float, intensity: float,
                 rep: kn.Repertoire, dt: float) -> None:
    """Истощение и восстановление пашни.

    Земля не портится от самого факта, что её пашут: у неё есть предел
    нагрузки, ниже которого она держится тысячелетиями. Пойма, куда река
    каждый год приносит ил, выдерживает больше; пар, навоз и бобовые
    поднимают предел ещё выше. Выше предела почва садится, ниже —
    отдыхает и возвращается.

    Без восстановления любой земледелец за пару веков превращает свою
    землю в пустошь и возвращается к собирательству — а мир не доходит
    до государств вовсе.
    """
    if cells.size == 0:
        return
    river = world.river.ravel()[cells]
    soil = world.soil.ravel()[cells]
    arable = np.maximum(1e-6, arable_fraction(
        world, cells, np.ones(cells.size, dtype=np.float32), river, soil))
    arable_km2 = float((grid.area[cells] * arable).sum())
    press = pop / max(arable_km2, 1.0)          # человек на км² пашни
    # какую нагрузку земля держит без потерь
    limit = (14.0 + 26.0 * river + 40.0 * rep.effect("soil_restore")
             + 18.0 * _saturate(rep.effect("yield"), 0.95, 0.75) - 18.0)
    limit = np.maximum(6.0, limit)
    over = np.clip(press / limit - 1.0, 0, 4.0)
    under = np.clip(1.0 - press / limit, 0, 1.0)
    add = 0.0035 * dt * over * (0.6 + 0.7 * intensity)
    back = 0.0022 * dt * under * (0.35 + 1.1 * river + 1.6 * rep.effect("soil_restore"))
    grid.depletion[cells] = np.clip(grid.depletion[cells] + add - back, 0.0, 0.80)


def collapse_risk(poly: Polity, rep: kn.Repertoire, food_ratio: float) -> float:
    """Риск обрушения сложного общества (по Тэйнтеру).

    Гибнут не от бедности, а от того, что содержание сложности начинает
    стоить больше, чем сложность приносит. Когда изъятие уже не покрывает
    ни войско, ни жрецов, ни чиновников, а законность истрачена, держава
    рассыпается разом — и вместе с ней осыпаются знания, которые держались
    только на её городах.
    """
    if poly.complexity < 0.30 or poly.pop < 5000:
        return 0.0
    cost = complexity_cost(poly, rep)
    # какая доля изымаемого уходит на содержание самого аппарата
    burden = cost / max(poly.surplus + cost, 1e-6)
    over_extent = max(0.0, poly.pop / max(admin_limit(rep, poly.form), 1.0) - 1.0)
    strain = (1.9 * max(0.0, burden - 0.40)
              + 1.3 * max(0.0, 0.45 - poly.legitimacy) * 2.0
              + 1.0 * max(0.0, 0.42 - poly.cohesion) * 2.0
              + 1.5 * max(0.0, 1.0 - food_ratio) * 2.0
              + 0.6 * max(0.0, poly.inequality - 0.55) * 2.0
              + 0.9 * min(1.5, over_extent))
    return float(np.clip(strain * (0.35 + poly.complexity), 0, 4.0))


_AFF_TRANSMIT = kn.AFF_IDX["transmit"]


def admin_limit(rep: kn.Repertoire, form: str) -> float:
    """Сколько людей можно удержать в одном политическом теле."""
    base = {"band": 8_000, "tribe": 25_000, "bigman": 40_000, "chiefdom": 130_000,
            "citystate": 260_000, "republic": 1_100_000, "confederation": 800_000,
            "kingdom": 3_000_000, "empire": 30_000_000}.get(form, 15_000)
    # Предел управляемого тела задан не территорией, а связью: гонец на коне
    # держит державу в десятки миллионов, телеграф и перепись — в сотни,
    # а сеть, где всякий достижим мгновенно, — в миллиарды.
    reach = (1.0 + 2.4 * rep.effect("admin")) * (1.0 + 0.8 * rep.effect("info")) \
        * (1.0 + 1.6 * min(1.0, rep.effect("literacy"))) \
        * (1.0 + 3.0 * rep.affordances()[_AFF_TRANSMIT])
    return base * reach


def update_complexity(poly: Polity, rep: kn.Repertoire, co: ag.Cohort):
    idx = np.array(poly.agent_ids, dtype=np.int64)
    idx = idx[co.alive[idx]] if idx.size else idx
    spec = float((co.role[idx] != ag.RI["commoner"]).mean()) if idx.size else 0.0
    tiers = float(np.clip(co.power[idx].max() if idx.size else 0.0, 0, 1))
    scale = min(1.0, math.log10(max(poly.pop, 10)) / 6.3)
    tgt = 0.35 * spec + 0.3 * tiers + 0.2 * scale + 0.15 * min(1.0, rep.effect("complexity"))
    poly.complexity += 0.14 * (tgt - poly.complexity)
    poly.complexity = float(np.clip(poly.complexity, 0, 1))


def pick_form(rep: kn.Repertoire, poly: Polity, co: ag.Cohort) -> str:
    """Форма правления — следствие масштаба, изъятия и того, кто чем владеет."""
    avail = kn.available_forms(rep)
    pop = poly.pop
    idx = np.array(poly.agent_ids, dtype=np.int64)
    idx = idx[co.alive[idx]] if idx.size else idx
    ineq = ag.gini(co.wealth[idx]) if idx.size > 3 else 0.0
    extract = rep.effect("surplus_extract")
    sed = float(MODE_SED[MODE_I[poly.subsistence]])
    sur = poly.surplus
    order = []
    # иерархия не появляется без запасаемого избытка — её нечем содержать
    if "empire" in avail and pop > 900_000 and extract > 0.6 and sur > 0.06:
        order.append("empire")
    if "kingdom" in avail and pop > 90_000 and extract > 0.32 and sur > 0.05:
        order.append("kingdom")
    if "republic" in avail and pop > 25_000 and ineq < 0.52 and sur > 0.05:
        order.append("republic")
    if "citystate" in avail and pop > 12_000 and poly.settlements and sur > 0.04:
        order.append("citystate")
    if "chiefdom" in avail and pop > 2_500 and ineq > 0.22 and sur > 0.03 and sed > 0.45:
        order.append("chiefdom")
    if "bigman" in avail and pop > 1_200 and ineq > 0.16 and sur > 0.015 and sed > 0.25:
        order.append("bigman")
    if pop > 1_500 and (sed > 0.2 or sur > 0.01):
        order.append("tribe")
    order.append("band")
    return order[0]


# ────────────────────────────────────────────────────────────────────────────
#  Поселения
# ────────────────────────────────────────────────────────────────────────────
def settlement_tier(pop: int) -> str:
    if pop >= 100_000:
        return "метрополия"
    if pop >= 25_000:
        return "большой город"
    if pop >= 6_000:
        return "город"
    if pop >= 1_200:
        return "городок"
    return "селение"


def urban_share(rep: kn.Repertoire, poly: Polity) -> float:
    if MODE_SED[MODE_I[poly.subsistence]] < 0.5:
        return 0.0
    u = 0.02 + 0.30 * rep.effect("urban") + 0.22 * poly.complexity + 0.18 * rep.effect("trade")
    u *= (0.5 + 0.8 * min(1.0, poly.surplus * 8))
    # Доиндустриальный город кормится окрестной пашней и потому мал: больше
    # пятой части народа в городах не удержать. Когда хлеб везут по железной
    # дороге, а поле пашет машина, ограничение снимается — и мир становится
    # городским: сегодня в городах живёт больше половины людей.
    cap = 0.22 + 0.55 * min(1.0, 0.55 * rep.effect("labor") + 0.45 * rep.effect("urban"))
    return float(np.clip(u, 0.0, min(0.80, cap)))


# ────────────────────────────────────────────────────────────────────────────
#  Деление и слияние народов
# ────────────────────────────────────────────────────────────────────────────
def territorial_extent(world, poly: Polity) -> float:
    """Наибольшее удаление владений от их середины, в клетках."""
    if len(poly.cells) < 2:
        return 0.0
    W = world.width
    cells = cells_arr(poly)
    ys, xs = np.divmod(cells, W)
    ang = xs / W * 2 * np.pi
    cx = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    dx = np.angle(np.exp(1j * (ang - cx))) * W / (2 * np.pi)
    dy = ys - ys.mean()
    return float(np.sqrt(dx ** 2 + dy ** 2).max())


def fission_pressure(poly: Polity, rep: kn.Repertoire, extent: float = 0.0) -> float:
    """Что рвёт народ надвое.

    Главное здесь — не теснота, а РАССТОЯНИЕ. Народ, расселившийся широко,
    расходится и без всякого кризиса: дальние роды реже видят своих,
    речь их отходит, и через несколько поколений это уже другой народ.
    Именно так растут языковые семьи — и именно поэтому расколы должны
    случаться на всём протяжении истории, а не только в первые века.
    """
    lim = admin_limit(rep, poly.form)
    over = poly.pop / max(lim, 1.0)
    mob = float(MODE_MOBILITY[MODE_I[poly.subsistence]])
    reach = (4.0 + 4.0 * mob + 7.0 * rep.effect("admin") + 4.0 * rep.effect("trade_range")
             + 2.5 * rep.effect("sea") + 3.0 * rep.effect("info"))
    spread = extent / max(reach, 1.0)
    p = (0.40 * max(0.0, over - 1.0) + 0.75 * max(0.0, spread - 1.0)
         + 0.5 * max(0.0, 0.45 - poly.cohesion) + 0.4 * max(0.0, 0.35 - poly.legitimacy))
    return float(np.clip(p, 0, 3.0))


def split_cells(world, poly: Polity, rng) -> tuple[set, set] | None:
    """Разрез территории на две связные части — по самой длинной оси."""
    if len(poly.cells) < 2:
        return None
    cells = cells_arr(poly)
    W = world.width
    ys, xs = np.divmod(cells, W)
    # учёт цикличности по долготе
    ang = xs / W * 2 * np.pi
    cx = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    dx = np.angle(np.exp(1j * (ang - cx))) * W / (2 * np.pi)
    dy = ys - ys.mean()
    if dx.std() >= dy.std():
        proj = dx
    else:
        proj = dy
    proj = proj + rng.normal(0, 0.3, proj.size)
    med = np.median(proj)
    a = set(int(c) for c in cells[proj <= med])
    b = set(int(c) for c in cells[proj > med])
    if not a or not b:
        return None
    return a, b


# ────────────────────────────────────────────────────────────────────────────
#  Контакты между народами
# ────────────────────────────────────────────────────────────────────────────
def contacts(world, grid: Grid, polities: dict) -> dict:
    """Кто с кем граничит и насколько плотно."""
    out: dict[int, dict[int, float]] = {}
    W = world.width
    for pid, p in polities.items():
        if p.dead is not None or not p.cells:
            continue
        acc: dict[int, int] = {}
        for c in sorted(p.cells):
            for nc in _neigh(world, c):
                o = int(grid.owner[nc])
                if o >= 0 and o != pid:
                    acc[o] = acc.get(o, 0) + 1
        edge = max(1, len(p.cells))
        out[pid] = {k: min(1.0, v / edge) for k, v in sorted(acc.items())}
    return out


def sea_contacts(world, grid: Grid, polities: dict, reps: dict) -> dict:
    """Морские связи — они не требуют общей границы и меняют всё."""
    out: dict[int, dict[int, float]] = {}
    coastal: dict[int, list[int]] = {}
    W = world.width
    for pid, p in polities.items():
        if p.dead is not None or not p.cells:
            continue
        cc = [c for c in sorted(p.cells) if world.coastal.ravel()[c]]
        if cc:
            coastal[pid] = cc
    keys = list(coastal)
    for i, a in enumerate(keys):
        ra = reps[a]
        ra_range = ra.effect("sea") * 8.0 + ra.effect("trade_range") * 4.0
        if ra_range < 1.5:
            continue
        ay, ax = np.divmod(np.array(coastal[a]), W)
        for b in keys[i + 1:]:
            rb = reps[b]
            rng_b = rb.effect("sea") * 8.0 + rb.effect("trade_range") * 4.0
            reach = max(ra_range, rng_b)
            by, bx = np.divmod(np.array(coastal[b]), W)
            dy = np.abs(ay[:, None] - by[None, :])
            dxr = np.abs(ax[:, None] - bx[None, :])
            dxr = np.minimum(dxr, W - dxr)
            d = np.sqrt(dy ** 2 + dxr ** 2).min()
            if d <= reach:
                s = float(np.clip((reach - d) / max(reach, 1e-6), 0, 1) * 0.55)
                out.setdefault(a, {})[b] = max(out.get(a, {}).get(b, 0.0), s)
                out.setdefault(b, {})[a] = max(out.get(b, {}).get(a, 0.0), s)
    return out


def trade_goods(mat_vecs: dict, polities, reps, links: dict) -> dict:
    """Что можно достать через торговлю. Именно так олово находит медь."""
    out: dict[int, np.ndarray] = {}
    n = len(kn.MAT_KEYS)
    for pid, nb in links.items():
        if not nb:
            continue
        r = reps[pid]
        f = min(1.0, 0.35 + r.effect("trade"))
        best = np.zeros(n, dtype=np.float32)
        for other, strength in nb.items():
            v = mat_vecs.get(other)
            if v is None:
                continue
            np.maximum(best, v * (strength * f), out=best)
        out[pid] = best
    return out
