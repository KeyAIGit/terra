"""
Трёхмерный обозреватель мира TERRA.

Собирает из каталога прогона один самодостаточный HTML-файл: вращаемая мышью
планета в WebGL (three.js вшит внутрь), с рельефом, биомами, владениями
народов, городами, реками, ночными огнями и летописью.

    from terra.globe import build_globe
    build_globe("runs/terra-1")            # -> runs/terra-1/globe.html

Файл работает полностью офлайн: ни одного внешнего запроса, никаких CDN
и хранилищ. Всё — текстуры, кадры, летопись — вшито как base64/JSON.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

from terra.agents import ROLE_RU
from terra.contracts import BIOME_COLORS, BIOME_NAMES
from terra.gallery import BELIEF_RU, TRAIT_RU
from terra.society import FORM_RU, MODE_RU
from terra.world import load_world

# Загрузчики и мелкие утилиты уже написаны в отчёте — переиспользуем их,
# чтобы контракт данных был ровно один на весь проект.
from terra.report import KIND_COLORS, KIND_ORDER, KIND_RU, _b64, _read_jsonl

# ────────────────────────────────────────────────────────────────────────────
#  Настройки сборки
# ────────────────────────────────────────────────────────────────────────────
MAX_FRAMES = 150            # не больше стольких кадров (прореживаем равномерно)
MAX_EVENTS = 14000          # не больше стольких событий летописи
TEX_TARGET_W = 2560         # желаемая ширина текстур (округляется до кратной W)
GEO_SEG_W = 512             # сегментов сферы по долготе
GEO_SEG_H = 256             # сегментов сферы по широте
DISP_LAND = 0.026           # подъём суши, доли радиуса планеты
DISP_SEA = 0.013            # глубина впадин, доли радиуса планеты
TARGET_BYTES = 25_000_000   # потолок размера готового HTML

MAX_ROUTES = 1600           # не больше стольких торговых путей в кадре
ROUTE_SAMPLES = 15          # точек вдоль дуги для проверки «над водой ли путь»
SEA_SHARE = 0.55            # доля воды под дугой, с которой путь считаем морским
MAX_PEOPLE = 6000           # не больше стольких замечательных людей
PEOPLE_BUCKET = 200         # людей отбираем поровну из отрезков в столько лет
MAX_DEEDS = 3               # сколько деяний оставляем каждому человеку

# Новые виды летописных записей. В общем словаре отчёта их пока нет, а глобус
# обязан работать с любым прогоном — поэтому дополняем словари прямо здесь.
KIND_RU_EXTRA = {
    "collapse": "обрушение",
    "religion": "вера",
}
KIND_COLORS_EXTRA = {
    # обрушение державы — самое тревожное, что бывает в мире: сигнальный красный
    "collapse": "#ff4b34",
    "religion": "#d7a6ec",
}
# обрушение ставим в самое начало ленты фильтров, веру — рядом с решениями
KIND_ORDER_EXTRA = ("collapse", "religion")

# Палитра укладов хозяйства
MODE_COLORS = {
    "forager": "#7d9fc4",
    "complex_forager": "#5fb8a4",
    "horticulture": "#9ec94f",
    "pastoral": "#e0bd4a",
    "agrarian": "#e08a3a",
    "intensive": "#cf5347",
}

# Гипсометрическая шкала: (высота в метрах, цвет)
HYPSO_LAND = [
    (0, (58, 110, 68)), (200, (96, 142, 74)), (500, (150, 166, 88)),
    (1000, (196, 176, 104)), (1800, (176, 138, 96)), (2800, (146, 118, 108)),
    (4000, (196, 190, 194)), (6500, (250, 252, 255)),
]
HYPSO_SEA = [
    (-7000, (6, 16, 40)), (-4000, (12, 34, 72)), (-2000, (20, 56, 104)),
    (-600, (30, 84, 136)), (-150, (46, 116, 164)), (0, (76, 152, 188)),
]


# ────────────────────────────────────────────────────────────────────────────
#  Мелкие утилиты
# ────────────────────────────────────────────────────────────────────────────
def _hex_rgb(s: str) -> tuple[int, int, int]:
    """'#a1b2c3' -> (161, 178, 195)."""
    s = str(s or "#888888").lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        s = "888888"
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (136, 136, 136)


def _resize_wrap(a: np.ndarray, tw: int, th: int, smooth: bool = True) -> np.ndarray:
    """Растянуть поле до (th, tw), считая мир цикличным по долготе.

    Тайлим массив трижды по X, увеличиваем, берём среднюю треть — так шва
    на стыке долгот не возникает вовсе.
    """
    from PIL import Image

    a = np.ascontiguousarray(np.asarray(a, dtype=np.float32))
    a3 = np.concatenate([a, a, a], axis=1)
    im = Image.fromarray(a3, mode="F")
    rs = Image.BICUBIC if smooth else Image.NEAREST
    im = im.resize((tw * 3, th), rs)
    return np.asarray(im, dtype=np.float32)[:, tw:2 * tw]


def _fbm(tw: int, th: int, seed: int, octaves: int = 7,
         base_w: int = 12, gain: float = 0.5) -> np.ndarray:
    """Многооктавный шум, цикличный по долготе; значения примерно 0..1.

    Октавы мельче трети ширины текстуры не берём: на экране они всё равно
    превращаются в пиксельную «манную кашу».
    """
    rng = np.random.default_rng(seed)
    out = np.zeros((th, tw), dtype=np.float32)
    amp, norm = 1.0, 0.0
    lim = max(base_w, tw // 3)
    for o in range(octaves):
        w = int(base_w * (2 ** o))
        h = max(2, w // 2)
        if w > lim:
            break
        g = rng.random((h, w)).astype(np.float32)
        out += amp * _resize_wrap(g, tw, th)
        norm += amp
        amp *= gain
    return out / max(norm, 1e-6)


def _png_b64(arr: np.ndarray) -> str:
    """uint8-массив (H,W) или (H,W,3) -> base64 PNG."""
    from PIL import Image

    im = Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8))
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=9)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ramp(vals: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    """Раскрасить поле по опорным точкам палитры. -> (H,W,3) float32 0..255."""
    xs = np.array([s[0] for s in stops], dtype=np.float32)
    cs = np.array([s[1] for s in stops], dtype=np.float32)
    out = np.empty(vals.shape + (3,), dtype=np.float32)
    for k in range(3):
        out[..., k] = np.interp(vals, xs, cs[:, k])
    return out


def _disp_units(h_m: np.ndarray, hmax: float, hmin: float) -> np.ndarray:
    """Метры -> смещение вершин в долях радиуса планеты."""
    up = np.clip(h_m, 0, None) / max(hmax, 1.0) * DISP_LAND
    dn = np.clip(h_m, None, 0) / max(abs(hmin), 1.0) * DISP_SEA
    return (up + dn).astype(np.float32)


def _warp(img: np.ndarray, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """Доменное искажение картинки на dx/dy пикселей (билинейно, X цикличен).

    Нужно, чтобы границы биомов и берега не повторяли квадратную сетку
    исходных клеток мира: без этого планета выглядит «лесенкой».
    """
    th, tw = img.shape[0], img.shape[1]
    xs = np.arange(tw, dtype=np.float32)[None, :] + dx
    ys = np.arange(th, dtype=np.float32)[:, None] + dy
    x0f = np.floor(xs)
    y0f = np.floor(ys)
    fx = (xs - x0f).astype(np.float32)
    fy = (ys - y0f).astype(np.float32)
    x0 = np.mod(x0f.astype(np.int32), tw)
    x1 = np.mod(x0 + 1, tw)
    y0 = np.clip(y0f.astype(np.int32), 0, th - 1)
    y1 = np.clip(y0 + 1, 0, th - 1)
    if img.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    top = img[y0, x0] * (1.0 - fx) + img[y0, x1] * fx
    bot = img[y1, x0] * (1.0 - fx) + img[y1, x1] * fx
    return (top * (1.0 - fy) + bot * fy).astype(np.float32)


# ────────────────────────────────────────────────────────────────────────────
#  Текстуры планеты
# ────────────────────────────────────────────────────────────────────────────
def _build_textures(w) -> dict[str, Any]:
    """Сгенерировать все карты планеты и вернуть их как base64 PNG."""
    H, W = int(w.height), int(w.width)
    scale = max(4, int(round(TEX_TARGET_W / W)))
    tw, th = W * scale, H * scale

    elev = np.nan_to_num(np.asarray(w.elevation, dtype=np.float32))
    rug = np.nan_to_num(np.asarray(getattr(w, "ruggedness", None)
                                   if getattr(w, "ruggedness", None) is not None
                                   else np.zeros((H, W)), dtype=np.float32))
    riv = np.nan_to_num(np.asarray(getattr(w, "river", None)
                                   if getattr(w, "river", None) is not None
                                   else np.zeros((H, W)), dtype=np.float32))
    biome = np.asarray(w.biome, dtype=np.int8)
    ids = sorted(BIOME_NAMES.keys())
    pal = np.zeros((max(ids) + 1, 3), dtype=np.float32)
    for b in ids:
        pal[b] = _hex_rgb(BIOME_COLORS.get(b, "#888888"))

    lat_col = (90.0 - (np.arange(th, dtype=np.float32) + 0.5) * 180.0 / th)[:, None]

    # ── шумы ───────────────────────────────────────────────────────────────
    # доменное искажение: сбивает квадратную сетку клеток мира
    wamp = 0.85 * scale
    wx = (_fbm(tw, th, 4242, octaves=3, base_w=max(8, W // 4)) - 0.5) * 2.0 * wamp
    wy = (_fbm(tw, th, 8181, octaves=3, base_w=max(8, W // 4)) - 0.5) * 2.0 * wamp
    n_coast = _fbm(tw, th, 991, octaves=4, base_w=max(8, W // 3), gain=0.55) - 0.5
    n_fine = _fbm(tw, th, 1701, octaves=6, base_w=max(8, W // 3), gain=0.60) - 0.5
    n_mid = _fbm(tw, th, 5150, octaves=3, base_w=max(6, W // 6), gain=0.55) - 0.5

    # ── поля мира в высоком разрешении, с искажением ───────────────────────
    e_up = _warp(_resize_wrap(elev, tw, th), wx, wy)
    rug_up = np.clip(_warp(_resize_wrap(rug, tw, th), wx, wy), 0.0, 1.0)
    riv_up = np.clip(_warp(_resize_wrap(riv, tw, th), wx, wy), 0.0, 1.0)

    # биом крупным планом: ближайшая клетка по искажённым координатам
    cx = ((np.arange(tw, dtype=np.float32) + 0.5) * W / tw - 0.5)[None, :] + wx / scale
    cy = ((np.arange(th, dtype=np.float32) + 0.5) * H / th - 0.5)[:, None] + wy / scale
    bx = np.mod(np.rint(cx).astype(np.int32), W)
    by = np.clip(np.rint(cy).astype(np.int32), 0, H - 1)
    bid = biome[by, bx]
    del cx, cy, bx, by

    # мягко смешанные цвета биомов (для «природы»)
    blend = _warp(np.stack([_resize_wrap(pal[np.clip(biome, 0, None)][..., k], tw, th)
                            for k in range(3)], axis=-1), wx, wy)
    del wx, wy

    # ── высота: берег ломаем шумом, горам добавляем фрактальную фактуру ────
    near = np.exp(-(e_up / 620.0) ** 2)
    h = e_up + n_coast * 720.0 * near

    land_soft = np.clip(h / 260.0, 0.0, 1.0)
    amp = (300.0 + 2100.0 * rug_up + 0.26 * np.clip(h, 0, None)) * land_soft
    h = h + n_fine * amp
    # дно океана тоже неровное — заметно на шельфе и у срединных хребтов
    h = h + (n_fine * 0.6 + n_mid * 0.4) * 520.0 * np.clip(-h / 1400.0, 0.0, 1.0)

    is_land = h > 0.0
    hmax = float(max(np.max(h[is_land]) if is_land.any() else 1.0, 1.0))
    hmin = float(min(np.min(h[~is_land]) if (~is_land).any() else -1.0, -1.0))
    depth = np.clip(-h / max(-hmin, 1.0), 0.0, 1.0)

    # ── карта нормалей ─────────────────────────────────────────────────────
    # Рельеф планеты в масштабе радиуса ничтожен, поэтому светотень
    # усиливаем: без этого хребты просто не читаются.
    d = _disp_units(h, hmax, hmin)
    coslat = np.clip(np.cos(np.radians(lat_col)), 0.18, 1.0)
    stepx = (2.0 * math.pi * coslat) / tw        # шаг по долготе, доли радиуса
    stepy = math.pi / th                         # шаг по широте
    gx = (np.roll(d, -1, axis=1) - np.roll(d, 1, axis=1)) * 0.5
    gy = (np.roll(d, -1, axis=0) - np.roll(d, 1, axis=0)) * 0.5
    boost = 4.5
    nx = np.clip(-gx / stepx * boost, -5.0, 5.0)
    ny = np.clip(gy / stepy * boost, -5.0, 5.0)  # +v — на север
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    nrm = np.stack([nx / ln, ny / ln, nz / ln], axis=-1)
    tex_nrm = np.clip(nrm * 0.5 + 0.5, 0, 1) * 255.0

    # лёгкая запечённая светотень с северо-запада — глубина даже в полутени
    shade = np.clip(1.0 + (nrm[..., 0] * -0.42 + nrm[..., 1] * 0.42), 0.42, 1.6)
    shade = np.where(is_land, shade, 1.0)
    del nx, ny, nz, ln, gx, gy

    # ── «природа»: цвета биомов + камень + снег + пестрота ─────────────────
    mott = n_fine * 0.5 + n_mid * 0.5
    # чистый цвет биома подмешиваем к мягкой растяжке: иначе вблизи всё
    # расплывается в один градиент
    nat = (blend * 0.78 + pal[np.clip(bid, 0, None)] * 0.22) \
        * (1.0 + mott[..., None] * 0.15)
    rocky = np.clip((h - 1500.0) / 2400.0, 0.0, 1.0) * (0.55 + 0.9 * rug_up)
    rocky = np.clip(rocky, 0.0, 1.0)[..., None]
    nat = nat * (1 - rocky) + np.array([128.0, 118.0, 108.0]) * rocky
    snowline = 5000.0 - 46.0 * np.abs(lat_col)
    snow = np.clip((h - snowline) / 850.0 + mott * 0.22, 0.0, 1.0)
    snow = np.maximum(snow, np.clip((np.abs(lat_col) - 66.0) / 8.0 + mott * 0.25,
                                    0.0, 1.0))
    snow = np.clip(snow, 0.0, 1.0) * is_land
    nat = nat * (1 - snow[..., None]) + np.array([240.0, 246.0, 252.0]) * snow[..., None]
    # немного повышаем насыщенность: иначе на шаре суша выглядит выцветшей
    g = nat.mean(axis=-1, keepdims=True)
    nat = np.clip(g + (nat - g) * 1.09, 0, 255)
    nat *= shade[..., None]
    floor = np.array([26.0, 42.0, 58.0]) * (1.0 - depth[..., None] * 0.55) \
        * (1.0 + mott[..., None] * 0.2)
    tex_nat = np.clip(np.where(is_land[..., None], nat, floor), 0, 255)

    # ── «биомы»: чистые категориальные цвета ───────────────────────────────
    bio = pal[np.clip(bid, 0, None)] * (0.78 + 0.30 * shade)[..., None]
    seab = np.array([24.0, 48.0, 78.0]) * (1.0 - depth[..., None] * 0.45)
    tex_bio = np.clip(np.where(is_land[..., None], bio, seab), 0, 255)

    # ── «гипсометрия»: только высота ───────────────────────────────────────
    hyp = np.where(is_land[..., None], _ramp(h, HYPSO_LAND), _ramp(h, HYPSO_SEA))
    hyp = hyp * (0.80 + 0.28 * shade)[..., None]
    tex_hyp = np.clip(hyp, 0, 255)

    # ── маски: R — реки, G — суша, B — нормированная глубина ───────────────
    # В поле `river` лежит не русло, а водность клетки. Порог по величине даёт
    # синие кляксы размером в клетку, поэтому берём «стрежень»: нерезкая маска
    # выделяет гребни поля водосбора — получаются тонкие ветвящиеся русла.
    riv_blur = _resize_wrap(_resize_wrap(riv_up, max(8, tw // 10), max(4, th // 10)),
                            tw, th)
    riv_m = (np.clip((riv_up - riv_blur) * 4.5, 0.0, 1.0)
             * np.clip((riv_up - 0.16) / 0.24, 0.0, 1.0) * is_land)
    mask = np.stack([riv_m * 255.0,
                     is_land.astype(np.float32) * 255.0,
                     depth * 255.0], axis=-1)

    # ── карта высот для смещения вершин (16 бит в каналах R,G) ─────────────
    hw, hh = max(256, tw // 2), max(128, th // 2)
    d_lo = _resize_wrap(d, hw, hh)
    lo, hi = float(d_lo.min()), float(d_lo.max())
    q = np.clip((d_lo - lo) / max(hi - lo, 1e-9), 0, 1) * 65535.0
    qi = q.astype(np.uint32)
    hgt = np.stack([(qi >> 8) & 0xFF, qi & 0xFF, np.zeros_like(qi)], axis=-1)

    return {
        "tw": tw, "th": th, "hw": hw, "hh": hh,
        "lo": round(lo, 8), "hi": round(hi, 8),
        "nat": _png_b64(tex_nat.astype(np.uint8)),
        "bio": _png_b64(tex_bio.astype(np.uint8)),
        "hyp": _png_b64(tex_hyp.astype(np.uint8)),
        "nrm": _png_b64(tex_nrm.astype(np.uint8)),
        "msk": _png_b64(mask.astype(np.uint8)),
        "hgt": _png_b64(hgt.astype(np.uint8)),
    }


# ────────────────────────────────────────────────────────────────────────────
#  Торговые пути и книга людей
# ────────────────────────────────────────────────────────────────────────────
def _cell_unit_vectors(H: int, W: int) -> np.ndarray:
    """Единичные векторы центров клеток, (H, W, 3).

    Усреднение таких векторов само разбирается с цикличностью по долготе:
    у клеток на 179-й и 0-й долготе векторы соседние, а не противоположные.
    """
    lat = np.radians(90.0 - (np.arange(H, dtype=np.float64) + 0.5) * 180.0 / H)
    lon = np.radians(-180.0 + (np.arange(W, dtype=np.float64) + 0.5) * 360.0 / W)
    out = np.empty((H, W, 3), dtype=np.float64)
    cl = np.cos(lat)[:, None]
    out[..., 0] = cl * np.cos(lon)[None, :]
    out[..., 1] = cl * np.sin(lon)[None, :]
    out[..., 2] = np.repeat(np.sin(lat)[:, None], W, axis=1)
    return out


def _vec_ll(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Вектор(ы) -> широта и долгота в градусах."""
    lat = np.degrees(np.arcsin(np.clip(v[..., 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(v[..., 1], v[..., 0]))
    return lat, lon


def _centroids(cm: np.ndarray, cellv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Центры владений всех народов кадра -> (векторы (n,3), маска годных)."""
    flat = np.asarray(cm, dtype=np.int32).ravel()
    ok = flat >= 0
    n = int(flat.max()) + 1 if ok.any() else 1
    acc = np.zeros((n, 3), dtype=np.float64)
    if ok.any():
        idx = flat[ok]
        v = cellv.reshape(-1, 3)[ok]
        for k in range(3):
            acc[:, k] = np.bincount(idx, weights=v[:, k], minlength=n)
    ln = np.linalg.norm(acc, axis=1)
    good = ln > 1e-9
    acc[good] /= ln[good][:, None]
    return acc, good


def _pack_routes(routes: list, cent: np.ndarray, good: np.ndarray,
                 is_land: np.ndarray, H: int, W: int) -> list[list[int]]:
    """Связи кадра -> [pid_a, pid_b, сила×100, морская ли].

    Морскими считаем те, чья дуга идёт преимущественно над водой: пробуем
    несколько точек вдоль большого круга и смотрим, что под ними.
    """
    sel: list[tuple[int, int, float]] = []
    for r in routes or []:
        try:
            a, b, s = int(r[0]), int(r[1]), float(r[2])
        except (TypeError, ValueError, IndexError):
            continue
        if a == b or a < 0 or b < 0:
            continue
        if a >= good.size or b >= good.size or not good[a] or not good[b]:
            continue
        sel.append((a, b, s))
    if not sel:
        return []
    if len(sel) > MAX_ROUTES:
        sel.sort(key=lambda t: -t[2])
        sel = sel[:MAX_ROUTES]

    ai = np.array([t[0] for t in sel], dtype=np.int32)
    bi = np.array([t[1] for t in sel], dtype=np.int32)
    va, vb = cent[ai], cent[bi]
    ang = np.arccos(np.clip((va * vb).sum(axis=1), -1.0, 1.0))
    sa = np.sin(ang)
    near = sa < 1e-6
    den = np.where(near, 1.0, sa)
    water = np.zeros(len(sel), dtype=np.float64)
    ts = np.linspace(0.12, 0.88, ROUTE_SAMPLES)
    for t in ts:
        w1 = np.where(near, 1.0 - t, np.sin((1.0 - t) * ang) / den)
        w2 = np.where(near, t, np.sin(t * ang) / den)
        p = va * w1[:, None] + vb * w2[:, None]
        ln = np.linalg.norm(p, axis=1)
        ln[ln < 1e-9] = 1.0
        p = p / ln[:, None]
        lat, lon = _vec_ll(p)
        yy = np.clip(((90.0 - lat) / 180.0 * H).astype(np.int32), 0, H - 1)
        xx = (((lon + 180.0) / 360.0 * W).astype(np.int32)) % W
        water += (~is_land[yy, xx]).astype(np.float64)
    sea = water / float(len(ts)) >= SEA_SHARE

    out = []
    for k, (a, b, s) in enumerate(sel):
        out.append([a, b, int(round(min(max(s, 0.0), 1.0) * 100)),
                    1 if bool(sea[k]) else 0])
    return out


def _collect_people(run_dir: Path) -> list[dict]:
    """Книга замечательных людей. Файла может не быть — это не беда."""
    rows = _read_jsonl(run_dir / "people.jsonl")
    if not rows:
        return []
    out: list[dict] = []
    for r in rows:
        try:
            born = int(r.get("born"))
        except (TypeError, ValueError):
            continue
        died = r.get("died")
        if died is None:
            died = r.get("last_seen")
        try:
            died = int(died)
        except (TypeError, ValueError):
            died = born
        deeds = []
        for d in (r.get("deeds") or [])[:MAX_DEEDS]:
            txt = str(d.get("text", "")).strip()
            if not txt:
                continue
            try:
                dy = int(d.get("year", born))
            except (TypeError, ValueError):
                dy = born
            deeds.append([dy, str(d.get("kind", "")), txt])
        traits = r.get("traits") or {}
        top = sorted(((str(k), float(v or 0.0)) for k, v in traits.items()),
                     key=lambda kv: -kv[1])[:3]
        beliefs = r.get("beliefs") or {}
        btop = sorted(((str(k), float(v or 0.0)) for k, v in beliefs.items()),
                      key=lambda kv: -kv[1])[:2]
        pid = r.get("polity")
        out.append({
            "n": str(r.get("name", "—")),
            "p": int(pid) if pid is not None else -1,
            "pn": str(r.get("polity_name") or "—"),
            "b": born, "d": max(died, born),
            "a": int(r.get("age") or max(died - born, 0)),
            "sx": int(r.get("sex") or 0),
            "r": str(r.get("role") or "commoner"),
            "e": str(r.get("era") or "—"),
            "pr": round(float(r.get("prestige") or 0.0), 2),
            "pw": round(float(r.get("power") or 0.0), 2),
            "wl": round(float(r.get("wealth") or 0.0), 2),
            "tr": [[k, round(v, 2)] for k, v in top],
            "bl": [[k, round(v, 2)] for k, v in btop],
            "ds": deeds,
        })

    if len(out) > MAX_PEOPLE:
        # прореживаем не «сверху списка», а поровну по эпохам: иначе
        # начало времён съест всю квоту и панель в конце прогона опустеет
        buckets: dict[int, list[dict]] = {}
        for p in out:
            buckets.setdefault(p["b"] // PEOPLE_BUCKET, []).append(p)
        quota = max(1, MAX_PEOPLE // max(len(buckets), 1))
        kept: list[dict] = []
        for key in sorted(buckets):
            grp = buckets[key]
            grp.sort(key=lambda p: -(p["pr"] + p["pw"] + 0.5 * len(p["ds"])))
            kept.extend(grp[:quota])
        out = kept
    out.sort(key=lambda p: p["b"])
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Сбор данных прогона
# ────────────────────────────────────────────────────────────────────────────
def _collect(run_dir: Path) -> dict[str, Any]:
    """Собрать всё, что нужно странице, из каталога прогона."""
    run: dict[str, Any] = {}
    rj = run_dir / "run.json"
    if rj.exists():
        run = json.loads(rj.read_text(encoding="utf-8"))
    cfg = dict(run.get("config") or {})

    w = load_world(str(run_dir / "world"))
    H, W = int(w.height), int(w.width)
    is_land = np.asarray(w.is_land, dtype=bool)
    elev = np.nan_to_num(np.asarray(w.elevation, dtype=np.float32))

    def _u8(field: str) -> str:
        v = getattr(w, field, None)
        if v is None:
            return _b64(np.zeros(H * W, dtype=np.uint8))
        v = np.nan_to_num(np.asarray(v, dtype=np.float32))
        return _b64((np.clip(v, 0, 1) * 255).astype(np.uint8).ravel())

    world_pack = {
        "w": W, "h": H,
        "biome": _b64(np.asarray(w.biome, dtype=np.int8).ravel()),
        "elev": _b64(np.clip(elev, -12000, 12000).astype(np.int16).ravel()),
        "land": _b64(is_land.astype(np.uint8).ravel()),
        "river": _u8("river"),
        "soil": _u8("soil"),
        "rug": _u8("ruggedness"),
    }

    # ── кадры ──────────────────────────────────────────────────────────────
    def _dedup(rows: list[dict]) -> list[dict]:
        seen: dict[int, dict] = {}
        for r in rows:
            seen[int(r.get("year", 0))] = r
        return [seen[y] for y in sorted(seen)]

    snaps = _dedup(_read_jsonl(run_dir / "snapshots.jsonl"))
    timeline = _dedup(_read_jsonl(run_dir / "timeline.jsonl"))
    chron = _read_jsonl(run_dir / "chronicle.jsonl")

    n_all = len(snaps)
    thinned = False
    if len(snaps) > MAX_FRAMES:
        idx = np.unique(np.linspace(0, len(snaps) - 1, MAX_FRAMES).round().astype(int))
        snaps = [snaps[i] for i in idx]
        thinned = True

    cellv = _cell_unit_vectors(H, W)

    def _frame(s: dict) -> dict:
        # центры владений считаем по карте культур: они нужны и торговым
        # путям, и перелёту камеры к землям народа
        cm_b64 = s.get("culture_map", "") or ""
        try:
            cm = np.frombuffer(base64.b64decode(cm_b64), dtype="<i2")
        except Exception:
            cm = np.full(H * W, -1, dtype=np.int16)
        if cm.size != H * W:
            cm = np.full(H * W, -1, dtype=np.int16)
        cent, good = _centroids(cm.reshape(H, W), cellv)
        clat, clon = _vec_ll(cent)

        pol = []
        for p in (s.get("polities") or []):
            pid = int(p.get("pid", -1))
            rec = {
                "id": pid,
                "n": p.get("name", "—"),
                "c": p.get("color", "#888888"),
                "p": int(p.get("pop", 0)),
                "m": p.get("mode", "forager"),
                "f": p.get("form", "band"),
                "s": int(p.get("cells", 0)),
                "t": int(p.get("tech", 0)),
                "cx": round(float(p.get("complexity", 0.0)), 3),
                "iq": round(float(p.get("ineq", 0.0)), 3),
                "ch": round(float(p.get("coh", 0.0)), 3),
                "e": p.get("era", "—"),
                "g": [str(g) for g in (p.get("gods") or [])],
                "cap": p.get("capital") or None,
                "lg": round(float(p.get("legit", 0.0) or 0.0), 3),
                "su": round(float(p.get("surplus", 0.0) or 0.0), 3),
            }
            pol.append(rec)

        # Список народов в снимке урезан по величине, а карта культур и связи
        # знают всех — поэтому центры владений храним отдельной таблицей
        # «народ → широта, долгота» (в сотых долях градуса, чтобы было компактно).
        ct: list[int] = []
        for pid in np.nonzero(good)[0]:
            ct.append(int(pid))
            ct.append(int(round(float(clat[pid]) * 100)))
            ct.append(int(round(float(clon[pid]) * 100)))
        st = []
        for c in (s.get("settlements") or []):
            st.append({
                "n": c.get("name", "—"),
                "y": int(c.get("y", 0)), "x": int(c.get("x", 0)),
                "p": int(c.get("pop", 0)),
                "t": str(c.get("tier", "")),
                "c": int(c.get("culture", -1)) if c.get("culture") is not None else -1,
                "w": round(float(c.get("walls", 0.0)), 2),
                "m": int(c.get("mon", 0)),
            })
        return {"year": int(s.get("year", 0)), "cm": cm_b64,
                "pol": pol, "set": st, "ct": ct,
                "rt": _pack_routes(s.get("routes") or [], cent, good,
                                   is_land, H, W)}

    frames = [_frame(s) for s in snaps]
    if not frames:
        frames = [{"year": int(cfg.get("year_start", 0)),
                   "cm": _b64(np.full(H * W, -1, dtype=np.int16)),
                   "pol": [], "set": [], "ct": [], "rt": []}]

    people = _collect_people(run_dir)

    # ── летопись ───────────────────────────────────────────────────────────
    ev_trunc = False
    if len(chron) > MAX_EVENTS:
        keep = set(sorted(range(len(chron)),
                          key=lambda i: -float(chron[i].get("weight", 0)))[:MAX_EVENTS])
        chron = [e for i, e in enumerate(chron) if i in keep]
        ev_trunc = True
    chron.sort(key=lambda e: (int(e.get("year", 0)), -float(e.get("weight", 0))))
    events = []
    for e in chron:
        y, x = e.get("y"), e.get("x")
        events.append({
            "yr": int(e.get("year", 0)),
            "k": e.get("kind", "—"),
            "t": e.get("text", ""),
            "w": round(float(e.get("weight", 1.0)), 2),
            "p": int(e["polity"]) if e.get("polity") is not None else None,
            "cy": int(y) if y is not None else None,
            "cx": int(x) if x is not None else None,
        })

    tl = [{"yr": int(t.get("year", 0)),
           "pop": round(float(t.get("pop", 0.0))),
           "np": int(t.get("polities", 0) or 0),
           "tm": int(t.get("tech_max", 0) or 0),
           "ct": int(t.get("cities", 0) or 0),
           "e": t.get("era", "—")} for t in timeline]

    stats = dict(run.get("stats") or {})
    last_tl = timeline[-1] if timeline else {}
    years = [int(f["year"]) for f in frames]
    head = {
        "run_id": run.get("run_id") or run_dir.name,
        "seed": cfg.get("seed"),
        "year_start": int(cfg.get("year_start", years[0])),
        "year_end": int(run.get("year", cfg.get("year_end", years[-1]))),
        "n_polities_ever": int(run.get("n_polities_ever", 0) or 0),
        "pop_end": float(last_tl.get("pop", 0.0)),
        "tech_max": int(last_tl.get("tech_max", 0) or 0),
        "wars": int(stats.get("wars", 0) or 0),
        "epidemics": int(stats.get("epidemics", 0) or 0),
        "discoveries": int(stats.get("discoveries", 0) or 0),
        "collapses": int(stats.get("collapses", 0) or 0),
        "era_end": last_tl.get("era", "—"),
        "frames": len(frames),
        "frames_all": n_all,
        "thinned": thinned,
        "events": len(events),
        "events_trunc": ev_trunc,
        "people": len(people),
    }

    # виды летописи: общий словарь проекта плюс те, что глобус знает сам
    kind_ru = dict(KIND_RU)
    kind_ru.update(KIND_RU_EXTRA)
    kind_colors = dict(KIND_COLORS)
    kind_colors.update(KIND_COLORS_EXTRA)
    seen_kinds = {e["k"] for e in events}
    order = [k for k in KIND_ORDER_EXTRA]
    order += [k for k in KIND_ORDER if k not in order]
    # если в прогоне завёлся вид, о котором не знает никто, — тоже покажем
    order += sorted(k for k in seen_kinds if k not in order)

    return {
        "head": head,
        "world": world_pack,
        "tex": _build_textures(w),
        "frames": frames,
        "events": events,
        "timeline": tl,
        "people": people,
        "dict": {
            "biomeNames": {str(k): v for k, v in BIOME_NAMES.items()},
            "biomeColors": {str(k): v for k, v in BIOME_COLORS.items()},
            "modeRu": MODE_RU, "formRu": FORM_RU,
            "modeColors": MODE_COLORS,
            "kindRu": kind_ru, "kindColors": kind_colors,
            "kindOrder": order,
            "roleRu": dict(ROLE_RU),
            "traitRu": dict(TRAIT_RU),
            "beliefRu": dict(BELIEF_RU),
        },
    }


# ────────────────────────────────────────────────────────────────────────────
#  Сборка страницы
# ────────────────────────────────────────────────────────────────────────────
def _three_source() -> str:
    """Прочитать локальную сборку three.js (CommonJS) для вшивания в HTML."""
    here = Path(__file__).resolve().parent
    cands = [
        here.parent / "node_modules" / "three" / "build" / "three.cjs",
        Path.cwd() / "node_modules" / "three" / "build" / "three.cjs",
    ]
    for c in cands:
        if c.exists():
            src = c.read_text(encoding="utf-8")
            # чтобы содержимое не оборвало наш <script>
            return src.replace("</script", "<\\/script").replace("<!--", "<\\!--")
    raise FileNotFoundError(
        "не найден node_modules/three/build/three.cjs — установите three "
        "локально (npm i three) рядом с пакетом terra")


def _render(payload: dict) -> str:
    """Склеить итоговый HTML."""
    heavy = {"frames": payload["frames"], "events": payload["events"],
             "timeline": payload["timeline"], "people": payload["people"]}
    raw = json.dumps(heavy, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")

    meta = {"head": payload["head"], "world": payload["world"],
            "tex": payload["tex"], "dict": payload["dict"]}
    meta_js = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))

    h = payload["head"]
    title = "TERRA · планета " + str(h["run_id"])
    return (
        "<!DOCTYPE html>\n<html lang=\"ru\"><head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>" + title + "</title>\n"
        "<style>\n" + _CSS + "\n</style>\n</head>\n<body>\n"
        + _BODY + "\n"
        "<script>var module={exports:{}},exports=module.exports;\n"
        + _three_source() +
        "\nvar THREE=module.exports;</script>\n"
        "<script>var TERRA=" + meta_js + ";</script>\n"
        "<script>var TERRA_GZ=\"" + gz + "\";</script>\n"
        "<script>\n" + _APP_JS + "\n</script>\n"
        "</body></html>\n"
    )


def build_globe(run_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Собрать трёхмерный обозреватель мира по каталогу прогона.

    run_dir  — каталог прогона (в нём world.npz/world.json, snapshots.jsonl…)
    out_path — куда положить HTML; по умолчанию <run_dir>/globe.html
    """
    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"каталог прогона не найден: {run_dir}")
    out = Path(out_path) if out_path else run_dir / "globe.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = _collect(run_dir)
    html = _render(payload)
    out.write_text(html, encoding="utf-8")

    size = out.stat().st_size
    if size > TARGET_BYTES:
        print(f"[globe] предупреждение: файл {size/1e6:.1f} МБ — больше "
              f"целевых {TARGET_BYTES/1e6:.0f} МБ", file=sys.stderr)
    print(f"[globe] {out} — {size/1e6:.2f} МБ, кадров: "
          f"{payload['head']['frames']}, событий: {payload['head']['events']}"
          f", людей: {payload['head']['people']}")
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Разметка, стили и код страницы
# ────────────────────────────────────────────────────────────────────────────
_CSS = r"""
:root{
  --bg:#070b10; --panel:rgba(15,22,30,.86); --line:#22303d;
  --ink:#c7d3dd; --ink2:#8b9bab; --ink3:#5f7183;
  --acc:#7fb3d5; --acc2:#c8a96e; --warn:#c4685a;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:var(--bg);color:var(--ink);
  font:13px/1.45 -apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
#stage{position:fixed;inset:0}
canvas{display:block;touch-action:none;cursor:grab}
canvas.drag{cursor:grabbing}
#labels{position:fixed;inset:0;pointer-events:none;overflow:hidden}
.lab{position:absolute;left:0;top:0;white-space:nowrap;font-size:11px;letter-spacing:.02em;
  color:#eaf2f8;text-shadow:0 0 4px #000,0 1px 3px #000,0 0 9px rgba(0,0,0,.85);
  transform:translate(-50%,-50%);will-change:transform;pointer-events:none}
.lab i{display:inline-block;width:4px;height:4px;border-radius:50%;background:#ffd9a0;
  margin-right:4px;vertical-align:middle;box-shadow:0 0 5px #ffb765}
.lab.big{font-size:12.5px;font-weight:600}

.pane{position:fixed;background:var(--panel);border:1px solid var(--line);border-radius:9px;
  backdrop-filter:blur(9px);-webkit-backdrop-filter:blur(9px);box-shadow:0 8px 34px rgba(0,0,0,.55)}
.pane h3{margin:0;padding:8px 11px;font-size:11px;font-weight:600;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink3);border-bottom:1px solid var(--line)}
.body{overflow-y:auto;overscroll-behavior:contain}
.body::-webkit-scrollbar{width:8px}
.body::-webkit-scrollbar-thumb{background:#22303d;border-radius:4px}
.body::-webkit-scrollbar-track{background:transparent}

#top{left:12px;top:12px;right:12px;height:38px;display:flex;align-items:center;gap:14px;
  padding:0 13px;z-index:6}
#top .ttl{font-weight:600;letter-spacing:.04em}
#top .ttl b{color:var(--acc)}
#top .yr{color:var(--acc2);font-variant-numeric:tabular-nums;font-weight:600;font-size:14px}
#top .era{color:var(--ink3)}
#top .sp{flex:1}
#top .kv{color:var(--ink3);font-size:11.5px}
#top .kv b{color:var(--ink2);font-weight:600}

#left{left:12px;top:60px;width:246px;bottom:96px;display:flex;flex-direction:column;z-index:5}
#right{right:12px;top:60px;width:302px;bottom:96px;display:flex;flex-direction:column;z-index:5}
#bar{left:12px;right:12px;bottom:12px;height:74px;padding:8px 13px;z-index:6}

#left .sec{border-bottom:1px solid var(--line)}
#left .sec:last-child{border-bottom:0}
.lay{padding:7px 11px 9px}
label.ck{display:flex;align-items:center;gap:7px;padding:3px 0;cursor:pointer;color:var(--ink2);
  user-select:none;font-size:12.5px}
label.ck:hover{color:var(--ink)}
label.ck input{accent-color:var(--acc);margin:0;width:13px;height:13px;cursor:pointer}
.grp{display:flex;gap:4px;padding:3px 0 6px;flex-wrap:wrap}
.grp button{flex:1;min-width:62px;background:#16212c;border:1px solid var(--line);color:var(--ink2);
  border-radius:5px;padding:4px 5px;font:inherit;font-size:11.5px;cursor:pointer}
.grp button:hover{border-color:#33475a;color:var(--ink)}
.grp button.on{background:#1e3646;border-color:var(--acc);color:#dbeaf5}
.hint{color:var(--ink3);font-size:11px;padding:1px 0 4px}

#plist{flex:1;min-height:70px}
.prow{display:flex;align-items:center;gap:7px;padding:4px 11px;cursor:pointer;
  border-left:2px solid transparent}
.prow:hover{background:#16222d}
.prow.on{background:#1a2b38;border-left-color:var(--acc)}
.prow .sw{width:10px;height:10px;border-radius:2px;flex:none;box-shadow:0 0 0 1px rgba(0,0,0,.5)}
.prow .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px}
.prow .pp{color:var(--ink3);font-size:11px;font-variant-numeric:tabular-nums}

#info{flex:none;max-height:296px;overflow:hidden;display:flex;flex-direction:column}
#info .body{padding:7px 11px 10px;overflow-y:auto;min-height:0}
.kv{display:flex;justify-content:space-between;gap:9px;padding:2px 0;font-size:12px}
.kv span:first-child{color:var(--ink3);flex:none}
.kv span:last-child{text-align:right;overflow:hidden;text-overflow:ellipsis}
.big{font-size:14px;font-weight:600;color:var(--acc2);padding:1px 0 4px}

.tabs{display:flex;border-bottom:1px solid var(--line)}
.tabs button{flex:1;background:transparent;border:0;border-bottom:2px solid transparent;
  color:var(--ink3);font:inherit;font-size:11px;font-weight:600;letter-spacing:.09em;
  text-transform:uppercase;padding:8px 6px;cursor:pointer}
.tabs button:hover{color:var(--ink2)}
.tabs button.on{color:var(--acc);border-bottom-color:var(--acc)}
.tabs .n{font-weight:400;letter-spacing:0;color:var(--ink3);font-size:10.5px}
.tabpane{flex:1;display:none;flex-direction:column;min-height:0}
.tabpane.on{display:flex}

#kinds{padding:7px 9px;display:flex;flex-wrap:wrap;gap:4px;border-bottom:1px solid var(--line)}
#kinds b{font-size:10.5px;font-weight:600;padding:2px 6px;border-radius:9px;cursor:pointer;
  background:#1a2732;color:var(--ink3);border:1px solid transparent;user-select:none}
#evs{flex:1}
#peopleList{flex:1}
.ev{padding:5px 10px 6px;border-bottom:1px solid #16212b;border-left:3px solid #2a3844;cursor:pointer}
.ev:hover{background:#16222d}
.ev.geo{cursor:pointer}
.ev .h{display:flex;gap:7px;align-items:baseline;font-size:10.5px}
.ev .y{color:var(--ink3);font-variant-numeric:tabular-nums;flex:none}
.ev .k{font-weight:600}
.ev .t{font-size:12px;color:var(--ink);margin-top:1px}
.ev .g{float:right;color:var(--ink3);font-size:10px}
.ev.alarm{background:rgba(255,75,52,.10);border-left-width:4px}
.ev.alarm .t{color:#ffd7cd}
.ev.alarm .k{letter-spacing:.05em}
.empty{padding:14px 11px;color:var(--ink3);font-size:12px;text-align:center}

.pers{padding:5px 10px 6px;border-bottom:1px solid #16212b;border-left:3px solid #2a3844;
  cursor:pointer}
.pers:hover{background:#16222d}
.pers.on{background:#1a2b38}
.pers .h{display:flex;gap:6px;align-items:baseline}
.pers .nm{font-size:12.5px;font-weight:600;color:#dbe7f0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.pers .rl{font-size:10.5px;color:var(--acc2);flex:none}
.pers .sub{font-size:10.5px;color:var(--ink3);margin-top:1px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.pers .dd{font-size:11.5px;color:var(--ink2);margin-top:2px}
.pers .yy{color:var(--ink3);font-variant-numeric:tabular-nums;font-size:10.5px;flex:none;
  margin-left:auto}
#peopleHint{padding:6px 10px;color:var(--ink3);font-size:11px;border-bottom:1px solid var(--line)}
.gods{display:flex;flex-wrap:wrap;gap:3px;padding:3px 0 2px}
.gods i{font-style:normal;font-size:10.5px;padding:1px 6px;border-radius:9px;
  background:#22283a;color:#cbbde8;border:1px solid #33395a}
.bars{padding:3px 0 1px}
.bars .b{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--ink3);padding:1px 0}
.bars .b u{flex:1;height:4px;background:#1b2731;border-radius:2px;overflow:hidden;
  text-decoration:none}
.bars .b u>i{display:block;height:100%;background:var(--acc)}

#bar .row{display:flex;align-items:center;gap:9px}
#bar .row+.row{margin-top:7px}
#bar button{background:#16212c;border:1px solid var(--line);color:var(--ink);border-radius:5px;
  min-width:31px;height:26px;padding:0 8px;font:inherit;font-size:13px;cursor:pointer}
#bar button:hover{border-color:#33475a}
#bar button.on{background:#1e3646;border-color:var(--acc)}
#slider{flex:1;accent-color:var(--acc);height:20px;cursor:pointer}
#bar .lbl{color:var(--ink3);font-size:11.5px;min-width:132px}
#bar .lbl b{color:var(--ink2)}
#bar select{background:#16212c;border:1px solid var(--line);color:var(--ink);border-radius:5px;
  height:26px;font:inherit;font-size:12px;padding:0 4px;cursor:pointer}

#legend{position:fixed;left:270px;bottom:96px;z-index:5;display:none;max-width:290px;padding:7px 10px}
#legend.show{display:block}
#legend .li{display:inline-flex;align-items:center;gap:5px;margin:2px 8px 2px 0;font-size:11px;
  color:var(--ink2)}
#legend .li i{width:9px;height:9px;border-radius:2px;display:inline-block}

#boot{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  background:var(--bg);z-index:40;flex-direction:column;gap:11px;color:var(--ink3)}
#boot .b{width:190px;height:3px;background:#182531;border-radius:2px;overflow:hidden}
#boot .b i{display:block;height:100%;width:20%;background:var(--acc);transition:width .25s}
#boot.gone{display:none}
#err{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:50;max-width:560px;
  padding:16px 20px;display:none;color:var(--warn)}
@media (max-width:1100px){
  #left{width:212px}#right{width:250px}#legend{left:236px}
}
@media (max-width:820px){
  #left,#right{display:none}#legend{left:12px}
}
"""

_BODY = r"""
<div id="stage"></div>
<div id="labels"></div>

<div class="pane" id="top">
  <span class="ttl">TERRA · <b id="runid">—</b></span>
  <span class="yr" id="year">—</span>
  <span class="era" id="era">—</span>
  <span class="sp"></span>
  <span class="kv" id="stat"></span>
</div>

<div class="pane" id="left">
  <h3>Слои</h3>
  <div class="sec lay">
    <div class="grp" id="basemap">
      <button data-b="nat" class="on">Природа</button>
      <button data-b="bio">Биомы</button>
      <button data-b="hyp">Рельеф</button>
    </div>
    <label class="ck"><input type="checkbox" id="ckCult" checked>Владения народов</label>
    <label class="ck"><input type="checkbox" id="ckMode">Уклад хозяйства</label>
    <label class="ck"><input type="checkbox" id="ckRoute" checked>Торговые пути</label>
    <label class="ck"><input type="checkbox" id="ckRiver" checked>Реки</label>
    <label class="ck"><input type="checkbox" id="ckCity" checked>Города</label>
    <label class="ck"><input type="checkbox" id="ckLab" checked>Подписи городов</label>
    <label class="ck"><input type="checkbox" id="ckNight" checked>Ночь и огни городов</label>
    <label class="ck"><input type="checkbox" id="ckSun" checked>Солнце следует за камерой</label>
    <label class="ck"><input type="checkbox" id="ckAtm" checked>Атмосфера и звёзды</label>
    <div class="grp" style="margin-top:5px">
      <button id="btnOrbit">Облететь планету</button>
      <button id="btnReset">Сброс вида</button>
    </div>
    <div class="hint">Тяните мышью — вращение, колесо — приближение, клик — сведения о клетке.</div>
  </div>
  <h3>Крупнейшие народы</h3>
  <div class="sec body" id="plist"></div>
  <div class="pane" id="info" style="position:static;border:0;border-top:1px solid var(--line);
       border-radius:0;box-shadow:none;background:transparent;display:none">
    <h3 id="infoTtl">Клетка</h3>
    <div class="body" id="infoBody"></div>
  </div>
</div>

<div class="pane" id="right">
  <div class="tabs" id="tabs">
    <button data-t="chron" class="on">Летопись</button>
    <button data-t="people">Люди <span class="n" id="peopleN"></span></button>
  </div>
  <div class="tabpane on" id="paneChron">
    <div id="kinds"></div>
    <div class="body" id="evs"></div>
  </div>
  <div class="tabpane" id="panePeople">
    <div id="peopleHint">Те, кто жил в эти годы. Клик — перелёт к землям народа.</div>
    <div class="body" id="peopleList"></div>
  </div>
</div>

<div class="pane" id="legend"></div>

<div class="pane" id="bar">
  <div class="row">
    <button id="btnPrev" title="Предыдущий кадр">◀</button>
    <button id="btnPlay" title="Играть / пауза">▶</button>
    <button id="btnNext" title="Следующий кадр">▶|</button>
    <input type="range" id="slider" min="0" max="0" value="0" step="1">
    <select id="speed" title="Скорость">
      <option value="0.5">0,5×</option>
      <option value="1" selected>1×</option>
      <option value="2">2×</option>
      <option value="4">4×</option>
      <option value="8">8×</option>
    </select>
  </div>
  <div class="row">
    <span class="lbl" id="frameLbl"></span>
    <span class="lbl" id="popLbl" style="min-width:auto;flex:1"></span>
  </div>
</div>

<div id="boot"><div>Собираем планету…</div><div class="b"><i id="bootBar"></i></div></div>
<div class="pane" id="err"></div>
"""

_APP_JS = r"""
(function(){
'use strict';

var T = TERRA, DICT = T.dict, WLD = T.world, TEX = T.tex, HEAD = T.head;
var W = WLD.w, H = WLD.h;
var SEGW = 512, SEGH = 256;      // сегментов сферы
var OVS = 8;                     // подпикселей на клетку в слоях-накладках
var LGS = 4;                     // то же для карты ночных огней
var MAXCITY = 1600;              // потолок трёхмерных меток городов
var NLAB = 34;                   // сколько городов подписываем

var ROUTE_SEG = 20;              // отрезков в одной торговой дуге
var MAXROUTE = 1600;             // потолок числа дуг в кадре

var D = null;                    // распакованные кадры/летопись/хроника
var scene, camera, renderer, planet, ocean, atmo, stars, cities, labWrap;
var routeMesh, rtGeo, rtUni, rtPos, rtTan, rtCol, rtSide, rtWid, rtFade;
var texs = {}, hgt = null, poleN = 0, poleS = 0;
var ovTex, ovBuf, ovW, ovH, mdTex, mdBuf, lgTex, lgBuf, lgW, lgH;
var frame = 0, playing = false, lastStep = 0, speed = 1;
var selPid = -1, selCity = -1;
var kindOn = {}, minW = 0;
var tab = 'chron', pplList = [], selPerson = -1;

// ── мелкие утилиты ────────────────────────────────────────────────────────
function $(id){ return document.getElementById(id); }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function nfmt(v){
  v = Math.round(Number(v) || 0);
  var s = String(Math.abs(v)), o = '';
  while (s.length > 3){ o = ' ' + s.slice(-3) + o; s = s.slice(0, -3); }
  return (v < 0 ? '−' : '') + s + o;
}
function popfmt(v){
  v = Number(v) || 0;
  if (v >= 1e6) return (v/1e6).toFixed(v >= 1e7 ? 0 : 1).replace('.', ',') + ' млн';
  if (v >= 1e4) return Math.round(v/1e3) + ' тыс.';
  return nfmt(v);
}
function ruYear(y){
  y = Math.round(y);
  return y < 0 ? nfmt(-y) + ' до н. э.' : nfmt(y) + ' н. э.';
}
function clamp(v, a, b){ return v < a ? a : (v > b ? b : v); }
function smoothstep(a, b, x){ x = clamp((x - a) / (b - a), 0, 1); return x*x*(3 - 2*x); }
function b64bytes(s){
  var bin = atob(s), n = bin.length, a = new Uint8Array(n);
  for (var i = 0; i < n; i++) a[i] = bin.charCodeAt(i);
  return a;
}
function hexRgb(s){
  s = String(s || '#888888').replace('#','');
  if (s.length === 3) s = s[0]+s[0]+s[1]+s[1]+s[2]+s[2];
  var v = parseInt(s, 16);
  if (isNaN(v)) v = 0x888888;
  return [(v>>16)&255, (v>>8)&255, v&255];
}
function hashColor(id){
  // устойчивый приглушённый цвет по номеру — для народов вне сводки кадра
  var h = ((Math.imul(id | 0, 2654435761) >>> 0) % 360) / 60;
  var c = 0.30, x = c*(1 - Math.abs(h % 2 - 1)), m = 0.44;
  var r = 0, g = 0, b = 0;
  if (h < 1){ r = c; g = x; } else if (h < 2){ r = x; g = c; }
  else if (h < 3){ g = c; b = x; } else if (h < 4){ g = x; b = c; }
  else if (h < 5){ r = x; b = c; } else { r = c; b = x; }
  return [Math.round((r+m)*255), Math.round((g+m)*255), Math.round((b+m)*255)];
}
function fail(e){
  var el = $('err');
  el.style.display = 'block';
  el.innerHTML = '<b>Не удалось построить планету.</b><br>' + esc(e && e.message || e);
  $('boot').classList.add('gone');
  throw e;
}

// ── распаковка тяжёлых данных (gzip средствами самого браузера) ───────────
function ungzip(b64){
  var u8 = b64bytes(b64);
  if (typeof DecompressionStream === 'undefined'){
    return Promise.reject(new Error('браузер не умеет DecompressionStream'));
  }
  var st = new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'));
  var rd = st.getReader(), parts = [], total = 0;
  function pump(){
    return rd.read().then(function(r){
      if (r.done){
        var all = new Uint8Array(total), o = 0;
        for (var i = 0; i < parts.length; i++){ all.set(parts[i], o); o += parts[i].length; }
        return JSON.parse(new TextDecoder('utf-8').decode(all));
      }
      parts.push(r.value); total += r.value.length;
      return pump();
    });
  }
  return pump();
}

function loadImg(b64){
  return new Promise(function(res, rej){
    var im = new Image();
    im.onload = function(){ res(im); };
    im.onerror = function(){ rej(new Error('не читается вшитая текстура')); };
    im.src = 'data:image/png;base64,' + b64;
  });
}

// ── геометрия сферы ───────────────────────────────────────────────────────
function ll2v(lat, lon, r){
  var a = lat*Math.PI/180, b = lon*Math.PI/180, cl = Math.cos(a);
  return new THREE.Vector3(r*cl*Math.cos(b), r*Math.sin(a), -r*cl*Math.sin(b));
}
function v2ll(v){
  var r = v.length() || 1;
  return { lat: Math.asin(clamp(v.y/r, -1, 1))*180/Math.PI,
           lon: Math.atan2(-v.z, v.x)*180/Math.PI };
}
function cellLatLon(y, x){
  return { lat: 90 - (y + 0.5)*180/H, lon: -180 + (x + 0.5)*360/W };
}
function hash01(str){
  var h = 2166136261;
  for (var i = 0; i < str.length; i++){ h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 65536)/65536;
}
function cityOff(s){
  // одинаковое смещение для метки, подписи и огня — иначе они разъедутся
  if (!s._o) s._o = [hash01(s.n + '|' + s.y) - 0.5, hash01(s.n + '#' + s.x) - 0.5];
  return s._o;
}
function cityLatLon(s){
  var o = cityOff(s);
  return { lat: 90 - (s.y + 0.5 + o[1]*0.66)*180/H,
           lon: -180 + (s.x + 0.5 + o[0]*0.66)*360/W };
}
function sampleH(u, v){
  var hw = TEX.hw, hh = TEX.hh;
  var fx = u*hw - 0.5, fy = (1 - v)*hh - 0.5;
  var x0 = Math.floor(fx), y0 = Math.floor(fy);
  var tx = fx - x0, ty = fy - y0;
  var x1 = ((x0 + 1) % hw + hw) % hw;  x0 = (x0 % hw + hw) % hw;
  var y1 = clamp(y0 + 1, 0, hh - 1);   y0 = clamp(y0, 0, hh - 1);
  var a = hgt[y0*hw + x0], b = hgt[y0*hw + x1];
  var c = hgt[y1*hw + x0], d = hgt[y1*hw + x1];
  return (a*(1 - tx) + b*tx)*(1 - ty) + (c*(1 - tx) + d*tx)*ty;
}
function dispAt(u, v){
  var d = sampleH(u, v);
  // у полюсов все вершины сходятся в точку — там высота обязана быть общей,
  // иначе шапка «распускается» веером
  var t = smoothstep(0.955, 1.0, Math.abs(2*v - 1));
  if (t > 0) d = d*(1 - t) + (v > 0.5 ? poleN : poleS)*t;
  return d;
}
function dispAtLL(lat, lon){
  return dispAt(((lon + 180)/360 % 1 + 1) % 1, 1 - (90 - lat)/180);
}

// ── шейдеры ───────────────────────────────────────────────────────────────
var VERT = `
varying vec2 vUv;
varying vec3 vN;
varying vec3 vW;
void main(){
  vUv = uv;
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vW = wp.xyz;
  vN = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

var FRAG_PLANET = `
precision highp float;
varying vec2 vUv; varying vec3 vN; varying vec3 vW;
uniform sampler2D uColor, uNormal, uMask, uOv, uOv2, uLights;
uniform vec3 uSun, uCam, uRim;
uniform float uAmb, uSunI, uOvMix, uOv2Mix, uRivers, uNight, uAtm;
vec3 toLin(vec3 c){ return pow(max(c, 0.0), vec3(2.2)); }
vec3 toSrgb(vec3 c){ return pow(max(c, 0.0), vec3(0.4545)); }
void main(){
  vec3 N = normalize(vN);
  vec3 T = normalize(cross(N, vec3(0.0, 1.0, 0.0)) + vec3(1e-5, 0.0, 0.0));
  vec3 B = cross(N, T);
  vec3 nm = texture2D(uNormal, vUv).xyz * 2.0 - 1.0;
  vec3 n = normalize(nm.x*T + nm.y*B + nm.z*N);
  vec3 msk = texture2D(uMask, vUv).rgb;
  vec3 base = toLin(texture2D(uColor, vUv).rgb);

  // реки
  float riv = msk.r * msk.g * uRivers;
  base = mix(base, toLin(vec3(0.13, 0.36, 0.63)), clamp(riv, 0.0, 0.82));

  // слои поверх поверхности
  vec4 ov = texture2D(uOv, vUv);
  base = mix(base, toLin(ov.rgb), ov.a * uOvMix * msk.g);
  vec4 ov2 = texture2D(uOv2, vUv);
  base = mix(base, toLin(ov2.rgb), ov2.a * uOv2Mix * msk.g);

  vec3 V = normalize(uCam - vW);
  float shel = dot(N, uSun);
  float day = smoothstep(-0.10, 0.22, shel);
  float dif = max(dot(n, uSun), 0.0) * (0.35 + 0.65 * day);
  vec3 col = base * (uAmb * (0.30 + 0.70 * day) + dif * uSunI);

  // холодная подсветка неба сверху — объём в тенях
  col += base * 0.038 * clamp(dot(n, normalize(vec3(0.0, 1.0, 0.2))) * 0.5 + 0.5, 0.0, 1.0)
              * vec3(0.55, 0.72, 1.0);

  // блик на влажной суше почти не нужен, но шельф чуть блестит
  float spec = pow(max(dot(reflect(-uSun, n), V), 0.0), 40.0) * (1.0 - msk.g) * 0.18;
  col += vec3(0.6, 0.75, 0.9) * spec * day;

  // ночные огни городов
  vec3 lg = texture2D(uLights, vUv).rgb;
  col += lg * lg * (1.0 - day) * uNight * 1.9;
  // и слабое общее свечение ночной стороны, чтобы очертания читались
  col += base * vec3(0.62, 0.74, 1.0) * (1.0 - day) * 0.075;

  // атмосферная дымка по краю диска: слабая и пологая — основное свечение
  // даёт оболочка атмосферы, здесь нужен только мягкий переход к ней
  float rim = 1.0 - clamp(dot(N, V), 0.0, 1.0);
  col += uRim * pow(rim, 5.5) * (0.12 + 0.8 * day) * 0.40 * uAtm;

  col = col * 3.0 / (col + vec3(3.0));   // мягкий спад в ярких местах
  gl_FragColor = vec4(toSrgb(col), 1.0);
}`;

var FRAG_OCEAN = `
precision highp float;
varying vec2 vUv; varying vec3 vN; varying vec3 vW;
uniform sampler2D uMask, uOv, uOv2, uLights;
uniform vec3 uSun, uCam, uRim;
uniform float uAmb, uTime, uNight, uAtm;
vec3 toSrgb(vec3 c){ return pow(max(c, 0.0), vec3(0.4545)); }
void main(){
  vec3 N = normalize(vN);
  vec3 V = normalize(uCam - vW);
  float depth = texture2D(uMask, vUv).b;
  float land  = texture2D(uMask, vUv).g;

  // мелкая рябь — только чтобы блик не был зеркалом
  vec3 T = normalize(cross(N, vec3(0.0, 1.0, 0.0)) + vec3(1e-5, 0.0, 0.0));
  vec3 B = cross(N, T);
  float w1 = sin(vW.x * 57.0 + uTime * 0.7) * cos(vW.z * 49.0 - uTime * 0.55);
  float w2 = sin(vW.y * 41.0 - uTime * 0.4) * cos(vW.x * 33.0 + uTime * 0.3);
  vec3 n = normalize(N + (T * (w1 * 0.0022 + w2 * 0.0015) + B * (w2 * 0.0022 - w1 * 0.0014)));

  vec3 shallow = vec3(0.036, 0.152, 0.238);
  vec3 deep    = vec3(0.008, 0.038, 0.130);
  vec3 c = mix(shallow, deep, smoothstep(0.004, 0.115, depth));

  float shel = dot(N, uSun);
  float day = smoothstep(-0.10, 0.22, shel);
  float dif = max(dot(n, uSun), 0.0);
  vec3 Hv = normalize(uSun + V);
  float hn = max(dot(n, Hv), 0.0);
  float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 4.0);
  float grz = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 1.6);   // насколько косо смотрим
  float spec = (pow(hn, 1100.0) * 0.72 + pow(hn, 190.0) * 0.010) * (0.035 + 0.965 * grz);

  vec3 col = c * (uAmb * 0.9 + dif * 0.85);
  col += vec3(1.0, 0.94, 0.82) * spec * day;
  col += vec3(0.26, 0.44, 0.70) * fres * (0.18 + 0.82 * day) * 0.38;
  col += c * vec3(0.7, 0.8, 1.0) * (1.0 - day) * 0.16;

  // слои народов должны быть видны и над водой (морские владения редки,
  // но приморские клетки закрашиваются до самой воды)
  vec4 ov = texture2D(uOv, vUv);
  vec4 ov2 = texture2D(uOv2, vUv);

  float rim = 1.0 - clamp(dot(N, V), 0.0, 1.0);
  col += uRim * pow(rim, 5.0) * (0.12 + 0.85 * day) * 0.42 * uAtm;

  col = col * 3.0 / (col + vec3(3.0));
  float a = mix(0.62, 0.985, smoothstep(0.0, 0.05, depth));
  gl_FragColor = vec4(toSrgb(col), a * (1.0 - land * 0.15));
}`;

var FRAG_ATMO = `
precision highp float;
varying vec3 vN; varying vec3 vW;
uniform vec3 uSun, uCam, uRim;
uniform float uAtmH;
void main(){
  // Кайма не должна читаться кольцом с обрезанным краем. Считаем, как высоко
  // над поверхностью проходит луч зрения, и гасим свечение по экспоненте —
  // ровно так же редеет настоящий воздух. Никаких границ оболочки не видно:
  // на её краю яркость уже неотличима от нуля.
  vec3 V = normalize(vW - uCam);
  float t = -dot(uCam, V);
  vec3 P = uCam + V * t;              // ближайшая к центру точка луча
  float h = length(P) - 1.0;          // высота этой точки над поверхностью
  float a = exp(-max(h, 0.0) / uAtmH);
  vec3 Pn = normalize(P);
  float lit = smoothstep(-0.32, 0.46, dot(Pn, uSun));
  // на просвет, против солнца, воздух светится заметно сильнее
  float fwd = 0.80 + 0.90 * pow(max(dot(V, uSun), 0.0), 5.0);
  vec3 c = uRim * (0.11 + 1.30 * lit) * fwd;
  gl_FragColor = vec4(pow(max(c, 0.0), vec3(0.4545)),
                      clamp(a * (0.10 + 1.05 * lit), 0.0, 1.0));
}`;

// ── торговые пути: светящиеся ленты, всегда развёрнутые к камере ──────────
var VERT_ROUTE = `
attribute vec3 tang;
attribute vec3 col;
attribute float side;
attribute float wid;
attribute float fade;
uniform vec3 uCam;
uniform float uPx;
varying vec3 vCol; varying float vSide; varying float vFade;
void main(){
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vec3 vd = wp.xyz - uCam;
  float dist = length(vd);
  vd /= max(dist, 1e-6);
  vec3 off = cross(normalize(tang), vd);
  float l = length(off);
  off = l > 1e-5 ? off / l : vec3(0.0);
  wp.xyz += off * (side * wid * uPx * dist);   // толщина в пикселях, не в мире
  vCol = col; vSide = side; vFade = fade;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
var FRAG_ROUTE = `
precision mediump float;
uniform float uOp;
varying vec3 vCol; varying float vSide; varying float vFade;
void main(){
  float a = 1.0 - abs(vSide);
  float core = a * a * a;             // тонкая яркая нить
  float halo = a * a;                 // мягкое свечение вокруг неё
  float I = (core * 0.80 + halo * 0.34) * vFade * uOp;
  if (I <= 0.002) discard;
  gl_FragColor = vec4(vCol, I);
}`;

var VERT_STAR = `
attribute float sz;
attribute vec3 tint;
varying vec3 vT;
void main(){
  vT = tint;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = sz;
  gl_Position = projectionMatrix * mv;
}`;
var FRAG_STAR = `
precision mediump float;
varying vec3 vT;
void main(){
  float d = length(gl_PointCoord - vec2(0.5));
  float a = smoothstep(0.5, 0.06, d);
  if (a <= 0.01) discard;
  gl_FragColor = vec4(vT * a, a);
}`;

// ── сцена ─────────────────────────────────────────────────────────────────
var SUN = new THREE.Vector3(0.5974, 0.2419, -0.7646).normalize();
var sunFollow = true, sunLat = 14, sunLon = 40, sunLight = null;
var SUN_OFF = 40;   // насколько солнце «отстаёт» от камеры по долготе
var RIM = new THREE.Color(0.30, 0.52, 0.92);
var uni = {};

function makeTex(img, wrap){
  var t = new THREE.Texture(img);
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.ClampToEdgeWrapping;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = true;
  t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  t.needsUpdate = true;
  return t;
}

function buildScene(){
  var stage = $('stage');
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false,
                                       powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(stage.clientWidth, stage.clientHeight);
  renderer.setClearColor(0x03060a, 1);
  stage.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, stage.clientWidth/stage.clientHeight, 0.01, 400);

  texs.nat = makeTex(texs.natImg);
  texs.bio = makeTex(texs.bioImg);
  texs.hyp = makeTex(texs.hypImg);
  texs.nrm = makeTex(texs.nrmImg);
  texs.msk = makeTex(texs.mskImg);

  // накладки: владения народов и уклад хозяйства
  ovW = W*OVS; ovH = H*OVS;
  ovBuf = new Uint8Array(ovW*ovH*4);
  ovTex = new THREE.DataTexture(ovBuf, ovW, ovH, THREE.RGBAFormat);
  ovTex.minFilter = THREE.LinearFilter; ovTex.magFilter = THREE.LinearFilter;
  ovTex.wrapS = THREE.RepeatWrapping; ovTex.needsUpdate = true;
  mdBuf = new Uint8Array(ovW*ovH*4);
  mdTex = new THREE.DataTexture(mdBuf, ovW, ovH, THREE.RGBAFormat);
  mdTex.minFilter = THREE.LinearFilter; mdTex.magFilter = THREE.LinearFilter;
  mdTex.wrapS = THREE.RepeatWrapping; mdTex.needsUpdate = true;

  lgW = W*LGS; lgH = H*LGS;
  lgBuf = new Uint8Array(lgW*lgH*4);
  lgTex = new THREE.DataTexture(lgBuf, lgW, lgH, THREE.RGBAFormat);
  lgTex.minFilter = THREE.LinearFilter; lgTex.magFilter = THREE.LinearFilter;
  lgTex.wrapS = THREE.RepeatWrapping; lgTex.needsUpdate = true;

  uni = {
    uColor:  { value: texs.nat },
    uNormal: { value: texs.nrm },
    uMask:   { value: texs.msk },
    uOv:     { value: ovTex },
    uOv2:    { value: mdTex },
    uLights: { value: lgTex },
    uSun:    { value: SUN },
    uCam:    { value: new THREE.Vector3() },
    uRim:    { value: RIM },
    uAmb:    { value: 0.14 },
    uSunI:   { value: 1.22 },
    uOvMix:  { value: 1.0 },
    uOv2Mix: { value: 0.0 },
    uRivers: { value: 1.0 },
    uNight:  { value: 1.0 },
    uAtm:    { value: 1.0 },
    uAtmH:   { value: 0.036 },
    uTime:   { value: 0.0 }
  };

  // ── планета ──
  var geo = new THREE.SphereGeometry(1, SEGW, SEGH);
  var pos = geo.attributes.position, uvA = geo.attributes.uv;
  for (var i = 0; i < pos.count; i++){
    var s = 1 + dispAt(uvA.getX(i), uvA.getY(i));
    pos.setXYZ(i, pos.getX(i)*s, pos.getY(i)*s, pos.getZ(i)*s);
  }
  pos.needsUpdate = true;
  geo.computeBoundingSphere();
  planet = new THREE.Mesh(geo, new THREE.ShaderMaterial({
    uniforms: uni, vertexShader: VERT, fragmentShader: FRAG_PLANET }));
  planet.renderOrder = 0;
  scene.add(planet);

  // ── океан: отдельный материал на уровне моря ──
  ocean = new THREE.Mesh(new THREE.SphereGeometry(0.99965, 256, 128),
    new THREE.ShaderMaterial({ uniforms: uni, vertexShader: VERT,
      fragmentShader: FRAG_OCEAN, transparent: true, depthWrite: false,
      side: THREE.FrontSide }));
  ocean.renderOrder = 1;
  scene.add(ocean);

  // ── атмосферный ореол ──
  // оболочку берём с большим запасом: свечение гаснет само, задолго до её края
  atmo = new THREE.Mesh(new THREE.SphereGeometry(1.16, 128, 64),
    new THREE.ShaderMaterial({ uniforms: uni, vertexShader: VERT,
      fragmentShader: FRAG_ATMO, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, side: THREE.BackSide }));
  atmo.renderOrder = 3;
  scene.add(atmo);

  buildRouteMesh();

  // ── звёзды ──
  var NS = 3600, sp = new Float32Array(NS*3), ss = new Float32Array(NS),
      st = new Float32Array(NS*3), rnd = mulberry(20260727);
  for (var k = 0; k < NS; k++){
    var z = rnd()*2 - 1, ph = rnd()*Math.PI*2, rr = Math.sqrt(1 - z*z);
    sp[k*3] = Math.cos(ph)*rr*90; sp[k*3+1] = z*90; sp[k*3+2] = Math.sin(ph)*rr*90;
    var m = Math.pow(rnd(), 3.4);
    ss[k] = 0.9 + m*3.4;
    var warm = 0.72 + rnd()*0.28, cold = 0.75 + rnd()*0.25, b = 0.42 + m*0.58;
    st[k*3] = b*warm; st[k*3+1] = b*(0.86 + rnd()*0.14); st[k*3+2] = b*cold;
  }
  var sg = new THREE.BufferGeometry();
  sg.setAttribute('position', new THREE.BufferAttribute(sp, 3));
  sg.setAttribute('sz', new THREE.BufferAttribute(ss, 1));
  sg.setAttribute('tint', new THREE.BufferAttribute(st, 3));
  stars = new THREE.Points(sg, new THREE.ShaderMaterial({
    vertexShader: VERT_STAR, fragmentShader: FRAG_STAR, transparent: true,
    depthWrite: false, blending: THREE.AdditiveBlending }));
  stars.renderOrder = -1;
  scene.add(stars);

  // ── города: настоящие трёхмерные метки ──
  var cg = new THREE.ConeGeometry(1, 1, 7);
  cg.translate(0, 0.5, 0);
  var cm = new THREE.MeshLambertMaterial({ emissive: 0x11161d });
  cities = new THREE.InstancedMesh(cg, cm, MAXCITY);
  cities.instanceColor = new THREE.InstancedBufferAttribute(
    new Float32Array(MAXCITY*3).fill(1), 3);
  cities.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  cities.count = 0;
  cities.frustumCulled = false;
  cities.renderOrder = 2;
  scene.add(cities);

  sunLight = new THREE.DirectionalLight(0xfff2e0, 2.1);
  sunLight.position.copy(SUN).multiplyScalar(12);
  scene.add(sunLight);
  scene.add(new THREE.AmbientLight(0x8fa8c8, 2.6));

  labWrap = $('labels');
  updatePx();
  window.addEventListener('resize', onResize);
}

function mulberry(a){
  return function(){
    a |= 0; a = a + 0x6D2B79F5 | 0;
    var t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

function onResize(){
  var st = $('stage');
  camera.aspect = st.clientWidth / st.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(st.clientWidth, st.clientHeight);
  updatePx();
}
function updatePx(){
  // сколько мировых единиц приходится на пиксель экрана на единицу удаления —
  // с этим множителем лента торгового пути держит постоянную толщину
  if (!rtUni) return;
  var h = Math.max(renderer.domElement.clientHeight, 1);
  rtUni.uPx.value = 2 * Math.tan(camera.fov * Math.PI / 360) / h;
}

// ── торговые пути ─────────────────────────────────────────────────────────
function buildRouteMesh(){
  var nv = MAXROUTE * (ROUTE_SEG + 1) * 2;
  rtPos = new Float32Array(nv * 3);
  rtTan = new Float32Array(nv * 3);
  rtCol = new Float32Array(nv * 3);
  rtSide = new Float32Array(nv);
  rtWid = new Float32Array(nv);
  rtFade = new Float32Array(nv);
  var idx = new Uint32Array(MAXROUTE * ROUTE_SEG * 6);
  for (var r = 0; r < MAXROUTE; r++){
    var v0 = r * (ROUTE_SEG + 1) * 2, o = r * ROUTE_SEG * 6;
    for (var s = 0; s < ROUTE_SEG; s++){
      var a = v0 + s * 2;
      idx[o] = a; idx[o+1] = a+1; idx[o+2] = a+2;
      idx[o+3] = a+1; idx[o+4] = a+3; idx[o+5] = a+2;
      o += 6;
    }
  }
  rtGeo = new THREE.BufferGeometry();
  rtGeo.setAttribute('position', new THREE.BufferAttribute(rtPos, 3));
  rtGeo.setAttribute('tang', new THREE.BufferAttribute(rtTan, 3));
  rtGeo.setAttribute('col', new THREE.BufferAttribute(rtCol, 3));
  rtGeo.setAttribute('side', new THREE.BufferAttribute(rtSide, 1));
  rtGeo.setAttribute('wid', new THREE.BufferAttribute(rtWid, 1));
  rtGeo.setAttribute('fade', new THREE.BufferAttribute(rtFade, 1));
  rtGeo.setIndex(new THREE.BufferAttribute(idx, 1));
  rtGeo.setDrawRange(0, 0);
  rtGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1.4);
  rtUni = { uCam: uni.uCam, uPx: { value: 0.002 }, uOp: { value: 0.62 } };
  routeMesh = new THREE.Mesh(rtGeo, new THREE.ShaderMaterial({
    uniforms: rtUni, vertexShader: VERT_ROUTE, fragmentShader: FRAG_ROUTE,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide }));
  routeMesh.frustumCulled = false;
  routeMesh.renderOrder = 2;
  scene.add(routeMesh);
}

// цвета: суша — тёплое золото караванов, море — холодная бирюза
var RT_LAND = [1.00, 0.62, 0.20], RT_SEA = [0.28, 0.82, 1.00];
var _rp = [], _rn = 0;
function buildRoutes(f){
  var rt = f.rt || [], k = 0, ctr = frameCtr(f);
  for (var i = 0; i < rt.length && k < MAXROUTE; i++){
    var r = rt[i];
    var A = ctr[r[0]], B = ctr[r[1]];
    if (!A || !B) continue;
    var va = ll2v(A[0], A[1], 1), vb = ll2v(B[0], B[1], 1);
    var ang = Math.acos(clamp(va.dot(vb), -1, 1));
    if (ang < 1e-4) continue;
    var sa = Math.sin(ang);
    var str = r[2] / 100, sea = r[3] === 1;
    // высота дуги растёт с дальностью — близкие связи стелются по земле
    var alt = 0.012 + 0.135 * Math.pow(ang / Math.PI, 0.72);
    var rA = 1 + Math.max(dispAtLL(A[0], A[1]), 0) + 0.0025;
    var rB = 1 + Math.max(dispAtLL(B[0], B[1]), 0) + 0.0025;
    var col = sea ? RT_SEA : RT_LAND;
    var wid = 0.60 + 1.75 * str;
    // слабые связи нарочно почти не видны: иначе к концу прогона паутина
    // из тысячи нитей затягивает планету сплошной пеленой
    var bri = 0.16 + 0.86 * str * str;
    if (selPid >= 0) bri *= (r[0] === selPid || r[1] === selPid) ? 2.2 : 0.14;

    // точки дуги: сперва все, потом по ним считаем направление ленты
    for (var s = 0; s <= ROUTE_SEG; s++){
      var t = s / ROUTE_SEG;
      var w1 = Math.sin((1 - t) * ang) / sa, w2 = Math.sin(t * ang) / sa;
      var px = va.x * w1 + vb.x * w2, py = va.y * w1 + vb.y * w2,
          pz = va.z * w1 + vb.z * w2;
      var ln = Math.sqrt(px*px + py*py + pz*pz) || 1;
      var rr = (rA + (rB - rA) * t) + alt * Math.sin(Math.PI * t);
      var m = rr / ln;
      _rp[s*3] = px*m; _rp[s*3+1] = py*m; _rp[s*3+2] = pz*m;
    }
    var v0 = k * (ROUTE_SEG + 1) * 2;
    for (s = 0; s <= ROUTE_SEG; s++){
      var a2 = Math.max(s - 1, 0) * 3, b2 = Math.min(s + 1, ROUTE_SEG) * 3;
      var tx = _rp[b2] - _rp[a2], ty = _rp[b2+1] - _rp[a2+1], tz = _rp[b2+2] - _rp[a2+2];
      var tl = Math.sqrt(tx*tx + ty*ty + tz*tz) || 1;
      tx /= tl; ty /= tl; tz /= tl;
      var tt = s / ROUTE_SEG;
      var fd = bri * smoothstep(0, 0.11, tt) * smoothstep(0, 0.11, 1 - tt);
      for (var q = 0; q < 2; q++){
        var vi = v0 + s*2 + q, o3 = vi*3;
        rtPos[o3] = _rp[s*3]; rtPos[o3+1] = _rp[s*3+1]; rtPos[o3+2] = _rp[s*3+2];
        rtTan[o3] = tx; rtTan[o3+1] = ty; rtTan[o3+2] = tz;
        rtCol[o3] = col[0]; rtCol[o3+1] = col[1]; rtCol[o3+2] = col[2];
        rtSide[vi] = q ? 1 : -1;
        rtWid[vi] = wid;
        rtFade[vi] = fd;
      }
    }
    k++;
  }
  _rn = k;
  var nv = k * (ROUTE_SEG + 1) * 2;
  rtGeo.setDrawRange(0, k * ROUTE_SEG * 6);
  // шлём в видеопамять только занятую часть буферов, а не все 1600 дуг
  var at = rtGeo.attributes, names = ['position','tang','col','side','wid','fade'];
  for (i = 0; i < names.length; i++){
    var A2 = at[names[i]];
    A2.clearUpdateRanges();
    A2.addUpdateRange(0, nv * A2.itemSize);
    A2.needsUpdate = true;
  }
}

// ── управление камерой ────────────────────────────────────────────────────
var cam = { lat: 10, lon: 88, dist: 4.0 };
var camV = { lat: 0, lon: 0 };
var camT = null, orbit = false, dragging = false;

function applyCamera(){
  var p = ll2v(cam.lat, cam.lon, cam.dist);
  camera.position.copy(p);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  uni.uCam.value.copy(p);
}
function updateSun(){
  // Свет, намертво прибитый к миру, делает половину планеты недоступной для
  // разглядывания, поэтому по умолчанию солнце идёт следом за камерой, отставая
  // на SUN_OFF градусов: и рельеф читается, и терминатор с огнями виден у края.
  if (sunFollow){
    sunLon = cam.lon - SUN_OFF;
    sunLat = clamp(cam.lat*0.45 + 8, -34, 34);
  }
  SUN.copy(ll2v(sunLat, sunLon, 1));
  if (sunLight) sunLight.position.copy(SUN).multiplyScalar(12);
}
function flyTo(lat, lon, dist){
  var dl = ((lon - cam.lon + 540) % 360) - 180;
  camT = { lat: clamp(lat, -86, 86), lon: cam.lon + dl,
           dist: dist == null ? Math.min(cam.dist, 2.1) : dist, t: 0 };
  orbit = false; $('btnOrbit').classList.remove('on');
}
function stepCamera(dt){
  if (camT){
    var k = 1 - Math.pow(0.0016, dt);
    cam.lat += (camT.lat - cam.lat)*k;
    cam.lon += (camT.lon - cam.lon)*k;
    cam.dist += (camT.dist - cam.dist)*k;
    if (Math.abs(camT.lat - cam.lat) < 0.02 && Math.abs(camT.lon - cam.lon) < 0.02
        && Math.abs(camT.dist - cam.dist) < 0.002) camT = null;
  } else if (orbit){
    cam.lon -= 5.5*dt;
    cam.lat += (12 - cam.lat)*0.4*dt;
  } else if (!dragging){
    cam.lon += camV.lon*dt; cam.lat += camV.lat*dt;
    var damp = Math.pow(0.0045, dt);
    camV.lon *= damp; camV.lat *= damp;
    if (Math.abs(camV.lon) < 0.02) camV.lon = 0;
    if (Math.abs(camV.lat) < 0.02) camV.lat = 0;
  }
  cam.lat = clamp(cam.lat, -86, 86);
  var lon0 = cam.lon;
  cam.lon = ((cam.lon + 180) % 360 + 360) % 360 - 180;
  if (camT) camT.lon += cam.lon - lon0;
  cam.dist = clamp(cam.dist, 1.25, 8.0);
  updateSun();
  applyCamera();
}

function bindControls(){
  var el = renderer.domElement;
  var px = 0, py = 0, moved = 0, down = false, pid0 = null, pinch = 0;

  function rate(){ return (cam.dist - 1) * 0.30 + 0.10; }

  el.addEventListener('pointerdown', function(e){
    if (e.pointerType === 'touch' && e.isPrimary === false) return;
    down = true; dragging = true; moved = 0; px = e.clientX; py = e.clientY;
    pid0 = e.pointerId; camT = null;
    camV.lon = camV.lat = 0;
    el.setPointerCapture(e.pointerId);
    el.classList.add('drag');
  });
  el.addEventListener('pointermove', function(e){
    if (!down || e.pointerId !== pid0) return;
    var dx = e.clientX - px, dy = e.clientY - py;
    px = e.clientX; py = e.clientY;
    moved += Math.abs(dx) + Math.abs(dy);
    var k = rate()*0.42;
    cam.lon -= dx*k; cam.lat += dy*k;
    camV.lon = -dx*k*22; camV.lat = dy*k*22;
    cam.lat = clamp(cam.lat, -86, 86);
    if (orbit){ orbit = false; $('btnOrbit').classList.remove('on'); }
  });
  function up(e){
    if (!down) return;
    down = false; dragging = false;
    el.classList.remove('drag');
    if (moved < 6) pick(e.clientX, e.clientY);
  }
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', function(){ down = false; dragging = false;
    el.classList.remove('drag'); });
  el.addEventListener('wheel', function(e){
    e.preventDefault();
    camT = null;
    cam.dist *= Math.exp(clamp(e.deltaY, -160, 160) * 0.0016);
    cam.dist = clamp(cam.dist, 1.25, 8.0);
  }, { passive: false });

  // жесты: два пальца — масштаб
  var touches = {};
  el.addEventListener('touchstart', function(e){
    if (e.touches.length === 2){
      pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                         e.touches[0].clientY - e.touches[1].clientY);
      down = false; dragging = false;
    }
  }, { passive: true });
  el.addEventListener('touchmove', function(e){
    if (e.touches.length === 2 && pinch){
      e.preventDefault();
      var d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                         e.touches[0].clientY - e.touches[1].clientY);
      cam.dist = clamp(cam.dist * pinch/Math.max(d, 1), 1.25, 8.0);
      pinch = d;
    }
  }, { passive: false });
  el.addEventListener('touchend', function(e){ if (e.touches.length < 2) pinch = 0; },
                      { passive: true });

  window.addEventListener('keydown', function(e){
    if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.key === ' '){ e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowLeft'){ setFrame(frame - 1); }
    else if (e.key === 'ArrowRight'){ setFrame(frame + 1); }
  });
}

// ── выбор точки на планете ────────────────────────────────────────────────
function screenRay(sx, sy){
  var r = renderer.domElement.getBoundingClientRect();
  var nd = new THREE.Vector2(((sx - r.left)/r.width)*2 - 1,
                             -((sy - r.top)/r.height)*2 + 1);
  var rc = new THREE.Raycaster();
  rc.setFromCamera(nd, camera);
  return rc.ray;
}
function raySphere(ray){
  var o = ray.origin, d = ray.direction;
  var b = o.dot(d), c = o.dot(o) - 1.0;
  var disc = b*b - c;
  if (disc < 0) return null;
  var t = -b - Math.sqrt(disc);
  if (t <= 0) return null;
  return o.clone().addScaledVector(d, t);
}
function pick(sx, sy){
  // сперва города: они мелкие, попасть по ним лучом трудно
  var fr = D.frames[frame], best = -1, bd = 18*18;
  var r = renderer.domElement.getBoundingClientRect();
  var vv = new THREE.Vector3();
  for (var i = 0; i < fr.set.length; i++){
    var s = fr.set[i];
    if (s.p < 900) continue;
    var ll = cityLatLon(s);
    vv.copy(ll2v(ll.lat, ll.lon, 1 + Math.max(dispAtLL(ll.lat, ll.lon), 0) + 0.004));
    if (vv.dot(camera.position) <= 1.0) continue;
    vv.project(camera);
    var X = r.left + (vv.x*0.5 + 0.5)*r.width, Y = r.top + (-vv.y*0.5 + 0.5)*r.height;
    var dd = (X - sx)*(X - sx) + (Y - sy)*(Y - sy);
    if (dd < bd){ bd = dd; best = i; }
  }
  if (best >= 0){ showCity(fr.set[best]); return; }
  var p = raySphere(screenRay(sx, sy));
  if (!p) { hideInfo(); return; }
  var ll = v2ll(p);
  var y = clamp(Math.floor((90 - ll.lat)/180*H), 0, H - 1);
  var x = ((Math.floor((ll.lon + 180)/360*W) % W) + W) % W;
  showCell(y, x);
}

// ── данные кадра ──────────────────────────────────────────────────────────
var wBiome, wElev, wLand, wRiver, wSoil, wRug;
function prepWorld(){
  wBiome = new Int8Array(b64bytes(WLD.biome).buffer);
  var e = b64bytes(WLD.elev);
  wElev = new Int16Array(e.buffer, e.byteOffset, e.length >> 1);
  wLand = b64bytes(WLD.land);
  wRiver = b64bytes(WLD.river);
  wSoil = b64bytes(WLD.soil);
  wRug = b64bytes(WLD.rug);
}
function smoothOwners(cm){
  // Одиночные клетки чужого цвета — след расселения, а не история. Клетку,
  // у которой меньше двух соседей своего владельца, отдаём тому, кто явно
  // преобладает в окрестности 3×3. Народ с горсткой земель не трогаем вовсе,
  // иначе он попросту исчезнет с карты.
  var n = cm.length, i, mx = 0;
  for (i = 0; i < n; i++) if (cm[i] > mx) mx = cm[i];
  var cnt = new Int32Array(mx + 2), nb = new Int32Array(mx + 2);
  for (i = 0; i < n; i++) if (cm[i] >= 0) cnt[cm[i]]++;
  var out = new Int16Array(cm), seen = [];
  for (var y = 0; y < H; y++){
    for (var x = 0; x < W; x++){
      var idx = y*W + x, pid = cm[idx];
      if (pid < 0) continue;
      var same = 0, bestId = -1, bestN = 0;
      seen.length = 0;
      for (var dy = -1; dy <= 1; dy++){
        var yy = y + dy;
        if (yy < 0 || yy >= H) continue;
        for (var dx = -1; dx <= 1; dx++){
          if (!dx && !dy) continue;
          var q = cm[yy*W + ((x + dx + W) % W)];
          if (q < 0) continue;
          if (q === pid){ same++; continue; }
          if (nb[q] === 0) seen.push(q);
          nb[q]++;
          if (nb[q] > bestN){ bestN = nb[q]; bestId = q; }
        }
      }
      for (var s = 0; s < seen.length; s++) nb[seen[s]] = 0;
      if (same < 2 && bestN >= 3 && bestId >= 0 && cnt[pid] > 2){
        out[idx] = bestId; cnt[pid]--; cnt[bestId]++;
      }
    }
  }
  return out;
}

function frameCtr(f){
  // «народ → центр владений»: таблица плоская, разворачиваем при первом спросе
  if (!f.ctr){
    var c = f.ct || [], m = {};
    for (var i = 0; i + 2 < c.length; i += 3) m[c[i]] = [c[i+1]/100, c[i+2]/100];
    f.ctr = m;
  }
  return f.ctr;
}
function centerOf(f, pid){
  var v = frameCtr(f)[pid];
  return v ? { lat: v[0], lon: v[1] } : null;
}

function frameData(i){
  var f = D.frames[i];
  if (!f.cmA){
    var b = b64bytes(f.cm);
    f.cmA = new Int16Array(b.buffer, b.byteOffset, b.length >> 1);
    f.cm = null;
    f.smA = smoothOwners(f.cmA);
    f.byId = {};
    var gods = {}, ng = 0;
    for (var k = 0; k < f.pol.length; k++){
      var p = f.pol[k];
      p.rgb = hexRgb(p.c);
      p.mrgb = hexRgb(DICT.modeColors[p.m] || '#888888');
      f.byId[p.id] = p;
      for (var j = 0; j < (p.g || []).length; j++)
        if (!gods[p.g[j]]){ gods[p.g[j]] = 1; ng++; }
    }
    f.nGods = ng;
    // Сводка народов в снимке урезана по величине, а карта владений знает
    // всех. Мелким народам, которых в сводке нет, даём устойчивый цвет по
    // номеру — иначе их земли зияли бы на карте дырами.
    var mx = 0;
    for (j = 0; j < f.smA.length; j++) if (f.smA[j] > mx) mx = f.smA[j];
    f.pcol = new Uint8Array((mx + 1)*3);
    f.mcol = new Uint8Array((mx + 1)*3);
    for (var pid = 0; pid <= mx; pid++){
      var q = f.byId[pid];
      var cc = q ? q.rgb : hashColor(pid);
      var mm = q ? q.mrgb : [104, 118, 132];
      f.pcol[pid*3] = cc[0]; f.pcol[pid*3+1] = cc[1]; f.pcol[pid*3+2] = cc[2];
      f.mcol[pid*3] = mm[0]; f.mcol[pid*3+1] = mm[1]; f.mcol[pid*3+2] = mm[2];
    }
    f.pol.sort(function(a, b2){ return b2.p - a.p; });
    f.set.sort(function(a, b2){ return b2.p - a.p; });
  }
  return f;
}

// Владелец клетки для отрисовки: номер народа, −1 — ничья суша, −2 — вода.
// Вода помечена особо: вдоль берега черту не проводим.
function ownerCode(cm, y, x){
  if (y < 0) y = 0; else if (y >= H) y = H - 1;
  x = x < 0 ? x + W : (x >= W ? x - W : x);
  var i = y*W + x, q = cm[i];
  return q >= 0 ? q : (wLand[i] ? -1 : -2);
}

// Владелец подпикселя: взвешенное голосование четырёх ближайших клеток.
// Прямая межа остаётся на месте, а углы срезаются наискось — вместо
// лесенки из квадратов получается очертание, похожее на карту.
function voteAt(cm, gy, gx){
  var fx = (gx + 0.5)/OVS - 0.5, fy = (gy + 0.5)/OVS - 0.5;
  var cx = Math.floor(fx), cy = Math.floor(fy);
  var o00 = ownerCode(cm, cy, cx), o10 = ownerCode(cm, cy, cx + 1),
      o01 = ownerCode(cm, cy + 1, cx), o11 = ownerCode(cm, cy + 1, cx + 1);
  if (o00 === o10 && o00 === o01 && o00 === o11) return o00;
  var tu = fx - cx, tv = fy - cy;
  var w00 = (1 - tu)*(1 - tv), s10 = 0, s01 = 0, s11 = 0;
  var w10 = tu*(1 - tv), w01 = (1 - tu)*tv, w11 = tu*tv;
  if (o10 === o00) w00 += w10; else s10 = w10;
  if (o01 === o00) w00 += w01; else if (o01 === o10) s10 += w01; else s01 = w01;
  if (o11 === o00) w00 += w11; else if (o11 === o10) s10 += w11;
    else if (o11 === o01) s01 += w11; else s11 = w11;
  var best = o00, bw = w00;
  if (s10 > bw){ best = o10; bw = s10; }
  if (s01 > bw){ best = o01; bw = s01; }
  if (s11 > bw){ best = o11; }
  return best;
}

var winGrid = null;
function buildOverlays(f){
  ovBuf.fill(0); mdBuf.fill(0);
  var cm = f.smA, S = OVS, cy, cx, sy, sx, gy0, gx0;
  if (!winGrid || winGrid.length !== ovW*ovH) winGrid = new Int16Array(ovW*ovH);

  // ── проход первый: кому принадлежит каждый подпиксель ──
  for (cy = 0; cy < H; cy++){
    for (cx = 0; cx < W; cx++){
      var own = ownerCode(cm, cy, cx), near = own >= 0, uni = true;
      for (var dy = -1; dy <= 1; dy++){
        for (var dx = -1; dx <= 1; dx++){
          if (!dx && !dy) continue;
          var q = ownerCode(cm, cy + dy, cx + dx);
          if (q >= 0) near = true;
          if (q !== own) uni = false;
        }
      }
      if (!near) continue;          // открытая вода — там рисовать нечего
      gy0 = cy*S; gx0 = cx*S;
      if (uni){
        for (sy = 0; sy < S; sy++){
          var b = (gy0 + sy)*ovW + gx0;
          for (sx = 0; sx < S; sx++) winGrid[b + sx] = own;
        }
      } else {
        for (sy = 0; sy < S; sy++){
          var b2 = (gy0 + sy)*ovW + gx0;
          for (sx = 0; sx < S; sx++) winGrid[b2 + sx] = voteAt(cm, gy0 + sy, gx0 + sx);
        }
      }
    }
  }

  // ── проход второй: цвет и межи ──
  var pcol = f.pcol, mcol = f.mcol, ma = 88;
  for (cy = 0; cy < H; cy++){
    for (cx = 0; cx < W; cx++){
      if (cm[cy*W + cx] < 0) continue;
      gy0 = cy*S; gx0 = cx*S;
      for (sy = 0; sy < S; sy++){
        var gy = gy0 + sy, src = gy*ovW, dst = ((ovH - 1 - gy)*ovW)*4;
        for (sx = 0; sx < S; sx++){
          var gx = gx0 + sx, w = winGrid[src + gx];
          if (w < 0) continue;
          var l = winGrid[src + (gx ? gx - 1 : ovW - 1)];
          var r = winGrid[src + (gx + 1 < ovW ? gx + 1 : 0)];
          var edge = (l !== w && l !== -2) || (r !== w && r !== -2);
          if (!edge && gy > 0){ var u = winGrid[src - ovW + gx];
            edge = u !== w && u !== -2; }
          if (!edge && gy + 1 < ovH){ var d = winGrid[src + ovW + gx];
            edge = d !== w && d !== -2; }
          var o = dst + gx*4, c3 = w*3;
          var cr = pcol[c3], cg = pcol[c3+1], cb = pcol[c3+2];
          var mr = mcol[c3], mg = mcol[c3+1], mb = mcol[c3+2];
          var a = selPid < 0 ? 74 : (w === selPid ? 190 : 34);
          if (edge){
            var lt = w === selPid ? 1 : 0;
            ovBuf[o]   = cr*0.28 + 8 + lt*150;
            ovBuf[o+1] = cg*0.28 + 8 + lt*160;
            ovBuf[o+2] = cb*0.28 + 11 + lt*170;
            ovBuf[o+3] = Math.min(255, a + 96);
            mdBuf[o] = mr*0.32 + 20; mdBuf[o+1] = mg*0.32 + 20;
            mdBuf[o+2] = mb*0.32 + 24; mdBuf[o+3] = ma + 60;
          } else {
            ovBuf[o] = cr; ovBuf[o+1] = cg; ovBuf[o+2] = cb; ovBuf[o+3] = a;
            mdBuf[o] = mr; mdBuf[o+1] = mg; mdBuf[o+2] = mb; mdBuf[o+3] = ma;
          }
        }
      }
    }
  }
  ovTex.needsUpdate = true; mdTex.needsUpdate = true;
}

function buildLights(f){
  lgBuf.fill(0);
  var st = f.set;
  for (var i = 0; i < st.length; i++){
    var s = st[i], p = s.p;
    if (p < 260) continue;
    var mag = Math.log(Math.max(p, 10))/Math.LN10;        // 2.4 … 6
    var rad = Math.max(1.0, (mag - 2.9)*1.25);
    var amp = clamp((mag - 2.4)/3.6, 0.05, 0.80);
    var o = cityOff(s);
    var ccx = Math.round((s.x + 0.5 + o[0]*0.66)*LGS);
    var ccy = Math.round((s.y + 0.5 + o[1]*0.66)*LGS);
    var r0 = Math.ceil(rad*2.0);
    for (var dy = -r0; dy <= r0; dy++){
      var yy = ccy + dy;
      if (yy < 0 || yy >= lgH) continue;
      var base = (lgH - 1 - yy)*lgW;
      for (var dx = -r0; dx <= r0; dx++){
        var g = Math.exp(-(dx*dx + dy*dy)/(rad*rad)*1.35)*amp;
        if (g < 0.005) continue;
        var o = (base + ((ccx + dx) % lgW + lgW) % lgW)*4;
        lgBuf[o]   = Math.min(255, lgBuf[o]   + g*255);
        lgBuf[o+1] = Math.min(255, lgBuf[o+1] + g*186);
        lgBuf[o+2] = Math.min(255, lgBuf[o+2] + g*108);
        lgBuf[o+3] = 255;
      }
    }
  }
  lgTex.needsUpdate = true;
}

var cityAll = 0;
function cityLimit(n){
  // издали 900 меток превращаются в «щетину» — показываем только крупные
  var lim = cam.dist > 3.4 ? 110 : (cam.dist > 2.6 ? 220
          : (cam.dist > 1.9 ? 420 : (cam.dist > 1.5 ? 700 : n)));
  return Math.min(n, lim);
}
var _m4 = new THREE.Matrix4(), _q = new THREE.Quaternion(),
    _up = new THREE.Vector3(0, 1, 0), _sc = new THREE.Vector3(), _cl = new THREE.Color();
function buildCities(f){
  var st = f.set, n = Math.min(st.length, MAXCITY);
  for (var i = 0; i < n; i++){
    var s = st[i];
    var ll = cityLatLon(s);
    var d = Math.max(dispAtLL(ll.lat, ll.lon), 0);
    var mag = Math.log(Math.max(s.p, 10))/Math.LN10;
    var hgt2 = clamp(0.0024 + (mag - 2.0)*0.0032, 0.0022, 0.0148);
    var rad = clamp(0.0015 + (mag - 2.0)*0.0011, 0.0014, 0.0058);
    var p = ll2v(ll.lat, ll.lon, 1 + d + 0.0012);
    _q.setFromUnitVectors(_up, p.clone().normalize());
    _sc.set(rad, hgt2, rad);
    _m4.compose(p, _q, _sc);
    cities.setMatrixAt(i, _m4);
    var pol = f.byId[s.c];
    _cl.setStyle(pol ? pol.c : '#d8c48c');
    _cl.offsetHSL(0, 0.12, 0.16);
    cities.setColorAt(i, _cl);
  }
  cityAll = n;
  cities.count = cityLimit(n);
  cities.instanceMatrix.needsUpdate = true;
  if (cities.instanceColor) cities.instanceColor.needsUpdate = true;
}

// ── подписи городов ───────────────────────────────────────────────────────
var labEls = [], labData = [];
function prepLabels(){
  for (var i = 0; i < NLAB; i++){
    var e = document.createElement('div');
    e.className = 'lab';
    e.style.display = 'none';
    labWrap.appendChild(e);
    labEls.push(e);
  }
}
function setLabelSet(f){
  labData = f.set.slice(0, NLAB);
  for (var i = 0; i < NLAB; i++){
    var s = labData[i];
    labEls[i].innerHTML = s ? '<i></i>' + esc(s.n) : '';
    labEls[i].className = 'lab' + (s && i < 10 ? ' big' : '');
    if (!s) labEls[i].style.display = 'none';
  }
}
var _lv = new THREE.Vector3();
function updateLabels(){
  var on = $('ckLab').checked && $('ckCity').checked;
  var r = renderer.domElement;
  var wpx = r.clientWidth, hpx = r.clientHeight;
  // поля, занятые панелями: подпись туда лезть не должна
  var wide = wpx > 1100, mid = wpx > 820;
  var mL = mid ? (wide ? 272 : 238) : 8, mR = mid ? (wide ? 328 : 276) : 8;
  var mT = 58, mB = 100;
  var rects = [];
  for (var i = 0; i < NLAB; i++){
    var s = labData[i], el = labEls[i];
    if (!on || !s){ if (el.style.display !== 'none') el.style.display = 'none'; continue; }
    var ll = cityLatLon(s);
    _lv.copy(ll2v(ll.lat, ll.lon, 1 + Math.max(dispAtLL(ll.lat, ll.lon), 0) + 0.03));
    // обратная сторона шара — прячем
    if (_lv.dot(camera.position) <= 1.02){ el.style.display = 'none'; continue; }
    _lv.project(camera);
    if (_lv.z > 1){ el.style.display = 'none'; continue; }
    var X = (_lv.x*0.5 + 0.5)*wpx, Y = (-_lv.y*0.5 + 0.5)*hpx - 13;
    if (X < mL || X > wpx - mR || Y < mT || Y > hpx - mB){
      el.style.display = 'none'; continue;
    }
    var wEst = 12 + (s.n.length)*6.2, hEst = 15;
    var bad = false;
    for (var j = 0; j < rects.length; j++){
      var q = rects[j];
      if (Math.abs(X - q[0]) < (wEst + q[2])*0.5 && Math.abs(Y - q[1]) < (hEst + q[3])*0.55){
        bad = true; break;
      }
    }
    if (bad){ el.style.display = 'none'; continue; }
    rects.push([X, Y, wEst, hEst]);
    el.style.display = '';
    el.style.transform = 'translate(-50%,-50%) translate(' + X.toFixed(1) + 'px,'
                       + Y.toFixed(1) + 'px)';
  }
}

// ── боковые панели ────────────────────────────────────────────────────────
function renderPolities(f){
  var box = $('plist'), out = [];
  var top = f.pol.slice(0, 16);
  for (var i = 0; i < top.length; i++){
    var p = top[i];
    out.push('<div class="prow' + (p.id === selPid ? ' on' : '') + '" data-p="' + p.id + '">'
      + '<i class="sw" style="background:' + esc(p.c) + '"></i>'
      + '<span class="nm">' + esc(p.n) + '</span>'
      + '<span class="pp">' + popfmt(p.p) + '</span></div>');
  }
  if (!top.length) out.push('<div class="empty">народов ещё нет</div>');
  box.innerHTML = out.join('');
}

function polityCentroid(f, pid){
  var c = centerOf(f, pid);
  if (c) return c;
  var cm = f.smA, sx = 0, sy = 0, sz = 0, n = 0;
  for (var y = 0; y < H; y++){
    for (var x = 0; x < W; x++){
      if (cm[y*W + x] !== pid) continue;
      var ll = cellLatLon(y, x), v = ll2v(ll.lat, ll.lon, 1);
      sx += v.x; sy += v.y; sz += v.z; n++;
    }
  }
  if (!n) return null;
  var vv = new THREE.Vector3(sx/n, sy/n, sz/n);
  if (vv.lengthSq() < 1e-6) return null;
  return v2ll(vv.normalize());
}

function selectPolity(pid, fly){
  selPid = (selPid === pid ? -1 : pid);
  var f = frameData(frame);
  buildOverlays(f);
  buildRoutes(f);
  renderPolities(f);
  if (selPid >= 0){
    var p = f.byId[selPid];
    if (p) showPolityInfo(p, f);
    if (fly){
      var c = polityCentroid(f, selPid);
      if (c) flyTo(c.lat, c.lon, Math.min(cam.dist, 2.35));
    }
    if (!$('ckCult').checked){ $('ckCult').checked = true; syncLayers(); }
  } else hideInfo();
}

function num(v){ return String(v == null ? '—' : v).replace('.', ','); }
function godsHtml(p){
  if (!p.g || !p.g.length) return '';
  var o = ['<div class="kv"><span>боги</span><span></span></div><div class="gods">'];
  for (var i = 0; i < p.g.length; i++) o.push('<i>' + esc(p.g[i]) + '</i>');
  return o.join('') + '</div>';
}
function showPolityInfo(p, f){
  var cnt = 0;
  for (var i = 0; i < f.set.length; i++) if (f.set[i].c === p.id) cnt++;
  var nr = 0;
  for (i = 0; i < (f.rt || []).length; i++)
    if (f.rt[i][0] === p.id || f.rt[i][1] === p.id) nr++;
  var rows = [
    ['столица', p.cap ? p.cap : 'нет'],
    ['население', popfmt(p.p)],
    ['земли', nfmt(p.s) + ' клеток'],
    ['уклад', DICT.modeRu[p.m] || p.m],
    ['устройство', DICT.formRu[p.f] || p.f],
    ['знания', nfmt(p.t) + ' технологий'],
    ['эпоха', p.e],
    ['сложность', num(p.cx)],
    ['неравенство', num(p.iq)],
    ['сплочённость', num(p.ch)],
    ['законность власти', num(p.lg)],
    ['излишек', num(p.su)],
    ['городов', nfmt(cnt)],
    ['торговых связей', nfmt(nr)]
  ];
  info('Народ', '<div class="big" style="color:' + esc(p.c) + '">' + esc(p.n) + '</div>'
       + kvRows(rows) + godsHtml(p));
}

function kvRows(rows){
  var o = [];
  for (var i = 0; i < rows.length; i++)
    o.push('<div class="kv"><span>' + esc(rows[i][0]) + '</span><span>'
           + esc(rows[i][1]) + '</span></div>');
  return o.join('');
}
function info(title, html){
  $('infoTtl').textContent = title;
  $('infoBody').innerHTML = html;
  $('info').style.display = '';
}
function hideInfo(){ $('info').style.display = 'none'; }

function showCell(y, x){
  var f = frameData(frame), i = y*W + x;
  var pid = f.smA[i], p = pid >= 0 ? f.byId[pid] : null;
  var ll = cellLatLon(y, x);
  var city = null;
  for (var k = 0; k < f.set.length; k++)
    if (f.set[k].y === y && f.set[k].x === x){ city = f.set[k]; break; }
  var rows = [
    ['широта', ll.lat.toFixed(1).replace('.', ',') + '°'],
    ['долгота', ll.lon.toFixed(1).replace('.', ',') + '°'],
    ['биом', DICT.biomeNames[String(wBiome[i])] || '—'],
    ['высота', nfmt(wElev[i]) + ' м'],
    ['почва', (wSoil[i]/255).toFixed(2).replace('.', ',')],
    ['изрезанность', (wRug[i]/255).toFixed(2).replace('.', ',')],
    ['реки', (wRiver[i]/255).toFixed(2).replace('.', ',')]
  ];
  if (p){
    rows.push(['народ', p.n]);
    rows.push(['столица', p.cap ? p.cap : 'нет']);
    rows.push(['население народа', popfmt(p.p)]);
    rows.push(['уклад', DICT.modeRu[p.m] || p.m]);
    rows.push(['устройство', DICT.formRu[p.f] || p.f]);
    rows.push(['знания', nfmt(p.t) + ' технологий']);
    rows.push(['эпоха', p.e]);
    rows.push(['законность власти', num(p.lg)]);
    rows.push(['излишек', num(p.su)]);
  } else if (pid >= 0){
    // народ есть на карте, но в сводку кадра не попал — она урезана по величине
    rows.push(['народ', 'малый народ № ' + pid]);
  } else {
    rows.push(['народ', wLand[i] ? 'ничья земля' : 'море']);
  }
  if (city){
    rows.push(['город', city.n + ' (' + popfmt(city.p) + ')']);
    rows.push(['ранг', city.t]);
  }
  info('Клетка ' + y + ', ' + x, kvRows(rows) + (p ? godsHtml(p) : ''));
}

function showCity(s){
  var f = frameData(frame), p = f.byId[s.c];
  var ll = cellLatLon(s.y, s.x), i = s.y*W + s.x;
  var rows = [
    ['жителей', popfmt(s.p)],
    ['ранг', s.t || '—'],
    ['народ', p ? p.n : '—'],
    ['уклад', p ? (DICT.modeRu[p.m] || p.m) : '—'],
    ['укрепления', String(s.w).replace('.', ',')],
    ['памятников', nfmt(s.m)],
    ['биом', DICT.biomeNames[String(wBiome[i])] || '—'],
    ['высота', nfmt(wElev[i]) + ' м'],
    ['координаты', ll.lat.toFixed(1).replace('.', ',') + '°, '
                 + ll.lon.toFixed(1).replace('.', ',') + '°']
  ];
  info('Город', '<div class="big">' + esc(s.n) + '</div>' + kvRows(rows));
  flyTo(ll.lat, ll.lon, Math.min(cam.dist, 1.75));
}

// ── летопись ──────────────────────────────────────────────────────────────
function evRange(i){
  var y = D.frames[i].year;
  var y0 = i > 0 ? D.frames[i-1].year : y - 1;
  var ev = D.events, lo = 0, hi = ev.length;
  while (lo < hi){ var m = (lo + hi) >> 1; if (ev[m].yr <= y0) lo = m + 1; else hi = m; }
  var a = lo;
  lo = a; hi = ev.length;
  while (lo < hi){ var m2 = (lo + hi) >> 1; if (ev[m2].yr <= y) lo = m2 + 1; else hi = m2; }
  return [a, lo];
}
function renderEvents(){
  var r = evRange(frame), ev = D.events, list = [];
  for (var i = r[0]; i < r[1]; i++) if (kindOn[ev[i].k] !== false) list.push(ev[i]);
  list.sort(function(a, b){ return b.w - a.w; });
  if (list.length > 250) list = list.slice(0, 250);
  if (!list.length){
    $('evs').innerHTML = '<div class="empty">в этих годах записей нет</div>';
    return;
  }
  var out = [];
  for (var j = 0; j < list.length; j++){
    var e = list[j], col = DICT.kindColors[e.k] || '#8b9bab';
    var geo = (e.cy != null && e.cx != null);
    out.push('<div class="ev' + (geo ? ' geo' : '') + (e.k === 'collapse' ? ' alarm' : '')
      + '" data-i="' + j
      + '" data-y="' + (geo ? e.cy : -1) + '" data-x="' + (geo ? e.cx : -1)
      + '" style="border-left-color:' + col + '">'
      + '<div class="h"><span class="y">' + ruYear(e.yr) + '</span>'
      + '<span class="k" style="color:' + col + '">'
      + esc(DICT.kindRu[e.k] || e.k) + '</span>'
      + (geo ? '<span class="g">к точке →</span>' : '') + '</div>'
      + '<div class="t">' + esc(e.t) + '</div></div>');
  }
  $('evs').innerHTML = out.join('');
}
function renderKinds(){
  var out = [];
  for (var i = 0; i < DICT.kindOrder.length; i++){
    var k = DICT.kindOrder[i];
    if (kindOn[k] === undefined) kindOn[k] = true;
    out.push('<b data-k="' + k + '" style="background:'
      + (DICT.kindColors[k] || '#888') + ';color:#0b1218;border-color:'
      + (DICT.kindColors[k] || '#888') + '">' + esc(DICT.kindRu[k] || k) + '</b>');
  }
  $('kinds').innerHTML = out.join('');
  $('kinds').addEventListener('click', function(e){
    var b = e.target.closest('b'); if (!b) return;
    var k = b.dataset.k;
    kindOn[k] = !kindOn[k];
    if (kindOn[k]){
      b.style.background = DICT.kindColors[k] || '#888'; b.style.color = '#0b1218';
    } else {
      b.style.background = '#1a2732'; b.style.color = '#5f7183';
    }
    renderEvents();
  });
}

// ── люди этого времени ────────────────────────────────────────────────────
function peopleWindow(){
  // «в районе текущего года» — это промежуток от прошлого кадра до нынешнего:
  // кадры идут через век, и жизнь человека почти всегда короче
  var y1 = D.frames[frame].year;
  var y0 = frame > 0 ? D.frames[frame - 1].year : y1 - 100;
  var span = Math.max(70, y1 - y0);
  return [y1 - span, y1 + 8];
}
function personDeed(p, y){
  if (!p.ds || !p.ds.length) return null;
  var best = p.ds[0], bd = 1e18;
  for (var i = 0; i < p.ds.length; i++){
    var d = Math.abs(p.ds[i][0] - y);
    if (d < bd){ bd = d; best = p.ds[i]; }
  }
  return best;
}
function renderPeople(){
  var box = $('peopleList'), P = D.people || [];
  var w = peopleWindow(), lo = w[0], hi = w[1], y = D.frames[frame].year;
  pplList = [];
  for (var i = 0; i < P.length; i++){
    var p = P[i];
    if (p.b > hi) break;              // список отсортирован по году рождения
    if (p.d >= lo) pplList.push(p);
  }
  pplList.sort(function(a, b){
    return (b.pr + b.pw + 0.35*b.ds.length) - (a.pr + a.pw + 0.35*a.ds.length);
  });
  if (pplList.length > 140) pplList = pplList.slice(0, 140);
  $('peopleN').textContent = pplList.length ? '· ' + pplList.length : '';
  if (!pplList.length){
    box.innerHTML = '<div class="empty">' + (P.length
      ? 'об этих годах книга людей молчит'
      : 'книги людей в этом прогоне нет') + '</div>';
    return;
  }
  var out = [], byId = frameData(frame).byId;
  for (i = 0; i < pplList.length; i++){
    var q = pplList[i], dd = personDeed(q, y);
    var col = (q.p >= 0 && byId[q.p]) ? byId[q.p].c : '#3a4a58';
    out.push('<div class="pers' + (i === selPerson ? ' on' : '') + '" data-i="' + i
      + '" style="border-left-color:' + esc(col) + '">'
      + '<div class="h"><span class="nm">' + esc(q.n) + '</span>'
      + '<span class="rl">' + esc(DICT.roleRu[q.r] || q.r) + '</span>'
      + '<span class="yy">' + shortYear(q.b) + '…' + shortYear(q.d) + '</span></div>'
      + '<div class="sub">' + esc(q.pn) + ' · ' + esc(q.e)
      + ' · ' + (q.sx === 1 ? 'муж.' : 'жен.') + '</div>'
      + (dd ? '<div class="dd">' + esc(dd[2]) + '</div>' : '')
      + '</div>');
  }
  box.innerHTML = out.join('');
}
function shortYear(y){
  y = Math.round(y);
  return y < 0 ? '−' + nfmt(-y) : String(y);
}
function bar(label, v){
  v = clamp(Number(v) || 0, 0, 1);
  return '<div class="b"><span style="min-width:96px">' + esc(label) + '</span>'
    + '<u><i style="width:' + (v*100).toFixed(0) + '%"></i></u>'
    + '<span style="min-width:26px;text-align:right">' + num(v.toFixed(2)) + '</span></div>';
}
function showPerson(i){
  var p = pplList[i];
  if (!p) return;
  selPerson = i;
  renderPeople();
  var rows = [
    ['народ', p.pn],
    ['роль', DICT.roleRu[p.r] || p.r],
    ['годы жизни', ruYear(p.b) + ' — ' + ruYear(p.d)],
    ['прожил', nfmt(p.a) + ' лет'],
    ['пол', p.sx === 1 ? 'мужской' : 'женский'],
    ['эпоха', p.e]
  ];
  var h = ['<div class="big">' + esc(p.n) + '</div>', kvRows(rows), '<div class="bars">',
           bar('признание', p.pr), bar('власть', p.pw), bar('достаток', p.wl), '</div>'];
  if (p.tr && p.tr.length){
    h.push('<div class="kv"><span>черты</span><span></span></div><div class="bars">');
    for (var k = 0; k < p.tr.length; k++)
      h.push(bar(DICT.traitRu[p.tr[k][0]] || p.tr[k][0], p.tr[k][1]));
    h.push('</div>');
  }
  if (p.bl && p.bl.length){
    h.push('<div class="kv"><span>верит</span><span></span></div>');
    for (k = 0; k < p.bl.length; k++)
      h.push('<div class="kv"><span></span><span>'
        + esc(DICT.beliefRu[p.bl[k][0]] || p.bl[k][0]) + '</span></div>');
  }
  if (p.ds && p.ds.length){
    h.push('<div class="kv"><span>деяния</span><span></span></div>');
    for (k = 0; k < p.ds.length; k++)
      h.push('<div class="kv" style="display:block"><span style="color:var(--ink3)">'
        + ruYear(p.ds[k][0]) + '</span><div style="margin-top:1px">'
        + esc(p.ds[k][2]) + '</div></div>');
  }
  info('Человек', h.join(''));

  // перелёт к землям народа: сперва ищем его в нынешнем кадре, а если народа
  // уже нет — берём кадр, ближайший к годам его жизни
  var f = frameData(frame), c = p.p >= 0 ? centerOf(f, p.p) : null;
  if (c){
    flyTo(c.lat, c.lon, Math.min(cam.dist, 2.3));
    if (f.byId[p.p] && selPid !== p.p) selectPolity(p.p, false);
    return;
  }
  var best = null, bd = 1e18;
  for (var j = 0; j < D.frames.length; j++){
    var fr = D.frames[j], q = p.p >= 0 ? frameCtr(fr)[p.p] : null;
    if (!q) continue;
    var d = Math.abs(fr.year - p.d);
    if (d < bd){ bd = d; best = q; }
  }
  if (best) flyTo(best[0], best[1], Math.min(cam.dist, 2.3));
}
function setTab(t){
  tab = t;
  var bs = $('tabs').children;
  for (var i = 0; i < bs.length; i++) bs[i].classList.toggle('on', bs[i].dataset.t === t);
  $('paneChron').classList.toggle('on', t === 'chron');
  $('panePeople').classList.toggle('on', t === 'people');
}

// ── кадры и время ─────────────────────────────────────────────────────────
function setFrame(i){
  i = clamp(i, 0, D.frames.length - 1);
  frame = i;
  var f = frameData(i);
  buildOverlays(f);
  buildLights(f);
  buildCities(f);
  buildRoutes(f);
  setLabelSet(f);
  renderPolities(f);
  renderEvents();
  selPerson = -1;
  renderPeople();
  $('slider').value = String(i);
  $('year').textContent = ruYear(f.year);
  var tl = nearestTl(f.year);
  $('era').textContent = tl ? tl.e : '';
  updateStat(f);
  $('frameLbl').innerHTML = 'кадр <b>' + (i + 1) + '</b> из <b>' + D.frames.length + '</b>'
    + (HEAD.thinned ? ' <span title="кадры прорежены">(из ' + HEAD.frames_all + ')</span>' : '');
  $('popLbl').innerHTML = 'народов <b>' + nfmt(f.pol.length) + '</b> · городов <b>'
    + nfmt(f.set.length) + '</b>' + (tl ? ' · людей <b>' + popfmt(tl.pop) + '</b>' : '')
    + ' · торговых путей <b>' + nfmt((f.rt || []).length) + '</b>';
  if (selPid >= 0 && f.byId[selPid]) showPolityInfo(f.byId[selPid], f);
}
function updateStat(f){
  $('stat').innerHTML = 'зерно <b>' + esc(String(HEAD.seed)) + '</b> · народов всего <b>'
    + nfmt(HEAD.n_polities_ever) + '</b> · войн <b>' + nfmt(HEAD.wars)
    + '</b> · открытий <b>' + nfmt(HEAD.discoveries)
    + '</b> · обрушений <b>' + nfmt(HEAD.collapses)
    + '</b> · богов в мире <b>' + nfmt(f.nGods || 0) + '</b>'
    + (HEAD.thinned ? ' · кадры прорежены до <b>' + HEAD.frames + '</b>' : '')
    + (HEAD.events_trunc ? ' · летопись урезана' : '');
}
function nearestTl(y){
  var t = D.timeline, best = null, bd = 1e18;
  for (var i = 0; i < t.length; i++){
    var d = Math.abs(t[i].yr - y);
    if (d < bd){ bd = d; best = t[i]; }
  }
  return best;
}
function togglePlay(){
  playing = !playing;
  $('btnPlay').textContent = playing ? '❚❚' : '▶';
  $('btnPlay').classList.toggle('on', playing);
  lastStep = performance.now();
}

// ── слои ──────────────────────────────────────────────────────────────────
function syncLayers(){
  uni.uOvMix.value = $('ckCult').checked ? 1 : 0;
  uni.uOv2Mix.value = $('ckMode').checked ? 1 : 0;
  uni.uRivers.value = $('ckRiver').checked ? 1 : 0;
  uni.uNight.value = $('ckNight').checked ? 1 : 0;
  uni.uAmb.value = $('ckNight').checked ? 0.14 : 0.50;
  uni.uAtm.value = $('ckAtm').checked ? 1 : 0;
  cities.visible = $('ckCity').checked;
  routeMesh.visible = $('ckRoute').checked;
  sunFollow = $('ckSun').checked;
  atmo.visible = $('ckAtm').checked;
  stars.visible = $('ckAtm').checked;
  renderLegend();
}
function renderLegend(){
  var el = $('legend'), out = [];
  if ($('ckMode').checked){
    out.push('<div style="color:var(--ink3);font-size:10.5px;letter-spacing:.08em;'
      + 'text-transform:uppercase;margin-bottom:3px">Уклад хозяйства</div>');
    for (var k in DICT.modeColors)
      out.push('<span class="li"><i style="background:' + DICT.modeColors[k] + '"></i>'
        + esc(DICT.modeRu[k] || k) + '</span>');
  } else if (base === 'bio'){
    out.push('<div style="color:var(--ink3);font-size:10.5px;letter-spacing:.08em;'
      + 'text-transform:uppercase;margin-bottom:3px">Биомы</div>');
    for (var b in DICT.biomeNames)
      out.push('<span class="li"><i style="background:' + DICT.biomeColors[b] + '"></i>'
        + esc(DICT.biomeNames[b]) + '</span>');
  } else if (base === 'hyp'){
    out.push('<div style="color:var(--ink3);font-size:10.5px;letter-spacing:.08em;'
      + 'text-transform:uppercase;margin-bottom:3px">Высота, м</div>');
    var st = [['#0c2248','−4000'], ['#1e5488','−1000'], ['#3a6e44','0'],
              ['#96a658','500'], ['#c4b068','1000'], ['#b08a60','1800'],
              ['#927670','2800'], ['#f5f8fb','4000+']];
    for (var i = 0; i < st.length; i++)
      out.push('<span class="li"><i style="background:' + st[i][0] + '"></i>'
        + st[i][1] + '</span>');
  }
  if ($('ckRoute').checked){
    if (out.length) out.push('<div style="height:5px"></div>');
    out.push('<div style="color:var(--ink3);font-size:10.5px;letter-spacing:.08em;'
      + 'text-transform:uppercase;margin-bottom:3px">Торговые пути</div>');
    out.push('<span class="li"><i style="background:#ffb352"></i>сухопутные</span>');
    out.push('<span class="li"><i style="background:#5cdcff"></i>морские</span>');
    out.push('<span class="li" style="color:var(--ink3)">толщина и яркость — сила связи</span>');
  }
  el.innerHTML = out.join('');
  el.classList.toggle('show', out.length > 0);
}

var base = 'nat';
function setBase(b){
  base = b;
  uni.uColor.value = texs[b] || texs.nat;
  var bs = $('basemap').children;
  for (var i = 0; i < bs.length; i++) bs[i].classList.toggle('on', bs[i].dataset.b === b);
  renderLegend();
}

// ── цикл отрисовки ────────────────────────────────────────────────────────
var prevT = 0;
function loop(now){
  requestAnimationFrame(loop);
  var dt = Math.min((now - prevT)/1000 || 0.016, 0.1);
  prevT = now;
  uni.uTime.value = now*0.001;
  stepCamera(dt);
  if (cityAll){
    var cl = cityLimit(cityAll);
    if (cl !== cities.count) cities.count = cl;
  }
  if (playing && now - lastStep > 720/speed){
    lastStep = now;
    setFrame(frame + 1 >= D.frames.length ? 0 : frame + 1);
  }
  renderer.render(scene, camera);
  updateLabels();
}

// ── запуск ────────────────────────────────────────────────────────────────
function bindUI(){
  $('runid').textContent = HEAD.run_id;
  $('slider').max = String(D.frames.length - 1);
  $('slider').addEventListener('input', function(){
    playing = false; $('btnPlay').textContent = '▶'; $('btnPlay').classList.remove('on');
    setFrame(parseInt(this.value, 10));
  });
  $('btnPrev').onclick = function(){ setFrame(frame - 1); };
  $('btnNext').onclick = function(){ setFrame(frame + 1); };
  $('btnPlay').onclick = togglePlay;
  $('speed').onchange = function(){ speed = parseFloat(this.value); };
  $('btnOrbit').onclick = function(){
    orbit = !orbit; camT = null; this.classList.toggle('on', orbit);
  };
  $('btnReset').onclick = function(){
    orbit = false; $('btnOrbit').classList.remove('on');
    selPid = -1; selPerson = -1;
    var f = frameData(frame);
    buildOverlays(f); buildRoutes(f); renderPolities(f); renderPeople();
    hideInfo();
    camT = { lat: 10, lon: 88, dist: 4.0 };
  };
  var cks = ['ckCult','ckMode','ckRoute','ckRiver','ckCity','ckLab','ckNight','ckAtm','ckSun'];
  for (var i = 0; i < cks.length; i++) $(cks[i]).addEventListener('change', syncLayers);
  $('tabs').addEventListener('click', function(e){
    var b = e.target.closest('button'); if (b) setTab(b.dataset.t);
  });
  $('peopleList').addEventListener('click', function(e){
    var r = e.target.closest('.pers'); if (!r) return;
    showPerson(parseInt(r.dataset.i, 10));
  });
  $('basemap').addEventListener('click', function(e){
    var b = e.target.closest('button'); if (b) setBase(b.dataset.b);
  });
  $('plist').addEventListener('click', function(e){
    var r = e.target.closest('.prow'); if (!r) return;
    selectPolity(parseInt(r.dataset.p, 10), true);
  });
  $('evs').addEventListener('click', function(e){
    var r = e.target.closest('.ev'); if (!r) return;
    var y = parseInt(r.dataset.y, 10), x = parseInt(r.dataset.x, 10);
    if (y < 0 || isNaN(y)) return;
    var ll = cellLatLon(y, x);
    flyTo(ll.lat, ll.lon, Math.min(cam.dist, 1.9));
    showCell(y, x);
  });
  renderKinds();
}

function boot(){
  var bar = $('bootBar');
  bar.style.width = '12%';
  prepWorld();
  Promise.all([
    ungzip(TERRA_GZ),
    loadImg(TEX.nat), loadImg(TEX.bio), loadImg(TEX.hyp),
    loadImg(TEX.nrm), loadImg(TEX.msk), loadImg(TEX.hgt)
  ]).then(function(res){
    bar.style.width = '55%';
    D = res[0];
    texs.natImg = res[1]; texs.bioImg = res[2]; texs.hypImg = res[3];
    texs.nrmImg = res[4]; texs.mskImg = res[5];

    // высоты для смещения вершин: 16 бит, упакованные в каналы R и G
    var cv = document.createElement('canvas');
    cv.width = TEX.hw; cv.height = TEX.hh;
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(res[6], 0, 0);
    var dat = cx.getImageData(0, 0, TEX.hw, TEX.hh).data;
    var n = TEX.hw*TEX.hh, k = (TEX.hi - TEX.lo)/65535;
    hgt = new Float32Array(n);
    for (var i = 0; i < n; i++) hgt[i] = TEX.lo + ((dat[i*4] << 8) | dat[i*4 + 1])*k;
    for (var j = 0; j < TEX.hw; j++){ poleN += hgt[j]; poleS += hgt[(TEX.hh - 1)*TEX.hw + j]; }
    poleN /= TEX.hw; poleS /= TEX.hw;

    bar.style.width = '78%';
    buildScene();
    prepLabels();
    bindControls();
    bindUI();
    setBase('nat');
    syncLayers();
    setFrame(D.frames.length - 1);
    applyCamera();
    bar.style.width = '100%';
    $('boot').classList.add('gone');

    // небольшой внешний доступ: удобно для проверок и для встраивания
    window.terraGlobe = {
      flyTo: flyTo,
      jumpTo: function(lat, lon, dist){
        camT = null; orbit = false; $('btnOrbit').classList.remove('on');
        cam.lat = clamp(lat, -86, 86); cam.lon = lon;
        if (dist != null) cam.dist = clamp(dist, 1.25, 8.0);
        camV.lon = camV.lat = 0;
        updateSun(); applyCamera();
      },
      setFrame: setFrame,
      frameCount: function(){ return D.frames.length; },
      frameIndex: function(){ return frame; },
      camera: cam,
      setLayer: function(id, on){ var e = $(id); if (e){ e.checked = !!on; syncLayers(); } },
      setBase: setBase,
      selectPolity: selectPolity,
      nightSide: function(dist){
        sunFollow = false; $('ckSun').checked = false;
        var s = v2ll(SUN.clone().negate());
        flyTo(s.lat, s.lon, dist || 3.6);
      },
      sun: function(follow, lat, lon){
        sunFollow = !!follow; $('ckSun').checked = !!follow;
        if (lat != null) sunLat = lat;
        if (lon != null) sunLon = lon;
        updateSun();
      },
      biggestCity: function(){ return frameData(frame).set[0]; },
      showCity: showCity,
      setTab: setTab,
      routeCount: function(){ return _rn; },
      routesOf: function(){ return (frameData(frame).rt || []).length; },
      peopleCount: function(){ return pplList.length; },
      peopleAll: function(){ return (D.people || []).length; },
      showPerson: showPerson,
      godCount: function(){ return frameData(frame).nGods || 0; },
      kinds: function(){ return DICT.kindOrder; },
      orbit: function(on){ orbit = !!on; camT = null;
                           $('btnOrbit').classList.toggle('on', orbit); },
      three: THREE, scene: function(){ return scene; },
      dispAt: function(lat, lon){ return dispAtLL(lat, lon); },
      stats: function(){
        var a = planet.geometry.attributes.position, mn = 9, mx = 0;
        for (var i = 0; i < a.count; i++){
          var r = Math.sqrt(a.getX(i)*a.getX(i) + a.getY(i)*a.getY(i) + a.getZ(i)*a.getZ(i));
          if (r < mn) mn = r; if (r > mx) mx = r;
        }
        return { rmin: mn, rmax: mx, lo: TEX.lo, hi: TEX.hi,
                 tris: SEGW*SEGH*2, cities: cities.count, frames: D.frames.length };
      }
    };
    requestAnimationFrame(loop);
  }).catch(fail);
}

if (document.readyState === 'loading')
  document.addEventListener('DOMContentLoaded', boot);
else boot();

})();
"""


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Трёхмерный обозреватель мира TERRA")
    ap.add_argument("run_dir", help="каталог прогона, например runs/terra-1")
    ap.add_argument("-o", "--out", default=None, help="путь к итоговому HTML")
    a = ap.parse_args()
    build_globe(a.run_dir, a.out)
