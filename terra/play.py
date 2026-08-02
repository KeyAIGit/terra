"""
TERRA — режим прогулки: наблюдатель спускается на землю.

Собирает из каталога прогона один самодостаточный офлайн HTML: три сцены
(столица державы, городок бронзового века, неолитическая деревня), по которым
можно ходить от первого лица, смотреть на закаты и разговаривать с жителями.
Всё в сценах — из данных прогона: имена, народы, боги, люди, летопись.

    from terra.play import build_play
    build_play("runs/terra-1")            # -> runs/terra-1/play.html

    python3 -m terra.play runs/terra-1 [-o out.html]

Файл работает офлайн; единственное добровольное исключение — свободный чат
с жителями через Anthropic API, если игрок сам вставит свой ключ.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from pathlib import Path

from terra.agents import DOMAIN_RU, MEM_RU, ROLE_RU, SCAR_RU
from terra.contracts import BIOME_COLORS, BIOME_NAMES
from terra.gallery import BELIEF_RU, TRAIT_RU
from terra.society import FORM_RU, MODE_RU
from terra.world import load_world

# ────────────────────────────────────────────────────────────────────────────
#  Настройки
# ────────────────────────────────────────────────────────────────────────────
RIVER_MIN = 0.35          # с какой величины river-поля в клетке рисуем реку
PEOPLE_WINDOW = 400       # реальные люди: жившие в пределах стольких лет от сцены
MAX_REAL = 14             # не больше стольких реальных людей на сцену
NPC_TOTAL = {"capital": 48, "bronze": 36, "neolithic": 28}
EVENTS_PER_SCENE = 10     # событий летописи в багаж сцены

_YEAR_TARGETS = {"capital": None, "bronze": -1500, "neolithic": -6000}
_ERA_OF = {"bronze": "бронза", "neolithic": "неолит"}


def _fmt_year(y: int) -> str:
    return f"{abs(int(y))} г. {'до н. э.' if y < 0 else 'н. э.'}"


def _fmt_pop(n: int) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}".replace(".", ",") + " млн"
    return f"{n:,}".replace(",", " ")


# ────────────────────────────────────────────────────────────────────────────
#  Загрузка прогона
# ────────────────────────────────────────────────────────────────────────────
def _read_jsonl(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _load(run_dir: Path) -> dict:
    snaps = _read_jsonl(run_dir / "snapshots.jsonl")
    if not snaps:
        raise FileNotFoundError(f"нет snapshots.jsonl в {run_dir}")
    people = _read_jsonl(run_dir / "people.jsonl")
    chron = _read_jsonl(run_dir / "chronicle.jsonl")
    lects = {}
    lf = run_dir / "lects.json.gz"
    if lf.exists():
        with gzip.open(lf, "rt", encoding="utf-8") as f:
            lects = json.load(f)
    world = load_world(str(run_dir / "world"))
    return {"snaps": snaps, "people": people, "chron": chron,
            "lects": lects, "world": world}


def _known_keys(tech: int) -> set:
    """Набор освоенных знаний народа с числом знаний tech (как в portrait.py)."""
    from terra import knowledge as kn
    cat = sorted(kn.CATALOG, key=lambda t: t.difficulty)
    return {t.key for t in cat[:max(0, int(tech))]}


# ────────────────────────────────────────────────────────────────────────────
#  Выбор сцен
# ────────────────────────────────────────────────────────────────────────────
def _people_near(people, pid, year, win=PEOPLE_WINDOW):
    return [p for p in people if p.get("polity") == pid
            and abs(p.get("born", 0) - year) <= win]


def _pick_scenes(data: dict) -> list[dict]:
    """Три опорные точки: столица последнего кадра, бронза ~-1500, неолит ~-6000."""
    snaps, people, lects, w = (data["snaps"], data["people"],
                               data["lects"], data["world"])
    out = []

    # 1. столица: крупнейший живой город последнего кадра
    last = snaps[-1]
    pols = {p["pid"]: p for p in last["polities"]}
    sets = [t for t in last["settlements"] if t["culture"] in pols]
    cap = max(sets, key=lambda t: t["pop"])
    out.append({"kind": "capital", "snap": last, "set": cap,
                "pol": pols[cap["culture"]]})

    # 2-3. бронза и неолит: кадр ближе всего к целевому году; среди поселений
    # верной эпохи берём скромные (городок, не метрополию), для чьего народа
    # есть язык и живые люди рядом; предпочитаем воду в кадре, затем людность
    for kind in ("bronze", "neolithic"):
        target = _YEAR_TARGETS[kind]
        snap = min(snaps, key=lambda s: abs(s["year"] - target))
        pmap = {p["pid"]: p for p in snap["polities"]}
        best, best_score = None, None
        for t in snap["settlements"]:
            pol = pmap.get(t["culture"])
            if not pol or pol.get("era") != _ERA_OF[kind]:
                continue
            if t.get("tier") in ("метрополия", "большой город"):
                continue
            if str(t["culture"]) not in lects:
                continue
            n_real = len(_people_near(people, t["culture"], snap["year"]))
            if n_real < 3:
                continue
            y, x = int(t["y"]), int(t["x"])
            water = (1 if float(w.river[y, x]) > RIVER_MIN else 0) + \
                    (1 if bool(w.coastal[y, x]) else 0)
            score = (water, min(n_real, 8), t["pop"])
            if best_score is None or score > best_score:
                best, best_score = t, score
        if best is None:  # запасной путь: просто людное поселение верной эпохи
            cands = [t for t in snap["settlements"]
                     if pmap.get(t["culture"], {}).get("era") == _ERA_OF[kind]]
            best = max(cands, key=lambda t: t["pop"]) if cands else snap["settlements"][0]
        out.append({"kind": kind, "snap": snap, "set": best,
                    "pol": pmap[best["culture"]]})
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Планировка поселения
# ────────────────────────────────────────────────────────────────────────────
# типы зданий; JS знает, как каждый рисовать
B_HOUSE, B_HOUSE2, B_HUT, B_TENT, B_GRANARY = "house", "house2", "hut", "tent", "granary"
B_TEMPLE, B_MARKET, B_WELL, B_FIRE, B_STELA = "temple", "market", "well", "fire", "stela"
B_TOWER, B_GATE, B_WALL, B_PEN, B_FIELD = "tower", "gate", "wall", "pen", "field"
B_JETTY, B_BOAT, B_TOTEM, B_RACK, B_TORCH = "jetty", "boat", "totem", "rack", "torch"
B_YARD = "yard"


class _Town:
    """Простая планировка: улицы, здания без пересечений, точки интереса."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.b: list[list] = []       # [type, x, z, rot, sx, sz, h]
        self.streets: list[list] = [] # [x1,z1,x2,z2,w]
        self.placed: list[tuple] = [] # (x, z, r) — для запрета пересечений
        self.pois: dict = {"fires": [], "fields": [], "gates": [], "sit": []}
        self.water = []               # аналитические зоны воды (для запретов)

    # аналитика воды: river = (px,pz,ang,halfw), sea = (ang,dist)
    def set_water(self, river, sea):
        self.river, self.sea = river, sea

    def in_water(self, x, z, pad=8.0):
        if self.river:
            px, pz, ang, hw = self.river
            d = abs(-(x - px) * math.sin(ang) + (z - pz) * math.cos(ang))
            if d < hw + pad:
                return True
        if self.sea:
            ang, dist = self.sea
            if x * math.cos(ang) + z * math.sin(ang) > dist - pad - 14:
                return True
        return False

    def free(self, x, z, r):
        if abs(x) > 570 or abs(z) > 570 or self.in_water(x, z):
            return False
        for (bx, bz, br) in self.placed:
            dx, dz = x - bx, z - bz
            if dx * dx + dz * dz < (r + br) ** 2:
                return False
        return True

    def near_street(self, x, z, maxd):
        for (x1, z1, x2, z2, _w) in self.streets:
            dx, dz = x2 - x1, z2 - z1
            L2 = dx * dx + dz * dz
            t = 0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (z - z1) * dz) / L2))
            qx, qz = x1 + t * dx, z1 + t * dz
            if (x - qx) ** 2 + (z - qz) ** 2 < maxd * maxd:
                return True
        return False

    def add(self, typ, x, z, rot, sx, sz, h, r=None, solid=True):
        self.b.append([typ, round(x, 1), round(z, 1), round(rot, 3),
                       round(sx, 2), round(sz, 2), round(h, 2)])
        if solid:
            self.placed.append((x, z, r if r is not None else max(sx, sz) * 0.62 + 1.2))
        return len(self.b) - 1

    def street(self, x1, z1, x2, z2, w=6.0):
        self.streets.append([round(x1, 1), round(z1, 1),
                             round(x2, 1), round(z2, 1), round(w, 1)])

    # дома вдоль улицы по обе стороны
    def line_houses(self, x1, z1, x2, z2, typ, n, size, setback, jitter=1.5,
                    two_story=0.0, hbase=3.0):
        rng = self.rng
        ang = math.atan2(z2 - z1, x2 - x1)
        L = math.hypot(x2 - x1, z2 - z1)
        homes = []
        for i in range(n):
            t = (i + 0.5) / n
            side = 1 if i % 2 == 0 else -1
            px = x1 + (x2 - x1) * t - math.sin(ang) * side * setback
            pz = z1 + (z2 - z1) * t + math.cos(ang) * side * setback
            px += rng.uniform(-jitter, jitter)
            pz += rng.uniform(-jitter, jitter)
            sx = size[0] * rng.uniform(0.85, 1.2)
            sz = size[1] * rng.uniform(0.85, 1.2)
            if not self.free(px, pz, max(sx, sz) * 0.62 + 1.0):
                continue
            tt = typ
            hh = hbase * rng.uniform(0.92, 1.1)
            if typ == B_HOUSE and rng.random() < two_story:
                tt, hh = B_HOUSE2, hbase * 1.9
            rot = ang + (0 if side > 0 else math.pi) + rng.uniform(-0.09, 0.09)
            homes.append(self.add(tt, px, pz, rot, sx, sz, hh))
        return homes


def _layout_capital(rng, sc) -> _Town:
    t = _Town(rng)
    t.set_water(sc["_river"], sc["_sea"])
    hw = 178                                   # полустена
    cx, cz = 0, 6                              # центр города
    # стены: 4 стороны с зазорами ворот (юг и восток)
    gates = {"s": (cx, cz + hw), "e": (cx + hw, cz - 30)}
    seg = []
    # южная стена с воротами
    seg += [(cx - hw, cz + hw, gates["s"][0] - 11, cz + hw),
            (gates["s"][0] + 11, cz + hw, cx + hw, cz + hw)]
    seg += [(cx - hw, cz - hw, cx + hw, cz - hw)]              # север
    seg += [(cx - hw, cz - hw, cx - hw, cz + hw)]              # запад
    seg += [(cx + hw, cz - hw, cx + hw, gates["e"][1] - 11),   # восток
            (cx + hw, gates["e"][1] + 11, cx + hw, cz + hw)]
    for (x1, z1, x2, z2) in seg:
        L = math.hypot(x2 - x1, z2 - z1)
        ang = math.atan2(z2 - z1, x2 - x1)
        t.add(B_WALL, (x1 + x2) / 2, (z1 + z2) / 2, ang, L, 2.6, 7.5, r=0, solid=False)
    for (x, z) in [(cx - hw, cz - hw), (cx + hw, cz - hw), (cx - hw, cz + hw),
                   (cx + hw, cz + hw), (cx - hw, cz - 30), (cx, cz - hw)]:
        t.add(B_TOWER, x, z, 0, 7.5, 7.5, 11.5, r=5.5)
    t.add(B_GATE, gates["s"][0], gates["s"][1], 0, 24, 8, 10.5, r=0, solid=False)
    t.add(B_GATE, gates["e"][0], gates["e"][1], math.pi / 2, 24, 8, 10.5, r=0, solid=False)
    t.pois["gates"] = [list(gates["s"]), list(gates["e"])]

    # главная улица: от южных ворот к площади; вторая — от восточных ворот
    plaza = (cx, cz - 62)
    t.street(gates["s"][0], gates["s"][1] - 4, gates["s"][0], plaza[1] + 22, 9)
    t.street(gates["e"][0], gates["e"][1], cx - 120, gates["e"][1], 7)
    # переулки-решётка
    for zz in (-130, -20, 60, 118):
        t.street(cx - hw + 16, cz + zz, cx + hw - 16, cz + zz, 5)
    for xx in (-120, -58, 58, 120):
        t.street(cx + xx, cz - hw + 16, cx + xx, cz + hw - 16, 5)

    # площадь: колодец, монумент-стела, рынок
    t.placed.append((plaza[0], plaza[1], 30))       # держим площадь пустой
    t.add(B_WELL, plaza[0] - 10, plaza[1] + 6, 0, 3, 3, 2.6, r=2.6)
    if sc["set"].get("mon", 0) > 0:
        t.add(B_STELA, plaza[0] + 12, plaza[1] + 10, 0.3, 2.2, 2.2, 7.0, r=2.2)
    for i in range(4):
        t.add(B_MARKET, plaza[0] + 26 + (i % 2) * 9, plaza[1] - 8 + (i // 2) * 11,
              0.12, 6.5, 4.5, 3.4, r=4.2)
    # святилище с колоннадой к северу от площади
    temple = t.add(B_TEMPLE, cx, plaza[1] - 56, 0, 26, 34, 12, r=26)
    t.add(B_STELA, cx - 20, plaza[1] - 30, 0, 1.8, 1.8, 5.5, r=1.8)
    t.add(B_STELA, cx + 20, plaza[1] - 30, 0, 1.8, 1.8, 5.5, r=1.8)
    # факелы вдоль главной улицы и на площади
    for zz in range(plaza[1] + 30, int(cz + hw), 42):
        t.add(B_TORCH, cx - 6.5, zz, 0, 0.4, 0.4, 3.4, r=0.7)
        t.add(B_TORCH, cx + 6.5, zz + 21, 0, 0.4, 0.4, 3.4, r=0.7)
    t.add(B_TORCH, plaza[0] - 24, plaza[1], 0, 0.4, 0.4, 3.4, r=0.7)

    homes = []
    # дома вдоль переулков (двухэтажные ближе к центру)
    for (x1, z1, x2, z2, _w) in list(t.streets):
        n = int(math.hypot(x2 - x1, z2 - z1) / 11.0)
        near_c = math.hypot((x1 + x2) / 2 - cx, (z1 + z2) / 2 - plaza[1]) < 110
        homes += t.line_houses(x1, z1, x2, z2, B_HOUSE, n, (7.6, 6.4), 9.5,
                               two_story=0.55 if near_c else 0.22, hbase=3.5)
    # плотная досыпка внутри стен
    for _ in range(560):
        x = rng.uniform(cx - hw + 14, cx + hw - 14)
        z = rng.uniform(cz - hw + 14, cz + hw - 14)
        if t.near_street(x, z, 24) and t.free(x, z, 5.6):
            typ = B_HOUSE2 if rng.random() < 0.3 else B_HOUSE
            homes.append(t.add(typ, x, z, rng.uniform(0, math.pi),
                               rng.uniform(6.2, 8.6), rng.uniform(5.4, 7.4),
                               3.4 if typ == B_HOUSE else 6.6))
    # за стеной: дорога, поля, оливы, хутора
    t.street(gates["s"][0], gates["s"][1], gates["s"][0] + 40, 560, 8)
    for i in range(9):
        x = rng.uniform(-250, 250)
        z = rng.uniform(hw + 60, hw + 210)
        if t.free(x, z + 6, 22):
            f = t.add(B_FIELD, x, z, rng.uniform(-0.2, 0.2), rng.uniform(26, 40),
                      rng.uniform(18, 28), 0.4, r=20)
            t.pois["fields"].append([t.b[f][1], t.b[f][2]])
    for _ in range(7):
        x, z = rng.uniform(-340, 340), rng.uniform(hw + 40, hw + 260)
        if t.free(x, z, 7):
            homes.append(t.add(B_HUT, x, z, rng.uniform(0, 6.2), 3.4, 3.4, 3.1))
    t.pois.update({"well": [plaza[0] - 10, plaza[1] + 6], "plaza": list(plaza),
                   "temple": [cx, plaza[1] - 38], "market": [plaza[0] + 30, plaza[1] - 2]})
    t.pois["fires"] = [[plaza[0] + 8, plaza[1] - 16]]
    t.add(B_FIRE, plaza[0] + 8, plaza[1] - 16, 0, 1.6, 1.6, 0.5, r=1.8)
    t.homes, t.temple_i = homes, temple
    return t


def _layout_bronze(rng, sc) -> _Town:
    t = _Town(rng)
    t.set_water(sc["_river"], sc["_sea"])
    plaza = (0, 8)
    t.placed.append((plaza[0], plaza[1], 26))
    # улицы: к морю (восток), к полям (север), на юг
    t.street(plaza[0] + 18, plaza[1], 236, 44, 7)
    t.street(plaza[0], plaza[1] + 16, -26, 196, 6)
    t.street(plaza[0] - 16, plaza[1] - 6, -188, -74, 6)
    t.street(plaza[0] + 6, plaza[1] - 16, 44, -158, 6)
    # зиккуратоподобное святилище на западной стороне площади
    temple = t.add(B_TEMPLE, plaza[0] - 56, plaza[1] - 6, 0.06, 34, 30, 15.5, r=30)
    t.add(B_WELL, plaza[0] + 2, plaza[1] + 8, 0, 3, 3, 2.4, r=2.6)
    for i in range(3):
        t.add(B_MARKET, plaza[0] + 20 + (i % 2) * 9.5, plaza[1] - 14 + (i // 2) * 12,
              rng.uniform(-0.15, 0.15), 6.2, 4.4, 3.2, r=4.0)
    t.add(B_FIRE, plaza[0] + 12, plaza[1] + 18, 0, 1.5, 1.5, 0.5, r=1.7)
    t.pois["fires"].append([plaza[0] + 12, plaza[1] + 18])

    homes = []
    for (x1, z1, x2, z2, _w) in list(t.streets):
        n = int(math.hypot(x2 - x1, z2 - z1) / 10.5)
        homes += t.line_houses(x1, z1, x2, z2, B_HOUSE, n, (7.2, 8.6), 8.6, hbase=3.5)
    for _ in range(430):
        x, z = rng.uniform(-200, 190), rng.uniform(-170, 200)
        if t.near_street(x, z, 26) and t.free(x, z, 5.8):
            homes.append(t.add(B_HOUSE, x, z, rng.uniform(0, math.pi),
                               rng.uniform(6.0, 8.8), rng.uniform(6.8, 9.6), 3.5))
            # внутренний дворик у части домов
            if rng.random() < 0.35:
                bx, bz = t.b[homes[-1]][1], t.b[homes[-1]][2]
                a = t.b[homes[-1]][3]
                yx = bx + math.cos(a) * 8.5
                yz = bz + math.sin(a) * 8.5
                if t.free(yx, yz, 4.6):
                    t.add(B_YARD, yx, yz, a, 7.6, 7.2, 1.5, r=4.6)
    # амбары к северу
    for i in range(5):
        x, z = rng.uniform(-60, 30), rng.uniform(-150, -110)
        if t.free(x, z, 4):
            t.add(B_GRANARY, x, z, rng.uniform(0, 6.2), 3.6, 3.6, 3.4)
    # причал и лодки у берега моря
    t.add(B_JETTY, 246, 52, 0.05, 26, 3.4, 1.2, r=0, solid=False)
    for i in range(3):
        t.add(B_BOAT, 250 + rng.uniform(-8, 18), 78 + i * 16 + rng.uniform(-4, 4),
              rng.uniform(-0.5, 0.5), 6.4, 1.8, 1.0, r=0, solid=False)
    # поля — полоса орошения к северу, между городом и рекой
    for i in range(10):
        x = -230 + i * 46 + rng.uniform(-8, 8)
        z = rng.uniform(-232, -180)
        if t.free(x, z, 20):
            f = t.add(B_FIELD, x, z, rng.uniform(-0.12, 0.12),
                      rng.uniform(26, 40), rng.uniform(17, 24), 0.4, r=18)
            t.pois["fields"].append([t.b[f][1], t.b[f][2]])
    for i in range(2):
        x, z = rng.uniform(90, 170), rng.uniform(150, 220)
        if t.free(x, z, 16):
            t.add(B_PEN, x, z, rng.uniform(0, 3.1), 16, 12, 1.1, r=10)
    t.pois.update({"well": [plaza[0] + 2, plaza[1] + 8], "plaza": list(plaza),
                   "temple": [plaza[0] - 34, plaza[1] - 6],
                   "market": [plaza[0] + 24, plaza[1] - 8],
                   "jetty": [240, 52]})
    t.pois["gates"] = [[plaza[0], plaza[1] + 120]]
    t.homes, t.temple_i = homes, temple
    return t


def _layout_neolithic(rng, sc) -> _Town:
    t = _Town(rng)
    t.set_water(sc["_river"], sc["_sea"])
    c = (0, 0)
    t.placed.append((c[0], c[1], 15))
    t.add(B_FIRE, c[0], c[1], 0, 2.2, 2.2, 0.6, r=2.4)
    t.pois["fires"].append([c[0], c[1]])
    # тропы
    t.street(c[0], c[1], -196, 36, 4)     # к берегу моря (запад)
    t.street(c[0], c[1], 108, 132, 4)     # к полям (юго-восток)
    t.street(c[0], c[1], 36, -142, 4)     # к загонам (север)
    homes = []
    # кольца круглых мазанок вокруг очага
    for ring, (rad, n) in enumerate([(26, 8), (44, 11), (64, 11)]):
        for i in range(n):
            a = i / n * 2 * math.pi + rng.uniform(-0.18, 0.18) + ring * 0.35
            x = c[0] + math.cos(a) * rad * rng.uniform(0.9, 1.12)
            z = c[1] + math.sin(a) * rad * rng.uniform(0.9, 1.12)
            r = rng.uniform(2.6, 3.5)
            if t.free(x, z, r + 1.4):
                homes.append(t.add(B_HUT, x, z, rng.uniform(0, 6.2), r, r,
                                   r * rng.uniform(0.95, 1.1)))
    # шатры из шкур — юго-западный край
    for _ in range(5):
        x, z = rng.uniform(-120, -60), rng.uniform(50, 110)
        if t.free(x, z, 4.2):
            homes.append(t.add(B_TENT, x, z, rng.uniform(0, 6.2), 3.4, 3.4, 3.2))
    # малые костры у жилья
    for _ in range(2):
        x, z = rng.uniform(-70, 70), rng.uniform(-70, 70)
        if t.free(x, z, 2.4):
            t.add(B_FIRE, x, z, 0, 1.4, 1.4, 0.5, r=1.6)
            t.pois["fires"].append([x, z])
    # амбарчики на сваях — северный край
    for i in range(4):
        x, z = rng.uniform(20, 80), rng.uniform(-120, -86)
        if t.free(x, z, 3.4):
            t.add(B_GRANARY, x, z, rng.uniform(0, 6.2), 3.0, 3.0, 3.2)
    # столбы предков (культ предков — из летописи народа)
    for i in range(3):
        t.add(B_TOTEM, c[0] - 16 + i * 5.5, c[1] - 24 - (i % 2) * 3, 0, 0.8, 0.8,
              4.2 + (i % 2), r=1.2)
    # загоны
    for i in range(2):
        x, z = rng.uniform(60, 130), rng.uniform(-160, -110)
        if t.free(x, z, 12):
            t.add(B_PEN, x, z, rng.uniform(0, 3.1), 15, 11, 1.1, r=9)
    # поля-огороды
    for i in range(5):
        x, z = rng.uniform(90, 200), rng.uniform(90, 190)
        if t.free(x, z, 12):
            f = t.add(B_FIELD, x, z, rng.uniform(-0.3, 0.3), rng.uniform(15, 22),
                      rng.uniform(11, 16), 0.35, r=11)
            t.pois["fields"].append([t.b[f][1], t.b[f][2]])
    # берег: лодки и вешала для рыбы
    for i in range(2):
        t.add(B_BOAT, -232 - rng.uniform(0, 8), 30 + i * 16, rng.uniform(-0.6, 0.6),
              5.2, 1.5, 0.9, r=0, solid=False)
    t.add(B_BOAT, -207, 52, 0.9, 5.0, 1.5, 0.9, r=0, solid=False)
    for i in range(3):
        t.add(B_RACK, -202 + rng.uniform(-5, 5), 12 + i * 13, rng.uniform(-0.3, 0.3),
              4.2, 0.5, 2.9, r=2.2)
    # частокол, если народ его знает
    if sc.get("palisade"):
        rad = 96
        n = 44
        for i in range(n):
            a = i / n * 2 * math.pi
            if 1.35 < a < 1.75:      # проём-вход с юга
                continue
            t.add(B_WALL, math.cos(a) * rad, math.sin(a) * rad,
                  a + math.pi / 2, 2 * math.pi * rad / n + 0.4, 0.8, 3.0,
                  r=0, solid=False)
    t.pois.update({"well": t.pois["fires"][0], "plaza": [c[0], c[1] + 8],
                   "temple": [c[0] - 13, c[1] - 26],
                   "market": [c[0] + 10, c[1] + 4], "shore": [-216, 30]})
    t.pois["gates"] = [[c[0], 108]]
    t.homes, t.temple_i = homes, None
    return t


_LAYOUTS = {"capital": _layout_capital, "bronze": _layout_bronze,
            "neolithic": _layout_neolithic}


# ────────────────────────────────────────────────────────────────────────────
#  Жители
# ────────────────────────────────────────────────────────────────────────────
_GEN_ROLES = {  # роли сгенерированных общинников по эпохам (с весами)
    "capital": [("farmer", 3), ("artisan", 3), ("trader", 2), ("warrior", 2),
                ("priest", 1), ("commoner", 4), ("healer", 1), ("scribe", 1)],
    "bronze": [("farmer", 4), ("artisan", 2), ("trader", 1), ("commoner", 4),
               ("priest", 1), ("healer", 1), ("warrior", 1)],
    "neolithic": [("hunter", 3), ("farmer", 3), ("commoner", 4),
                  ("healer", 1), ("elder", 1), ("artisan", 1)],
}


def _top_traits(tr: dict, n=3):
    """Самые выраженные черты: дальше всего от середины 0.5."""
    items = sorted(tr.items(), key=lambda kv: -abs(kv[1] - 0.5))[:n]
    return [[TRAIT_RU.get(k, k), round(v, 2)] for k, v in items]


def _top_beliefs(bl: dict, n=2):
    items = sorted(bl.items(), key=lambda kv: -abs(kv[1] - 0.5))[:n]
    return [[BELIEF_RU.get(k, k), round(v, 2)] for k, v in items]


def _npc_from_person(p: dict, year: int) -> dict:
    age = p.get("age")
    if not age:
        end = p.get("died") or p.get("last_seen") or (p.get("born", year) + 40)
        age = end - p.get("born", year - 40)
    age = max(15, min(78, int(age)))
    tr = p.get("traits", {})
    life = p.get("life") or {}
    return {
        "name": p.get("name", "?"), "sex": int(p.get("sex", 1)),
        "role": p.get("role", "commoner"),
        "role_ru": ROLE_RU.get(p.get("role", "commoner"), "общинник"),
        "age": age, "real": 1, "born": p.get("born"),
        "traits": _top_traits(tr), "beliefs": _top_beliefs(p.get("beliefs", {})),
        "deeds": [{"y": d.get("year"), "t": d.get("text", "")}
                  for d in p.get("deeds", [])[:3]],
        "tr": {k: round(tr.get(k, 0.5), 2) for k in
               ("aggression", "piety", "curiosity", "sociability", "ambition")},
        "prestige": round(p.get("prestige", 0), 2),
        # прожитая жизнь: ремесло рук, следы пережитого, личная память
        "crafts": [[DOMAIN_RU.get(d, d), lvl] for d, lvl in (life.get("crafts") or [])],
        "scars": {SCAR_RU.get(k, k): v for k, v in (life.get("scars") or {}).items()},
        "memories": [{"y": m.get("year"), "k": MEM_RU.get(m.get("kind"), m.get("kind"))}
                     for m in (life.get("memories") or [])][-4:],
        "lore": life.get("lore", 0),
        "taught": life.get("taught", 0),
    }


def _gen_npc(rng: random.Random, lect, kind: str) -> dict:
    roles = _GEN_ROLES[kind]
    pool = [r for r, w in roles for _ in range(w)]
    role = rng.choice(pool)
    sex = rng.randint(0, 1)
    name = lect.person_name(rng, sex) if lect else f"Житель {rng.randint(2, 99)}"
    tr = {k: round(min(1, max(0, rng.gauss(0.5, 0.17))), 2) for k in
          ("aggression", "piety", "curiosity", "sociability", "ambition",
           "patience", "empathy", "diligence", "risk", "conformity")}
    bl = {k: round(min(1, max(0, rng.gauss(0.5, 0.16))), 2) for k in
          ("elsewhere", "danger", "novelty", "trust", "authority", "divine",
           "scarcity")}
    return {
        "name": name, "sex": sex, "role": role,
        "role_ru": ROLE_RU.get(role, "общинник"),
        "age": rng.randint(16, 68), "real": 0, "born": None,
        "traits": _top_traits(tr), "beliefs": _top_beliefs(bl), "deeds": [],
        "tr": {k: tr[k] for k in ("aggression", "piety", "curiosity",
                                  "sociability", "ambition")},
        "prestige": 0,
    }


def _routes(rng: random.Random, town: _Town, npcs: list[dict]):
    """Дом и дневной маршрут каждому жителю: дом → колодец/рынок/поле → дом."""
    homes = [i for i in town.homes] or [0]
    p = town.pois
    stops_all = [p.get("well"), p.get("market"), p.get("temple"),
                 p.get("plaza")] + p.get("fields", [])[:4] + \
                ([p.get("jetty")] if p.get("jetty") else []) + \
                ([p.get("shore")] if p.get("shore") else [])
    stops_all = [s for s in stops_all if s]
    for i, n in enumerate(npcs):
        hb = town.b[rng.choice(homes)]
        hx, hz = hb[1] + rng.uniform(-1, 1), hb[2] + rng.uniform(4, 6)
        n["home"] = [round(hx, 1), round(hz, 1)]
        k = 2 if rng.random() < 0.5 else 3
        picks = rng.sample(stops_all, min(k, len(stops_all)))
        if n["role"] in ("farmer", "hunter") and p.get("fields"):
            picks[0] = rng.choice(p["fields"])
        if n["role"] == "trader" and p.get("market"):
            picks[0] = p["market"]
        if n["role"] == "priest" and p.get("temple"):
            picks[0] = p["temple"]
        route = [n["home"]] + [[round(s[0] + rng.uniform(-4, 4), 1),
                                round(s[1] + rng.uniform(-4, 4), 1)] for s in picks]
        n["route"] = route
        n["phase"] = round(rng.random(), 2)
        n["night"] = "fire" if i < 3 and p["fires"] else "home"
        if n["night"] == "fire":
            f = rng.choice(p["fires"])
            n["nightpos"] = [round(f[0] + rng.uniform(-3, 3), 1),
                             round(f[1] + rng.uniform(-3, 3), 1)]


# ────────────────────────────────────────────────────────────────────────────
#  Летопись сцены
# ────────────────────────────────────────────────────────────────────────────
def _scene_events(chron, pid, year) -> list[dict]:
    ev = [e for e in chron if e.get("polity") == pid
          and year - PEOPLE_WINDOW <= e["year"] <= year]
    ev.sort(key=lambda e: -e.get("weight", 1))
    ev = ev[:EVENTS_PER_SCENE]
    ev.sort(key=lambda e: e["year"])
    return [{"y": e["year"], "k": e.get("kind", ""), "t": e.get("text", "")}
            for e in ev]


# ────────────────────────────────────────────────────────────────────────────
#  Сборка сцены
# ────────────────────────────────────────────────────────────────────────────
_TITLES = {"capital": "Столица державы", "bronze": "Городок бронзового века",
           "neolithic": "Неолитическая деревня"}


def _build_scene(data: dict, pick: dict, seed: int) -> dict:
    from terra.lang import Lect
    kind, snap, st, pol = pick["kind"], pick["snap"], pick["set"], pick["pol"]
    w = data["world"]
    rng = random.Random(seed)
    y, x = int(st["y"]), int(st["x"])
    year = snap["year"]
    riv = float(w.river[y, x])
    coastal = bool(w.coastal[y, x])
    keys = _known_keys(pol.get("tech", 10))
    garment = next((g for g in ("wool", "weave", "tailored_clothing", "hide_work")
                    if g in keys), "hide_work")

    sc = {
        "id": kind, "title": _TITLES[kind], "name": st["name"],
        "polity": pol["name"], "pid": pol["pid"],
        "color": pol.get("color", "#888"),
        "form_ru": FORM_RU.get(pol.get("form", ""), pol.get("form", "")),
        "mode_ru": MODE_RU.get(pol.get("mode", ""), pol.get("mode", "")),
        "era": pol.get("era", "?"), "year": year, "year_ru": _fmt_year(year),
        "pop": int(st["pop"]), "pop_ru": _fmt_pop(st["pop"]),
        "polity_pop": int(pol.get("pop", 0)),
        "polity_pop_ru": _fmt_pop(pol.get("pop", 0)),
        "tier": st.get("tier", ""), "capital_of": pol.get("capital"),
        "gods": pol.get("gods", [])[:4],
        "walls": 1 if st.get("walls", 0) > 0 else 0,
        "palisade": 1 if ("palisade" in keys and kind == "neolithic"
                          and st.get("walls", 0) == 0) else 0,
        "mon": int(st.get("mon", 0)),
        "biome": int(w.biome[y, x]),
        "biome_ru": BIOME_NAMES.get(int(w.biome[y, x]), "?"),
        "biome_color": BIOME_COLORS.get(int(w.biome[y, x]), "#888"),
        "lat": round(float(w.latitude[y, x]), 1),
        "rugg": round(float(w.ruggedness[y, x]), 2),
        "soil": round(float(w.soil[y, x]), 2),
        "river_v": round(riv, 2), "coastal": 1 if coastal else 0,
        "tech": int(pol.get("tech", 0)), "garment": garment,
        "seed": seed,
    }
    sc["palisade"] = 1 if ("palisade" in keys and kind == "neolithic") else 0

    # аналитика воды (метры сцены): река — линия, море — полуплоскость
    river = None
    if riv > RIVER_MIN:
        if kind == "capital":
            river = (0.0, -252.0, 0.12, 13 + riv * 22)
        elif kind == "bronze":
            river = (0.0, -286.0, -0.1, 12 + riv * 20)
        else:
            river = (0.0, 262.0, 0.1, 10 + riv * 16)
    sea = None
    if coastal:
        sea = (0.0, 258.0) if kind == "bronze" else (math.pi, 236.0)
    pick["_river"], pick["_sea"] = river, sea
    pick["palisade"] = sc["palisade"]
    sc["river"] = list(river) if river else None
    sc["sea"] = list(sea) if sea else None

    # планировка
    town = _LAYOUTS[kind](rng, {**pick, "set": st})
    sc["buildings"] = town.b
    sc["streets"] = town.streets
    sc["pois"] = town.pois

    # жители: реальные + порождённые языком народа
    lect = None
    ld = data["lects"].get(str(pol["pid"]))
    if ld:
        try:
            lect = Lect.from_dict(ld["lect"])
        except Exception:
            lect = None
    real = _people_near(data["people"], pol["pid"], year)
    real.sort(key=lambda p: -(p.get("prestige", 0) + 1.6 * p.get("power", 0)))
    seen_names, npcs = set(), []
    for p in real:
        if len(npcs) >= MAX_REAL:
            break
        if p.get("name") in seen_names:
            continue
        seen_names.add(p.get("name"))
        npcs.append(_npc_from_person(p, year))
    want = NPC_TOTAL[kind]
    guard = 0
    while len(npcs) < want and guard < want * 4:
        guard += 1
        n = _gen_npc(rng, lect, kind)
        if n["name"] in seen_names:
            continue
        seen_names.add(n["name"])
        npcs.append(n)
    _routes(rng, town, npcs)
    sc["npcs"] = npcs
    sc["events"] = _scene_events(data["chron"], pol["pid"], year)

    # карточка меню
    god_s = ", ".join(sc["gods"][:2]) if sc["gods"] else "—"
    geo = sc["biome_ru"]
    if sc["river"]:
        geo += ", у реки"
    if sc["coastal"]:
        geo += ", берег моря"
    sc["desc"] = (f"{st.get('tier', 'поселение').capitalize()} {st['name']} — "
                  f"{_fmt_pop(st['pop'])} жителей. "
                  f"{sc['form_ru'].capitalize()} {pol['name']} "
                  f"({sc['polity_pop_ru']} душ, {sc['mode_ru']}). "
                  f"Боги: {god_s}. {geo.capitalize()}, широта {sc['lat']:.0f}°.")
    return sc


# ────────────────────────────────────────────────────────────────────────────
#  three.js и HTML
# ────────────────────────────────────────────────────────────────────────────
def _three_source() -> str:
    here = Path(__file__).resolve().parent
    cands = [here.parent / "node_modules" / "three" / "build" / "three.cjs",
             Path.cwd() / "node_modules" / "three" / "build" / "three.cjs"]
    for c in cands:
        if c.exists():
            src = c.read_text(encoding="utf-8")
            return src.replace("</script", "<\\/script").replace("<!--", "<\\!--")
    raise FileNotFoundError("не найден node_modules/three/build/three.cjs")


def _render(payload: dict) -> str:
    data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data_js = data_js.replace("</script", "<\\/script")
    title = "TERRA · на земле · " + str(payload.get("run_id", ""))
    return ("<!DOCTYPE html>\n<html lang=\"ru\"><head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>" + title + "</title>\n<style>\n" + _CSS + "\n</style>\n"
            "</head>\n<body>\n" + _BODY + "\n"
            "<script>var module={exports:{}},exports=module.exports;\n"
            + _three_source() +
            "\nvar THREE=module.exports;module=undefined;exports=undefined;</script>\n"
            "<script>var PLAY=" + data_js + ";</script>\n"
            "<script>\n" + _APP_JS + "\n</script>\n</body></html>\n")


def build_scene_data(run_dir: str | Path, kinds: list | None = None) -> dict:
    """Собрать данные сцен прогона — общая точка для play.html и export_ue.

    Возвращает {"run_id": ..., "scenes": [сцена, ...]}: каждая сцена — тот же
    словарь, что вшивается в play.html (планировка, здания, улицы, жители,
    река/море, сид). Сид сцены канонический — по её месту в ПОЛНОМ списке
    (capital=11, bronze=12, neolithic=13), поэтому сцена собирается одинаково
    и в полном play.html, и при выборочном экспорте.

    kinds — оставить только эти сцены (подсписок ["capital","bronze","neolithic"]).
    """
    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"каталог прогона не найден: {run_dir}")
    data = _load(run_dir)
    picks = _pick_scenes(data)
    run_id = ""
    rj = run_dir / "run.json"
    if rj.exists():
        try:
            run_id = json.loads(rj.read_text(encoding="utf-8")).get("run_id", "")
        except Exception:
            pass
    scenes = [_build_scene(data, p, seed=11 + i)
              for i, p in enumerate(picks)
              if kinds is None or p["kind"] in kinds]
    return {"run_id": run_id or run_dir.name, "scenes": scenes}


def build_play(run_dir: str | Path, out_path: str | Path | None = None,
               scenes: list | None = None) -> Path:
    """Собрать игровой режим прогулки по поселениям прогона.

    run_dir  — каталог прогона; out_path — куда класть HTML
    scenes   — какие сцены включить: подсписок ["capital","bronze","neolithic"]
    """
    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"каталог прогона не найден: {run_dir}")
    out = Path(out_path) if out_path else run_dir / "play.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = build_scene_data(run_dir, kinds=scenes)
    html = _render(payload)
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size
    print(f"[play] {out}  ({size/1e6:.1f} МБ, сцен: {len(payload['scenes'])})")
    for s in payload["scenes"]:
        print(f"  · {s['title']}: {s['name']} ({s['polity']}, {s['year_ru']}), "
              f"зданий {len(s['buildings'])}, жителей {len(s['npcs'])}, "
              f"событий {len(s['events'])}")
    return out


# ── статические куски страницы (CSS/BODY) ──────────────────────────────────
_CSS = r"""
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;
 background:#07090d;font-family:Georgia,'Times New Roman',serif;color:#e8e0d0}
#c3d{position:fixed;inset:0;display:block}
.ov{position:fixed;inset:0;z-index:30}
/* ─ меню ─ */
#menu{background:radial-gradient(1200px 700px at 50% 20%,#1a2233 0%,#0a0d14 70%);
 display:flex;flex-direction:column;align-items:center;justify-content:center;gap:26px}
#menu h1{font-size:34px;letter-spacing:.16em;margin:0;color:#f0e6cf;font-weight:normal}
#menu .sub{color:#9aa3b5;font-size:14px;margin-top:-14px;letter-spacing:.06em}
#cards{display:flex;gap:20px;flex-wrap:wrap;justify-content:center;max-width:1200px}
.card{width:300px;background:linear-gradient(180deg,#141a26,#0e1119);
 border:1px solid #2a3347;border-radius:10px;padding:0 0 14px 0;cursor:pointer;
 transition:transform .15s,border-color .15s;overflow:hidden}
.card:hover{transform:translateY(-4px);border-color:#c9a35a}
.card .band{height:86px;position:relative;overflow:hidden}
.card h2{font-size:19px;margin:12px 14px 4px;color:#f0e6cf;font-weight:normal}
.card .when{color:#c9a35a;font-size:13px;margin:0 14px 8px;letter-spacing:.05em}
.card p{font-size:12.5px;line-height:1.5;color:#aeb6c6;margin:0 14px}
#menu .foot{color:#5d6579;font-size:12px;max-width:760px;text-align:center;line-height:1.6}
/* ─ HUD ─ */
#hud{position:fixed;left:14px;top:12px;z-index:20;pointer-events:none;
 text-shadow:0 1px 3px #000c}
#hud .place{font-size:20px;color:#f4ead2;letter-spacing:.04em}
#hud .line{font-size:13px;color:#cfd6e2;margin-top:3px}
#hud .line b{color:#e8d9ae;font-weight:normal}
#hint{position:fixed;right:14px;bottom:12px;z-index:20;font-size:12px;color:#98a1b3;
 text-align:right;line-height:1.65;text-shadow:0 1px 2px #000;pointer-events:none}
#hint b{color:#d8cba4;font-weight:normal}
#dot{position:fixed;left:50%;top:50%;width:4px;height:4px;margin:-2px;border-radius:50%;
 background:#fff9;z-index:18;box-shadow:0 0 3px #0008}
#talk{position:fixed;left:50%;bottom:13%;transform:translateX(-50%);z-index:20;
 font-size:15px;color:#f2e7c8;background:#10141dd0;padding:8px 18px;border-radius:20px;
 border:1px solid #3a445c;display:none;text-shadow:none}
#talk b{color:#ffd98a;font-weight:normal}
#menuBtn{position:fixed;right:14px;top:12px;z-index:21;background:#141a26cc;
 border:1px solid #303a52;color:#c9d0de;padding:5px 13px;border-radius:16px;
 font-size:12.5px;cursor:pointer;font-family:inherit}
#menuBtn:hover{border-color:#c9a35a;color:#f0e6cf}
#map{position:fixed;right:14px;top:52px;z-index:19;border:1px solid #3a4257;
 border-radius:8px;display:none;background:#0a0d13cc}
#pause{background:#060810d8;display:none;align-items:center;justify-content:center;
 flex-direction:column;gap:14px;text-align:center}
#pause .t{font-size:22px;color:#eee4c8}
#pause .s{font-size:13px;color:#9aa3b5;line-height:1.8}
/* ─ диалог ─ */
#dlg{background:#05070cd9;display:none;align-items:center;justify-content:center}
#dlgBox{width:min(940px,94vw);height:min(560px,88vh);display:flex;gap:0;
 background:#0f1420;border:1px solid #33405c;border-radius:12px;overflow:hidden}
#dcard{width:300px;min-width:240px;background:linear-gradient(180deg,#161d2c,#10141f);
 border-right:1px solid #27304a;padding:18px;overflow-y:auto}
#dcard h3{margin:2px 0 2px;font-size:21px;color:#f4e9cd;font-weight:normal}
#dcard .r{color:#c9a35a;font-size:13px;margin-bottom:10px}
#dcard .kv{font-size:12.5px;color:#aeb6c6;line-height:1.65}
#dcard .kv b{color:#dfe5ef;font-weight:normal}
#dcard .sec{margin-top:12px;font-size:11px;color:#7b849a;letter-spacing:.12em;
 text-transform:uppercase}
#dcard .chip{display:inline-block;background:#1c2436;border:1px solid #2e3a55;
 border-radius:10px;padding:2px 9px;margin:3px 3px 0 0;font-size:11.5px;color:#c6cdda}
#dcard .chip.scar{background:#2a1c1c;border-color:#553030;color:#e0b9b9}
#dcard .deed{font-size:12px;color:#b9c1cf;margin-top:5px;line-height:1.45;
 padding-left:10px;border-left:2px solid #3a4763}
#dcard .deed i{color:#8a93a8;font-style:normal}
#dright{flex:1;display:flex;flex-direction:column;min-width:0}
#dmsgs{flex:1;overflow-y:auto;padding:16px 18px;font-size:14px;line-height:1.55}
.msg{margin-bottom:12px;max-width:92%}
.msg .who{font-size:11px;color:#8a93a8;margin-bottom:2px;letter-spacing:.06em}
.msg .txt{background:#1a2234;border:1px solid #2b3550;border-radius:10px;
 padding:8px 12px;color:#e6ddc9;display:inline-block}
.msg.me{margin-left:auto;text-align:right}
.msg.me .txt{background:#243046;color:#dfe6f2}
.msg.err .txt{background:#3a1820;border-color:#7c2f3a;color:#f0b9b9}
#dtopics{display:flex;gap:7px;flex-wrap:wrap;padding:10px 14px;border-top:1px solid #222c44}
#dtopics button{background:#1b2334;border:1px solid #33405c;color:#d9d2bd;
 border-radius:16px;padding:6px 13px;font-size:12.5px;cursor:pointer;font-family:inherit}
#dtopics button:hover{border-color:#c9a35a;color:#ffedbe}
#dapi{padding:9px 14px 12px;border-top:1px solid #222c44;display:flex;gap:7px;
 flex-wrap:wrap;align-items:center}
#dapi input[type=password]{width:210px;background:#0c1019;border:1px solid #2b3550;
 color:#cfd6e2;border-radius:8px;padding:6px 9px;font-size:12px}
#dapi input[type=text]{flex:1;min-width:160px;background:#0c1019;
 border:1px solid #2b3550;color:#e8e0d0;border-radius:8px;padding:7px 10px;font-size:13px}
#dapi button{background:#243046;border:1px solid #33405c;color:#d9d2bd;border-radius:8px;
 padding:6px 14px;cursor:pointer;font-family:inherit;font-size:12.5px}
#dapi .note{width:100%;font-size:10.5px;color:#6d7689;line-height:1.45}
#dclose{position:absolute;right:0;top:0;background:none;border:none;color:#8a93a8;
 font-size:22px;cursor:pointer;padding:8px 14px}
#dclose:hover{color:#f0e6cf}
#dwrap{position:relative}
#fade{position:fixed;inset:0;background:#000;z-index:40;opacity:1;
 transition:opacity 1.1s;pointer-events:none}
#loading{position:fixed;inset:0;z-index:41;display:none;align-items:center;
 justify-content:center;color:#c9a35a;font-size:16px;letter-spacing:.2em;
 background:#07090d}
"""

_BODY = r"""
<canvas id="c3d"></canvas>
<div id="hud" style="display:none">
  <div class="place" id="hudPlace"></div>
  <div class="line" id="hudLine"></div>
  <div class="line" id="hudTime"></div>
</div>
<button id="menuBtn" style="display:none">&#9776; меню</button>
<canvas id="map" width="230" height="230"></canvas>
<div id="dot" style="display:none"></div>
<div id="talk"></div>
<div id="hint" style="display:none"></div>
<div id="menu" class="ov">
  <h1>TERRA &middot; НА ЗЕМЛЕ</h1>
  <div class="sub">спуститься в свой мир и пройти по нему</div>
  <div id="cards"></div>
  <div class="foot" id="menuFoot"></div>
</div>
<div id="pause" class="ov">
  <div class="t">Пауза</div>
  <div class="s" id="pauseText">Щёлкните, чтобы вернуться к прогулке</div>
</div>
<div id="dlg" class="ov"><div id="dwrap"><div id="dlgBox">
  <div id="dcard"></div>
  <div id="dright">
    <div id="dmsgs"></div>
    <div id="dtopics"></div>
    <div id="dapi">
      <input type="password" id="apiKey" placeholder="ключ Anthropic API (не обязательно)">
      <input type="text" id="apiMsg" placeholder="свой вопрос&hellip; (нужен ключ)" disabled>
      <button id="apiSend" disabled>Спросить</button>
      <div class="note">Ключ живёт только в памяти этой страницы, никуда не сохраняется
      и уходит лишь на api.anthropic.com при вашем вопросе.</div>
    </div>
  </div>
</div><button id="dclose">&times;</button></div></div>
<div id="loading">&hellip;&nbsp;МИР СОБИРАЕТСЯ&nbsp;&hellip;</div>
<div id="fade"></div>
"""

# JS-приложение подключается из соседней константы (ниже), чтобы файл читался
from terra._play_js import APP_JS as _APP_JS  # noqa: E402


def main():
    ap = argparse.ArgumentParser("terra.play")
    ap.add_argument("run", help="каталог прогона (runs/terra-1)")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--scenes", default=None,
                    help="через запятую: capital,bronze,neolithic")
    a = ap.parse_args()
    scenes = a.scenes.split(",") if a.scenes else None
    build_play(a.run, a.out, scenes)


if __name__ == "__main__":
    main()
