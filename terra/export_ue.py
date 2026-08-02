"""
TERRA — экспорт сцен прогона в пакет для Unreal Engine 5.

Берёт те же данные сцены, что и play.html (общая точка — terra.play.build_scene_data),
и раскладывает их в папку export_ue/<сцена>/:

    terrain.obj / terrain.mtl / terrain_color.png   — ландшафт статичным мешем (см, Z вверх)
    terrain_far.obj / water.obj                     — кольцо до горизонта и плоскость воды
    masks/heightmap.png (PNG16) + grass/dirt/rock/sand.png (PNG8, 1024²)
    buildings.json                                  — манифест застройки + дороги
    people.json                                     — жители: спавны, маршруты, карточки
    meta.json                                       — сцена, народ, широта, диапазоны высот
    proxy_meshes/*.obj                              — простые примитивы-блокауты по типам

Рядом со сценами кладутся общий import_terra.py (скрипт для встроенного Python UE)
и README_UE.md — оба берутся из terra/ue/.

    python3 -m terra.export_ue runs/terra-1 [--scene capital|bronze|neolithic|all] [-o export_ue]

Система координат UE: X_ue = x сцены, Y_ue = z сцены, Z_ue = высота; всё в сантиметрах
(1 м сцены = 100 см UE). yaw_deg — поворот вокруг Z: локальный +X (фасад) смотрит
в мировом направлении (cos yaw, sin yaw). Север сцены = −Y_ue.

После записи каждой сцены гоняются самопроверки (парсинг OBJ, «здания на рельефе»,
PNG16, спавны людей); при провале код выхода ненулевой.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from terra.play import build_scene_data

# ────────────────────────────────────────────────────────────────────────────
#  Константы рельефа — ДЕРЖАТЬ В СИНХРОНЕ с terra/_play_js.py (groundH и др.)
# ────────────────────────────────────────────────────────────────────────────
WATER_Y = -1.1            # уровень воды, м
BASE_H = 2.3              # высота ровной городской площадки, м
TSIZE = 1200.0            # сторона основного ландшафта, м
FLATR = {"capital": 250.0, "bronze": 235.0, "neolithic": 180.0}
GRID_N = 257              # сетка terrain.obj (вершин по стороне)
FAR_SIZE = 6000.0         # сторона дальнего кольца, м
FAR_N = 81                # сетка terrain_far.obj
HMAP_PX = 1009            # heightmap PNG16 (UE-дружелюбный размер Landscape)
COLOR_PX = 2048           # запечённая цветовая текстура ландшафта
MASK_PX = 1024            # весовые маски материалов
M2CM = 100.0              # метры сцены -> сантиметры UE

# палитры биомов — копия PALS из _play_js.py (нужные для запекания цвета)
PALS = {
    6: {"grass": "#93a05a", "grass2": "#7e8f4e", "dry": "#c0ac6e", "rock": "#8f8878",
        "sand": "#d2c298", "path": "#b39c70", "field": "#8a7a46", "water": "#2f6f86",
        "deep": "#1d4a63"},
    12: {"grass": "#5b8d4c", "grass2": "#4d7d43", "dry": "#8fa060", "rock": "#7d7a68",
         "sand": "#c6b489", "path": "#9c8c64", "field": "#6d7a3d", "water": "#2e7a6e",
         "deep": "#174f4a"},
    8: {"grass": "#b1a06e", "grass2": "#a3915f", "dry": "#c9b681", "rock": "#8b8378",
        "sand": "#d8c69c", "path": "#bda878", "field": "#93824c", "water": "#2e6b80",
        "deep": "#1a4a63"},
    5: {"grass": "#a2ac62", "grass2": "#8f9c55", "dry": "#c4b273", "rock": "#8d8578",
        "sand": "#d0c096", "path": "#b3a071", "field": "#8a7a46", "water": "#2f6f86",
        "deep": "#1d4a63"},
    10: {"grass": "#659552", "grass2": "#568547", "dry": "#94a45e", "rock": "#84806e",
         "sand": "#c9b78c", "path": "#a08e62", "field": "#75823f", "water": "#2a7268",
         "deep": "#144a45"},
    9: {"grass": "#b0a45e", "grass2": "#9d9350", "dry": "#c9b675", "rock": "#8b8378",
        "sand": "#d6c396", "path": "#bda878", "field": "#93824c", "water": "#2f6f86",
        "deep": "#1d4a63"},
    4: {"grass": "#6f9448", "grass2": "#5d833f", "dry": "#a0a05c", "rock": "#837d6e",
        "sand": "#c9ba8e", "path": "#a3906a", "field": "#77743c", "water": "#2f6f86",
        "deep": "#1d4a63"},
}

# эпохи — копия ERACOL из _play_js.py (цвета материалов прокси-мешей)
ERACOL = {
    "capital": {"wallS": "#98907e", "house": "#cfc0a2", "roof": "#9d5f43",
                "wood": "#6b5138", "stoneT": "#d0c6ac", "col": "#cfc6b0",
                "pave": "#a89a80", "door": "#4a3826"},
    "bronze": {"wallS": "#b5986e", "house": "#c7ab80", "roof": "#c3a778",
               "wood": "#5d4832", "stoneT": "#d8cba8", "col": "#c9ad82",
               "pave": "#b09a72", "door": "#443521"},
    "neolithic": {"wallS": "#8a7052", "house": "#b5987a", "roof": "#c2ab74",
                  "wood": "#6a5340", "stoneT": "#a89878", "col": "#b5987a",
                  "pave": "#b3a078", "door": "#3f3020"},
}

CLOTH = {"wool": ["#9c4f3a", "#a8583f", "#7c5a41", "#8a7351", "#5d6e7e", "#996e35",
                  "#7a4a52"],
         "hide": ["#8a6a4e", "#7a5c42", "#93765a", "#6d5540", "#84644a"]}


def _hex2rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)], dtype=np.float64) / 255.0


# ────────────────────────────────────────────────────────────────────────────
#  Высотное поле — точный порт groundH из _play_js.py (numpy, векторно)
# ────────────────────────────────────────────────────────────────────────────
def _sstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _h2(x, y, seed):
    n = np.sin(x * 127.1 + y * 311.7 + seed * 13.7) * 43758.5453
    return n - np.floor(n)


def _vnoise(x, y, seed):
    ix, iy = np.floor(x), np.floor(y)
    fx, fy = x - ix, y - iy
    a = _h2(ix, iy, seed)
    b = _h2(ix + 1, iy, seed)
    c = _h2(ix, iy + 1, seed)
    d = _h2(ix + 1, iy + 1, seed)
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def _fbm(x, y, octaves, seed):
    x = np.asarray(x, dtype=np.float64).copy()
    y = np.asarray(y, dtype=np.float64).copy()
    s = np.zeros_like(x)
    amp, norm = 0.5, 0.0
    for _ in range(octaves):
        s += amp * _vnoise(x, y, seed)
        norm += amp
        x *= 2.03
        y *= 1.97
        amp *= 0.5
    return s / norm


class HeightField:
    """Аналитический рельеф сцены (метры). Один в один с groundH из JS игры."""

    def __init__(self, sc: dict):
        self.kind = sc["id"]
        self.rugg = float(sc["rugg"])
        self.seed = int(sc["seed"]) * 17 + 3          # NZSEED в JS
        self.river = sc.get("river")                  # [px,pz,ang,halfw] | None
        self.sea = sc.get("sea")                      # [ang,dist] | None
        self.flatr = FLATR[self.kind]

    def river_dist(self, x, z):
        if not self.river:
            return np.full_like(np.asarray(x, dtype=np.float64), 1e9)
        px, pz, a, _hw = self.river
        return np.abs(-(x - px) * math.sin(a) + (z - pz) * math.cos(a))

    def sea_s(self, x, z):
        if not self.sea:
            return np.full_like(np.asarray(x, dtype=np.float64), -1e9)
        a, dist = self.sea
        return x * math.cos(a) + z * math.sin(a) - dist

    def h(self, x, z):
        """Высота рельефа, м. x/z — числа или numpy-массивы (метры сцены)."""
        x = np.asarray(x, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64)
        amp = 7.0 + self.rugg * 30.0
        h = (_fbm(x * 0.0042, z * 0.0042, 5, self.seed) * amp
             + _fbm(x * 0.021, z * 0.021, 3, self.seed) * amp * 0.14)
        dc = np.hypot(x, z)
        h = h + _sstep((dc - 330.0) / 280.0) * self.rugg * 26.0
        flat = BASE_H + _fbm(x * 0.05, z * 0.05, 2, self.seed) * 0.55
        t = _sstep((dc - self.flatr) / 170.0)
        h = flat + (h + 2.4 - flat) * t
        if self.river:
            hw = self.river[3]
            d = self.river_dist(x, z)
            carve = 1.0 - _sstep((d - hw * 0.4) / (hw * 1.25))
            target = h + (-3.8 - hw * 0.03 - h) * carve
            h = np.where(carve > 0, np.minimum(h, target), h)
        if self.sea:
            s = self.sea_s(x, z)
            target = 2.0 + (-11.0 - 2.0) * _sstep((s + 42.0) / 100.0)
            h = np.where(s > -60.0, np.minimum(h, target), h)
        return h

    def h_far(self, x, z):
        """Рельеф дальнего кольца — порт «юбки» из buildTerrain (JS)."""
        x = np.asarray(x, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64)
        cx = np.clip(x, -596.0, 596.0)
        cz = np.clip(z, -596.0, 596.0)
        hh = self.h(cx, cz) - 0.5
        far = np.maximum(np.abs(x), np.abs(z)) - 596.0
        bump = (_fbm(x * 0.002, z * 0.002, 3, self.seed) * self.rugg * 30.0
                * _sstep(far / 700.0))
        hh = np.where((far > 0) & (hh > WATER_Y + 0.5), hh + bump, hh)
        return hh


def _grid_axes(n: int, size: float):
    c = np.linspace(-size / 2.0, size / 2.0, n)
    return c


def make_height_grid(hf: HeightField, n: int = GRID_N, size: float = TSIZE):
    """Сетка высот H[i,j]: i — вдоль z сцены (Y UE), j — вдоль x (X UE)."""
    ax = _grid_axes(n, size)
    X, Z = np.meshgrid(ax, ax)          # строка i: z = ax[i]; столбец j: x = ax[j]
    return ax, hf.h(X, Z)


def grid_height_at(H: np.ndarray, ax: np.ndarray, x, z):
    """Высота с сетки в точке (x,z) — интерполяция ТОЙ ЖЕ триангуляцией,
    что в terrain.obj (диагональ A(i,j)—C(i+1,j+1)). Вход/выход в метрах."""
    n = len(ax)
    step = ax[1] - ax[0]
    u = (np.asarray(x, dtype=np.float64) - ax[0]) / step
    v = (np.asarray(z, dtype=np.float64) - ax[0]) / step
    u = np.clip(u, 0.0, n - 1.001)
    v = np.clip(v, 0.0, n - 1.001)
    j = np.floor(u).astype(int)
    i = np.floor(v).astype(int)
    fu, fv = u - j, v - i
    ha = H[i, j]
    hb = H[i, j + 1]
    hc = H[i + 1, j + 1]
    hd = H[i + 1, j]
    upper = fu >= fv                     # треугольник A-B-C, иначе A-C-D
    h1 = ha * (1 - fu) + hb * (fu - fv) + hc * fv
    h2 = ha * (1 - fv) + hd * (fv - fu) + hc * fu
    return np.where(upper, h1, h2)


# ────────────────────────────────────────────────────────────────────────────
#  Запись OBJ
# ────────────────────────────────────────────────────────────────────────────
def write_grid_obj(path: Path, ax: np.ndarray, H: np.ndarray, name: str,
                   mtl: str | None = None, matname: str = "terrain",
                   with_uv: bool = True):
    """Регулярная сетка -> OBJ (см, Z вверх). Нормали из градиента высот."""
    n = len(ax)
    step = float(ax[1] - ax[0])
    dz_di, dz_dj = np.gradient(H, step, step)   # d(h)/d(z сцены), d(h)/d(x)
    nx = -dz_dj
    ny = -dz_di
    nz = np.ones_like(H)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / norm, ny / norm, nz / norm

    lines = [f"# TERRA export: {name} (см, Z вверх; X=x сцены, Y=z сцены)",
             f"o {name}"]
    if mtl:
        lines.append(f"mtllib {mtl}")
    half = (n - 1) * step / 2.0
    for i in range(n):
        zi = ax[i]
        row = H[i]
        for j in range(n):
            lines.append(f"v {ax[j] * M2CM:.1f} {zi * M2CM:.1f} {row[j] * M2CM:.1f}")
    # UV пишем ВСЕГДА, даже если текстуры нет. Импортёр Interchange в UE 5.8
    # предполагает, что у грани есть индекс UV, и без него роняет проверку
    # UVs.IsValidIndex(VertexData.UVIndex) (проверено на Mac, UE 5.8.1).
    for i in range(n):
        v = 1.0 - (ax[i] + half) / (2 * half)
        for j in range(n):
            u = (ax[j] + half) / (2 * half)
            lines.append(f"vt {u:.5f} {v:.5f}")
    for i in range(n):
        for j in range(n):
            lines.append(f"vn {nx[i, j]:.4f} {ny[i, j]:.4f} {nz[i, j]:.4f}")
    lines.append(f"usemtl {matname}")
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j + 1
            b = i * n + j + 2
            c = (i + 1) * n + j + 2
            d = (i + 1) * n + j + 1
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
            lines.append(f"f {a}/{a}/{a} {c}/{c}/{c} {d}/{d}/{d}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_water_obj(path: Path, size_m: float, water_col: str):
    """Плоскость воды на уровне WATER_Y (см, Z вверх)."""
    n = 9
    ax = _grid_axes(n, size_m)
    y = WATER_Y * M2CM
    lines = ["# TERRA export: water", "o water", "mtllib water.mtl"]
    for i in range(n):
        for j in range(n):
            lines.append(f"v {ax[j] * M2CM:.1f} {ax[i] * M2CM:.1f} {y:.1f}")
    # UV обязательны для импортёра UE (см. комментарий в write_terrain_obj)
    for i in range(n):
        for j in range(n):
            lines.append(f"vt {j / (n - 1):.4f} {1.0 - i / (n - 1):.4f}")
    lines.append("vn 0 0 1")
    lines.append("usemtl water")
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j + 1
            b = i * n + j + 2
            c = (i + 1) * n + j + 2
            d = (i + 1) * n + j + 1
            lines.append(f"f {a}/{a}/1 {b}/{b}/1 {c}/{c}/1")
            lines.append(f"f {a}/{a}/1 {c}/{c}/1 {d}/{d}/1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r, g, b = _hex2rgb(water_col)
    path.with_suffix(".mtl").write_text(
        f"newmtl water\nKd {r:.3f} {g:.3f} {b:.3f}\nd 0.82\nNs 220\n", encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
#  Прокси-меши: конструктор примитивов с грубыми UV и слотами материалов
# ────────────────────────────────────────────────────────────────────────────
class MeshBuilder:
    """Простые примитивы (см, Z вверх, низ на z=0). Слоты walls/roof/trim."""

    def __init__(self):
        self.v: list[tuple] = []
        self.vt: list[tuple] = []
        self.vn: list[tuple] = []
        self.faces: dict[str, list] = {}      # slot -> [(vi..., ti..., ni...), ...]

    def _vi(self, p):
        self.v.append(p)
        return len(self.v)

    def _ti(self, t):
        self.vt.append(t)
        return len(self.vt)

    def _ni(self, nrm):
        self.vn.append(nrm)
        return len(self.vn)

    def quad(self, slot, p1, p2, p3, p4):
        """Четырёхугольник двумя треугольниками; нормаль по порядку обхода."""
        a = np.array(p2) - np.array(p1)
        b = np.array(p3) - np.array(p1)
        nrm = np.cross(a, b)
        ln = np.linalg.norm(nrm)
        nrm = tuple((nrm / ln) if ln > 0 else (0, 0, 1))
        ni = self._ni(nrm)
        ts = [self._ti(t) for t in ((0, 0), (1, 0), (1, 1), (0, 1))]
        vs = [self._vi(p) for p in (p1, p2, p3, p4)]
        f = self.faces.setdefault(slot, [])
        f.append(((vs[0], vs[1], vs[2]), (ts[0], ts[1], ts[2]), ni))
        f.append(((vs[0], vs[2], vs[3]), (ts[0], ts[2], ts[3]), ni))

    def tri(self, slot, p1, p2, p3):
        a = np.array(p2) - np.array(p1)
        b = np.array(p3) - np.array(p1)
        nrm = np.cross(a, b)
        ln = np.linalg.norm(nrm)
        nrm = tuple((nrm / ln) if ln > 0 else (0, 0, 1))
        ni = self._ni(nrm)
        ts = [self._ti(t) for t in ((0, 0), (1, 0), (0.5, 1))]
        vs = [self._vi(p) for p in (p1, p2, p3)]
        self.faces.setdefault(slot, []).append(((vs[0], vs[1], vs[2]),
                                                (ts[0], ts[1], ts[2]), ni))

    def box(self, slot, cx, cy, z0, sx, sy, h, yaw=0.0):
        """Коробка: центр (cx,cy), низ z0, размеры sx×sy×h, поворот yaw (рад)."""
        c, s = math.cos(yaw), math.sin(yaw)

        def W(lx, ly, lz):
            return (cx + lx * c - ly * s, cy + lx * s + ly * c, z0 + lz)
        hx, hy = sx / 2.0, sy / 2.0
        p = {"---": W(-hx, -hy, 0), "+--": W(hx, -hy, 0),
             "++-": W(hx, hy, 0), "-+-": W(-hx, hy, 0),
             "--+": W(-hx, -hy, h), "+-+": W(hx, -hy, h),
             "+++": W(hx, hy, h), "-++": W(-hx, hy, h)}
        self.quad(slot, p["--+"], p["+-+"], p["+++"], p["-++"])          # верх
        self.quad(slot, p["-+-"], p["++-"], p["+--"], p["---"])          # низ
        self.quad(slot, p["---"], p["+--"], p["+-+"], p["--+"])          # y-
        self.quad(slot, p["++-"], p["-+-"], p["-++"], p["+++"])          # y+
        self.quad(slot, p["+--"], p["++-"], p["+++"], p["+-+"])          # x+
        self.quad(slot, p["-+-"], p["---"], p["--+"], p["-++"])          # x-

    def cyl(self, slot, cx, cy, z0, r_bot, r_top, h, seg=12, cap=True):
        """Цилиндр/конус вдоль Z: низ z0, радиусы низа/верха."""
        bot, top = [], []
        for k in range(seg):
            a = k / seg * 2 * math.pi
            bot.append((cx + math.cos(a) * r_bot, cy + math.sin(a) * r_bot, z0))
            top.append((cx + math.cos(a) * r_top, cy + math.sin(a) * r_top, z0 + h))
        for k in range(seg):
            k2 = (k + 1) % seg
            if r_top > 1e-6:
                self.quad(slot, bot[k], bot[k2], top[k2], top[k])
            else:
                self.tri(slot, bot[k], bot[k2],
                         (cx, cy, z0 + h))
        if cap and r_top > 1e-6:
            for k in range(1, seg - 1):
                self.tri(slot, top[0], top[k], top[k + 1])
        if cap:
            for k in range(1, seg - 1):
                self.tri(slot, bot[0], bot[k + 1], bot[k])

    def prism(self, slot, cx, cy, z0, sx, sy, h, yaw=0.0):
        """Двускатная призма: конёк вдоль локального X на высоте z0+h."""
        c, s = math.cos(yaw), math.sin(yaw)

        def W(lx, ly, lz):
            return (cx + lx * c - ly * s, cy + lx * s + ly * c, z0 + lz)
        hx, hy = sx / 2.0, sy / 2.0
        a1, a2 = W(-hx, -hy, 0), W(hx, -hy, 0)
        b1, b2 = W(-hx, hy, 0), W(hx, hy, 0)
        r1, r2 = W(-hx, 0, h), W(hx, 0, h)
        self.quad(slot, a1, a2, r2, r1)                  # скат y-
        self.quad(slot, r1, r2, b2, b1)                  # скат y+
        self.tri(slot, a2, b2, r2)                       # фронтон x+
        self.tri(slot, b1, a1, r1)                       # фронтон x-
        self.quad(slot, b1, b2, a2, a1)                  # низ

    def bbox(self):
        v = np.array(self.v)
        return v.min(axis=0), v.max(axis=0)

    def write(self, path: Path, name: str, mtl_colors: dict[str, str]):
        lines = [f"# TERRA proxy: {name} (см, Z вверх, низ на z=0, фасад +X)",
                 f"o {name}", f"mtllib {path.stem}.mtl"]
        for p in self.v:
            lines.append(f"v {p[0]:.2f} {p[1]:.2f} {p[2]:.2f}")
        for t in self.vt:
            lines.append(f"vt {t[0]:.3f} {t[1]:.3f}")
        for nrm in self.vn:
            lines.append(f"vn {nrm[0]:.4f} {nrm[1]:.4f} {nrm[2]:.4f}")
        for slot, faces in self.faces.items():
            lines.append(f"usemtl {slot}")
            for (vs, ts, ni) in faces:
                lines.append("f " + " ".join(f"{v}/{t}/{ni}" for v, t in zip(vs, ts)))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        mtl = []
        for slot, hexcol in mtl_colors.items():
            r, g, b = _hex2rgb(hexcol)
            mtl.append(f"newmtl {slot}\nKd {r:.3f} {g:.3f} {b:.3f}\nNs 8\n")
        path.with_suffix(".mtl").write_text("\n".join(mtl), encoding="utf-8")


def _mul(hexcol: str, f: float) -> str:
    r, g, b = (np.clip(_hex2rgb(hexcol) * f, 0, 1) * 255).astype(int)
    return f"#{r:02x}{g:02x}{b:02x}"


def build_proxy(kind: str, era: str) -> tuple[MeshBuilder, dict]:
    """Прокси-меш типа kind: габарит-«единица» 100×100×100 см (низ z=0).
    Масштаб в UE: size_cm/100 по осям. Свесы крыш могут выходить за 100."""
    E = ERACOL[era]
    m = MeshBuilder()
    S = 100.0
    cols = {"walls": E["house"], "roof": E["roof"], "trim": E["wood"]}
    if kind == "hut_round":
        m.cyl("walls", 0, 0, 0, S * 0.5, S * 0.5, S * 0.457)
        m.cyl("roof", 0, 0, S * 0.457, S * 0.637, 0.0, S * 0.543, seg=12)
        m.box("trim", S * 0.48, 0, 0, S * 0.06, S * 0.3, S * 0.4)      # дверь
        cols = {"walls": E["house"], "roof": ERACOL["neolithic"]["roof"],
                "trim": E["door"]}
    elif kind == "house_flat":
        m.box("walls", 0, 0, 0, S, S, S * 0.88)
        m.box("roof", 0, 0, S * 0.88, S * 1.04, S * 1.04, S * 0.04)
        for sgn in (-1, 1):
            m.box("walls", sgn * S * 0.5, 0, S * 0.9, S * 0.05, S * 1.04, S * 0.1)
            m.box("walls", 0, sgn * S * 0.5, S * 0.9, S * 1.04, S * 0.05, S * 0.1)
        m.box("trim", S * 0.5, 0, 0, S * 0.04, S * 0.26, S * 0.55)     # дверь
    elif kind == "house_gable":
        m.box("walls", 0, 0, 0, S, S, S * 0.62)
        m.prism("roof", 0, 0, S * 0.62, S * 1.18, S * 1.18, S * 0.38)
        m.box("trim", S * 0.5, 0, 0, S * 0.04, S * 0.24, S * 0.5)      # дверь
    elif kind == "temple":
        # подий + целла + шестиколонный портик; фасад — локальный +Y
        m.box("walls", 0, 0, 0, S, S * 0.98, S * 0.1)
        m.box("walls", 0, 0, S * 0.1, S * 0.9, S * 0.9, S * 0.06)
        m.box("walls", 0, 0, S * 0.16, S * 0.62, S * 0.55, S * 0.5)
        for i in range(6):
            x = (i / 5.0 - 0.5) * S * 0.76
            m.cyl("trim", x, S * 0.36, S * 0.16, S * 0.035, S * 0.035, S * 0.5, seg=8)
        m.box("walls", 0, 0, S * 0.66, S * 0.86, S * 0.84, S * 0.08)
        m.prism("roof", 0, 0, S * 0.74, S * 0.9, S * 0.94, S * 0.26, yaw=math.pi / 2)
        cols = {"walls": E["stoneT"], "roof": E["roof"], "trim": E["col"]}
    elif kind == "ziggurat":
        m.box("walls", 0, 0, 0, S, S, S * 0.33)
        m.box("walls", 0, 0, S * 0.33, S * 0.7, S * 0.7, S * 0.25)
        m.box("walls", 0, 0, S * 0.58, S * 0.46, S * 0.46, S * 0.18)
        m.box("trim", 0, 0, S * 0.76, S * 0.24, S * 0.28, S * 0.15)    # белёная целла
        m.prism("roof", 0, 0, S * 0.91, S * 0.26, S * 0.32, S * 0.09)
        for k in range(5):                                             # пандус на +X
            t = k / 5.0
            m.box("walls", S * (0.5 + 0.09 + t * 0.36), 0, 0,
                  S * 0.1, S * 0.14, S * 0.33 * (1 - t))
        cols = {"walls": E["wallS"], "roof": "#8f5a44", "trim": "#ddd2b4"}
    elif kind == "wall_segment":
        wood = era == "neolithic"
        m.box("walls", 0, 0, 0, S, S * (0.62 if wood else 0.5), S * 0.85)
        if wood:
            for k in range(5):
                x = (k / 4.0 - 0.5) * S * 0.9
                m.cyl("trim", x, 0, S * 0.8, S * 0.05, 0.0, S * 0.2, seg=6)
        else:
            m.box("walls", 0, 0, S * 0.85, S, S * 0.66, S * 0.03)
            for k in range(3):
                x = (k / 2.0 - 0.5) * S * 0.66
                m.box("trim", x, 0, S * 0.88, S * 0.16, S * 0.3, S * 0.12)
        cols = {"walls": E["wood"] if wood else E["wallS"],
                "roof": _mul(E["wallS"], 1.05), "trim": _mul(E["wood"] if wood else E["wallS"], 0.92)}
    elif kind == "tower":
        m.box("walls", 0, 0, 0, S * 0.85, S * 0.85, S * 0.82)
        m.box("roof", 0, 0, S * 0.82, S, S, S * 0.06)
        for sgn in (-1, 1):
            m.box("trim", sgn * S * 0.42, 0, S * 0.88, S * 0.12, S * 0.12, S * 0.12)
            m.box("trim", 0, sgn * S * 0.42, S * 0.88, S * 0.12, S * 0.12, S * 0.12)
        cols = {"walls": E["wallS"], "roof": _mul(E["wallS"], 1.06), "trim": E["wallS"]}
    elif kind == "gate":
        for sgn in (-1, 1):
            m.box("walls", sgn * S * 0.42, 0, 0, S * 0.23, S * 0.88, S * 0.86)
        m.box("walls", 0, 0, S * 0.71, S, S * 0.75, S * 0.29)
        m.box("trim", -S * 0.2, 0, 0, S * 0.04, S * 0.5, S * 0.6)      # створки
        m.box("trim", S * 0.2, 0, 0, S * 0.04, S * 0.5, S * 0.6)
        cols = {"walls": E["wallS"], "roof": E["wallS"], "trim": "#5f4a34"}
    elif kind == "well":
        m.cyl("walls", 0, 0, 0, S * 0.45, S * 0.45, S * 0.34)
        m.cyl("roof", 0, 0, S * 0.34, S * 0.36, S * 0.36, S * 0.04)    # «вода»
        for sgn in (-1, 1):
            m.box("trim", sgn * S * 0.43, 0, 0, S * 0.08, S * 0.08, S * 0.94)
        m.box("trim", 0, 0, S * 0.94, S * 0.95, S * 0.06, S * 0.06)    # перекладина
        cols = {"walls": E["wallS"], "roof": "#222831", "trim": E["wood"]}
    elif kind == "fire_pit":
        for k in range(7):
            a = k / 7.0 * 2 * math.pi
            m.box("walls", math.cos(a) * S * 0.42, math.sin(a) * S * 0.42, 0,
                  S * 0.16, S * 0.14, S * 0.14, yaw=a)
        m.cyl("trim", -S * 0.1, 0, 0, S * 0.05, S * 0.03, S * 0.9, seg=6)
        m.cyl("trim", S * 0.1, S * 0.05, 0, S * 0.05, S * 0.03, S * 0.85, seg=6)
        m.cyl("roof", 0, 0, S * 0.02, S * 0.2, S * 0.06, S * 0.5, seg=8)  # «пламя»
        cols = {"walls": "#6d675e", "roof": "#c96b2f", "trim": "#3a2c1c"}
    elif kind == "stela":
        m.box("walls", 0, 0, 0, S * 0.5, S * 0.5, S * 0.1)
        m.box("walls", 0, 0, S * 0.1, S * 0.34, S * 0.24, S * 0.9)
        for k in range(1, 4):
            m.box("trim", 0, 0, S * (0.1 + 0.9 * k / 4.0), S * 0.36, S * 0.26, S * 0.03)
        cols = {"walls": E["stoneT"], "roof": E["stoneT"], "trim": _mul(E["stoneT"], 0.8)}
    elif kind == "market_stall":
        for ix in (-1, 1):
            for iy in (-1, 1):
                m.cyl("trim", ix * S * 0.42, iy * S * 0.4, 0, S * 0.035, S * 0.035,
                      S * 0.9, seg=6)
        m.box("roof", 0, 0, S * 0.9, S * 1.04, S * 1.06, S * 0.06)     # навес
        m.box("walls", 0, 0, 0, S * 0.7, S * 0.42, S * 0.35)           # прилавок
        cols = {"walls": E["wood"], "roof": "#a05a40", "trim": E["wood"]}
    elif kind == "boat":
        m.box("walls", 0, 0, S * 0.15, S * 0.72, S * 0.9, S * 0.5)     # корпус
        m.prism("walls", S * 0.43, 0, S * 0.15, S * 0.22, S * 0.9, S * 0.5,
                yaw=math.pi / 2)
        m.prism("walls", -S * 0.43, 0, S * 0.15, S * 0.22, S * 0.9, S * 0.5,
                yaw=math.pi / 2)
        m.box("trim", 0, 0, S * 0.55, S * 0.6, S * 0.1, S * 0.06)      # банка
        cols = {"walls": _mul(E["wood"], 0.9), "roof": E["wood"], "trim": E["wood"]}
    elif kind == "pier":
        m.box("walls", 0, 0, S * 0.88, S, S, S * 0.12)                 # настил
        for tx in (-0.4, 0.0, 0.4):
            for ty in (-0.35, 0.35):
                m.cyl("trim", S * tx, S * ty, 0, S * 0.05, S * 0.05, S * 0.9, seg=6)
        cols = {"walls": E["wood"], "roof": E["wood"], "trim": _mul(E["wood"], 0.85)}
    elif kind == "field":
        m.box("walls", 0, 0, 0, S, S, S * 0.24)                        # пашня
        for k in range(4):
            y = (k / 3.0 - 0.5) * S * 0.8
            m.box("roof", 0, y, S * 0.24, S * 0.92, S * 0.1, S * 0.7)  # ряды посевов
        cols = {"walls": PALS[5]["field"], "roof": "#a89a50", "trim": E["wood"]}
    elif kind == "pen":
        for sgn in (-1, 1):
            m.box("walls", 0, sgn * S * 0.5, S * 0.25, S, S * 0.04, S * 0.14)
            m.box("walls", 0, sgn * S * 0.5, S * 0.6, S, S * 0.04, S * 0.14)
            m.box("walls", sgn * S * 0.5, 0, S * 0.25, S * 0.04, S, S * 0.14)
            m.box("walls", sgn * S * 0.5, 0, S * 0.6, S * 0.04, S, S * 0.14)
        for ix in (-1, 0, 1):
            for iy in (-1, 1):
                m.cyl("trim", ix * S * 0.5, iy * S * 0.5, 0, S * 0.035, S * 0.035, S)
                m.cyl("trim", iy * S * 0.5, ix * S * 0.5, 0, S * 0.035, S * 0.035, S)
        cols = {"walls": E["wood"], "roof": E["wood"], "trim": _mul(E["wood"], 0.85)}
    elif kind == "person":
        # человек ~175 см: ноги, туловище-капсула, голова; спавнится масштабом 1
        m.cyl("trim", -14, 0, 0, 8, 7, 75, seg=8)
        m.cyl("trim", 14, 0, 0, 8, 7, 75, seg=8)
        m.cyl("walls", 0, 0, 70, 26, 22, 65, seg=10)                   # туловище
        m.cyl("walls", -30, 0, 75, 6, 5, 55, seg=6)
        m.cyl("walls", 30, 0, 75, 6, 5, 55, seg=6)
        m.cyl("roof", 0, 0, 135, 12, 11, 30, seg=10)                   # голова
        cols = {"walls": "#8a6a4e", "roof": "#c2a077", "trim": "#5d564a"}
    else:
        raise ValueError(f"неизвестный прокси-тип: {kind}")
    return m, cols


PROXY_KINDS = ["hut_round", "house_flat", "house_gable", "temple", "ziggurat",
               "wall_segment", "tower", "gate", "well", "fire_pit", "stela",
               "market_stall", "boat", "pier", "field", "pen", "person"]


# ────────────────────────────────────────────────────────────────────────────
#  Манифест застройки: перевод типов play -> типы UE + габариты
# ────────────────────────────────────────────────────────────────────────────
def _rot_local(x, z, rot, lx, lz):
    """Локальная точка (lx,lz) здания -> мировые метры (конвенция фасада play)."""
    c, s = math.cos(rot), math.sin(rot)
    return x + lx * c - lz * s, z + lx * s + lz * c


def convert_buildings(sc: dict, ground_cm) -> list[dict]:
    """[type,x,z,rot,sx,sz,h] игры -> манифест UE. ground_cm(x_m,z_m)->Z_ue см."""
    kind = sc["id"]
    out = []

    def add(ue_type, src, x, z, rot, sx, sz, sh, z_override=None):
        gz = float(ground_cm(x, z))
        entry = {
            "type": ue_type, "src": src,
            "pos_cm": [round(x * M2CM, 1), round(z * M2CM, 1),
                       round(gz if z_override is None else z_override, 1)],
            "yaw_deg": round(math.degrees(rot) % 360.0, 2),
            "size_cm": [round(sx * M2CM, 1), round(sz * M2CM, 1),
                        round(sh * M2CM, 1)],
        }
        out.append(entry)

    for b in sc["buildings"]:
        t, x, z, rot, sx, sz, h = b[0], b[1], b[2], b[3], b[4], b[5], b[6]
        if t in ("house", "house2"):
            if t == "house2":
                add("house_gable", t, x, z, rot, sx * 1.1, sz * 1.1, h * 2.46)
            elif kind == "bronze":
                add("house_flat", t, x, z, rot, sx * 1.06, sz * 1.06, h + 0.8)
            else:
                add("house_gable", t, x, z, rot, sx, sz, h * 1.62)
        elif t == "hut":
            add("hut_round", t, x, z, rot, sx * 2, sx * 2, h * 1.84)
        elif t == "tent":
            add("hut_round", t, x, z, rot, sx * 2.1, sx * 2.1, h * 0.93)
        elif t == "granary":
            add("hut_round", t, x, z, rot, sx * 1.05, sz * 1.05, 1.65 + h * 0.6)
        elif t == "temple":
            if kind == "bronze":
                add("ziggurat", t, x, z, rot, sx, sz, h * 1.2)
            else:
                add("temple", t, x, z, rot, sx * 1.22, sz * 1.2, 1.42 + h * 1.18)
        elif t == "market":
            add("market_stall", t, x, z, rot, sx * 1.15, sz * 1.2, 2.9)
        elif t == "well":
            add("well", t, x, z, rot, 2.2, 2.2, 2.65)
        elif t == "fire":
            add("fire_pit", t, x, z, rot, sx * 1.8 + 0.45, sx * 1.8 + 0.45, 0.9)
        elif t == "stela":
            add("stela", t, x, z, rot, sx * 1.4, sx * 1.4, max(h, 1.2))
        elif t == "tower":
            add("tower", t, x, z, rot, sx * 1.18, sz * 1.18, h + 1.3)
        elif t == "gate":
            add("gate", t, x, z, rot, sx, 7.0, h)
        elif t == "wall":
            if kind == "neolithic":
                add("wall_segment", t, x, z, rot, sx, 0.8, h + 0.65)
            else:
                add("wall_segment", t, x, z, rot, sx, sz * 1.35, h + 1.2)
        elif t == "pen":
            add("pen", t, x, z, rot, sx, sz, 1.1)
        elif t == "field":
            add("field", t, x, z, rot, sx, sz, 0.5)
        elif t == "jetty":
            gz = float(ground_cm(x, z))
            top = max(WATER_Y * M2CM + 115.0, gz + 120.0)
            add("pier", t, x, z, rot, sx, max(sz, 3.2), (top - gz) / M2CM)
        elif t == "boat":
            add("boat", t, x, z, rot, sx, sz, 0.8)
        elif t == "totem":
            add("stela", t, x, z, rot, max(sx * 0.92, 0.7), max(sx * 0.92, 0.7),
                h + 0.55)
        elif t == "rack":
            add("market_stall", t, x, z, rot, sx + 0.2, 0.7, h)
        elif t == "torch":
            add("stela", t, x, z, rot, 0.5, 0.5, h + 0.25)
        elif t == "yard":
            for (lx, lz, ln, yaw2) in ((0, sz / 2, sx, rot), (0, -sz / 2, sx, rot),
                                       (sx / 2, 0, sz * 0.55, rot + math.pi / 2)):
                wx, wz = _rot_local(x, z, rot, lx, lz)
                add("wall_segment", t, wx, wz, yaw2, ln, 0.35, h)
        # прочие типы в игре не встречаются
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Люди
# ────────────────────────────────────────────────────────────────────────────
def _skin_tone(lat: float) -> str:
    L = abs(lat)
    return "#d9b490" if L > 32 else ("#8a5c3c" if L < 16 else "#b98f6b")


def _cloth_color(rng, npc: dict, garment: str, kind: str) -> str:
    pool = CLOTH["wool"] if garment in ("wool", "weave") else CLOTH["hide"]
    role = npc.get("role", "")
    if role == "priest":
        return "#d8cfba"
    if role == "chief":
        return "#8a4a3a" if kind == "neolithic" else "#7c3f4a"
    if role == "warrior":
        return "#5d564a"
    return pool[rng.randrange(len(pool))]


SPAWN_SKIP_TYPES = {"field", "pen", "boat", "fire_pit", "pier"}   # проходимое


def manifest_rects(buildings: list[dict]) -> list[tuple]:
    """Ориентированные прямоугольники зданий из манифеста (метры сцены)."""
    rects = []
    for b in buildings:
        if b["type"] in SPAWN_SKIP_TYPES:
            continue
        yaw = math.radians(b["yaw_deg"])
        rects.append((b["pos_cm"][0] / M2CM, b["pos_cm"][1] / M2CM,
                      math.cos(yaw), math.sin(yaw),
                      b["size_cm"][0] / M2CM / 2.0, b["size_cm"][1] / M2CM / 2.0))
    return rects


def point_in_rects(px: float, pz: float, rects: list[tuple],
                   margin: float = 0.0):
    """Индекс первого прямоугольника, содержащего точку, или None."""
    for i, (cx, cz, c, s, hx, hz) in enumerate(rects):
        dxw, dzw = px - cx, pz - cz
        lx = dxw * c + dzw * s
        lz = -dxw * s + dzw * c
        if abs(lx) < hx + margin and abs(lz) < hz + margin:
            return i
    return None


def _push_from_rect(px, pz, rect, margin):
    """Вытолкнуть точку из прямоугольника по кратчайшей оси."""
    cx, cz, c, s, hx, hz = rect
    dxw, dzw = px - cx, pz - cz
    lx = dxw * c + dzw * s
    lz = -dxw * s + dzw * c
    ox = hx + margin - abs(lx)
    oz = hz + margin - abs(lz)
    if ox < oz:
        lx += math.copysign(ox + 0.03, lx if lx != 0 else 1.0)
    else:
        lz += math.copysign(oz + 0.03, lz if lz != 0 else 1.0)
    return cx + lx * c - lz * s, cz + lx * s + lz * c


def convert_people(sc: dict, hf: HeightField, H, ax,
                   buildings: list[dict]) -> tuple[list[dict], int]:
    """npcs сцены -> people.json; спавны выталкиваются из зданий и воды.

    Гарантия: точка спавна вне ВСЕХ прямоугольников манифеста (с запасом)
    и не в воде — этим же критерием пользуется verify_scene."""
    import random as _random
    rng = _random.Random(sc["seed"] * 17 + 9)
    rects = manifest_rects(buildings)
    moved = 0

    def clean(px, pz, margin):
        return (point_in_rects(px, pz, rects, margin) is None
                and float(hf.h(px, pz)) >= WATER_Y + 0.25)

    def free_pos(px, pz):
        """Вытолкнуть точку из зданий и воды; вернуть (x, z, сдвинута?)."""
        ox, oz = px, pz
        for _ in range(40):
            i = point_in_rects(px, pz, rects, 0.5)
            if i is not None:
                px, pz = _push_from_rect(px, pz, rects[i], 0.55)
                continue
            if float(hf.h(px, pz)) < WATER_Y + 0.25:
                dc = math.hypot(px, pz) or 1.0
                px -= px / dc * 6.0
                pz -= pz / dc * 6.0
                continue
            break
        px = float(np.clip(px, -560.0, 560.0))
        pz = float(np.clip(pz, -560.0, 560.0))
        if not clean(px, pz, 0.5):
            # редкий тупик: спираль вокруг площади до чистого места
            base = sc.get("pois", {}).get("plaza") or [0.0, 0.0]
            for k in range(1, 400):
                a = k * 2.399963            # золотой угол
                r = 4.0 + k * 0.9
                qx, qz = base[0] + math.cos(a) * r, base[1] + math.sin(a) * r
                if abs(qx) < 560 and abs(qz) < 560 and clean(qx, qz, 0.5):
                    px, pz = qx, qz
                    break
        return px, pz, (abs(px - ox) + abs(pz - oz) > 0.05)

    people = []
    for npc in sc["npcs"]:
        hx, hz = npc["home"]
        sx_, sz_, was_moved = free_pos(hx, hz)
        if was_moved:
            moved += 1
        gz = float(grid_height_at(H, ax, sx_, sz_)) * M2CM
        route = []
        for (wx, wz) in npc.get("route", [])[:4]:
            wgz = float(grid_height_at(H, ax, wx, wz)) * M2CM
            route.append([round(wx * M2CM, 1), round(wz * M2CM, 1), round(wgz, 1)])
        if len(route) >= 2:
            yaw = math.degrees(math.atan2(route[1][1] - sz_ * M2CM,
                                          route[1][0] - sx_ * M2CM))
        else:
            yaw = rng.uniform(0, 360)
        deeds = [f"{d['y']}: {d['t']}" for d in npc.get("deeds", []) if d.get("t")]
        traits = [f"{name} {val}" for name, val in npc.get("traits", [])]
        beliefs = [f"{name} {val}" for name, val in npc.get("beliefs", [])]
        people.append({
            "name": npc["name"], "sex": npc["sex"], "age": npc["age"],
            "role": npc["role"], "role_ru": npc["role_ru"],
            "real": npc.get("real", 0), "born": npc.get("born"),
            "cloth_hex": _cloth_color(rng, npc, sc["garment"], sc["id"]),
            "skin_hex": _skin_tone(sc["lat"]),
            "spawn_cm": [round(sx_ * M2CM, 1), round(sz_ * M2CM, 1), round(gz, 1)],
            "yaw_deg": round(yaw % 360.0, 1),
            "route_cm": route,
            "card": {"deeds": deeds, "traits": traits, "beliefs": beliefs,
                     "prestige": npc.get("prestige", 0),
                     "real_person": bool(npc.get("real", 0))},
        })
    return people, moved


# ────────────────────────────────────────────────────────────────────────────
#  Запекание цвета ландшафта и масок
# ────────────────────────────────────────────────────────────────────────────
def _seg_dist(px, pz, seg):
    x1, z1, x2, z2 = seg[0], seg[1], seg[2], seg[3]
    dx, dz = x2 - x1, z2 - z1
    L2 = dx * dx + dz * dz
    if L2 < 1e-9:
        return np.hypot(px - x1, pz - z1)
    t = np.clip(((px - x1) * dx + (pz - z1) * dz) / L2, 0.0, 1.0)
    return np.hypot(px - (x1 + t * dx), pz - (z1 + t * dz))


def bake_ground_maps(sc: dict, hf: HeightField, color_px=COLOR_PX, mask_px=MASK_PX):
    """Цветовая текстура (порт раскраски buildTerrain) + весовые маски.

    Возвращает (color uint8 [px,px,3], {"grass","dirt","rock","sand"} uint8).
    Строка 0 картинок = z = −600 м (север, −Y UE)."""
    from scipy.spatial import cKDTree

    P = PALS.get(sc["biome"], PALS[5])
    is_cap = sc["id"] == "capital"
    c_grass, c_grass2 = _hex2rgb(P["grass"]), _hex2rgb(P["grass2"])
    c_dry, c_rock = _hex2rgb(P["dry"]), _hex2rgb(P["rock"])
    c_sand, c_path = _hex2rgb(P["sand"]), _hex2rgb(P["path"])
    c_field = _hex2rgb(P["field"])
    c_pave = _hex2rgb(ERACOL[sc["id"]]["pave"])
    c_deep = _hex2rgb(P["deep"]) * 0.55
    c_street = c_pave if is_cap else c_path

    solid = [(b[1], b[2]) for b in sc["buildings"] if b[0] not in ("field", "pen")]
    tree = cKDTree(np.array(solid)) if solid else None
    streets = sc.get("streets", [])
    plaza = sc.get("pois", {}).get("plaza")
    fields = sc.get("pois", {}).get("fields", [])
    flatr = FLATR[sc["id"]]
    seed = hf.seed

    px = color_px
    scale = mask_px / color_px
    color = np.zeros((px, px, 3), dtype=np.uint8)
    masks_acc = {k: np.zeros((mask_px, mask_px), dtype=np.float32)
                 for k in ("dirt", "rock", "sand")}
    axis = np.linspace(-TSIZE / 2, TSIZE / 2, px)
    chunk = 128
    for r0 in range(0, px, chunk):
        r1 = min(px, r0 + chunk)
        Z = np.repeat(axis[r0:r1][:, None], px, axis=1)
        X = np.repeat(axis[None, :], r1 - r0, axis=0)
        h = hf.h(X, Z)
        dc = np.hypot(X, Z)
        m = _fbm(X * 0.013 + 40.0, Z * 0.013, 3, seed)
        col = c_grass[None, None, :] + (c_grass2 - c_grass)[None, None, :] * m[..., None]
        dry_a = 0.6 * _sstep((_fbm(X * 0.013, Z * 0.013 + 9.0, 3, seed) - 0.46) / 0.34)
        col += (c_dry[None, None, :] - col) * dry_a[..., None]
        sand_w = np.zeros_like(h)
        if sc.get("river"):
            hw = sc["river"][3]
            rd = hf.river_dist(X, Z)
            wet = np.clip(0.5 * (1.0 - rd / (hw * 2.6)), 0, 1) * (rd < hw * 2.6)
            col += (c_grass2[None, None, :] - col) * wet[..., None]
        a_sand = _sstep((0.9 - h) / 1.6) * (h < 0.9)
        col += (c_sand[None, None, :] - col) * a_sand[..., None]
        sand_w = np.maximum(sand_w, a_sand)
        a_deep = _sstep((WATER_Y - 0.3 - h) / 5.5) * (h < WATER_Y - 0.3)
        col += (c_deep[None, None, :] - col) * a_deep[..., None]
        if sc.get("sea"):
            ss = hf.sea_s(X, Z)
            a_sea = _sstep((ss + 46.0) / 60.0) * 0.9 * ((ss > -46.0) & (h > -2.0))
            col += (c_sand[None, None, :] - col) * a_sea[..., None]
            sand_w = np.maximum(sand_w, a_sea)
        e = 0.9
        slope = np.abs(hf.h(X + e, Z) - h) + np.abs(hf.h(X, Z + e) - h)
        a_rock = _sstep((slope - 1.05) / 1.3)
        col += (c_rock[None, None, :] - col) * a_rock[..., None]
        dirt_w = np.zeros_like(h)
        if streets:
            sd = np.full_like(h, 1e9)
            for s in streets:
                sd = np.minimum(sd, _seg_dist(X, Z, s))
            sw = 4.2
            a_st = 0.85 * (1.0 - _sstep((sd - sw * 0.5) / (sw * 0.9))) * (sd < sw + 4)
            col += (c_street[None, None, :] - col) * a_st[..., None]
            dirt_w = np.maximum(dirt_w, a_st)
        if plaza:
            pd = np.hypot(X - plaza[0], Z - plaza[1])
            a_pl = 0.85 * (1.0 - _sstep((pd - 18.0) / 14.0)) * (pd < 34)
            col += (c_street[None, None, :] - col) * a_pl[..., None]
            dirt_w = np.maximum(dirt_w, a_pl)
        if tree is not None:
            tr, _ = tree.query(np.stack([X.ravel(), Z.ravel()], axis=1),
                               workers=-1)
            tr = tr.reshape(h.shape)
            a_tr = (0.45 if is_cap else 0.6) * np.clip(1.0 - tr / 14.0, 0, 1)
            col += (c_path[None, None, :] - col) * a_tr[..., None]
            dirt_w = np.maximum(dirt_w, a_tr)
        dust = _sstep(1.0 - dc / (flatr * 0.8))
        a_du = dust * (0.34 if is_cap else 0.44) * (0.5 + 0.5 * _fbm(X * 0.045,
                                                                     Z * 0.045, 2, seed))
        col += (c_path[None, None, :] - col) * a_du[..., None]
        dirt_w = np.maximum(dirt_w, a_du)
        for ff in fields:
            fd = np.hypot(X - ff[0], Z - ff[1])
            a_f = 0.5 * (1.0 - _sstep((fd - 12.0) / 8.0)) * (fd < 20)
            col += (c_field[None, None, :] - col) * a_f[..., None]
            dirt_w = np.maximum(dirt_w, a_f)
        g2 = 0.93 + _fbm(X * 0.09, Z * 0.09, 2, seed) * 0.14
        col *= g2[..., None]
        color[r0:r1] = (np.clip(col, 0, 1) * 255).astype(np.uint8)

        # маски — та же полоса, даунсемпл усреднением блоков
        mr0, mr1 = int(round(r0 * scale)), int(round(r1 * scale))
        if mr1 > mr0:
            blk = int(round(1 / scale))
            for key, w in (("dirt", dirt_w), ("rock", a_rock), ("sand", sand_w)):
                ww = w[: (mr1 - mr0) * blk, : mask_px * blk]
                ww = ww.reshape(mr1 - mr0, blk, mask_px, blk).mean(axis=(1, 3))
                masks_acc[key][mr0:mr1] = ww

    dirt, rock, sand = masks_acc["dirt"], masks_acc["rock"], masks_acc["sand"]
    grass = np.clip(1.0 - np.maximum(dirt, np.maximum(rock, sand)), 0, 1)
    tot = grass + dirt + rock + sand
    tot[tot < 1e-6] = 1.0
    masks = {"grass": grass / tot, "dirt": dirt / tot, "rock": rock / tot,
             "sand": sand / tot}
    masks8 = {k: (np.clip(v, 0, 1) * 255).astype(np.uint8) for k, v in masks.items()}
    return color, masks8


# ────────────────────────────────────────────────────────────────────────────
#  Мини-парсер OBJ для самопроверок
# ────────────────────────────────────────────────────────────────────────────
def parse_obj(path: Path) -> dict:
    v, f, max_vi = [], 0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            parts = line.split()
            v.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("f "):
            f += 1
            for tok in line.split()[1:]:
                max_vi = max(max_vi, int(tok.split("/")[0]))
    arr = np.array(v) if v else np.zeros((0, 3))
    return {"n_v": len(v), "n_f": f, "v": arr, "max_vi": max_vi,
            "idx_ok": max_vi <= len(v),
            "has_nan": bool(np.isnan(arr).any() or np.isinf(arr).any()),
            "bbox": (arr.min(axis=0), arr.max(axis=0)) if len(v) else None}


# ────────────────────────────────────────────────────────────────────────────
#  Экспорт одной сцены
# ────────────────────────────────────────────────────────────────────────────
def export_scene(sc: dict, run_id: str, out_dir: Path) -> dict:
    kind = sc["id"]
    d = out_dir / kind
    (d / "masks").mkdir(parents=True, exist_ok=True)
    (d / "proxy_meshes").mkdir(parents=True, exist_ok=True)
    hf = HeightField(sc)
    ax, H = make_height_grid(hf)
    has_water = bool(sc.get("river") or sc.get("sea"))

    # 1. ландшафт, кольцо, вода
    write_grid_obj(d / "terrain.obj", ax, H, f"terra_{kind}_terrain",
                   mtl="terrain.mtl", matname="terrain")
    (d / "terrain.mtl").write_text(
        "newmtl terrain\nKd 1.000 1.000 1.000\nmap_Kd terrain_color.png\nNs 4\n",
        encoding="utf-8")
    fax = _grid_axes(FAR_N, FAR_SIZE)
    FX, FZ = np.meshgrid(fax, fax)
    FH = hf.h_far(FX, FZ)
    write_grid_obj(d / "terrain_far.obj", fax, FH, f"terra_{kind}_far",
                   mtl="terrain_far.mtl", matname="far", with_uv=False)
    edge = _hex2rgb(PALS.get(sc["biome"], PALS[5])["grass"])
    edge = edge + (_hex2rgb(PALS.get(sc["biome"], PALS[5])["dry"]) - edge) * 0.6
    edge *= 0.94
    (d / "terrain_far.mtl").write_text(
        f"newmtl far\nKd {edge[0]:.3f} {edge[1]:.3f} {edge[2]:.3f}\nNs 2\n",
        encoding="utf-8")
    if has_water:
        write_water_obj(d / "water.obj", FAR_SIZE + 800,
                        PALS.get(sc["biome"], PALS[5])["water"])

    # 2. маски и heightmap
    color, masks8 = bake_ground_maps(sc, hf)
    Image.fromarray(color, "RGB").save(d / "terrain_color.png", optimize=True)
    for key, img in masks8.items():
        Image.fromarray(img, "L").save(d / "masks" / f"{key}.png", optimize=True)
    hax = np.linspace(-TSIZE / 2, TSIZE / 2, HMAP_PX)
    HX, HZ = np.meshgrid(hax, hax)
    HH = hf.h(HX, HZ)
    hmin, hmax = float(HH.min()), float(HH.max())
    span = max(hmax - hmin, 1e-6)
    h16 = np.round((HH - hmin) / span * 65535.0).astype(np.uint16)
    Image.fromarray(h16).save(d / "masks" / "heightmap.png")  # PIL: uint16 -> I;16

    # 3. здания и дороги
    def ground_cm(x_m, z_m):
        return float(grid_height_at(H, ax, x_m, z_m)) * M2CM
    buildings = convert_buildings(sc, ground_cm)
    roads = []
    for s in sc.get("streets", []):
        pts = []
        for (px, pz) in ((s[0], s[1]), (s[2], s[3])):
            pts.append([round(px * M2CM, 1), round(pz * M2CM, 1),
                        round(ground_cm(px, pz), 1)])
        roads.append({"width_cm": round(s[4] * M2CM, 1), "points_cm": pts})
    (d / "buildings.json").write_text(json.dumps({
        "coords": "см; X=x сцены, Y=z сцены, Z вверх; yaw вокруг Z, фасад +X",
        "scale_rule": "актор прокси-меша масштабировать в size_cm/native_size_cm",
        "buildings": buildings, "roads": roads,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # 4. люди
    people, moved = convert_people(sc, hf, H, ax, buildings)
    (d / "people.json").write_text(json.dumps({
        "coords": "см; спавн на рельефе; route_cm — дневной маршрут",
        "people": people}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 5. прокси-меши
    proxy_index = {}
    for pk in PROXY_KINDS:
        mb, cols = build_proxy(pk, kind)
        mb.write(d / "proxy_meshes" / f"{pk}.obj", pk, cols)
        lo, hi = mb.bbox()
        proxy_index[pk] = {
            "native_size_cm": 100.0 if pk != "person" else None,
            "bbox_cm": [[round(float(v), 1) for v in lo],
                        [round(float(v), 1) for v in hi]],
            "slots": list(cols.keys()), "colors": cols,
        }
    (d / "proxy_meshes" / "proxy_index.json").write_text(
        json.dumps(proxy_index, ensure_ascii=False, indent=1), encoding="utf-8")

    # 6. meta
    plaza_xy = sc.get("pois", {}).get("plaza") or [0.0, 0.0]
    lat = float(sc["lat"])
    sun_elev = max(12.0, min(88.0, 90.0 - abs(lat) + 15.0)) * 0.9
    hmin_cm, hmax_cm = hmin * M2CM, hmax * M2CM
    meta = {
        "run_id": run_id, "scene": kind, "title": sc["title"],
        "settlement": sc["name"], "polity": sc["polity"], "era": sc["era"],
        "year": sc["year"], "year_ru": sc["year_ru"], "gods": sc.get("gods", []),
        "population": sc.get("pop"), "biome": sc.get("biome_ru"),
        "latitude_deg": lat, "seed": sc["seed"], "desc": sc.get("desc", ""),
        "coords": {"axes": "X=x сцены, Y=z сцены, Z вверх; север = −Y",
                   "units": "см", "yaw": "вокруг Z, фасад локальный +X"},
        "terrain": {"size_cm": TSIZE * M2CM, "grid": GRID_N,
                    "step_cm": round(TSIZE * M2CM / (GRID_N - 1), 2),
                    "z_min_cm": round(float(H.min()) * M2CM, 1),
                    "z_max_cm": round(float(H.max()) * M2CM, 1),
                    "water_z_cm": round(WATER_Y * M2CM, 1) if has_water else None,
                    "far_size_cm": FAR_SIZE * M2CM},
        "heightmap": {
            "px": HMAP_PX, "min_cm": round(hmin_cm, 1), "max_cm": round(hmax_cm, 1),
            "note": "PNG16: 0 -> min_cm, 65535 -> max_cm; строка 0 = север (−Y)",
            "landscape_scale_xy": round(TSIZE * M2CM / (HMAP_PX - 1), 4),
            "landscape_scale_z": round((hmax_cm - hmin_cm) / 51200.0 * 100.0, 4),
            "landscape_z_location_cm": round((hmin_cm + hmax_cm) / 2.0, 1),
        },
        "sun": {"elevation_deg": round(sun_elev, 1),
                "azimuth_note": "солнце с юга (+Y) при lat>0, с севера при lat<0"},
        "player_start_cm": [
            round(plaza_xy[0] * M2CM, 1), round(plaza_xy[1] * M2CM, 1),
            round(ground_cm(plaza_xy[0], plaza_xy[1]) + 120.0, 1)],
        "counts": {"buildings": len(buildings), "roads": len(roads),
                   "people": len(people)},
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "exporter": "terra.export_ue",
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    return {"dir": d, "H": H, "ax": ax, "hf": hf, "meta": meta,
            "buildings": buildings, "people": people, "moved": moved}


# ────────────────────────────────────────────────────────────────────────────
#  Самопроверки сцены
# ────────────────────────────────────────────────────────────────────────────
def verify_scene(res: dict, checks: list):
    d, H, ax, hf = res["dir"], res["H"], res["ax"], res["hf"]
    kind = d.name

    def check(name, cond, detail=""):
        checks.append((f"{kind}: {name}", bool(cond), detail))

    # OBJ ландшафта: перечитать с диска и сверить с сеткой
    ter = parse_obj(d / "terrain.obj")
    check("terrain.obj парсится, вершин 257²",
          ter["n_v"] == GRID_N * GRID_N and ter["n_f"] == (GRID_N - 1) ** 2 * 2,
          f"v={ter['n_v']} f={ter['n_f']}")
    check("terrain.obj без NaN/Inf, индексы граней валидны",
          not ter["has_nan"] and ter["idx_ok"])
    lo, hi = ter["bbox"]
    check("bbox XY = 1200 м (120000 см)",
          abs(lo[0] + 60000) < 1 and abs(hi[0] - 60000) < 1
          and abs(lo[1] + 60000) < 1 and abs(hi[1] - 60000) < 1,
          f"{lo[:2]}..{hi[:2]}")
    zmin_meta = res["meta"]["terrain"]["z_min_cm"]
    zmax_meta = res["meta"]["terrain"]["z_max_cm"]
    check("bbox Z совпадает с meta",
          abs(lo[2] - zmin_meta) < 1 and abs(hi[2] - zmax_meta) < 1,
          f"{lo[2]:.0f}..{hi[2]:.0f} vs {zmin_meta}..{zmax_meta}")

    # здания на рельефе: манифест против ПЕРЕЧИТАННОГО OBJ и против аналитики
    grid_from_obj = ter["v"][:, 2].reshape(GRID_N, GRID_N) / M2CM
    worst_obj, worst_ana = 0.0, 0.0
    n_bad = 0
    for b in res["buildings"]:
        x_m, z_m = b["pos_cm"][0] / M2CM, b["pos_cm"][1] / M2CM
        z_man = b["pos_cm"][2]
        z_obj = float(grid_height_at(grid_from_obj, ax, x_m, z_m)) * M2CM
        z_ana = float(hf.h(x_m, z_m)) * M2CM
        worst_obj = max(worst_obj, abs(z_man - z_obj))
        worst_ana = max(worst_ana, abs(z_man - z_ana))
        if abs(z_man - z_obj) >= 30.0:
            n_bad += 1
    check("здания: |z − рельеф OBJ| < 30 см у 100 %", n_bad == 0,
          f"наруш. {n_bad}, максимум {worst_obj:.1f} см")
    check("здания: |z − аналитический рельеф| < 30 см", worst_ana < 30.0,
          f"максимум {worst_ana:.1f} см")

    # heightmap PNG16
    im = Image.open(d / "masks" / "heightmap.png")
    arr = np.array(im)
    hm = res["meta"]["heightmap"]
    check("heightmap: PNG16 1009², полный диапазон",
          arr.dtype == np.uint16 and arr.shape == (HMAP_PX, HMAP_PX)
          and int(arr.min()) == 0 and int(arr.max()) == 65535,
          f"dtype={arr.dtype} shape={arr.shape} {arr.min()}..{arr.max()}")
    mid = arr[HMAP_PX // 2, HMAP_PX // 2] / 65535.0 * (hm["max_cm"] - hm["min_cm"]) \
        + hm["min_cm"]
    ana_mid = float(hf.h(0.0, 0.0)) * M2CM
    check("heightmap: центр совпадает с аналитикой (<50 см)",
          abs(mid - ana_mid) < 50.0, f"{mid:.0f} vs {ana_mid:.0f} см")

    # маски
    for key in ("grass", "dirt", "rock", "sand"):
        mi = np.array(Image.open(d / "masks" / f"{key}.png"))
        check(f"маска {key}: PNG8 1024²",
              mi.dtype == np.uint8 and mi.shape == (MASK_PX, MASK_PX))

    # люди: не в воде и не в зданиях
    n_wet, n_inside = 0, 0
    for p in res["people"]:
        x_m, z_m = p["spawn_cm"][0] / M2CM, p["spawn_cm"][1] / M2CM
        if float(hf.h(x_m, z_m)) < WATER_Y + 0.2:
            n_wet += 1
    check("люди: спавны не в воде", n_wet == 0, f"в воде {n_wet}")
    # против ориентированных прямоугольников из ПЕРЕЧИТАННОГО buildings.json
    from_json = json.loads((d / "buildings.json").read_text(encoding="utf-8"))
    rects = manifest_rects(from_json["buildings"])
    for p in res["people"]:
        x_m, z_m = p["spawn_cm"][0] / M2CM, p["spawn_cm"][1] / M2CM
        if point_in_rects(x_m, z_m, rects, 0.0) is not None:
            n_inside += 1
    check("люди: спавны не внутри зданий", n_inside == 0, f"внутри {n_inside}")

    # прокси-меши: все парсятся, bbox соответствует индексу
    idx = json.loads((d / "proxy_meshes" / "proxy_index.json").read_text(encoding="utf-8"))
    ok_p, bad_p = 0, []
    for pk in PROXY_KINDS:
        po = parse_obj(d / "proxy_meshes" / f"{pk}.obj")
        lo2, hi2 = po["bbox"]
        want_lo, want_hi = idx[pk]["bbox_cm"]
        if (po["n_v"] > 0 and not po["has_nan"] and po["idx_ok"]
                and all(abs(lo2[i] - want_lo[i]) < 0.5 for i in range(3))
                and all(abs(hi2[i] - want_hi[i]) < 0.5 for i in range(3))):
            ok_p += 1
        else:
            bad_p.append(pk)
    check("прокси-меши: 17/17 парсятся, bbox по индексу", ok_p == len(PROXY_KINDS),
          f"плохие: {bad_p}")

    if res["meta"]["terrain"]["water_z_cm"] is not None:
        w = parse_obj(d / "water.obj")
        check("water.obj парсится на уровне воды",
              w["n_v"] > 0 and not w["has_nan"]
              and abs(w["bbox"][0][2] - WATER_Y * M2CM) < 0.6)
    far = parse_obj(d / "terrain_far.obj")
    check("terrain_far.obj: кольцо 6 км без NaN",
          far["n_v"] == FAR_N * FAR_N and not far["has_nan"]
          and abs(far["bbox"][1][0] - FAR_SIZE / 2 * M2CM) < 1)


# ────────────────────────────────────────────────────────────────────────────
#  CLI
# ────────────────────────────────────────────────────────────────────────────
def export(run_dir: str | Path, scene: str = "all",
           out_dir: str | Path = "export_ue") -> bool:
    kinds = None if scene == "all" else [scene]
    payload = build_scene_data(run_dir, kinds=kinds)
    if not payload["scenes"]:
        raise SystemExit(f"в прогоне нет сцены «{scene}»")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # общий скрипт импорта и README — рядом со сценами
    src = Path(__file__).resolve().parent / "ue"
    for fname in ("import_terra.py", "README_UE.md"):
        shutil.copy2(src / fname, out / fname)

    checks: list = []
    for sc in payload["scenes"]:
        print(f"[export_ue] сцена «{sc['title']}»: {sc['name']} ({sc['year_ru']})…")
        res = export_scene(sc, payload["run_id"], out)
        if res["moved"]:
            print(f"  · спавны людей поправлены (вытолкнуты из зданий/воды): "
                  f"{res['moved']}")
        verify_scene(res, checks)
        total = sum(f.stat().st_size for f in res["dir"].rglob("*") if f.is_file())
        print(f"  · {res['dir']}  ({total / 1e6:.1f} МБ, зданий "
              f"{len(res['buildings'])}, людей {len(res['people'])})")

    n_fail = 0
    print("\n── самопроверки экспорта " + "─" * 38)
    for (name, ok, detail) in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}" + (f"  {detail}" if detail and not ok else ""))
        n_fail += 0 if ok else 1
    print(f"\n{'ВСЕ ' + str(len(checks)) + ' ПРОВЕРОК ПРОЙДЕНЫ' if n_fail == 0 else str(n_fail) + ' ПРОВЕРОК ПРОВАЛЕНО'}; "
          f"пакет: {out.resolve()}")
    return n_fail == 0


def main():
    ap = argparse.ArgumentParser(
        "terra.export_ue", description="экспорт сцен прогона в пакет для UE5")
    ap.add_argument("run", help="каталог прогона (runs/terra-1)")
    ap.add_argument("--scene", default="all",
                    choices=["capital", "bronze", "neolithic", "all"])
    ap.add_argument("-o", "--out", default="export_ue")
    a = ap.parse_args()
    ok = export(a.run, a.scene, a.out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
