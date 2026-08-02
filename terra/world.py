"""
TERRA — L0: генератор планеты земного типа.

Планета строится снизу вверх:
    тектоника → рельеф → материки → климат → гидрология → почвы → биомы →
    недра → биота → климатическая история.

Зависимости: numpy (обязательно), scipy.ndimage (используется, есть fallback нет —
scipy считается доступной). Никакого noise/opensimplex/PIL.

Всё детерминировано по seed.
"""
from __future__ import annotations

import heapq
import json
import math
import os
import time
from typing import Any

import numpy as np
from scipy import ndimage as ndi

try:  # запуск как пакет
    from .contracts import (
        BIOME_NAMES, BIOTIC_KEYS, BOREAL, DESERT, ICE, LAKE, MEDITERRANEAN,
        MONTANE, OCEAN, ORE_KEYS, SAVANNA, SCHEMA_VERSION, TEMPERATE_FOREST,
        TEMPERATE_GRASSLAND, TROPICAL_FOREST, TUNDRA, WETLAND, XERIC_SHRUB,
        Climate, World,
    )
except ImportError:  # запуск как скрипт
    from contracts import (  # type: ignore
        BIOME_NAMES, BIOTIC_KEYS, BOREAL, DESERT, ICE, LAKE, MEDITERRANEAN,
        MONTANE, OCEAN, ORE_KEYS, SAVANNA, SCHEMA_VERSION, TEMPERATE_FOREST,
        TEMPERATE_GRASSLAND, TROPICAL_FOREST, TUNDRA, WETLAND, XERIC_SHRUB,
        Climate, World,
    )

__all__ = [
    "generate_world", "climate_at", "save_world", "load_world", "ascii_map",
    "biome_histogram", "world_summary", "shock_duration",
    "SHOCK_KINDS", "SHOCK_DUR", "DEFAULT_CFG", "BIOME_CHARS", "ROLE_NAMES",
    "ROLE_LATITUDINAL", "ROLE_MERIDIONAL", "ROLE_SOUTH_ISOLATE",
    "ROLE_ARCHIPELAGO", "ROLE_POLAR_N", "ROLE_POLAR_S", "ROLE_ISLAND",
]

# роли материков — задают асимметрию истории (по Даймонду)
ROLE_LATITUDINAL = "latitudinal_major"   # аналог Афроевразии
ROLE_MERIDIONAL = "meridional"           # аналог Америк
ROLE_SOUTH_ISOLATE = "southern_isolate"  # аналог Австралии
ROLE_ARCHIPELAGO = "archipelago"
ROLE_POLAR_N = "polar_north"
ROLE_POLAR_S = "polar_south"
ROLE_ISLAND = "island"

ROLE_NAMES = {
    ROLE_LATITUDINAL: "Великий Пояс",
    ROLE_MERIDIONAL: "Долгий Материк",
    ROLE_SOUTH_ISOLATE: "Отчуждённая Земля",
    ROLE_ARCHIPELAGO: "Тысяча Островов",
    ROLE_POLAR_N: "Северный Венец",
    ROLE_POLAR_S: "Южный Панцирь",
}

# ────────────────────────────────────────────────────────────────────────────
#  Базовые численные утилиты
# ────────────────────────────────────────────────────────────────────────────


def _smoothstep(x, a=0.0, b=1.0):
    """Плавная ступенька 0→1 на отрезке [a, b]."""
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a + 1e-12), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _gauss(x, mu, sigma):
    return np.exp(-0.5 * ((np.asarray(x, dtype=np.float64) - mu) / sigma) ** 2)


def _norm01(a):
    a = np.asarray(a, dtype=np.float64)
    lo, hi = float(a.min()), float(a.max())
    if hi - lo < 1e-12:
        return np.zeros_like(a)
    return (a - lo) / (hi - lo)


def _blur(a, sigma):
    """Гауссово размытие: по X — цикличное, по Y — отражение."""
    if sigma <= 0:
        return np.asarray(a, dtype=np.float64)
    return ndi.gaussian_filter(np.asarray(a, dtype=np.float64), sigma,
                               mode=("reflect", "wrap"))


def _upsample_cyclic(g, H, W):
    """Билинейный (со smoothstep) апскейл. По X — тор, по Y — зажим."""
    h, w = g.shape
    gy = (np.arange(H) + 0.5) * (h / H) - 0.5
    gx = (np.arange(W) + 0.5) * (w / W) - 0.5
    y0 = np.floor(gy).astype(np.int64)
    x0 = np.floor(gx).astype(np.int64)
    ty = gy - y0
    tx = gx - x0
    ty = ty * ty * (3.0 - 2.0 * ty)
    tx = tx * tx * (3.0 - 2.0 * tx)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)
    x0c = x0 % w
    x1c = (x0 + 1) % w
    a = g[np.ix_(y0c, x0c)]
    b = g[np.ix_(y0c, x1c)]
    c = g[np.ix_(y1c, x0c)]
    d = g[np.ix_(y1c, x1c)]
    top = a + (b - a) * tx[None, :]
    bot = c + (d - c) * tx[None, :]
    return top + (bot - top) * ty[:, None]


def _fbm(rng, H, W, octaves=6, base_w=4, gain=0.55, lacunarity=2.0,
         standardize=True):
    """Фрактальный шум: сумма октав сглаженного случайного поля.

    Каждая октава — случайное поле низкого разрешения, растянутое на сетку.
    По X апскейл цикличный, поэтому итог — тор по долготе.
    """
    total = np.zeros((H, W), dtype=np.float64)
    amp, nrm = 1.0, 0.0
    for o in range(octaves):
        w = max(3, int(round(base_w * lacunarity ** o)))
        h = max(2, int(round(w * H / W)))
        if w > 3 * W:
            break
        g = rng.standard_normal((h, w))
        total += amp * _upsample_cyclic(g, H, W)
        nrm += amp
        amp *= gain
    total /= max(nrm, 1e-9)
    if standardize:
        total = (total - total.mean()) / (total.std() + 1e-9)
    return total


def _ridged(rng, H, W, octaves=5, base_w=6):
    """Хребтовый шум — для гранитных поясов и жил."""
    f = _fbm(rng, H, W, octaves=octaves, base_w=base_w)
    return 1.0 - np.abs(np.tanh(f * 1.1))


def _edt_cyclic(mask):
    """Расстояние до ближайшей True-клетки + индексы этой клетки. Тор по X."""
    H, W = mask.shape
    tiled = np.concatenate([mask, mask, mask], axis=1)
    dist, idx = ndi.distance_transform_edt(~tiled, return_indices=True)
    d = dist[:, W:2 * W]
    iy = idx[0][:, W:2 * W]
    ix = idx[1][:, W:2 * W] % W
    return d, iy, ix


def _dx_cyclic(a):
    """Центральная производная по X с заворотом."""
    return 0.5 * (np.roll(a, -1, axis=1) - np.roll(a, 1, axis=1))


def _dy_clamped(a):
    up = np.vstack([a[:1], a[:-1]])
    dn = np.vstack([a[1:], a[-1:]])
    return 0.5 * (dn - up)


def _label_cyclic(mask):
    """Связные компоненты (8-связность) с цикличностью по X.

    Возвращает (labels int32, n) с нумерацией 1..n по убыванию площади.
    """
    H, W = mask.shape
    lab, n = ndi.label(mask, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return lab.astype(np.int32), 0
    parent = np.arange(n + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    left, right = lab[:, 0], lab[:, -1]
    for y in range(H):
        if left[y] == 0:
            continue
        for dy in (-1, 0, 1):
            yy = y + dy
            if 0 <= yy < H and right[yy] != 0:
                union(int(left[y]), int(right[yy]))
    roots = np.array([find(i) for i in range(n + 1)])
    roots[0] = 0
    merged = roots[lab]
    uniq = np.unique(merged)
    uniq = uniq[uniq != 0]
    areas = np.array([(merged == u).sum() for u in uniq])
    order = uniq[np.argsort(-areas)]
    remap = np.zeros(merged.max() + 1, dtype=np.int32)
    for i, u in enumerate(order):
        remap[u] = i + 1
    return remap[merged].astype(np.int32), len(order)


def _calibrate_fraction(raw, mask, frac, thresh=0.3):
    """Монотонно перешкалировать поле так, чтобы ровно `frac` доли клеток
    внутри `mask` были выше `thresh`. Нужно для редких ресурсов (олово)."""
    out = np.zeros_like(raw, dtype=np.float64)
    vals = raw[mask]
    if vals.size == 0:
        return out
    frac = float(np.clip(frac, 1e-4, 0.999))
    q = float(np.quantile(vals, 1.0 - frac))
    lo = float(vals.min())
    hi = float(vals.max())
    if hi - q < 1e-9:
        hi = q + 1e-9
    if q - lo < 1e-9:
        lo = q - 1e-9
    low = mask & (raw <= q)
    high = mask & (raw > q)
    out[low] = thresh * (raw[low] - lo) / (q - lo)
    out[high] = thresh + (1.0 - thresh) * (raw[high] - q) / (hi - q)
    return np.clip(out, 0.0, 1.0)


def _circular_extent(xs, W):
    """Протяжённость набора долгот на окружности, в клетках."""
    u = np.unique(xs)
    if u.size <= 1:
        return 1
    gaps = np.diff(u)
    wrap_gap = (u[0] + W) - u[-1]
    biggest = max(float(gaps.max()), float(wrap_gap))
    return int(max(1, W - biggest + 1))


# ────────────────────────────────────────────────────────────────────────────
#  Шаблоны материков
#  Координаты: u ∈ [0,1) — долгота (цикл), v ∈ [0,1] — широта (0 = сев. полюс)
# ────────────────────────────────────────────────────────────────────────────


def _earthlike_templates(rng):
    """Континентальные «пятна». Не копия Земли — планета с теми же аффордансами:
    широтный гигант, меридиональная лента, южный изолят, архипелаг, шапки.

    Бюджет долготы (u) выдержан жёстко, иначе материки слипаются и вся
    последующая история теряет асимметрию:
        0.00–0.51  гигант с широтной осью
        0.44–0.63  архипелаг и южный изолят (южнее)
        0.63–0.67  пролив-океан
        0.67–0.82  меридиональная лента
        0.82–1.00  великий океан
    """
    j = lambda s: float(rng.normal(0.0, s))          # noqa: E731 — джиттер
    u0 = float(rng.uniform(0.0, 1.0))                 # общий поворот планеты

    def U(u):
        return (u + u0) % 1.0

    T = []

    # 1. широтный гигант: главная ось строго ВОСТОК—ЗАПАД
    lat_main = 0.315 + j(0.012)
    big = [
        (U(0.030 + j(0.008)), lat_main + 0.02 + j(0.015), 0.082, 0.108, 1.00),
        (U(0.115 + j(0.008)), lat_main - 0.02 + j(0.015), 0.086, 0.116, 1.00),
        (U(0.205 + j(0.008)), lat_main - 0.03 + j(0.015), 0.090, 0.112, 1.00),
        (U(0.300 + j(0.008)), lat_main - 0.01 + j(0.015), 0.090, 0.104, 1.00),
        (U(0.385 + j(0.008)), lat_main + 0.03 + j(0.015), 0.076, 0.092, 0.98),
        (U(0.450 + j(0.008)), lat_main + 0.07 + j(0.015), 0.050, 0.072, 0.94),
        # южная доля («Африка») — связь через перешеек
        (U(0.095 + j(0.008)), 0.455 + j(0.012), 0.066, 0.082, 0.98),
        (U(0.115 + j(0.008)), 0.560 + j(0.012), 0.064, 0.078, 0.98),
        (U(0.125 + j(0.008)), 0.655 + j(0.012), 0.046, 0.062, 0.94),
        # тропические полуострова юго-востока
        (U(0.320 + j(0.008)), 0.415 + j(0.012), 0.048, 0.075, 0.94),
        (U(0.395 + j(0.008)), 0.445 + j(0.012), 0.038, 0.060, 0.90),
    ]
    T.append((ROLE_LATITUDINAL, big))

    # 2. меридиональная лента: главная ось СЕВЕР—ЮГ, узкая, с перешейком
    um = 0.742 + j(0.010)
    mer = [
        (um - 0.006, 0.170 + j(0.012), 0.066, 0.100, 1.00),
        (um - 0.014, 0.282 + j(0.012), 0.058, 0.092, 1.00),
        (um + 0.008, 0.382 + j(0.008), 0.032, 0.062, 0.95),
        (um + 0.028, 0.495 + j(0.008), 0.050, 0.090, 1.00),
        (um + 0.038, 0.612 + j(0.008), 0.044, 0.094, 1.00),
        (um + 0.030, 0.728 + j(0.008), 0.030, 0.074, 0.94),
    ]
    T.append((ROLE_MERIDIONAL, [(U(x) % 1.0, y, a, b, sg) for x, y, a, b, sg in mer]))

    # 3. южный изолят — далеко от всех, без сухопутной связи
    ui = 0.520 + j(0.010)
    iso = [
        (U(ui), 0.700 + j(0.010), 0.050, 0.080, 1.00),
        (U(ui + 0.032), 0.728 + j(0.010), 0.036, 0.050, 0.96),
        (U(ui - 0.030), 0.712 + j(0.010), 0.032, 0.048, 0.94),
    ]
    T.append((ROLE_SOUTH_ISOLATE, iso))

    # 4. архипелаг — цепочка мелких пятен у экватора, восточнее гиганта
    arc = []
    ua = 0.462 + j(0.008)
    for k in range(8):
        arc.append((U(ua + 0.019 * k + j(0.005)),
                    0.512 + 0.026 * math.sin(k * 1.15) + j(0.010),
                    0.023, 0.030, 0.86 + 0.06 * rng.random()))
    T.append((ROLE_ARCHIPELAGO, arc))

    # 5. северная приполярная земля («Гренландия») — в великом океане
    T.append((ROLE_POLAR_N, [(U(0.880 + j(0.015)), 0.108 + j(0.010),
                             0.042, 0.052, 0.98)]))

    # 6. южный ледяной панцирь — пояс с рваным краем
    cap = []
    for k in range(6):
        cap.append((U(0.083 + 0.1667 * k + j(0.02)),
                    0.984 + j(0.005), 0.115, 0.026, 1.00))
    T.append((ROLE_POLAR_S, cap))

    # «рвы» — гарантированные океанические коридоры (u_c, u_hw, v_c, v_hh, сила)
    moats = [
        (U(0.657), 0.030, 0.50, 0.60, 1.00),   # пролив гигант ↔ лента
        (U(0.902), 0.056, 0.60, 0.42, 1.00),   # великий океан
        (U(0.540), 0.150, 0.612, 0.034, 0.95),  # архипелаг ↔ изолят
        (0.5, 0.5, 0.868, 0.036, 1.00),        # пояс вокруг южной шапки
        (0.5, 0.5, 0.016, 0.040, 0.85),        # северный полярный океан
    ]

    # отрицательные «пятна» — дополнительное углубление океанов
    seas = [
        (U(0.648), 0.44, 0.042, 0.245, 1.10),   # пролив гигант ↔ лента
        (U(0.912), 0.46, 0.085, 0.290, 1.10),   # великий океан
        (U(0.905), 0.76, 0.075, 0.180, 0.95),
        (U(0.520), 0.618, 0.100, 0.038, 0.85),  # изолят отрезан от архипелага
        (U(0.520), 0.845, 0.115, 0.050, 0.95),  # изолят отрезан от шапки
        (U(0.760), 0.860, 0.095, 0.050, 0.90),
        (U(0.130), 0.870, 0.110, 0.055, 0.90),
    ]
    return T, seas, moats


def _random_templates(rng):
    """Не-земной вариант компоновки (cfg['earth_like_layout'] = False)."""
    T = []
    for i in range(int(rng.integers(3, 7))):
        n = int(rng.integers(2, 7))
        cu, cv = rng.random(), float(rng.uniform(0.12, 0.88))
        blobs = []
        for _ in range(n):
            blobs.append(((cu + rng.normal(0, 0.06)) % 1.0,
                          float(np.clip(cv + rng.normal(0, 0.07), 0.05, 0.95)),
                          float(rng.uniform(0.04, 0.10)),
                          float(rng.uniform(0.05, 0.12)),
                          float(rng.uniform(0.75, 1.05))))
        T.append((ROLE_ISLAND, blobs))
    return T, [], []


def _moat_field(moats, U, V):
    """Океанические коридоры: прямоугольные полосы с мягким краем.

    Без них материки слипаются, и вся асимметрия истории пропадает.
    """
    out = np.zeros_like(U)
    for (uc, uhw, vc, vhh, s) in moats:
        du = np.abs(((U - uc + 0.5) % 1.0) - 0.5)
        dv = np.abs(V - vc)
        fu = 1.0 - _smoothstep(du, uhw * 0.55, uhw)
        fv = 1.0 - _smoothstep(dv, vhh * 0.60, vhh)
        out = np.maximum(out, s * fu * fv)
    return out


def _blob_field(blobs, U, V, mode="max"):
    """Объединение эллиптических «пятен» с плато внутри и мягким краем.

    Плато важно: порог уровня моря — глобальный квантиль, и если пятна
    куполообразные, крупный материк «съедает» бюджет суши у мелких.
    """
    out = np.zeros_like(U)
    for (cu, cv, ru, rv, s) in blobs:
        du = U - cu
        du -= np.round(du)                    # цикличность по долготе
        dv = V - cv
        q = (du / ru) ** 2 + (dv / rv) ** 2
        val = s * _smoothstep(np.clip(1.0 - q, 0.0, 1.0), 0.0, 0.80)
        out = np.maximum(out, val) if mode == "max" else out + val
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Тектоника
# ────────────────────────────────────────────────────────────────────────────


def _build_plates(rng, H, W, cont_pot, n_plates):
    """Диаграмма Вороного по случайным центрам, цикличная по X.

    Континентальные зародыши смещены внутрь шаблонных материков, океанические —
    в воду. Каждой плите даётся вектор дрейфа; часть векторов подкручена так,
    чтобы гарантированно возникли крупные орогены.
    """
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)

    # доменное искажение — чтобы границы плит не были прямыми
    wx = _fbm(rng, H, W, octaves=4, base_w=4) * (W * 0.045)
    wy = _fbm(rng, H, W, octaves=4, base_w=4) * (H * 0.045)
    px = xs + wx
    py = np.clip(ys + wy, 0, H - 1)

    cont_hi = cont_pot > 0.45
    ocean_lo = cont_pot < 0.12

    n_cont = int(round(n_plates * 0.45))
    seeds, is_cont = [], []

    def pick(mask, k):
        idx = np.flatnonzero(mask.ravel())
        if idx.size == 0:
            idx = np.arange(H * W)
        chosen = rng.choice(idx, size=min(k, idx.size), replace=False)
        return [(int(c // W), int(c % W)) for c in chosen]

    # континентальные зародыши — по одному на каждую крупную область суши
    for (y, x) in pick(cont_hi, n_cont):
        seeds.append((y, x))
        is_cont.append(True)
    for (y, x) in pick(ocean_lo, n_plates - len(seeds)):
        seeds.append((y, x))
        is_cont.append(False)
    while len(seeds) < n_plates:
        seeds.append((int(rng.integers(0, H)), int(rng.integers(0, W))))
        is_cont.append(False)

    seeds = np.array(seeds[:n_plates], dtype=np.float64)
    is_cont = np.array(is_cont[:n_plates], dtype=bool)

    # Вороной
    best = np.full((H, W), np.inf)
    plate = np.zeros((H, W), dtype=np.int16)
    for i, (sy, sx) in enumerate(seeds):
        dx = px - sx
        dx -= W * np.round(dx / W)
        dy = (py - sy) * 1.25          # лёгкая анизотропия: плиты вытянуты по X
        d = dx * dx + dy * dy
        m = d < best
        best[m] = d[m]
        plate[m] = i

    # векторы дрейфа
    ang = rng.uniform(0, 2 * math.pi, n_plates)
    mag = rng.uniform(0.45, 1.0, n_plates)
    vel = np.stack([np.cos(ang) * mag, np.sin(ang) * mag], axis=1)  # (vx, vy)

    # подкрутка: каждая континентальная плита получает соседа-«молот»
    order = np.argsort(seeds[:, 1])
    for k in range(0, len(order) - 1, 2):
        a, b = int(order[k]), int(order[k + 1])
        dx = seeds[b, 1] - seeds[a, 1]
        dx -= W * round(dx / W)
        dy = seeds[b, 0] - seeds[a, 0]
        nrm = math.hypot(dx, dy) + 1e-9
        if rng.random() < 0.62:                       # конвергенция
            vel[a] = np.array([dx, dy]) / nrm * mag[a]
            vel[b] = -np.array([dx, dy]) / nrm * mag[b]
        elif rng.random() < 0.5:                      # дивергенция
            vel[a] = -np.array([dx, dy]) / nrm * mag[a]
            vel[b] = np.array([dx, dy]) / nrm * mag[b]
    return plate, seeds, vel, is_cont


def _plate_boundaries(plate, vel, is_cont, H, W):
    """Классификация границ плит и размазывание их влияния по расстоянию."""
    pr = np.roll(plate, -1, axis=1)                       # сосед справа
    pd = np.vstack([plate[1:], plate[-1:]])               # сосед снизу

    conv = np.zeros((H, W))
    div = np.zeros((H, W))
    shear = np.zeros((H, W))
    cc = np.zeros((H, W))   # континент—континент
    co = np.zeros((H, W))   # континент—океан
    oo = np.zeros((H, W))   # океан—океан
    bnd = np.zeros((H, W), dtype=bool)

    for other, dvec in ((pr, (1.0, 0.0)), (pd, (0.0, 1.0))):
        m = other != plate
        if not m.any():
            continue
        a = plate[m]
        b = other[m]
        rel = vel[a] - vel[b]
        c = rel[:, 0] * dvec[0] + rel[:, 1] * dvec[1]     # >0 — сближение
        s = np.abs(rel[:, 0] * dvec[1] - rel[:, 1] * dvec[0])
        ca, cb = is_cont[a], is_cont[b]
        conv[m] = np.maximum(conv[m], np.clip(c, 0, None))
        div[m] = np.maximum(div[m], np.clip(-c, 0, None))
        shear[m] = np.maximum(shear[m], s)
        cc[m] = np.maximum(cc[m], (ca & cb).astype(float))
        co[m] = np.maximum(co[m], (ca ^ cb).astype(float))
        oo[m] = np.maximum(oo[m], (~ca & ~cb).astype(float))
        bnd[m] = True

    if not bnd.any():
        z = np.zeros((H, W))
        return dict(conv=z, div=z, shear=z, cc=z, co=z, oo=z,
                    dist=np.full((H, W), 99.0), bnd=bnd)

    dist, iy, ix = _edt_cyclic(bnd)
    g = lambda f: f[iy, ix]                               # noqa: E731
    return dict(conv=g(conv), div=g(div), shear=g(shear),
                cc=g(cc), co=g(co), oo=g(oo), dist=dist, bnd=bnd)


# ────────────────────────────────────────────────────────────────────────────
#  Рельеф
# ────────────────────────────────────────────────────────────────────────────


def _build_relief(rng, H, W, cont_pot, B, land_target):
    """Собрать поле высот из континентального потенциала и тектоники."""
    d = B["dist"]

    # ширина влияния границы зависит от типа
    belt_mount = np.exp(-(d / 4.2) ** 1.5)          # орогенный пояс
    belt_arc = np.exp(-(d / 2.6) ** 1.6)            # островная дуга
    belt_rift = np.exp(-(d / 3.0) ** 1.6)
    belt_ridge = np.exp(-(d / 5.5) ** 1.4)
    belt_trench = np.exp(-(np.abs(d - 3.0) / 2.0) ** 2)

    conv = np.clip(B["conv"], 0, 2.0)
    div = np.clip(B["div"], 0, 2.0)

    orogen = conv * belt_mount * (0.45 + 0.85 * B["cc"] + 0.55 * B["co"])
    arcs = conv * belt_arc * B["oo"]
    rift = div * belt_rift * (B["cc"] + 0.4 * B["co"])
    ridge = div * belt_ridge * B["oo"]
    trench = conv * belt_trench * (B["oo"] + B["co"]) * 0.8

    orogen = _norm01(_blur(orogen, 0.8))
    arcs = _norm01(_blur(arcs, 0.6))
    rift = _norm01(_blur(rift, 0.9))
    ridge = _norm01(_blur(ridge, 1.1))
    trench = _norm01(_blur(trench, 0.9))

    # потенциал суши: шаблоны + тектоника + шум (амплитуда шума растёт у суши)
    soft = _blur(np.clip(cont_pot, 0, 1.4), 3.0)
    n_big = _fbm(rng, H, W, octaves=4, base_w=4)
    n_med = _fbm(rng, H, W, octaves=5, base_w=9)
    noise = 0.70 * n_big + 0.30 * n_med

    P = (cont_pot
         + noise * (0.075 + 0.30 * np.clip(soft, 0, 1.0))
         + 0.34 * arcs
         + 0.22 * orogen
         - 0.16 * rift * (1.0 - soft))

    P = _blur(P, 0.75)                     # убрать одноклеточную «моль» в материках
    t = float(np.quantile(P, 1.0 - land_target))
    is_land = P > t

    span_up = max(float(P.max()) - t, 1e-6)
    span_dn = max(t - float(P.min()), 1e-6)
    hn = np.clip((P - t) / span_up, 0, 1)
    dn = np.clip((t - P) / span_dn, 0, 1)

    elev = np.where(
        is_land,
        30.0 + 1000.0 * hn ** 1.15,
        -(110.0 + 5000.0 * dn ** 1.55),
    )

    # горы, дуги, рифты, срединные хребты, жёлоба
    cont_mask = is_land.astype(np.float64)
    elev += 6600.0 * (orogen ** 1.75) * (0.30 + 0.70 * cont_mask)
    elev += 1500.0 * (arcs ** 1.4) * (0.35 + 0.65 * cont_mask)
    elev += 1450.0 * ridge * (1.0 - cont_mask)
    elev -= 2200.0 * (trench ** 1.2) * (1.0 - cont_mask) * (1.0 - ridge)
    elev -= 320.0 * rift * cont_mask

    # шероховатость рельефа
    rough = _fbm(rng, H, W, octaves=8, base_w=14)
    elev += rough * (110.0 + 620.0 * np.clip(orogen * 2.4, 0, 1)) * cont_mask
    elev += rough * 190.0 * (1.0 - cont_mask)

    # горы и дуги подняли шельф — вернуть долю суши точно к цели
    off = float(np.quantile(elev, 1.0 - land_target))
    elev = elev - off
    is_land = elev > 0.0
    elev = np.clip(elev, -6000.0, 8100.0)
    return elev, is_land, dict(orogen=orogen, arcs=arcs, rift=rift,
                               ridge=ridge, trench=trench)


def _landmasses(is_land, H, W):
    """Связные компоненты суши + площадь + ось (1 = широтная)."""
    lab, n = _label_cyclic(is_land)
    lm = np.where(lab > 0, lab - 1, -1).astype(np.int16)
    area, axis = {}, {}
    for i in range(n):
        m = lm == i
        ys, xs = np.nonzero(m)
        area[i] = int(ys.size)
        ext_x = _circular_extent(xs, W)
        ext_y = int(ys.max() - ys.min() + 1)
        ex_deg = ext_x * 360.0 / W
        ey_deg = ext_y * 180.0 / H
        r = ex_deg / max(ey_deg, 1e-6)
        axis[i] = float(np.clip(0.5 + 0.5 * math.log2(max(r, 1e-6)) / 2.0, 0, 1))
    return lm, n, area, axis


def _assign_roles(lm, n_lm, templates, U, V, area, axis, H, W):
    """Сопоставить шаблоны материков с реально получившимися массивами суши."""
    roles: dict[int, str] = {}
    prio = [ROLE_LATITUDINAL, ROLE_MERIDIONAL, ROLE_SOUTH_ISOLATE,
            ROLE_POLAR_S, ROLE_POLAR_N, ROLE_ARCHIPELAGO]
    by_role = {r: b for r, b in templates}
    for role in prio:
        if role not in by_role:
            continue
        core = _blob_field(by_role[role], U, V) > 0.55
        cand = lm[core & (lm >= 0)]
        if cand.size == 0:
            continue
        ids, cnt = np.unique(cand, return_counts=True)
        for i in np.argsort(-cnt):
            k = int(ids[i])
            if k not in roles:
                roles[k] = role
                break
    # всё остальное — острова; но крупный неопознанный массив тоже материк
    for i in range(n_lm):
        if i not in roles:
            roles[i] = ROLE_ISLAND
    names = {}
    used = {}
    for i in range(n_lm):
        r = roles[i]
        if r in ROLE_NAMES and r not in used:
            names[i] = ROLE_NAMES[r]
            used[r] = i
        elif area.get(i, 0) >= 200:
            names[i] = f"Земля-{i}"
        else:
            names[i] = f"остров-{i}"
    return roles, names


# ────────────────────────────────────────────────────────────────────────────
#  Климат
# ────────────────────────────────────────────────────────────────────────────


def _sea_level_temp(lat):
    """Зональный профиль среднегодовой температуры: +27 °C на экваторе,
    -25 °C на полюсе, с реалистичным «плечом» в средних широтах."""
    s = np.abs(np.sin(np.radians(lat)))
    return 27.0 - 20.0 * s ** 2 - 32.0 * s ** 6


def _zonal_precip(lat, itcz=0.0):
    """Ячейки Хэдли и Феррела: влажно у экватора и на 50–60°, сухо на 25–30°."""
    a = np.abs(lat)
    p = (135.0
         + 2150.0 * _gauss(lat, itcz, 12.0)
         + 340.0 * _gauss(a, 9.0, 22.0)
         + 930.0 * _gauss(a, 50.0, 16.0)
         - 170.0 * _gauss(a, 27.0, 9.0))
    return np.clip(p, 45.0, None)


def _wind_field(lat):
    """Доля западного переноса (ветер дует на восток). Остальное — восточный."""
    a = np.abs(lat)
    w = _smoothstep(a, 24.0, 38.0) * (1.0 - _smoothstep(a, 62.0, 76.0))
    return np.clip(w, 0.0, 1.0)


def _advect_moisture(is_land, elev, lat, direction, H, W):
    """Влага переносится ветром от океана вглубь суши и теряется на подъёме.

    direction = +1: ветер дует на восток (западный перенос);
    direction = -1: ветер дует на запад (пассаты).
    После W шагов каждая клетка суши хранит произведение коэффициентов
    сохранения вдоль пути от ближайшего наветренного океана.
    """
    up = direction * _dx_cyclic(elev)           # подъём по ходу ветра, м/клетку
    up = np.clip(up, 0, None)
    a = np.abs(lat)
    # в субтропиках воздух опускается и сушит быстрее
    base_loss = (0.0104
                 + 0.0125 * _gauss(a, 27.0, 12.0)
                 + 0.0055 * _smoothstep(a, 55.0, 80.0)
                 - 0.0050 * _gauss(a, 0.0, 13.0))
    keep = np.exp(-(base_loss + 0.0022 * up + 0.55 * (up / 900.0) ** 2))
    keep = np.where(is_land, keep, 1.0)

    m = np.where(is_land, 0.0, 1.0)
    for _ in range(W):
        src = np.roll(m, direction, axis=1)
        m = np.where(is_land, src * keep, 1.0)
    return m, up


def _build_climate(rng, H, W, elev, is_land, latitude, maritime, dist_ocean):
    lat2 = latitude[:, None] * np.ones((1, W))
    elev_km = np.clip(elev, 0, None) / 1000.0

    # ── температура ──
    t = _sea_level_temp(lat2)
    t = t - 6.0 * elev_km                                   # градиент высоты
    cont = 1.0 - maritime
    t = t + 1.7 * maritime * _smoothstep(np.abs(lat2), 15.0, 55.0)
    t = t - 1.6 * cont * (np.abs(lat2) / 90.0) ** 1.2 * is_land
    t = t + 0.9 * _fbm(rng, H, W, octaves=5, base_w=7)
    base_temp = np.where(is_land, t, np.maximum(t, -2.2))    # океан не мёрзнет

    # сезонность (не в контракте, нужна для средиземноморья и биомов)
    season = np.clip(0.30 + 0.70 * cont, 0, 1) * _smoothstep(np.abs(lat2), 8.0, 45.0)

    # ── осадки ──
    itcz = 0.0
    P0 = _zonal_precip(lat2, itcz)
    wwest = _wind_field(lat2)

    m_e, up_e = _advect_moisture(is_land, elev, lat2, +1, H, W)   # западный
    m_w, up_w = _advect_moisture(is_land, elev, lat2, -1, H, W)   # пассаты
    moist = wwest * m_e + (1.0 - wwest) * m_w
    upslope = wwest * up_e + (1.0 - wwest) * up_w

    oro = np.clip(upslope / 260.0, 0.0, 1.5)
    precip = P0 * (0.20 + 0.80 * moist) * (1.0 + 0.80 * oro)

    # муссонный довесок: крупная тропическая суша летом тянет влагу с востока
    monsoon = (_gauss(lat2, 0.0, 26.0)
               * np.exp(-np.clip(dist_ocean, 0, 40) / 9.0)
               * is_land)
    precip *= 1.0 + 0.55 * monsoon

    precip *= np.exp(0.34 * _fbm(rng, H, W, octaves=6, base_w=8))
    precip = np.clip(precip, 20.0, 5200.0).astype(np.float64)

    # ── средиземноморский признак: западное побережье 28–45° ──
    acc = (~is_land).astype(np.float64)
    for k in range(1, 9):
        acc = np.maximum(acc, np.roll((~is_land).astype(np.float64), k, axis=1)
                         * (1.0 - k / 9.0))
    west_ocean = acc * is_land
    medit = (west_ocean
             * _gauss(np.abs(lat2), 36.0, 7.5)
             * _smoothstep(season, 0.25, 0.55))
    medit = np.clip(medit / max(float(medit.max()), 1e-6), 0, 1)

    return base_temp, precip, season, medit, wwest, west_ocean


# ────────────────────────────────────────────────────────────────────────────
#  Гидрология
# ────────────────────────────────────────────────────────────────────────────

_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_NBD = [math.hypot(dy, dx) for dy, dx in _NB]


def _hydrology(elev, is_land, precip, latitude, H, W):
    """Заполнение впадин (priority-flood + ε), направления стока, аккумуляция."""
    N = H * W
    ef = elev.astype(np.float64).ravel().copy()
    land = is_land.ravel()
    fill = ef.copy()
    done = np.zeros(N, dtype=bool)

    # два уровня: истинный (для озёр) и с ε-уклоном (для направлений стока)
    true_fill = ef.copy()
    heap = []
    for i in np.flatnonzero(~land):
        done[i] = True
        heapq.heappush(heap, (ef[i], int(i)))

    eps = 1e-3
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        e, i = pop(heap)
        fe = fill[i]
        y, x = divmod(i, W)
        for dy, dx in _NB:
            ny = y + dy
            if ny < 0 or ny >= H:
                continue
            j = ny * W + ((x + dx) % W)
            if done[j]:
                continue
            done[j] = True
            true_fill[j] = ef[j] if ef[j] > e else e
            fill[j] = ef[j] if ef[j] > fe + eps else fe + eps
            push(heap, (true_fill[j], j))

    # глубина ниже точки перелива — это и есть настоящая котловина
    lake_depth = np.where(land, true_fill - ef, 0.0)

    # D8 по заполненному рельефу
    recv = np.full(N, -1, dtype=np.int64)
    li = np.flatnonzero(land)
    ly, lx = li // W, li % W
    best = np.zeros(li.size)
    for (dy, dx), dd in zip(_NB, _NBD):
        ny = ly + dy
        ok = (ny >= 0) & (ny < H)
        nj = np.where(ok, np.clip(ny, 0, H - 1) * W + (lx + dx) % W, li)
        drop = np.where(ok, (fill[li] - fill[nj]) / dd, -1.0)
        upd = drop > best
        best[upd] = drop[upd]
        recv[li[upd]] = nj[upd]

    # аккумуляция: обход сверху вниз по заполненной высоте
    coslat = np.cos(np.radians(latitude))[:, None] * np.ones((1, W))
    acc = (precip * np.clip(coslat, 0.05, 1.0) / 1000.0).ravel().copy()
    acc[~land] = 0.0
    order = li[np.argsort(-fill[li], kind="stable")]
    accw = acc
    rv = recv
    for i in order:
        r = rv[i]
        if r >= 0:
            accw[r] += accw[i]

    acc2 = accw.reshape(H, W)
    acc2[~is_land] = 0.0
    ref = float(np.quantile(acc2[is_land], 0.997)) if is_land.any() else 1.0
    river = np.clip(np.log1p(acc2) / math.log1p(max(ref, 1e-3)), 0, 1)
    river[~is_land] = 0.0

    return fill.reshape(H, W), lake_depth.reshape(H, W), acc2, river


def _lakes(lake_depth, acc, is_land, H, W, target=0.013):
    """Крупные внутренние впадины со стоком → озёра.

    Порог глубины берётся как квантиль, иначе на «сухих» мирах озёр не будет
    вовсе, а на «мокрых» они зальют половину суши.
    """
    if not is_land.any():
        return np.zeros((H, W), dtype=bool)
    thr_acc = float(np.quantile(acc[is_land], 0.45))
    pool = is_land & (lake_depth > 0.5) & (acc > thr_acc)
    if not pool.any():
        return np.zeros((H, W), dtype=bool)
    want = max(4, int(target * is_land.sum()))
    d = lake_depth[pool]
    thr = float(np.sort(d)[::-1][min(want, d.size) - 1])
    return pool & (lake_depth >= thr)


# ────────────────────────────────────────────────────────────────────────────
#  Почвы
# ────────────────────────────────────────────────────────────────────────────


def _soils(rng, H, W, elev, is_land, temp, precip, river, slope,
           volcanism, latitude, lake):
    # оптимум увлажнения ~ 700–900 мм
    f_p = np.exp(-0.5 * ((np.log(np.clip(precip, 20, None)) - math.log(820.0)) / 0.92) ** 2)
    # оптимум температуры ~ 8–18 °C
    f_t = np.exp(-0.5 * ((temp - 13.0) / 16.0) ** 2)
    f_t = np.where(temp < -6, f_t * 0.28, f_t)

    # аллювий: много стока + пологий склон = пойма
    al = np.clip(river * 1.25, 0, 1) * np.exp(-slope / 45.0)
    alluvial = np.clip(al / max(float(np.quantile(al[is_land], 0.995)), 1e-6), 0, 1) \
        if is_land.any() else al

    volc = np.clip(volcanism, 0, 1)

    # выщелачивание: жарко + очень мокро → латериты
    leach = _smoothstep(temp, 17.0, 24.0) * _smoothstep(precip, 1200.0, 2200.0)

    # лёсс: перигляциальные и степные окраины
    loess = (_gauss(np.abs(latitude)[:, None] * np.ones((1, W)), 47.0, 9.0)
             * _smoothstep(precip, 260.0, 620.0)
             * (1.0 - _smoothstep(precip, 900.0, 1400.0)))

    s = (0.10
         + 0.52 * f_p * f_t
         + 0.34 * alluvial
         + 0.16 * volc
         + 0.14 * loess
         - 0.26 * leach
         - 0.20 * _smoothstep(slope, 40.0, 190.0)
         - 0.12 * _smoothstep(np.abs(elev), 2200.0, 4200.0))
    s += 0.06 * _fbm(rng, H, W, octaves=6, base_w=9)
    s = np.clip(s, 0.0, 1.0)
    s[~is_land] = 0.0
    s[lake] = 0.0
    return s.astype(np.float64), alluvial


# ────────────────────────────────────────────────────────────────────────────
#  Биомы
# ────────────────────────────────────────────────────────────────────────────


def _classify_biome(temp, precip, elev, is_land, lake, medit, wet_pot, rug):
    """Классификация по (T, P, h). Используется и при генерации, и в climate_at."""
    b = np.full(temp.shape, OCEAN, dtype=np.int8)
    L = is_land

    hot = L & (temp >= 19.5)
    warm = L & (temp >= 5.0) & (temp < 19.5)
    cool = L & (temp >= -1.0) & (temp < 5.0)
    cold = L & (temp >= -17.0) & (temp < -1.0)
    frozen = L & (temp < -17.0)

    b[hot & (precip < 335)] = DESERT
    b[hot & (precip >= 335) & (precip < 660)] = XERIC_SHRUB
    b[hot & (precip >= 660) & (precip < 1150)] = SAVANNA
    b[hot & (precip >= 1150)] = TROPICAL_FOREST

    b[warm & (precip < 275)] = DESERT
    b[warm & (precip >= 275) & (precip < 460)] = XERIC_SHRUB
    b[warm & (precip >= 460) & (precip < 700)] = TEMPERATE_GRASSLAND
    b[warm & (precip >= 700)] = TEMPERATE_FOREST

    b[cool & (precip < 200)] = XERIC_SHRUB
    b[cool & (precip >= 200) & (precip < 300)] = TEMPERATE_GRASSLAND
    b[cool & (precip >= 300)] = BOREAL

    b[cold] = TUNDRA
    b[cold & (precip >= 330) & (temp >= -4.0)] = BOREAL
    b[frozen] = ICE

    # средиземноморье — тёплая зима, сухое лето, западные побережья 28–45°
    med = (L & (medit > 0.42) & (temp >= 10.5) & (temp <= 22.0)
           & (precip >= 260) & (precip <= 950))
    b[med] = MEDITERRANEAN

    # горы
    mont = L & (temp > -17.0) & ((elev > 2750) | ((elev > 2000) & (rug > 0.70)))
    b[mont] = MONTANE

    # болота
    wetm = L & (wet_pot > 0.45) & (temp > -1.0) & (elev < 1400)
    b[wetm] = WETLAND

    b[lake] = LAKE
    b[~L & (temp < -13.0)] = ICE          # морской лёд у полюсов
    return b


# ────────────────────────────────────────────────────────────────────────────
#  Недра
# ────────────────────────────────────────────────────────────────────────────


def _ores(rng, H, W, elev, is_land, B, tect, precip, temp, latitude,
          alluvial, slope):
    """Каждое поле привязано к геологии, а не к случайной раскраске."""
    land = is_land
    orogen = tect["orogen"]
    arcs = tect["arcs"]
    rift = tect["rift"]

    # вулканизм: дуги + рифты + горячие точки
    hot_noise = np.clip(_ridged(rng, H, W, octaves=4, base_w=5) - 0.72, 0, None) * 3.0
    volcanism = np.clip(1.25 * arcs + 0.85 * orogen * B["co"]
                        + 0.55 * rift + 0.45 * hot_noise, 0, 1)
    volcanism = _blur(volcanism, 0.7)
    recent_volc = np.clip(1.4 * arcs + 0.9 * rift + 0.5 * hot_noise
                          - 0.25 * B["cc"], 0, 1)

    # щиты/кратоны: древняя стабильная кора вдали от границ
    age = _norm01(_fbm(rng, H, W, octaves=4, base_w=4))
    shield = np.clip(_smoothstep(B["dist"], 5.0, 16.0) * age
                     * (1.0 - _smoothstep(elev, 900.0, 2600.0)), 0, 1) * land

    # осадочные бассейны: низкая пологая суша, бывшее мелководье
    basin = (np.clip(1.0 - elev / 900.0, 0, 1)
             * np.exp(-slope / 60.0)
             * (0.35 + 0.65 * _norm01(_fbm(rng, H, W, octaves=4, base_w=5)))) * land

    # древние орогены-«гранитные пояса»: узкие, редкие, привязаны к швам
    gran_seed = _ridged(rng, H, W, octaves=5, base_w=7)
    granite = np.clip((orogen ** 0.7) * (0.25 + 0.9 * age)
                      * np.clip(gran_seed - 0.60, 0, None) * 4.0, 0, 1) * land

    n = lambda o=6, b=8: _norm01(_fbm(rng, H, W, octaves=o, base_w=b))  # noqa: E731

    ore: dict[str, np.ndarray] = {}

    # медь — порфировые залежи вулканических дуг + щитовые интрузии
    cu = 0.95 * (arcs ** 0.8) * n(5, 6) + 0.55 * orogen * B["co"] * n(5, 7) \
        + 0.30 * shield * n(5, 6)
    ore["copper"] = _calibrate_fraction(cu, land, 0.075, 0.3)

    # золото — эпитермальные жилы дуг и зеленокаменные пояса щитов
    au = 0.85 * (arcs ** 1.1) * n(6, 9) + 0.70 * shield * np.clip(n(6, 10) - 0.45, 0, None) * 2.2 \
        + 0.35 * alluvial * n(6, 9)          # россыпи
    ore["gold"] = _calibrate_fraction(au, land, 0.035, 0.3)

    ag = 0.9 * (arcs ** 0.9) * n(6, 8) + 0.4 * orogen * n(6, 9) + 0.2 * shield * n(6, 8)
    ore["silver"] = _calibrate_fraction(ag, land, 0.045, 0.3)

    # ОЛОВО — гранитные пояса, очень редко: без него нет бронзы
    sn = granite * (0.35 + 0.9 * n(6, 11)) + 0.18 * shield * np.clip(n(6, 12) - 0.6, 0, None) * 3.0
    tin_frac = float(rng.uniform(0.006, 0.012))
    ore["tin"] = _calibrate_fraction(sn, land, tin_frac, 0.3)

    # железо — обильно: полосчатые формации щитов + бурые руды бассейнов + болота
    fe = 0.85 * shield * (0.4 + n(5, 6)) + 0.75 * basin * (0.35 + n(5, 7)) \
        + 0.30 * orogen * n(5, 8) + 0.25 * _smoothstep(precip, 700, 1800) * basin
    ore["iron"] = _calibrate_fraction(fe, land, 0.32, 0.3)

    # кремень — меловые/известняковые платформы бывших тёплых мелководий
    carb = basin * _smoothstep(np.abs(latitude)[:, None] * np.ones((1, W)), 62.0, 30.0) \
        * (0.3 + n(5, 6))
    fl = carb * (0.4 + 0.9 * n(6, 9)) + 0.25 * shield * n(6, 10)
    ore["flint"] = _calibrate_fraction(fl, land, 0.14, 0.3)

    # глина — поймы и дельты
    cl = 0.85 * alluvial + 0.45 * basin * _smoothstep(precip, 200, 900) \
        + 0.30 * np.clip(1.0 - elev / 400.0, 0, 1) * land
    ore["clay"] = _calibrate_fraction(cl, land, 0.22, 0.3)

    # соль — эвапориты аридных котловин и жарких побережий
    arid = 1.0 - _smoothstep(precip, 150.0, 700.0)
    endorheic = _smoothstep(np.where(land, 1.0, 0.0) * np.exp(-slope / 30.0), 0.3, 0.9)
    coast_arid = np.exp(-np.clip(_edt_cyclic(~is_land)[0], 0, 30) / 3.0)
    sl = arid * (0.7 * endorheic + 0.6 * coast_arid + 0.5 * _smoothstep(temp, 8, 26)) \
        * (0.4 + n(5, 7))
    ore["salt"] = _calibrate_fraction(sl, land, 0.07, 0.3)

    # обсидиан — только свежий вулканизм, крайне локально
    ob = (recent_volc ** 2.2) * np.clip(n(7, 14) - 0.35, 0, None) * 2.5
    ore["obsidian"] = _calibrate_fraction(ob, land, float(rng.uniform(0.004, 0.009)), 0.3)

    # уголь — древние болота умеренного пояса (палеоположение ≠ нынешнему)
    paleo_shift = float(rng.uniform(-22, 22))
    palat = np.abs(latitude[:, None] * np.ones((1, W)) + paleo_shift)
    co = basin * _gauss(palat, 42.0, 16.0) * (0.25 + n(5, 6)) \
        + 0.4 * basin * _smoothstep(precip, 500, 1400) * n(5, 7)
    ore["coal"] = _calibrate_fraction(co, land, 0.10, 0.3)

    # строительный камень — горы и щиты
    st = 0.9 * _smoothstep(elev, 250.0, 2200.0) + 0.6 * shield + 0.5 * orogen \
        + 0.35 * _smoothstep(slope, 20.0, 160.0)
    ore["stone"] = _calibrate_fraction(st * land, land, 0.30, 0.3)

    for k in ORE_KEYS:
        v = ore.get(k, np.zeros((H, W)))
        v = np.clip(v, 0, 1)
        v[~land] = 0.0
        ore[k] = v.astype(np.float32)

    return ore, volcanism, shield, basin, recent_volc


# ────────────────────────────────────────────────────────────────────────────
#  Биота
# ────────────────────────────────────────────────────────────────────────────


def _pick_hotspots(rng, score, is_land, lm, H, W, k):
    """Выбрать k «очагов» по сглаженной пригодности, разнося их по материкам."""
    sm = _blur(score * is_land, 3.0)
    sm[~is_land] = -1.0
    pts = []
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    for _ in range(k):
        i = int(np.argmax(sm))
        if sm.ravel()[i] <= 0.02:
            break
        cy, cx = divmod(i, W)
        pts.append((cy, cx))
        du = xx - cx
        du -= W * np.round(du / W)
        d2 = (du / 13.0) ** 2 + ((yy - cy) / 9.0) ** 2
        sm *= np.clip(d2 / 1.6, 0, 1) ** 0.8            # подавить окрестность
        same = lm == lm[cy, cx]
        sm[same] *= 0.45                                # следующий — другой материк
    return pts


def _hotspot_mask(pts, H, W, r_lon, r_lat):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    m = np.zeros((H, W))
    for (cy, cx) in pts:
        du = xx - cx
        du -= W * np.round(du / W)
        m = np.maximum(m, np.exp(-0.5 * ((du / r_lon) ** 2 + ((yy - cy) / r_lat) ** 2)))
    return m


def _norm_land(a, land, q=0.99):
    """Нормировка поля на 99-й процентиль по суше (устойчиво к выбросам)."""
    if not land.any():
        return np.zeros_like(a)
    ref = float(np.quantile(a[land], q))
    return np.clip(a / max(ref, 1e-6), 0.0, 1.0)


def _biotic(rng, H, W, biome, temp, precip, elev, is_land, soil, river, season,
            medit, roles, lm, shelf, coastal):
    bt: dict[str, np.ndarray] = {}
    land = is_land
    B = biome

    openness = np.zeros((H, W))
    for b, v in ((TEMPERATE_GRASSLAND, 1.0), (SAVANNA, 1.0), (MEDITERRANEAN, 0.85),
                 (XERIC_SHRUB, 0.75), (TUNDRA, 0.7), (DESERT, 0.25),
                 (TEMPERATE_FOREST, 0.35), (BOREAL, 0.4), (TROPICAL_FOREST, 0.12),
                 (MONTANE, 0.5), (WETLAND, 0.55)):
        openness[B == b] = v

    forestness = np.zeros((H, W))
    for b, v in ((TROPICAL_FOREST, 1.0), (TEMPERATE_FOREST, 1.0), (BOREAL, 0.85),
                 (MEDITERRANEAN, 0.45), (SAVANNA, 0.3), (MONTANE, 0.4),
                 (WETLAND, 0.5)):
        forestness[B == b] = v

    # ── дикие злаки: крупносеменные однолетники сезонно-засушливых зон ──
    grain_base = (_smoothstep(season, 0.30, 0.70)
                  * np.exp(-0.5 * ((np.log(np.clip(precip, 30, None)) - math.log(520.0)) / 0.50) ** 2)
                  * _gauss(temp, 15.5, 6.5)
                  * (0.35 + 0.65 * soil)
                  * (0.45 + 0.55 * openness)
                  * (0.7 + 0.6 * medit)) * land
    k = int(rng.integers(2, 6))
    pts = _pick_hotspots(rng, grain_base, land, lm, H, W, k)
    hot = _hotspot_mask(pts, H, W, r_lon=11.0, r_lat=7.0)
    grains = grain_base * (0.10 + 1.15 * hot)
    bt["wild_grains"] = _norm_land(grains, land)

    # ── бобовые: те же пояса, но шире и мягче ──
    pul = (grain_base * 0.8 + 0.5 * _gauss(temp, 16.0, 8.0)
           * _smoothstep(precip, 250, 900) * (0.3 + 0.7 * soil)) * land
    pul *= (0.35 + 0.9 * _hotspot_mask(pts, H, W, 16.0, 11.0))
    bt["wild_pulses"] = _norm_land(pul, land)

    # ── клубни и корнеплоды: влажные тропики и поймы ──
    roots = (_smoothstep(temp, 12.0, 22.0) * _smoothstep(precip, 700, 1800)
             * (0.4 + 0.6 * forestness) * (0.5 + 0.7 * river)) * land
    roots *= (0.55 + 0.75 * _norm01(_fbm(rng, H, W, octaves=5, base_w=7)))
    bt["wild_roots"] = _norm_land(roots, land)

    fruit = ((0.55 * forestness + 0.45 * medit)
             * _smoothstep(precip, 350, 1200) * _gauss(temp, 17.0, 9.5)
             * (0.4 + 0.6 * soil)) * land
    fruit *= (0.5 + 0.8 * _norm01(_fbm(rng, H, W, octaves=5, base_w=8)))
    bt["wild_fruit"] = _norm_land(fruit, land)

    # ── фауна ──
    big = np.zeros((H, W))
    for b, v in ((SAVANNA, 1.0), (TEMPERATE_GRASSLAND, 0.95), (BOREAL, 0.7),
                 (XERIC_SHRUB, 0.5), (TUNDRA, 0.55), (MEDITERRANEAN, 0.5),
                 (TEMPERATE_FOREST, 0.55), (MONTANE, 0.4), (WETLAND, 0.45),
                 (TROPICAL_FOREST, 0.3), (DESERT, 0.12)):
        big[B == b] = v
    fauna_large = big * (0.45 + 0.55 * _smoothstep(precip, 120, 900)) \
        * (0.55 + 0.45 * _norm01(_fbm(rng, H, W, octaves=4, base_w=5)))
    bt["fauna_large"] = np.clip(fauna_large, 0, 1) * land

    small = (0.35 + 0.45 * forestness + 0.25 * _smoothstep(precip, 100, 800)
             + 0.20 * river) * land
    small *= (0.75 + 0.45 * _norm01(_fbm(rng, H, W, octaves=5, base_w=8)))
    bt["fauna_small"] = np.clip(small, 0, 1)

    # ── одомашниваемые: ключевая асимметрия истории ──
    herd_mult = {ROLE_LATITUDINAL: 1.00, ROLE_POLAR_N: 0.60, ROLE_ARCHIPELAGO: 0.34,
                 ROLE_MERIDIONAL: 0.58, ROLE_SOUTH_ISOLATE: 0.22,
                 ROLE_ISLAND: 0.32, ROLE_POLAR_S: 0.0}
    draft_mult = {ROLE_LATITUDINAL: 1.00, ROLE_POLAR_N: 0.28, ROLE_ARCHIPELAGO: 0.07,
                  ROLE_MERIDIONAL: 0.06, ROLE_SOUTH_ISOLATE: 0.02,
                  ROLE_ISLAND: 0.06, ROLE_POLAR_S: 0.0}
    mh = np.zeros((H, W))
    md = np.zeros((H, W))
    for i, r in roles.items():
        m = lm == i
        mh[m] = herd_mult.get(r, 0.15)
        md[m] = draft_mult.get(r, 0.05)

    # внутри материка стадные есть не везде — только в открытых поясах
    herd_core = (bt["fauna_large"] * (0.35 + 0.65 * openness)
                 * _smoothstep(temp, -12.0, 2.0)
                 * (0.4 + 0.6 * _smoothstep(precip, 150, 800)))
    herd_patch = _norm01(_fbm(rng, H, W, octaves=4, base_w=4))
    herd = herd_core * mh * np.clip(1.25 * herd_patch + 0.15, 0, 1) * 1.6
    bt["dom_herd"] = np.clip(herd, 0, 1) * land

    draft_core = (herd_core * (0.45 + 0.55 * openness)
                  * _smoothstep(temp, -6.0, 6.0)
                  * (0.35 + 0.65 * _smoothstep(precip, 200, 700)))
    draft = draft_core * md * np.clip(1.3 * _norm01(_fbm(rng, H, W, octaves=4, base_w=4)) + 0.1, 0, 1) * 2.0
    bt["dom_draft"] = np.clip(draft, 0, 1) * land

    timber = (forestness * _smoothstep(precip, 250, 1100)
              * _smoothstep(temp, -9.0, 4.0)
              * (0.6 + 0.4 * _norm01(_fbm(rng, H, W, octaves=5, base_w=8)))) * land
    bt["timber"] = np.clip(timber * 1.15, 0, 1)

    # ── море: шельф + апвеллинг у западных побережий + эстуарии ──
    ocean = ~land
    wcoast = np.zeros((H, W))
    for k2 in range(1, 7):
        wcoast = np.maximum(wcoast, np.roll(land.astype(float), -k2, axis=1) * (1 - k2 / 7.0))
    upwell = wcoast * ocean * _gauss(np.abs(np.linspace(90, -90, H))[:, None]
                                     * np.ones((1, W)), 26.0, 14.0)
    marine = (shelf * (0.55 + 0.45 * _smoothstep(-elev, 0, 160))
              + 0.75 * upwell
              + 0.30 * _gauss(np.abs(np.linspace(90, -90, H))[:, None] * np.ones((1, W)), 55.0, 18.0) * ocean)
    marine = np.clip(marine, 0, 1)
    # прибрежная суша получает доступ к морю
    mm = marine.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            mm = np.maximum(mm, np.roll(np.roll(marine, dy, axis=0), dx, axis=1))
    marine = np.where(land, np.where(coastal, mm * 0.9, 0.0), marine)
    marine = np.maximum(marine, np.where(land & (river > 0.55), 0.35 * river, 0.0))
    bt["marine"] = np.clip(marine, 0, 1)

    for kk in BIOTIC_KEYS:
        v = np.clip(bt.get(kk, np.zeros((H, W))), 0, 1)
        if kk != "marine":
            v = np.where(land, v, 0.0)
        bt[kk] = v.astype(np.float32)
    return bt, pts


# ────────────────────────────────────────────────────────────────────────────
#  Климатическая история
# ────────────────────────────────────────────────────────────────────────────

SHOCK_KINDS = ("drought", "flood", "eruption", "cold", "plague_reservoir")
SHOCK_DUR = {           # (мин. лет, макс. лет) — длительность растёт с severity
    "drought": (2, 30),
    "flood": (1, 6),
    "eruption": (1, 8),
    "cold": (2, 26),
    "plague_reservoir": (15, 140),
}


def shock_duration(kind: str, severity: float) -> int:
    lo, hi = SHOCK_DUR.get(kind, (1, 10))
    return int(max(1, round(lo + (hi - lo) * float(np.clip(severity, 0, 1)))))


def _climate_history(rng, year_start, n_years):
    yr = np.arange(year_start, year_start + n_years, dtype=np.float64)

    # ── дегляциация: -5 °C → 0 к -8000 ──
    T = -5.0 * (1.0 - _smoothstep(yr, -12300.0, -8000.0))

    # поздний дриас: резкое похолодание -10800..-9700
    yd_a = float(rng.uniform(-10900, -10650))
    yd_b = yd_a + float(rng.uniform(1000, 1250))
    yd = _smoothstep(yr, yd_a - 60, yd_a + 60) * (1.0 - _smoothstep(yr, yd_b - 40, yd_b + 90))
    T -= 2.9 * yd

    # голоценовый оптимум ~ -7000..-4000
    opt_c = float(rng.uniform(-6000, -5000))
    T += 0.75 * _gauss(yr, opt_c, 1150.0)

    # резкие аридные события (аналоги 8.2 ka и 4.2 ka)
    e82 = float(rng.uniform(-6320, -6120))
    e42 = float(rng.uniform(-4300, -4120))
    ev82 = _gauss(yr, e82, 70.0)
    ev42 = _gauss(yr, e42, 95.0)
    T -= 0.95 * ev82 + 0.55 * ev42

    # слабые колебания 200–1500 лет + красный шум
    osc = np.zeros(n_years)
    for _ in range(7):
        per = float(rng.uniform(200, 1500))
        amp = float(rng.uniform(0.05, 0.20))
        pha = float(rng.uniform(0, 2 * math.pi))
        osc += amp * np.sin(2 * math.pi * yr / per + pha)
    red = np.zeros(n_years)
    w = rng.standard_normal(n_years)
    phi = 0.988
    acc = 0.0
    for i in range(n_years):
        acc = phi * acc + w[i]
        red[i] = acc
    red = red / (red.std() + 1e-9) * 0.22
    T += np.clip(osc + red, -0.6, 0.6)

    # ── осадки: множитель ──
    Pm = 1.0 + 0.055 * np.clip(T + 0.0, -3.0, 2.0)
    # «зелёная Сахара»: влажный африкано-азиатский муссонный максимум
    green = _smoothstep(yr, -9600.0, -8600.0) * (1.0 - _smoothstep(yr, -5200.0, -3400.0))
    Pm += 0.17 * green
    Pm -= 0.26 * ev82 + 0.20 * ev42
    Pm -= 0.10 * yd
    posc = np.zeros(n_years)
    for _ in range(5):
        per = float(rng.uniform(230, 1400))
        posc += float(rng.uniform(0.01, 0.05)) * np.sin(
            2 * math.pi * yr / per + float(rng.uniform(0, 2 * math.pi)))
    Pm += posc + 0.5 * (red / max(float(np.abs(red).max()), 1e-9)) * 0.06
    Pm = np.clip(Pm, 0.70, 1.30)

    # ── уровень моря: -60 м → 0 к -4000, дальше стабильно ──
    lgm = -60.0
    s = _smoothstep(yr, -12200.0, -6600.0)
    s2 = _smoothstep(yr, -7200.0, -4000.0)
    rise = 0.72 * s + 0.28 * s2
    rise = rise - rise[0]
    rise = rise / max(float(rise.max()), 1e-9)
    SL = lgm * (1.0 - rise)
    SL -= 3.2 * yd * _smoothstep(yr, -12000, -10000)     # пауза на дриасе
    SL += 0.45 * np.clip(T, -1.0, 1.5) * _smoothstep(yr, -4500.0, -3500.0)
    SL = np.minimum(SL, 1.2)

    return (T.astype(np.float32), Pm.astype(np.float32), SL.astype(np.float32))


def _make_shocks(rng, H, W, year_start, n_years, is_land, precip, temp,
                 volcanism, river, n_shocks):
    """Пуассоновский поток региональных событий."""
    rate = n_shocks / float(n_years)
    years, t = [], float(year_start) + rng.exponential(1.0 / rate)
    while t < year_start + n_years:
        years.append(int(t))
        t += rng.exponential(1.0 / rate)
    # поток мог дать больше или меньше цели — привести к n_shocks, сохранив разброс
    if len(years) > n_shocks:
        years = sorted(int(y) for y in rng.choice(years, size=n_shocks, replace=False))
    elif len(years) < n_shocks:
        extra = rng.integers(year_start, year_start + n_years, n_shocks - len(years))
        years = sorted(years + [int(e) for e in extra])

    lat = np.abs(np.linspace(90, -90, H))[:, None] * np.ones((1, W))
    land = is_land.astype(np.float64)

    wmap = {
        "drought": land * (1.0 - _smoothstep(precip, 200, 1400)) * _smoothstep(temp, -5, 12) + 1e-6,
        "flood": land * (_smoothstep(river, 0.3, 0.9) + 0.4 * _smoothstep(precip, 800, 2500)) + 1e-6,
        "eruption": land * (volcanism ** 1.5) + 1e-6,
        "cold": land * _smoothstep(lat, 25, 70) + 1e-6,
        "plague_reservoir": land * _smoothstep(temp, 2, 22) * _smoothstep(precip, 300, 1600) + 1e-6,
    }
    flat = {k: (v.ravel() / v.sum()) for k, v in wmap.items()}
    kinds = list(SHOCK_KINDS)
    kw = np.array([0.30, 0.20, 0.13, 0.17, 0.20])
    kw = kw / kw.sum()

    shocks = []
    for y in years:
        kind = kinds[int(rng.choice(len(kinds), p=kw))]
        i = int(rng.choice(H * W, p=flat[kind]))
        cy, cx = divmod(i, W)
        sev = float(np.clip(rng.beta(1.9, 3.1) * 1.15, 0.05, 1.0))
        rad = float(np.clip(rng.gamma(2.4, 3.4) + 2.0, 2.5, 26.0))
        if kind == "eruption":
            rad *= 0.6
        shocks.append((int(y), kind, int(cy), int(cx),
                       round(rad, 2), round(sev, 3)))
    shocks.sort(key=lambda s: s[0])
    return shocks


# ────────────────────────────────────────────────────────────────────────────
#  Сборка мира
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_CFG: dict[str, Any] = {
    "earth_like_layout": True,
    "land_fraction": None,      # None → случайно в [0.272, 0.315]
    "n_plates": None,           # None → случайно 10..16
    "year_start": -12000,
    "n_years": 14000,
    "n_shocks": None,           # None → случайно 60..200
}


def generate_world(seed: int, width: int = 180, height: int = 90,
                   cfg: dict | None = None) -> World:
    """Сгенерировать планету земного типа. Полностью детерминировано по seed."""
    t0 = time.time()
    conf = dict(DEFAULT_CFG)
    if cfg:
        conf.update(cfg)
    rng = np.random.default_rng(int(seed))
    H, W = int(height), int(width)

    latitude = (90.0 - (np.arange(H) + 0.5) * 180.0 / H).astype(np.float64)
    V, U = np.mgrid[0:H, 0:W].astype(np.float64)
    U = (U + 0.5) / W
    V = (V + 0.5) / H

    # ── 1. шаблоны материков ──
    if conf["earth_like_layout"]:
        templates, seas, moats = _earthlike_templates(rng)
    else:
        templates, seas, moats = _random_templates(rng)

    wu = _fbm(rng, H, W, octaves=4, base_w=5) * 0.030
    wv = _fbm(rng, H, W, octaves=4, base_w=5) * 0.020
    Uw = (U + wu) % 1.0
    Vw = np.clip(V + wv, 0.0, 1.0)

    cont_pot = np.zeros((H, W))
    for _role, blobs in templates:
        cont_pot = np.maximum(cont_pot, _blob_field(blobs, Uw, Vw))
    sea_pot = _blob_field(seas, Uw, Vw) if seas else np.zeros((H, W))
    moat_pot = _moat_field(moats, Uw, Vw)
    cont_pot = np.clip(cont_pot - 0.85 * sea_pot - 1.40 * moat_pot, -1.0, 1.2)

    # ── 2. тектоника ──
    n_plates = conf["n_plates"] or int(rng.integers(10, 17))
    plate, seeds, vel, is_cont = _build_plates(rng, H, W, cont_pot, n_plates)
    B = _plate_boundaries(plate, vel, is_cont, H, W)

    # ── 3. рельеф ──
    land_target = conf["land_fraction"] or float(rng.uniform(0.275, 0.312))
    elev, is_land, tect = _build_relief(rng, H, W, cont_pot, B, land_target)

    # производные геометрии
    dist_ocean, _, _ = _edt_cyclic(~is_land)
    maritime = np.exp(-dist_ocean / 6.5)
    coastal = is_land & _dilate_cyclic(~is_land)
    shelf = (~is_land) & (elev > -220)

    gx = _dx_cyclic(elev)
    gy = _dy_clamped(elev)
    slope = np.hypot(gx, gy)
    emax = ndi.maximum_filter(elev, size=3, mode=("reflect", "wrap"))
    emin = ndi.minimum_filter(elev, size=3, mode=("reflect", "wrap"))
    rug = np.clip((emax - emin) / 900.0, 0, 1) * is_land

    # ── 4. материки ──
    lm, n_lm, area, axis = _landmasses(is_land, H, W)
    roles, names = _assign_roles(lm, n_lm, templates, Uw, Vw, area, axis, H, W)

    # ── 5. климат ──
    base_temp, base_precip, season, medit, wwest, west_ocean = _build_climate(
        rng, H, W, elev, is_land, latitude, maritime, dist_ocean)

    # ── 6. гидрология ──
    fill, lake_depth, acc, river = _hydrology(elev, is_land, base_precip,
                                              latitude, H, W)
    lake = _lakes(lake_depth, acc, is_land, H, W)

    # ── 7. недра (нужен вулканизм для почв) ──
    ore, volcanism, shield, basin, recent_volc = _ores(
        rng, H, W, elev, is_land, B, tect, base_precip, base_temp,
        latitude, np.clip(river, 0, 1), slope)

    # ── 8. почвы ──
    soil, alluvial = _soils(rng, H, W, elev, is_land, base_temp, base_precip,
                            river, slope, volcanism, latitude, lake)

    # ── 9. биомы ──
    wet_pot = np.clip(0.65 * river + 0.5 * _smoothstep(base_precip, 700, 1800)
                      - 0.9 * _smoothstep(slope, 15, 90)
                      - 0.5 * _smoothstep(np.abs(elev), 900, 2200), 0, 1) * is_land
    biome = _classify_biome(base_temp, base_precip, elev, is_land, lake,
                            medit, wet_pot, rug)

    # ── 10. биота ──
    biotic, grain_pts = _biotic(rng, H, W, biome, base_temp, base_precip, elev,
                                is_land, soil, river, season, medit, roles, lm,
                                shelf.astype(float), coastal)

    # ── 11. история климата ──
    year_start = int(conf["year_start"])
    n_years = int(conf["n_years"])
    gT, gP, SL = _climate_history(rng, year_start, n_years)
    n_shocks = conf["n_shocks"] or int(rng.integers(60, 201))
    shocks = _make_shocks(rng, H, W, year_start, n_years, is_land, base_precip,
                          base_temp, volcanism, river, n_shocks)

    world = World(
        seed=int(seed), width=W, height=H,
        elevation=elev.astype(np.float32),
        is_land=is_land.astype(bool),
        plate_id=plate.astype(np.int16),
        landmass_id=lm.astype(np.int16),
        latitude=(latitude[:, None] * np.ones((1, W))).astype(np.float32),
        ruggedness=rug.astype(np.float32),
        coastal=coastal.astype(bool),
        river=river.astype(np.float32),
        soil=soil.astype(np.float32),
        base_temp=base_temp.astype(np.float32),
        base_precip=base_precip.astype(np.float32),
        biome=biome.astype(np.int8),
        ore=ore,
        biotic=biotic,
        landmass_axis={int(k): float(v) for k, v in axis.items()},
        landmass_area={int(k): int(v) for k, v in area.items()},
        landmass_name={int(k): str(v) for k, v in names.items()},
        year_start=year_start, n_years=n_years,
        global_temp_anom=gT, global_precip_anom=gP, sea_level=SL,
        shocks=shocks,
        meta={
            "schema": SCHEMA_VERSION,
            "land_fraction": float(is_land.mean()),
            "n_plates": int(n_plates),
            "n_landmasses": int(n_lm),
            "earth_like_layout": bool(conf["earth_like_layout"]),
            "landmass_role": {int(k): str(v) for k, v in roles.items()},
            "grain_hotspots": [[int(a), int(b)] for a, b in grain_pts],
            "gen_seconds": 0.0,
            # поля-помощники для climate_at (не входят в контракт напрямую)
            "medit": medit.astype(np.float32),
            "wet_pot": wet_pot.astype(np.float32),
            "lake_mask": lake.astype(bool),
            "volcanism": volcanism.astype(np.float32),
            "shelf": shelf.astype(bool),
            "season": season.astype(np.float32),
            "dist_ocean": dist_ocean.astype(np.float32),
            "slope": slope.astype(np.float32),
        },
    )
    world.meta["gen_seconds"] = round(time.time() - t0, 3)
    return world


def _dilate_cyclic(mask):
    """Дилатация 3×3 с заворотом по X (для поиска береговой линии)."""
    out = np.zeros_like(mask)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sh = np.roll(mask, dx, axis=1)
            if dy < 0:
                sh = np.vstack([sh[1:], sh[-1:]])
            elif dy > 0:
                sh = np.vstack([sh[:1], sh[:-1]])
            out |= sh
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Климат конкретного года
# ────────────────────────────────────────────────────────────────────────────


def climate_at(world: World, year: int) -> Climate:
    """Температура, осадки, биомы и биопродуктивность года `year`."""
    H, W = world.height, world.width
    i = int(np.clip(year - world.year_start, 0, world.n_years - 1))
    dT = float(world.global_temp_anom[i]) if world.global_temp_anom is not None else 0.0
    mP = float(world.global_precip_anom[i]) if world.global_precip_anom is not None else 1.0

    lat = world.latitude.astype(np.float64)
    alat = np.abs(lat)

    # полярное усиление
    amp = 0.65 + 1.00 * (alat / 90.0) ** 1.5
    temp = world.base_temp.astype(np.float64) + dT * amp

    precip = world.base_precip.astype(np.float64) * mP
    # во влажные фазы субтропики зеленеют сильнее среднего («зелёная Сахара»)
    wet_extra = max(0.0, mP - 1.0)
    precip *= 1.0 + 2.2 * wet_extra * _gauss(alat, 22.0, 11.0)
    dry_extra = max(0.0, 1.0 - mP)
    precip *= 1.0 - 0.8 * dry_extra * _gauss(alat, 30.0, 16.0)

    # ── активные шоки ──
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    for (sy, kind, cy, cx, rad, sev) in world.shocks:
        dur = shock_duration(kind, sev)
        if not (sy <= year < sy + dur):
            continue
        du = xx - cx
        du -= W * np.round(du / W)
        d2 = (du * du + (yy - cy) ** 2) / max(rad * rad, 1.0)
        k = np.exp(-0.5 * d2)
        if k.max() < 1e-3:
            continue
        if kind == "drought":
            precip *= 1.0 - 0.62 * sev * k
            temp += 1.4 * sev * k
        elif kind == "flood":
            precip *= 1.0 + 0.85 * sev * k
        elif kind == "eruption":
            temp -= 3.2 * sev * k
            precip *= 1.0 - 0.18 * sev * k
        elif kind == "cold":
            temp -= 4.2 * sev * k
            precip *= 1.0 - 0.12 * sev * k
        # plague_reservoir не меняет климат — это событие для слоя обществ

    precip = np.clip(precip, 12.0, 6000.0)

    meta = world.meta
    medit = np.asarray(meta.get("medit", np.zeros((H, W))), dtype=np.float64)
    wet_pot = np.asarray(meta.get("wet_pot", np.zeros((H, W))), dtype=np.float64)
    lake = np.asarray(meta.get("lake_mask", world.biome == LAKE), dtype=bool)

    biome = _classify_biome(temp, precip, world.elevation.astype(np.float64),
                            world.is_land, lake, medit, wet_pot,
                            world.ruggedness.astype(np.float64))

    prod = _productivity(temp, precip, world.soil.astype(np.float64),
                         world.river.astype(np.float64), world.is_land,
                         biome, world.biotic["marine"].astype(np.float64))

    return Climate(year=int(year), temp=temp.astype(np.float32),
                   precip=precip.astype(np.float32), biome=biome.astype(np.int8),
                   productivity=prod.astype(np.float32))


def _productivity(temp, precip, soil, river, is_land, biome, marine):
    """Чистая первичная продукция, нормированная: пойма ≈ 1.2, пустыня ≈ 0.03."""
    f_t = np.clip((temp + 10.0) / 25.0, 0.0, 1.0) ** 0.85
    f_p = np.clip(precip / 1000.0, 0.0, 1.0) ** 1.75
    p = 1.03 * f_t * f_p * (0.55 + 0.55 * soil) * (1.0 + 0.35 * river)
    p = np.where(is_land, p, 0.10 + 0.35 * marine)
    p[biome == ICE] = 0.0
    p[biome == LAKE] = 0.45
    return np.clip(p, 0.0, 1.5)


# ────────────────────────────────────────────────────────────────────────────
#  Сериализация
# ────────────────────────────────────────────────────────────────────────────

_ARRAY_FIELDS = ("elevation", "is_land", "plate_id", "landmass_id", "latitude",
                 "ruggedness", "coastal", "river", "soil", "base_temp",
                 "base_precip", "biome", "global_temp_anom",
                 "global_precip_anom", "sea_level")


def save_world(world: World, path: str) -> str:
    """Сохранить мир: `<base>.npz` (поля) + `<base>.json` (скаляры и словари)."""
    base = path[:-4] if path.endswith(".npz") else path
    d = os.path.dirname(base)
    if d:
        os.makedirs(d, exist_ok=True)

    arrays: dict[str, np.ndarray] = {}
    for name in _ARRAY_FIELDS:
        v = getattr(world, name)
        if v is not None:
            arrays[name] = np.asarray(v)
    for k, v in world.ore.items():
        arrays["ore__" + k] = np.asarray(v)
    for k, v in world.biotic.items():
        arrays["biotic__" + k] = np.asarray(v)
    scal: dict[str, Any] = {}
    for k, v in world.meta.items():
        if isinstance(v, np.ndarray):
            arrays["meta__" + k] = v
        else:
            scal[k] = v

    np.savez_compressed(base + ".npz", **arrays)
    doc = {
        "schema": SCHEMA_VERSION,
        "seed": int(world.seed), "width": int(world.width),
        "height": int(world.height),
        "year_start": int(world.year_start), "n_years": int(world.n_years),
        "landmass_axis": {str(k): float(v) for k, v in world.landmass_axis.items()},
        "landmass_area": {str(k): int(v) for k, v in world.landmass_area.items()},
        "landmass_name": {str(k): str(v) for k, v in world.landmass_name.items()},
        "shocks": [[int(a), str(b), int(c), int(d2), float(e), float(f)]
                   for (a, b, c, d2, e, f) in world.shocks],
        "meta": scal,
        "meta_arrays": [k for k in arrays if k.startswith("meta__")],
    }
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    return base


def load_world(path: str) -> World:
    base = path[:-4] if path.endswith(".npz") else path
    if base.endswith(".json"):
        base = base[:-5]
    with open(base + ".json", "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    z = np.load(base + ".npz")
    arrays = {k: z[k] for k in z.files}

    ore = {k[5:]: arrays[k] for k in arrays if k.startswith("ore__")}
    biotic = {k[8:]: arrays[k] for k in arrays if k.startswith("biotic__")}
    meta = dict(doc.get("meta", {}))
    for k in arrays:
        if k.startswith("meta__"):
            meta[k[6:]] = arrays[k]
    meta["landmass_role"] = {int(a): b for a, b in
                             (meta.get("landmass_role") or {}).items()}

    return World(
        seed=int(doc["seed"]), width=int(doc["width"]), height=int(doc["height"]),
        elevation=arrays["elevation"], is_land=arrays["is_land"].astype(bool),
        plate_id=arrays["plate_id"], landmass_id=arrays["landmass_id"],
        latitude=arrays["latitude"], ruggedness=arrays["ruggedness"],
        coastal=arrays["coastal"].astype(bool), river=arrays["river"],
        soil=arrays["soil"], base_temp=arrays["base_temp"],
        base_precip=arrays["base_precip"], biome=arrays["biome"],
        ore=ore, biotic=biotic,
        landmass_axis={int(k): float(v) for k, v in doc["landmass_axis"].items()},
        landmass_area={int(k): int(v) for k, v in doc["landmass_area"].items()},
        landmass_name={int(k): str(v) for k, v in doc["landmass_name"].items()},
        year_start=int(doc["year_start"]), n_years=int(doc["n_years"]),
        global_temp_anom=arrays.get("global_temp_anom"),
        global_precip_anom=arrays.get("global_precip_anom"),
        sea_level=arrays.get("sea_level"),
        shocks=[tuple(s) for s in doc.get("shocks", [])],
        meta=meta,
    )


# ────────────────────────────────────────────────────────────────────────────
#  Быстрая визуальная проверка
# ────────────────────────────────────────────────────────────────────────────

BIOME_CHARS = {
    OCEAN: ".", ICE: "*", TUNDRA: ",", BOREAL: "f", TEMPERATE_FOREST: "F",
    TEMPERATE_GRASSLAND: '"', MEDITERRANEAN: "m", DESERT: " ", XERIC_SHRUB: "s",
    SAVANNA: "v", TROPICAL_FOREST: "T", MONTANE: "^", WETLAND: "=", LAKE: "o",
}


def ascii_map(world: World, out_w: int = 110, out_h: int = 40) -> str:
    """Грубая ASCII-карта: 180×90 → ~110×40 (мода биома в блоке)."""
    H, W = world.height, world.width
    b = world.biome
    land = world.is_land
    xs = np.linspace(0, W, out_w + 1).astype(int)
    ys = np.linspace(0, H, out_h + 1).astype(int)
    rows = ["+" + "-" * out_w + "+"]
    for j in range(out_h):
        y0, y1 = ys[j], max(ys[j] + 1, ys[j + 1])
        line = []
        for i in range(out_w):
            x0, x1 = xs[i], max(xs[i] + 1, xs[i + 1])
            blk = b[y0:y1, x0:x1].ravel()
            lb = land[y0:y1, x0:x1].ravel()
            if lb.mean() < 0.35:
                sub = blk[~lb]
                ch = "." if sub.size == 0 or (sub == OCEAN).all() else \
                    BIOME_CHARS.get(int(np.bincount(sub.astype(int)).argmax()), ".")
            else:
                sub = blk[lb]
                ch = BIOME_CHARS.get(int(np.bincount(sub.astype(int)).argmax()), "?")
            line.append(ch)
        rows.append("|" + "".join(line) + "|")
    rows.append("+" + "-" * out_w + "+")
    legend = "  ".join(f"{BIOME_CHARS[k]}={BIOME_NAMES[k]}" for k in
                       (ICE, TUNDRA, BOREAL, TEMPERATE_FOREST, TEMPERATE_GRASSLAND,
                        MEDITERRANEAN, DESERT, XERIC_SHRUB, SAVANNA,
                        TROPICAL_FOREST, MONTANE, WETLAND, LAKE))
    rows.append(legend)
    return "\n".join(rows)


def biome_histogram(world: World, land_only: bool = True) -> list[tuple[str, float]]:
    """Гистограмма биомов в процентах (по умолчанию — от площади суши)."""
    b = world.biome
    m = world.is_land if land_only else np.ones_like(world.is_land, dtype=bool)
    tot = int(m.sum())
    if tot == 0:
        return []
    cnt = np.bincount(b[m].astype(int), minlength=14)
    out = [(BIOME_NAMES[i], 100.0 * cnt[i] / tot) for i in range(14) if cnt[i] > 0]
    out.sort(key=lambda p: -p[1])
    return out


def world_summary(world: World, min_area: int = 200) -> str:
    """Текстовая сводка для быстрой проверки правдоподобия."""
    L = world.is_land
    nland = int(L.sum())
    lines = [f"seed={world.seed}  {world.width}×{world.height}  "
             f"суша {100.0 * L.mean():.1f}%  ({nland} клеток)"]
    roles = world.meta.get("landmass_role", {})
    big = [(i, a) for i, a in world.landmass_area.items() if a >= min_area]
    big.sort(key=lambda p: -p[1])
    lines.append(f"материков площадью > {min_area}: {len(big)}")
    for i, a in big:
        lines.append(f"   {world.landmass_name.get(i, i):<20} "
                     f"площадь {a:>5}  ось {world.landmass_axis.get(i, 0):.2f}  "
                     f"[{roles.get(i, '?')}]")
    lines.append("биомы (% суши):")
    for name, pc in biome_histogram(world):
        lines.append(f"   {name:<24}{pc:5.1f}%")
    tin = float((world.ore["tin"][L] > 0.3).mean() * 100)
    gr = float((world.biotic["wild_grains"][L] > 0.6).mean() * 100)
    obs = float((world.ore["obsidian"][L] > 0.3).mean() * 100)
    draft = float((world.biotic["dom_draft"][L] > 0.4).mean() * 100)
    lines.append(f"олово > 0.3: {tin:.2f}% суши   "
                 f"обсидиан > 0.3: {obs:.2f}%   "
                 f"дикие злаки > 0.6: {gr:.2f}%   "
                 f"тягловые > 0.4: {draft:.2f}%")
    ep = world.elevation
    lines.append(f"высоты: {ep.min():.0f} … {ep.max():.0f} м, "
                 f"суша до {ep[L].max():.0f} м")
    lines.append(f"шоков: {len(world.shocks)}   "
                 f"плит: {world.meta.get('n_plates')}   "
                 f"массивов суши: {world.meta.get('n_landmasses')}")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    t0 = time.time()
    w = generate_world(1)
    dt = time.time() - t0

    L = w.is_land
    print(f"доля суши: {100.0 * L.mean():.2f}%")

    big = [(i, a) for i, a in w.landmass_area.items() if a > 200]
    big.sort(key=lambda p: -p[1])
    roles = w.meta.get("landmass_role", {})
    print(f"материков с площадью > 200 клеток: {len(big)}")
    for i, a in big:
        print(f"   {w.landmass_name.get(i, i):<20} площадь {a:>5}  "
              f"ось {w.landmass_axis[i]:.2f}  [{roles.get(i, '?')}]")

    print("гистограмма биомов (% суши):")
    for name, pc in biome_histogram(w):
        print(f"   {name:<24}{pc:5.1f}%")

    tin = float((w.ore['tin'][L] > 0.3).mean() * 100)
    gr = float((w.biotic['wild_grains'][L] > 0.6).mean() * 100)
    print(f"суша с tin > 0.3:          {tin:.2f}%")
    print(f"суша с wild_grains > 0.6:  {gr:.2f}%")

    print(ascii_map(w))
    print(f"время генерации: {dt:.2f} с (внутри модуля "
          f"{w.meta['gen_seconds']:.2f} с)")

