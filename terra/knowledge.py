"""
TERRA — эмерджентное познание.

Главный принцип: НЕТ дерева технологий.
Есть пространство физически возможного, заданное через аффордансы, материалы,
экологию и социальный масштаб. Открытие происходит, когда конкретный человек
с когнитивным досугом случайно нащупывает комбинацию, которая физически работает
ЗДЕСЬ и СЕЙЧАС. Порядок открытий — следствие географии, демографии и удачи,
а не сценария.

Поэтому:
  • земледелие может не появиться вовсе — если рядом нет крупносеменных злаков;
  • бронза может быть пропущена — если на материке нет олова, и народ уйдёт
    сразу от меди к железу или застрянет в камне;
  • письменность рождается только под давлением учёта, а не «по расписанию»;
  • знания ЗАБЫВАЮТСЯ, если носитель обеднел или вымер.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .contracts import (
    AFFORDANCES, DESERT, MEDITERRANEAN, MONTANE, SAVANNA, TEMPERATE_FOREST,
    TEMPERATE_GRASSLAND, TROPICAL_FOREST, TUNDRA, WETLAND, Tech,
)

AFF_IDX = {a: i for i, a in enumerate(AFFORDANCES)}


# ────────────────────────────────────────────────────────────────────────────
#  Каталог знаний
# ────────────────────────────────────────────────────────────────────────────
_CATALOG: list[Tech] = []
_BY_KEY: dict[str, Tech] = {}
_START: set[str] = set()


def T(key, name, era, *, gives=None, aff=None, mat=None, biome=(), pop=0.0,
      surplus=0.0, sed=0.0, diff=1.0, eff=None, lossy=0.5, start=False):
    t = Tech(
        tid=len(_CATALOG), key=key, name=name, era_hint=era,
        gives=gives or {}, needs_aff=aff or {}, needs_mat=mat or {},
        needs_biome=tuple(biome), needs_pop=pop, needs_surplus=surplus,
        needs_sedentism=sed, difficulty=diff, effects=eff or {}, lossy=lossy,
    )
    _CATALOG.append(t)
    _BY_KEY[key] = t
    if start:
        _START.add(key)
    return t


# ── I. То, что человечество уже принесло из палеолита (12 000 до н. э.) ──────
T("fire", "владение огнём", "палеолит", gives={"heat": 0.30},
  eff={"food": 0.14, "health": 0.05, "cold": 0.35}, lossy=0.01, start=True)
T("knapping", "оббивка камня", "палеолит", gives={"cut": 0.35, "pierce": 0.30},
  mat={"flint": 0.05}, eff={"food": 0.10, "military": 0.08}, lossy=0.02, start=True)
T("hafting", "насаживание на древко", "палеолит", gives={"bind": 0.25, "lever": 0.20},
  aff={"cut": 0.2}, eff={"food": 0.08, "military": 0.10}, lossy=0.05, start=True)
T("spear", "копьё", "палеолит", gives={"pierce": 0.4, "project": 0.15},
  aff={"bind": 0.2}, eff={"food": 0.10, "military": 0.15}, lossy=0.03, start=True)
T("cordage", "плетение верёвки", "палеолит", gives={"bind": 0.35, "weave": 0.20},
  eff={"carry": 0.1}, lossy=0.05, start=True)
T("hide_work", "выделка шкур", "палеолит", gives={"cure": 0.25, "contain": 0.15},
  aff={"cut": 0.25}, eff={"cold": 0.3, "carry": 0.1}, lossy=0.06, start=True)
T("shelter", "жилище", "палеолит", gives={"shelter": 0.3},
  aff={"bind": 0.2}, eff={"cold": 0.25, "health": 0.05}, lossy=0.05, start=True)
T("burial", "погребение", "палеолит", gives={"signal": 0.2, "organize": 0.10},
  eff={"cohesion": 0.05, "meaning": 0.2}, lossy=0.08, start=True)
T("ochre_art", "образ и знак", "палеолит", gives={"signal": 0.3, "record": 0.10},
  eff={"cohesion": 0.05, "meaning": 0.25}, lossy=0.1, start=True)
T("tally", "зарубки счёта", "палеолит", gives={"count": 0.2, "record": 0.15},
  aff={"cut": 0.2}, eff={"info": 0.05}, lossy=0.2, start=True)

# ── II. Верхнепалеолитическая доработка ─────────────────────────────────────
T("microlith", "микролиты и вкладыши", "мезолит", gives={"cut": 0.5, "pierce": 0.45},
  aff={"cut": 0.3, "bind": 0.3}, mat={"flint": 0.15}, diff=1.4,
  eff={"food": 0.10, "military": 0.06}, lossy=0.15)
T("atlatl", "копьеметалка", "палеолит", gives={"project": 0.4, "lever": 0.35},
  aff={"lever": 0.15, "pierce": 0.3}, diff=1.6, eff={"food": 0.12, "military": 0.15}, lossy=0.2)
T("bow", "лук и стрелы", "мезолит", gives={"project": 0.65, "lever": 0.4},
  aff={"bind": 0.3, "pierce": 0.35}, mat={"timber": 0.2}, diff=2.6,
  eff={"food": 0.18, "military": 0.30}, lossy=0.25)
T("net", "сеть", "мезолит", gives={"weave": 0.4, "contain": 0.3, "bind": 0.45},
  aff={"bind": 0.35}, diff=1.8, eff={"food": 0.14, "marine_bonus": 0.5}, lossy=0.2)
T("trap", "ловушки и силки", "мезолит", gives={"organize": 0.15},
  aff={"bind": 0.3}, diff=1.5, eff={"food": 0.12}, lossy=0.2)
T("fish_hook", "крючок и острога", "мезолит", gives={"pierce": 0.35},
  aff={"cut": 0.35, "bind": 0.3}, diff=1.6, eff={"marine_bonus": 0.6}, lossy=0.2)
T("basket", "корзина", "мезолит", gives={"contain": 0.4, "weave": 0.45, "store": 0.25, "bind": 0.4},
  aff={"weave": 0.18}, diff=1.5, eff={"carry": 0.25, "storage": 0.3}, lossy=0.15)
T("dugout", "долблёный чёлн", "мезолит", gives={"float": 0.35},
  aff={"cut": 0.4, "heat": 0.25}, mat={"timber": 0.35}, diff=2.2,
  eff={"sea": 0.25, "marine_bonus": 0.4, "trade_range": 0.2}, lossy=0.25)
T("sled_travois", "волокуша", "мезолит", gives={"carry": 0.35},
  aff={"bind": 0.3, "cut": 0.3}, diff=1.4, eff={"carry": 0.3}, lossy=0.2)
T("tailored_clothing", "шитая одежда", "мезолит", gives={"cure": 0.4, "weave": 0.3},
  aff={"pierce": 0.35, "cure": 0.25, "bind": 0.3}, diff=2.0, eff={"cold": 0.45, "health": 0.05}, lossy=0.2)
T("dog", "собака", "мезолит", gives={"organize": 0.12},
  aff={"organize": 0.1}, mat={"fauna_large": 0.15}, diff=2.5,
  eff={"food": 0.12, "military": 0.08, "safety": 0.15}, lossy=0.3)
T("smoke_dry", "копчение и сушка", "мезолит", gives={"store": 0.4, "cure": 0.35},
  aff={"heat": 0.3}, diff=1.6, eff={"storage": 0.5, "health": 0.03}, lossy=0.2)
T("pit_store", "яма-хранилище", "мезолит", gives={"store": 0.35, "contain": 0.25},
  aff={"contain": 0.12}, diff=1.5, eff={"storage": 0.5}, lossy=0.2)

# ── III. Оседлость и продовольствие ────────────────────────────────────────
T("sedentism", "оседлость", "неолит", gives={"shelter": 0.5, "organize": 0.25},
  aff={"store": 0.35, "shelter": 0.3}, pop=60, diff=2.2,
  eff={"sedentism": 0.5, "fertility": 0.25, "health": -0.06, "storage": 0.3}, lossy=0.35)
T("wild_harvest", "жатва диких злаков", "неолит", gives={"grind": 0.25, "store": 0.3},
  aff={"cut": 0.35, "contain": 0.3}, mat={"wild_grains": 0.30}, diff=1.8,
  eff={"food": 0.20, "sedentism": 0.2}, lossy=0.25)
T("quern", "зернотёрка", "неолит", gives={"grind": 0.45},
  aff={"cut": 0.3}, mat={"stone": 0.12}, diff=1.5, eff={"food": 0.10, "health": 0.04}, lossy=0.2)
T("cultivation", "возделывание", "неолит", gives={"irrigate": 0.15, "organize": 0.3, "predict": 0.2},
  aff={"grind": 0.3, "store": 0.35, "cut": 0.35}, mat={"wild_grains": 0.35, "soil": 0.35},
  pop=80, sed=0.3, diff=3.4, eff={"mode:horticulture": 1, "food": 0.25}, lossy=0.4)
T("root_cultivation", "клубневое хозяйство", "неолит", gives={"organize": 0.25, "irrigate": 0.1},
  aff={"cut": 0.35, "contain": 0.3}, mat={"wild_roots": 0.40}, pop=60, sed=0.25, diff=3.0,
  eff={"mode:horticulture": 1, "food": 0.18}, lossy=0.4)
T("pulses", "бобовые в поле", "неолит", gives={"predict": 0.15},
  aff={"organize": 0.25}, mat={"wild_pulses": 0.3}, diff=2.0,
  eff={"food": 0.12, "health": 0.08, "soil_restore": 0.3}, lossy=0.35)
T("domestication_plant", "одомашнивание растений", "неолит", gives={"predict": 0.35, "organize": 0.35},
  aff={"predict": 0.2, "organize": 0.3}, mat={"wild_grains": 0.3}, pop=150, sed=0.4, diff=3.6,
  eff={"food": 0.35, "yield": 0.4}, lossy=0.45)
T("herding", "приручение стада", "неолит", gives={"organize": 0.3, "carry": 0.2},
  aff={"organize": 0.2}, mat={"dom_herd": 0.35}, pop=60, diff=3.0,
  eff={"mode:pastoral": 1, "food": 0.22, "military": 0.08}, lossy=0.4)
T("dairy", "молочное хозяйство", "неолит", gives={"ferment": 0.3, "contain": 0.3},
  aff={"contain": 0.35}, mat={"dom_herd": 0.4}, diff=2.4, eff={"food": 0.20, "health": 0.05}, lossy=0.35)
T("wool", "шерсть и руно", "неолит", gives={"weave": 0.5, "bind": 0.6},
  aff={"weave": 0.35}, mat={"dom_herd": 0.4}, diff=2.2, eff={"cold": 0.3, "trade_good": 0.3}, lossy=0.3)
T("draft_animal", "тягловый скот", "неолит", gives={"traction": 0.55, "carry": 0.5},
  aff={"organize": 0.3}, mat={"dom_draft": 0.35}, diff=3.2,
  eff={"labor": 0.35, "carry": 0.5, "trade_range": 0.3}, lossy=0.4)
T("hoe", "мотыга", "неолит", gives={"lever": 0.35},
  aff={"cut": 0.4, "bind": 0.3}, diff=1.6, eff={"yield": 0.15}, lossy=0.25)
T("ard_plough", "соха", "неолит", gives={"traction": 0.6, "lever": 0.5},
  aff={"traction": 0.45, "cut": 0.45}, mat={"soil": 0.3}, sed=0.5, diff=3.0,
  eff={"mode:agrarian": 1, "yield": 0.45, "labor": 0.3}, lossy=0.45)
T("granary", "амбар", "неолит", gives={"store": 0.6, "contain": 0.5},
  aff={"store": 0.4, "shelter": 0.4}, sed=0.5, pop=200, diff=2.0,
  eff={"storage": 1.0, "famine_buffer": 0.5, "surplus_extract": 0.2}, lossy=0.4)
T("irrigation", "орошение", "неолит", gives={"irrigate": 0.6, "organize": 0.5, "measure": 0.25},
  aff={"organize": 0.4, "traction": 0.2}, mat={"river": 0.35}, pop=400, surplus=0.05, sed=0.6, diff=3.4,
  eff={"yield": 0.6, "admin": 0.35, "mode:intensive": 1}, lossy=0.6)
T("terrace", "террасирование", "античность", gives={"organize": 0.45, "measure": 0.2},
  aff={"organize": 0.4, "lever": 0.4}, biome=(MONTANE,), pop=500, surplus=0.06, diff=3.0,
  eff={"yield": 0.35, "montane_bonus": 0.6}, lossy=0.6)
T("rotation", "севооборот и пар", "античность", gives={"predict": 0.45},
  aff={"predict": 0.35, "count": 0.3}, sed=0.6, diff=2.6, eff={"yield": 0.3, "soil_restore": 0.5}, lossy=0.5)
T("manure", "унавоживание", "неолит", gives={"predict": 0.25},
  aff={"organize": 0.3}, mat={"dom_herd": 0.25}, sed=0.5, diff=1.8, eff={"yield": 0.2}, lossy=0.4)
T("orchard", "садоводство и прививка", "античность", gives={"predict": 0.4},
  aff={"predict": 0.3, "cut": 0.4}, sed=0.6, diff=2.6, eff={"food": 0.15, "trade_good": 0.35}, lossy=0.5)
T("beer", "брожение", "неолит", gives={"ferment": 0.5},
  aff={"contain": 0.4, "grind": 0.3}, diff=2.0, eff={"cohesion": 0.10, "trade_good": 0.2, "health": -0.02}, lossy=0.35)

# ── IV. Огонь высокой температуры ──────────────────────────────────────────
T("pottery", "керамика", "неолит", gives={"contain": 0.6, "heat": 0.45, "store": 0.45},
  aff={"heat": 0.3, "contain": 0.3}, mat={"clay": 0.25}, sed=0.35, diff=2.4,
  eff={"storage": 0.5, "health": 0.06, "food": 0.08, "trade_good": 0.2}, lossy=0.35)
T("kiln", "горн", "неолит", gives={"heat": 0.7, "smelt": 0.3},
  aff={"heat": 0.45, "shelter": 0.35}, mat={"clay": 0.3}, sed=0.5, pop=150, diff=2.8,
  eff={"labor": 0.1}, lossy=0.55)
T("brick", "сырцовый и обожжённый кирпич", "неолит", gives={"shelter": 0.6},
  aff={"heat": 0.5, "contain": 0.4}, mat={"clay": 0.35}, sed=0.55, pop=300, diff=2.2,
  eff={"defense": 0.25, "urban": 0.3}, lossy=0.5)
T("copper_native", "самородная медь", "халколит", gives={"smelt": 0.25, "cut": 0.4},
  aff={"heat": 0.4}, mat={"copper": 0.25}, diff=2.6, eff={"prestige_goods": 0.35}, lossy=0.5)
T("copper_smelt", "выплавка меди", "халколит", gives={"smelt": 0.5, "cut": 0.55, "pierce": 0.5},
  aff={"heat": 0.6, "smelt": 0.2}, mat={"copper": 0.30}, pop=250, surplus=0.03, diff=3.4,
  eff={"military": 0.15, "labor": 0.15, "prestige_goods": 0.4, "trade_good": 0.4}, lossy=0.65)
T("bronze_arsenic", "мышьяковистая бронза", "бронза", gives={"smelt": 0.6, "cut": 0.65},
  aff={"smelt": 0.45}, mat={"copper": 0.35}, diff=3.0,
  eff={"military": 0.2, "labor": 0.15, "health": -0.04}, lossy=0.65)
T("bronze_tin", "оловянная бронза", "бронза", gives={"smelt": 0.75, "cut": 0.75, "armor": 0.4},
  aff={"smelt": 0.5}, mat={"copper": 0.30, "tin": 0.20}, pop=600, surplus=0.05, diff=3.6,
  eff={"military": 0.35, "labor": 0.25, "prestige_goods": 0.5, "trade_range": 0.5}, lossy=0.7)
T("iron_bloom", "сыродутное железо", "железо", gives={"smelt": 0.85, "cut": 0.85, "armor": 0.5},
  aff={"heat": 0.75, "smelt": 0.6}, mat={"iron": 0.30}, pop=800, surplus=0.06, diff=4.2,
  eff={"military": 0.4, "labor": 0.45, "yield": 0.2}, lossy=0.7)
T("steel", "закалённая сталь", "железо", gives={"cut": 0.95, "armor": 0.7},
  aff={"smelt": 0.8, "measure": 0.3}, mat={"iron": 0.35, "coal": 0.1}, pop=2000, surplus=0.08, diff=4.6,
  eff={"military": 0.35, "labor": 0.3}, lossy=0.75)
T("bellows", "меха", "бронза", gives={"heat": 0.75, "propel": 0.25},
  aff={"heat": 0.5, "cure": 0.3}, diff=2.4, eff={"smelt_aid": 0.4}, lossy=0.6)
T("glass", "стекло", "античность", gives={"contain": 0.5, "measure": 0.2},
  aff={"heat": 0.7, "smelt": 0.4}, mat={"salt": 0.2}, surplus=0.07, diff=3.4,
  eff={"prestige_goods": 0.4, "trade_good": 0.4}, lossy=0.75)
T("charcoal", "углежжение", "бронза", gives={"heat": 0.6},
  aff={"heat": 0.4}, mat={"timber": 0.3}, diff=1.8, eff={"smelt_aid": 0.35, "deforest": 0.3}, lossy=0.5)
T("lime_plaster", "известь и штукатурка", "неолит", gives={"shelter": 0.45, "contain": 0.35},
  aff={"heat": 0.5}, mat={"stone": 0.3}, sed=0.5, diff=2.2, eff={"urban": 0.2, "health": 0.03}, lossy=0.5)

# ── V. Движение, вода, пространство ────────────────────────────────────────
T("plank_boat", "дощатая лодка", "неолит", gives={"float": 0.6},
  aff={"cut": 0.5, "bind": 0.45, "float": 0.3}, mat={"timber": 0.3}, diff=3.0,
  eff={"sea": 0.5, "trade_range": 0.45, "marine_bonus": 0.4}, lossy=0.55)
T("sail", "парус", "бронза", gives={"propel": 0.5, "float": 0.7},
  aff={"weave": 0.45, "float": 0.5}, diff=3.0, eff={"sea": 0.8, "trade_range": 0.8}, lossy=0.6)
T("keel_ship", "килевое судно", "античность", gives={"float": 0.85, "propel": 0.6},
  aff={"float": 0.7, "propel": 0.45, "measure": 0.3}, pop=1500, surplus=0.06, diff=3.8,
  eff={"sea": 1.2, "trade_range": 1.0, "military": 0.2}, lossy=0.7)
T("navigation", "навигация по звёздам", "античность", gives={"predict": 0.6, "measure": 0.5},
  aff={"predict": 0.4, "count": 0.4, "float": 0.5}, diff=3.4, eff={"sea": 0.7, "trade_range": 0.6}, lossy=0.7)
T("wheel", "колесо", "бронза", gives={"traction": 0.5, "carry": 0.6, "lever": 0.5},
  aff={"cut": 0.5, "lever": 0.4}, mat={"timber": 0.3}, sed=0.4, pop=300, diff=3.6,
  eff={"labor": 0.2, "carry": 0.4}, lossy=0.6)
T("cart", "повозка", "бронза", gives={"carry": 0.75},
  aff={"traction": 0.5, "carry": 0.55}, mat={"dom_draft": 0.3}, diff=2.4,
  eff={"trade_range": 0.5, "carry": 0.5, "admin": 0.15}, lossy=0.6)
T("chariot", "боевая колесница", "бронза", gives={"propel": 0.4},
  aff={"carry": 0.7, "traction": 0.55, "smelt": 0.4}, mat={"dom_draft": 0.4}, surplus=0.07, diff=3.4,
  eff={"military": 0.45, "inequality": 0.2}, lossy=0.75)
T("riding", "верховая езда", "бронза", gives={"propel": 0.55, "signal": 0.4},
  aff={"organize": 0.35}, mat={"dom_draft": 0.45}, diff=3.0,
  eff={"military": 0.4, "mobility": 0.6, "trade_range": 0.5, "admin": 0.25}, lossy=0.6)
T("road", "дороги", "античность", gives={"organize": 0.6, "measure": 0.35},
  aff={"organize": 0.5, "measure": 0.25}, pop=3000, surplus=0.08, diff=2.8,
  eff={"admin": 0.4, "trade_range": 0.6, "military": 0.15}, lossy=0.65)
T("bridge", "мост", "античность", gives={"lever": 0.6, "measure": 0.4},
  aff={"lever": 0.45, "measure": 0.3}, pop=1000, surplus=0.05, diff=2.6,
  eff={"trade_range": 0.25, "admin": 0.15}, lossy=0.6)
T("canal", "канал", "античность", gives={"irrigate": 0.75, "organize": 0.7},
  aff={"irrigate": 0.55, "organize": 0.55}, mat={"river": 0.3}, pop=5000, surplus=0.10, diff=3.6,
  eff={"yield": 0.3, "trade_range": 0.5, "admin": 0.3}, lossy=0.75)

# ── VI. Записанное и посчитанное ───────────────────────────────────────────
T("token_account", "счётные фишки", "неолит", gives={"count": 0.45, "record": 0.4},
  aff={"count": 0.25, "contain": 0.35}, sed=0.5, pop=400, surplus=0.04, diff=2.4,
  eff={"admin": 0.2, "trade": 0.2}, lossy=0.6)
T("proto_writing", "протописьмо", "бронза", gives={"record": 0.6, "signal": 0.5},
  aff={"record": 0.38, "count": 0.4}, pop=1200, surplus=0.05, sed=0.6, diff=3.2,
  eff={"admin": 0.35, "info": 0.35}, lossy=0.75)
T("writing", "письменность", "бронза", gives={"record": 0.85, "count": 0.6, "organize": 0.6},
  aff={"record": 0.55, "organize": 0.45}, pop=3000, surplus=0.07, sed=0.7, diff=4.0,
  eff={"admin": 0.6, "info": 0.8, "literacy": 0.15, "retention": 0.5}, lossy=0.8)
T("alphabet", "алфавит", "железо", gives={"record": 0.95},
  aff={"record": 0.8}, pop=2000, diff=3.2, eff={"literacy": 0.4, "info": 0.5, "admin": 0.2}, lossy=0.8)
T("numerals", "позиционный счёт", "античность", gives={"count": 0.8, "measure": 0.5},
  aff={"count": 0.5, "record": 0.6}, diff=3.2, eff={"admin": 0.3, "trade": 0.3, "info": 0.3}, lossy=0.8)
T("calendar", "календарь", "неолит", gives={"predict": 0.65, "measure": 0.45, "count": 0.5},
  aff={"count": 0.35, "predict": 0.3}, sed=0.4, pop=300, diff=2.8,
  eff={"yield": 0.15, "legitimacy": 0.15, "info": 0.2}, lossy=0.65)
T("geometry", "землемерие", "античность", gives={"measure": 0.8},
  aff={"measure": 0.45, "count": 0.6, "record": 0.6}, surplus=0.08, diff=3.4,
  eff={"admin": 0.3, "labor": 0.25, "yield": 0.1}, lossy=0.8)
T("astronomy", "астрономия", "античность", gives={"predict": 0.85, "measure": 0.7},
  aff={"predict": 0.55, "record": 0.6, "count": 0.6}, surplus=0.09, pop=5000, diff=3.8,
  eff={"legitimacy": 0.2, "sea": 0.3, "info": 0.3}, lossy=0.85)
T("archive", "архив и школа", "античность", gives={"record": 0.9, "organize": 0.7},
  aff={"record": 0.75, "organize": 0.6}, pop=6000, surplus=0.10, diff=3.0,
  eff={"retention": 0.9, "info": 0.6, "literacy": 0.25}, lossy=0.85)
T("codified_law", "писаный закон", "бронза", gives={"organize": 0.75},
  aff={"record": 0.6, "organize": 0.55}, pop=4000, diff=3.0,
  eff={"legitimacy": 0.3, "admin": 0.35, "cohesion": 0.15, "inequality": 0.1}, lossy=0.8)
T("coinage", "монета", "железо", gives={"count": 0.7, "signal": 0.6},
  aff={"smelt": 0.5, "count": 0.5, "measure": 0.4}, mat={"silver": 0.2}, pop=5000, surplus=0.08, diff=3.2,
  eff={"trade": 0.7, "admin": 0.3, "inequality": 0.15}, lossy=0.8)

# ── VII. Тело, болезнь, вещество ───────────────────────────────────────────
T("herbal", "траволечение", "мезолит", gives={"cure": 0.4, "record": 0.15},
  aff={"predict": 0.15}, diff=1.8, eff={"health": 0.10}, lossy=0.3)
T("midwifery", "родовспоможение", "неолит", gives={"cure": 0.45},
  aff={"cure": 0.3}, diff=2.0, eff={"fertility": 0.12, "health": 0.08}, lossy=0.35)
T("surgery", "хирургия и трепанация", "античность", gives={"cure": 0.65, "cut": 0.6},
  aff={"cure": 0.45, "cut": 0.55}, pop=2000, diff=3.2, eff={"health": 0.10}, lossy=0.7)
T("sanitation", "канализация и водовод", "античность", gives={"irrigate": 0.6, "organize": 0.6},
  aff={"organize": 0.55, "shelter": 0.5}, pop=8000, surplus=0.09, diff=3.4,
  eff={"health": 0.30, "urban": 0.6, "plague_resist": 0.4}, lossy=0.8)
T("soap", "мыло и щёлочь", "античность", gives={"cure": 0.5},
  aff={"heat": 0.5, "ferment": 0.35}, diff=2.4, eff={"health": 0.10, "plague_resist": 0.2}, lossy=0.6)
T("salting", "засол", "неолит", gives={"store": 0.55, "cure": 0.4},
  aff={"store": 0.35}, mat={"salt": 0.25}, diff=1.8, eff={"storage": 0.6, "trade_good": 0.5}, lossy=0.35)

# ── VIII. Общественные технологии (изобретаются так же, как вещи) ──────────
T("ritual_cycle", "годовой обряд", "мезолит", gives={"organize": 0.3, "signal": 0.45},
  aff={"signal": 0.25}, diff=1.6, eff={"cohesion": 0.20, "meaning": 0.3}, lossy=0.2)
T("ancestor_cult", "культ предков", "неолит", gives={"organize": 0.35, "signal": 0.5},
  aff={"signal": 0.35, "organize": 0.2}, diff=2.0,
  eff={"cohesion": 0.20, "legitimacy": 0.2, "property": 0.25}, lossy=0.3)
T("gift_exchange", "дарообмен", "мезолит", gives={"organize": 0.3, "count": 0.2},
  aff={"organize": 0.2}, diff=1.6, eff={"trade": 0.3, "cohesion": 0.1, "alliance": 0.3}, lossy=0.25)
T("exogamy_rule", "правила брака", "мезолит", gives={"organize": 0.35},
  aff={"organize": 0.25}, diff=1.8, eff={"alliance": 0.4, "health": 0.06, "cohesion": 0.1}, lossy=0.25)
T("property_norm", "право владения", "неолит", gives={"organize": 0.5, "count": 0.3},
  aff={"organize": 0.35, "store": 0.4}, sed=0.5, diff=2.4,
  eff={"inequality": 0.30, "surplus_extract": 0.3, "yield": 0.15}, lossy=0.5)
T("redistribution", "перераспределение", "неолит", gives={"organize": 0.55},
  aff={"organize": 0.45, "store": 0.5}, pop=400, surplus=0.04, diff=2.6,
  eff={"form:chiefdom": 1, "cohesion": 0.15, "legitimacy": 0.2, "admin": 0.2}, lossy=0.55)
T("priesthood", "жречество", "неолит", gives={"organize": 0.6, "predict": 0.4, "record": 0.3},
  aff={"signal": 0.5, "organize": 0.45}, pop=800, surplus=0.05, diff=2.8,
  eff={"legitimacy": 0.35, "inequality": 0.2, "info": 0.2, "complexity": 0.3}, lossy=0.6)
T("standing_war", "постоянная дружина", "бронза", gives={"organize": 0.6, "armor": 0.35},
  aff={"organize": 0.45, "armor": 0.2}, pop=1000, surplus=0.06, diff=2.8,
  eff={"military": 0.45, "inequality": 0.25, "complexity": 0.3, "surplus_extract": 0.3}, lossy=0.65)
T("tribute", "дань", "бронза", gives={"organize": 0.65, "count": 0.45},
  aff={"organize": 0.55, "count": 0.35}, pop=2000, surplus=0.06, diff=2.8,
  eff={"admin": 0.35, "surplus_extract": 0.5, "inequality": 0.25, "form:kingdom": 1}, lossy=0.7)
T("bureaucracy", "чиновничество", "бронза", gives={"organize": 0.85, "record": 0.7, "count": 0.6},
  aff={"record": 0.6, "organize": 0.65}, pop=8000, surplus=0.09, diff=3.4,
  eff={"admin": 0.8, "complexity": 0.5, "surplus_extract": 0.4, "form:empire": 1}, lossy=0.85)
T("assembly", "народное собрание", "железо", gives={"organize": 0.7},
  aff={"organize": 0.5, "signal": 0.5}, pop=2000, diff=3.0,
  eff={"legitimacy": 0.35, "cohesion": 0.2, "inequality": -0.15, "form:republic": 1}, lossy=0.7)
T("moralizing_god", "нравственное божество", "бронза", gives={"organize": 0.7, "signal": 0.75},
  aff={"signal": 0.6, "organize": 0.5}, pop=6000, diff=3.2,
  eff={"cohesion": 0.35, "legitimacy": 0.3, "scale": 0.5, "trade": 0.2}, lossy=0.75)
T("guild", "цех и ремесленная каста", "античность", gives={"organize": 0.6, "measure": 0.3},
  aff={"organize": 0.5}, pop=4000, surplus=0.08, diff=2.6,
  eff={"labor": 0.3, "info": 0.25, "retention": 0.3, "complexity": 0.25}, lossy=0.65)
T("slavery", "рабство", "бронза", gives={"organize": 0.5},
  aff={"organize": 0.4, "project": 0.25}, pop=1500, diff=2.0,
  eff={"labor": 0.45, "inequality": 0.45, "cohesion": -0.15, "surplus_extract": 0.35}, lossy=0.55)
T("market", "рынок", "железо", gives={"organize": 0.65, "count": 0.55},
  aff={"count": 0.45, "organize": 0.5}, pop=3000, surplus=0.07, diff=2.8,
  eff={"trade": 0.6, "labor": 0.2, "inequality": 0.15}, lossy=0.7)
T("credit", "долг и процент", "античность", gives={"count": 0.7, "record": 0.6},
  aff={"count": 0.6, "record": 0.55}, pop=6000, surplus=0.09, diff=3.0,
  eff={"trade": 0.4, "inequality": 0.25, "labor": 0.2}, lossy=0.8)
T("philosophy", "философия", "античность", gives={"predict": 0.6, "record": 0.7, "organize": 0.5},
  aff={"record": 0.7, "predict": 0.45}, pop=8000, surplus=0.11, diff=3.6,
  eff={"info": 0.5, "innovation": 0.35, "legitimacy": 0.1}, lossy=0.85)

# ── IX. Строительство и оборона ────────────────────────────────────────────
T("palisade", "частокол", "неолит", gives={"shelter": 0.45, "armor": 0.25},
  aff={"cut": 0.4, "bind": 0.35}, sed=0.4, pop=150, diff=1.8, eff={"defense": 0.35}, lossy=0.4)
T("megalith", "мегалит", "неолит", gives={"lever": 0.6, "measure": 0.35, "signal": 0.6},
  aff={"lever": 0.4, "organize": 0.4}, pop=500, surplus=0.05, diff=2.6,
  eff={"legitimacy": 0.25, "cohesion": 0.2, "meaning": 0.4}, lossy=0.6)
T("city_wall", "городская стена", "бронза", gives={"shelter": 0.7, "armor": 0.5},
  aff={"shelter": 0.55, "organize": 0.45}, pop=2500, surplus=0.06, diff=2.8,
  eff={"defense": 0.8, "urban": 0.3, "complexity": 0.2}, lossy=0.7)
T("monumental", "монументальное строительство", "бронза", gives={"lever": 0.75, "organize": 0.7, "measure": 0.5},
  aff={"lever": 0.55, "organize": 0.6, "measure": 0.35}, pop=5000, surplus=0.09, diff=3.2,
  eff={"legitimacy": 0.45, "inequality": 0.2, "meaning": 0.5, "complexity": 0.3}, lossy=0.75)
T("arch", "арка и свод", "античность", gives={"lever": 0.85, "shelter": 0.8},
  aff={"measure": 0.55, "lever": 0.6}, pop=6000, surplus=0.09, diff=3.4,
  eff={"urban": 0.5, "labor": 0.2, "defense": 0.2}, lossy=0.8)
T("concrete", "гидравлический раствор", "античность", gives={"shelter": 0.9},
  aff={"heat": 0.65, "measure": 0.5}, mat={"stone": 0.3}, pop=8000, surplus=0.10, diff=3.6,
  eff={"urban": 0.6, "defense": 0.3, "labor": 0.25}, lossy=0.85)
T("siege", "осадное дело", "античность", gives={"lever": 0.8, "project": 0.8},
  aff={"lever": 0.6, "project": 0.6, "measure": 0.4}, pop=5000, surplus=0.08, diff=3.2,
  eff={"military": 0.4, "siege": 0.7}, lossy=0.75)
T("crossbow", "самострел", "античность", gives={"project": 0.85, "lever": 0.6},
  aff={"project": 0.6, "smelt": 0.5, "lever": 0.5}, diff=3.2, eff={"military": 0.3, "defense": 0.25}, lossy=0.7)
T("composite_armor", "доспех", "бронза", gives={"armor": 0.7},
  aff={"smelt": 0.5, "cure": 0.4}, surplus=0.06, diff=2.6, eff={"military": 0.3, "inequality": 0.1}, lossy=0.65)

# ── X. Механика и энергия ──────────────────────────────────────────────────
T("lever_machine", "простые механизмы", "античность", gives={"lever": 0.7, "measure": 0.45},
  aff={"lever": 0.5, "measure": 0.35}, diff=2.6, eff={"labor": 0.3}, lossy=0.7)
T("pulley", "блок и полиспаст", "античность", gives={"lever": 0.8},
  aff={"lever": 0.6, "bind": 0.5}, diff=2.6, eff={"labor": 0.3, "sea": 0.2}, lossy=0.7)
T("watermill", "водяная мельница", "античность", gives={"propel": 0.7, "grind": 0.8},
  aff={"lever": 0.65, "grind": 0.5}, mat={"river": 0.35}, pop=4000, surplus=0.08, diff=3.4,
  eff={"labor": 0.5, "food": 0.1}, lossy=0.8)
T("windmill", "ветряная мельница", "средневековье", gives={"propel": 0.75, "grind": 0.8},
  aff={"propel": 0.5, "lever": 0.65, "weave": 0.5}, pop=4000, surplus=0.08, diff=3.4,
  eff={"labor": 0.45}, lossy=0.8)
T("horse_collar", "хомут", "средневековье", gives={"traction": 0.85},
  aff={"traction": 0.6, "cure": 0.4}, mat={"dom_draft": 0.4}, diff=2.4, eff={"yield": 0.3, "labor": 0.3}, lossy=0.7)
T("heavy_plough", "тяжёлый плуг", "средневековье", gives={"traction": 0.9, "lever": 0.7},
  aff={"traction": 0.7, "smelt": 0.7}, biome=(TEMPERATE_FOREST,), diff=3.0, eff={"yield": 0.5}, lossy=0.75)
T("paper", "бумага", "средневековье", gives={"record": 0.95, "weave": 0.6},
  aff={"weave": 0.5, "record": 0.7}, pop=8000, surplus=0.09, diff=3.4,
  eff={"info": 0.5, "literacy": 0.25, "admin": 0.2}, lossy=0.85)
T("printing", "печать", "средневековье", gives={"record": 1.0, "signal": 0.9},
  aff={"record": 0.9, "smelt": 0.6, "measure": 0.5}, pop=20000, surplus=0.12, diff=4.0,
  eff={"info": 1.0, "literacy": 0.6, "innovation": 0.5, "retention": 0.8}, lossy=0.9)
T("gunpowder", "порох", "средневековье", gives={"propel": 0.9, "project": 0.95},
  aff={"ferment": 0.5, "heat": 0.7, "measure": 0.5}, mat={"salt": 0.3}, pop=10000, surplus=0.10, diff=4.4,
  eff={"military": 0.6, "siege": 0.8}, lossy=0.85)
T("optics", "линзы", "средневековье", gives={"measure": 0.85, "predict": 0.7},
  aff={"measure": 0.6, "heat": 0.7}, pop=15000, surplus=0.12, diff=3.8,
  eff={"info": 0.4, "innovation": 0.4, "sea": 0.2}, lossy=0.9)
T("mech_clock", "механические часы", "средневековье", gives={"measure": 0.95, "count": 0.85},
  aff={"measure": 0.7, "smelt": 0.7, "lever": 0.7}, pop=15000, surplus=0.12, diff=4.0,
  eff={"labor": 0.25, "info": 0.3, "sea": 0.3}, lossy=0.9)
T("experiment", "опытный метод", "новое время", gives={"predict": 1.0, "measure": 0.9},
  aff={"predict": 0.75, "measure": 0.75, "record": 0.85}, pop=30000, surplus=0.14, diff=4.6,
  eff={"innovation": 1.2, "info": 0.8}, lossy=0.95)
T("steam", "паровая машина", "новое время", gives={"propel": 1.0, "heat": 1.0, "power": 0.70},
  aff={"propel": 0.8, "measure": 0.85, "smelt": 0.85, "predict": 0.8}, mat={"coal": 0.3},
  pop=60000, surplus=0.16, diff=5.0, eff={"labor": 1.5, "trade_range": 1.0, "urban": 0.8}, lossy=0.95)

# ────────────────────────────────────────────────────────────────────────────
#  X. Новое время: работа не из мышц, вещество на части, счёт без головы
#
#  Здесь ничего не «наступает по расписанию». Всё то же правило: нужны
#  аффордансы, материалы, масштаб связного населения и избыток, которым можно
#  кормить тех, кто не пашет. Народ без угля не построит паровой машины, народ
#  без чистого песка не выплавит стекла и не дойдёт до кремния, а народ без
#  школ не наберёт достаточно голов, чтобы держать всё это разом.
#
#  Отсюда же и то, ради чего всё затевалось: вселенные могут дойти до машин,
#  которые считают сами, — а могут не дойти никогда.
# ────────────────────────────────────────────────────────────────────────────

# ── сила ──
T("water_mill", "водяная мельница", "средневековье",
  gives={"power": 0.35, "grind": 0.85, "lever": 0.75},
  aff={"lever": 0.55, "traction": 0.4}, mat={"river": 0.35, "timber": 0.2},
  pop=1200, surplus=0.06, diff=2.8, eff={"labor": 0.45, "yield": 0.1}, lossy=0.55)
T("distillation", "перегонка", "средневековье",
  gives={"refine": 0.40, "ferment": 0.85, "cure": 0.7},
  aff={"ferment": 0.5, "heat": 0.75, "contain": 0.6}, pop=4000, surplus=0.08, diff=3.4,
  eff={"health": 0.2, "trade_good": 0.25}, lossy=0.75)
T("coke_iron", "кокс и чугун", "новое время",
  gives={"smelt": 1.0, "refine": 0.55, "heat": 1.0},
  aff={"smelt": 0.85, "refine": 0.35, "measure": 0.6}, mat={"coal": 0.35, "iron": 0.3},
  pop=40000, surplus=0.14, diff=4.6,
  eff={"labor": 0.7, "military": 0.4, "trade_good": 0.3}, lossy=0.9)
T("machine_tool", "станок", "новое время",
  gives={"precision": 0.55, "cut": 1.0, "measure": 1.0},
  aff={"power": 0.5, "smelt": 0.9, "measure": 0.85}, pop=50000, surplus=0.15, diff=4.8,
  eff={"labor": 0.8, "innovation": 0.4}, lossy=0.92)
T("steel_mass", "массовая сталь", "промышленная эпоха",
  gives={"smelt": 1.0, "armor": 1.0, "precision": 0.7},
  aff={"smelt": 1.0, "refine": 0.5, "precision": 0.45}, mat={"iron": 0.35, "coal": 0.3},
  pop=120000, surplus=0.18, diff=5.2,
  eff={"labor": 0.9, "military": 0.5, "urban": 0.6, "trade_good": 0.35}, lossy=0.95)
T("railway", "железная дорога", "промышленная эпоха",
  gives={"carry": 1.0, "propel": 1.0, "organize": 0.9},
  aff={"power": 0.65, "smelt": 0.95, "precision": 0.5}, mat={"iron": 0.3, "coal": 0.3},
  pop=200000, surplus=0.18, diff=5.0,
  eff={"trade_range": 1.4, "admin": 0.7, "military": 0.4, "urban": 0.5}, lossy=0.95)
T("steam_ship", "пароход", "промышленная эпоха",
  gives={"float": 1.0, "propel": 1.0},
  aff={"power": 0.65, "float": 0.8, "precision": 0.45}, mat={"coal": 0.3},
  pop=150000, surplus=0.17, diff=4.9,
  eff={"sea": 1.0, "trade_range": 1.2, "military": 0.35}, lossy=0.95)
T("interchangeable", "взаимозаменяемая деталь", "промышленная эпоха",
  gives={"precision": 0.80, "organize": 0.95},
  aff={"precision": 0.55, "measure": 0.95, "organize": 0.7}, pop=150000, surplus=0.18,
  diff=4.7, eff={"labor": 0.9, "military": 0.4}, lossy=0.92)
T("chemistry", "химия", "промышленная эпоха",
  gives={"refine": 0.78, "predict": 1.0, "cure": 0.9},
  aff={"refine": 0.5, "predict": 0.95, "measure": 0.9}, pop=120000, surplus=0.18, diff=5.4,
  eff={"innovation": 0.8, "health": 0.35, "trade_good": 0.3}, lossy=0.95)
T("electric_generator", "электрическая машина", "промышленная эпоха",
  gives={"power": 0.92, "signal": 1.0, "transmit": 0.35},
  aff={"power": 0.7, "precision": 0.6, "predict": 0.95},
  mat={"copper": 0.3, "iron": 0.25}, pop=250000, surplus=0.20, diff=5.6,
  eff={"labor": 1.2, "urban": 0.7, "info": 0.4}, lossy=0.96)
T("telegraph", "телеграф", "промышленная эпоха",
  gives={"transmit": 0.55, "signal": 1.0, "record": 1.0},
  aff={"power": 0.55, "signal": 0.9, "record": 0.9}, mat={"copper": 0.28},
  pop=200000, surplus=0.18, diff=4.8,
  eff={"admin": 0.9, "trade": 0.5, "info": 0.6, "military": 0.3}, lossy=0.94)
T("oil_refining", "нефтепереработка", "промышленная эпоха",
  gives={"refine": 0.95, "heat": 1.0},
  aff={"refine": 0.7, "heat": 0.95, "measure": 0.9}, mat={"oil": 0.3},
  pop=200000, surplus=0.19, diff=5.2,
  eff={"labor": 0.6, "trade_good": 0.5, "innovation": 0.3}, lossy=0.95)
T("combustion_engine", "двигатель внутреннего сгорания", "современность",
  gives={"power": 1.0, "propel": 1.0, "traction": 1.0},
  aff={"refine": 0.85, "precision": 0.7, "power": 0.8}, mat={"oil": 0.3},
  pop=400000, surplus=0.20, diff=5.6,
  eff={"labor": 1.3, "trade_range": 1.2, "military": 0.6, "mobility": 0.8}, lossy=0.96)
T("electrolysis", "электролиз", "современность",
  gives={"refine": 1.0, "smelt": 1.0},
  aff={"power": 0.85, "refine": 0.7}, mat={"bauxite": 0.25},
  pop=350000, surplus=0.20, diff=5.5,
  eff={"trade_good": 0.4, "labor": 0.4, "innovation": 0.3}, lossy=0.96)
T("fertilizer", "связанный азот", "современность",
  gives={"irrigate": 1.0, "refine": 1.0},
  aff={"refine": 0.8, "power": 0.8, "predict": 1.0}, pop=400000, surplus=0.20, diff=5.8,
  eff={"mode:mechanized": 1.0, "yield": 1.3, "food": 0.6, "famine_buffer": 0.6},
  lossy=0.96)
T("power_grid", "энергосеть", "современность",
  gives={"power": 1.0, "transmit": 0.6},
  aff={"power": 0.92, "organize": 0.95, "precision": 0.7}, mat={"copper": 0.3},
  pop=600000, surplus=0.22, diff=5.4,
  eff={"labor": 1.1, "urban": 1.0, "complexity": 0.4, "health": 0.2}, lossy=0.97)

# ── здоровье и население: то, что переломило демографию ──
T("germ_theory", "теория заражения", "промышленная эпоха",
  gives={"cure": 1.0, "predict": 1.0},
  aff={"predict": 0.95, "measure": 0.9, "refine": 0.5}, pop=150000, surplus=0.18, diff=5.2,
  eff={"health": 1.2, "plague_resist": 1.0, "urban": 0.4}, lossy=0.95)
T("vaccination", "прививка", "промышленная эпоха",
  gives={"cure": 1.0},
  aff={"cure": 0.9, "predict": 0.9}, pop=200000, surplus=0.18, diff=5.0,
  eff={"health": 1.0, "plague_resist": 1.2}, lossy=0.94)
T("antibiotics", "антибиотики", "современность",
  gives={"cure": 1.0},
  aff={"cure": 1.0, "refine": 0.8, "predict": 1.0}, pop=500000, surplus=0.21, diff=5.7,
  eff={"health": 1.4, "plague_resist": 1.0}, lossy=0.96)
T("public_health", "общественное здравоохранение", "современность",
  gives={"organize": 1.0, "cure": 1.0},
  aff={"cure": 0.95, "organize": 0.9, "record": 0.9},
  pop=800000, surplus=0.22, diff=5.0,
  eff={"health": 1.0, "plague_resist": 0.8, "admin": 0.5, "urban": 0.4}, lossy=0.95)
T("mass_schooling", "всеобщая школа", "современность",
  gives={"record": 1.0, "count": 1.0, "organize": 1.0},
  aff={"record": 1.0, "organize": 0.9}, pop=500000, surplus=0.20, diff=4.6,
  eff={"literacy": 1.4, "info": 0.9, "retention": 1.2, "innovation": 0.5,
       "complexity": 0.3}, lossy=0.93)
# Демографический переход: когда дети перестают умирать, а женщины идут учиться
# и работать, семьи становятся маленькими. Это не «политика» — это то, что
# происходит с людьми, и без этого население мира ушло бы в бессмыслицу.
T("family_planning", "планирование семьи", "современность",
  gives={"cure": 1.0, "count": 1.0},
  aff={"cure": 0.95, "record": 1.0, "refine": 0.8},
  pop=1500000, surplus=0.22, diff=4.8,
  eff={"fertility": -2.6, "health": 0.4}, lossy=0.9)

# ── счёт без головы ──
T("mech_calculator", "счётная машина", "новое время",
  gives={"compute": 0.35, "count": 1.0},
  aff={"precision": 0.5, "count": 0.85, "measure": 0.9}, pop=60000, surplus=0.16, diff=4.6,
  eff={"admin": 0.4, "info": 0.4, "innovation": 0.25}, lossy=0.9)
T("statistics", "статистика", "промышленная эпоха",
  gives={"compute": 0.5, "predict": 1.0, "count": 1.0},
  aff={"compute": 0.3, "predict": 0.95, "record": 0.95}, pop=200000, surplus=0.18, diff=4.8,
  eff={"admin": 0.8, "info": 0.6, "health": 0.2, "innovation": 0.4}, lossy=0.93)
T("radio", "радио", "современность",
  gives={"transmit": 0.9, "signal": 1.0},
  aff={"power": 0.85, "transmit": 0.5, "predict": 1.0}, mat={"copper": 0.3},
  pop=500000, surplus=0.20, diff=5.4,
  eff={"info": 1.0, "admin": 0.6, "cohesion": 0.4, "military": 0.4}, lossy=0.96)
T("semiconductor", "полупроводник", "информационная эпоха",
  gives={"compute": 0.75, "precision": 0.95},
  aff={"refine": 1.0, "precision": 0.75, "predict": 1.0}, mat={"silica": 0.3},
  pop=1000000, surplus=0.23, diff=6.0,
  eff={"innovation": 0.9, "info": 0.6}, lossy=0.97)
T("computer", "вычислительная машина", "информационная эпоха",
  gives={"compute": 0.92, "count": 1.0, "record": 1.0},
  aff={"compute": 0.7, "power": 0.9, "precision": 0.9}, pop=2000000, surplus=0.24, diff=6.2,
  eff={"admin": 1.2, "info": 1.2, "innovation": 1.0, "complexity": 0.5}, lossy=0.97)
T("network", "сеть", "информационная эпоха",
  gives={"transmit": 1.0, "compute": 0.95, "organize": 1.0},
  aff={"compute": 0.85, "transmit": 0.85, "organize": 0.95}, pop=4000000, surplus=0.25,
  diff=6.0, eff={"info": 1.5, "trade": 0.8, "admin": 0.8, "innovation": 1.0,
                 "cohesion": -0.2}, lossy=0.97)
T("automation", "автоматизация", "информационная эпоха",
  gives={"precision": 1.0, "power": 1.0, "organize": 1.0},
  aff={"compute": 0.85, "precision": 0.9, "power": 0.95}, pop=3000000, surplus=0.25,
  diff=5.9, eff={"labor": 1.6, "yield": 0.5, "inequality": 0.4}, lossy=0.97)
T("machine_learning", "обучающаяся машина", "информационная эпоха",
  gives={"compute": 1.0, "predict": 1.0},
  aff={"compute": 0.92, "predict": 1.0, "record": 1.0}, pop=8000000, surplus=0.26,
  diff=6.4, eff={"innovation": 1.4, "info": 1.0, "admin": 0.6}, lossy=0.98)
# Здесь заканчивается то, что мы про себя знаем, и начинается то, ради чего
# затевалась мультивселенная: как ЭТО пройдёт в мире, который прожил свою,
# а не нашу историю.
T("artificial_mind", "искусственный разум", "информационная эпоха",
  gives={"compute": 1.0, "predict": 1.0, "organize": 1.0},
  aff={"compute": 1.0, "predict": 1.0, "organize": 1.0}, pop=20000000, surplus=0.28,
  diff=7.0, eff={"innovation": 2.0, "admin": 1.5, "labor": 1.2, "info": 1.2,
                 "complexity": 0.8}, lossy=0.99)

# ── полёт, высота, сила недр ──
T("aviation", "авиация", "современность",
  gives={"propel": 1.0, "float": 1.0, "carry": 1.0},
  aff={"power": 0.95, "precision": 0.8, "refine": 0.9}, mat={"bauxite": 0.25, "oil": 0.25},
  pop=1000000, surplus=0.23, diff=5.9,
  eff={"trade_range": 1.3, "military": 0.9, "mobility": 1.0}, lossy=0.97)
T("reinforced_concrete", "железобетон", "современность",
  gives={"shelter": 1.0, "lever": 1.0},
  aff={"smelt": 1.0, "precision": 0.6, "measure": 0.95}, mat={"stone": 0.3, "iron": 0.3},
  pop=400000, surplus=0.20, diff=4.9,
  eff={"urban": 1.2, "labor": 0.4, "defense": 0.5}, lossy=0.95)
T("high_rise", "высотный город", "современность",
  gives={"shelter": 1.0, "organize": 1.0},
  aff={"shelter": 0.95, "power": 0.9, "precision": 0.75}, pop=2000000, surplus=0.24,
  diff=5.2, eff={"urban": 1.6, "complexity": 0.5, "inequality": 0.3}, lossy=0.96)
T("nuclear_fission", "расщепление ядра", "информационная эпоха",
  gives={"power": 1.0, "heat": 1.0, "project": 1.0},
  aff={"refine": 1.0, "predict": 1.0, "compute": 0.6, "precision": 0.9},
  mat={"uranium": 0.25}, pop=5000000, surplus=0.26, diff=6.8,
  eff={"labor": 0.9, "military": 1.5, "complexity": 0.5}, lossy=0.98)
T("spaceflight", "космический полёт", "информационная эпоха",
  gives={"propel": 1.0, "transmit": 1.0, "predict": 1.0},
  aff={"power": 1.0, "compute": 0.85, "precision": 0.95, "refine": 1.0},
  pop=10000000, surplus=0.27, diff=6.6,
  eff={"info": 0.8, "military": 0.6, "innovation": 0.7, "legitimacy": 0.3}, lossy=0.98)

MODE_UNLOCK = {k: v for t in _CATALOG for k, v in ()}  # заполняется ниже
N_TECH = len(_CATALOG)
CATALOG = _CATALOG
BY_KEY = _BY_KEY
STARTING = frozenset(_START)
STARTING_IDS = frozenset(_BY_KEY[k].tid for k in _START)

# предвычисленные матрицы для скорости
_GIVES = np.zeros((N_TECH, len(AFFORDANCES)), dtype=np.float32)
_NEEDS = np.zeros((N_TECH, len(AFFORDANCES)), dtype=np.float32)
for t in _CATALOG:
    for a, v in t.gives.items():
        _GIVES[t.tid, AFF_IDX[a]] = v
    for a, v in t.needs_aff.items():
        _NEEDS[t.tid, AFF_IDX[a]] = v
_DIFF = np.array([t.difficulty for t in _CATALOG], dtype=np.float32)
_POP = np.array([t.needs_pop for t in _CATALOG], dtype=np.float32)
_SUR = np.array([t.needs_surplus for t in _CATALOG], dtype=np.float32)
_SED = np.array([t.needs_sedentism for t in _CATALOG], dtype=np.float32)
_LOSSY = np.array([t.lossy for t in _CATALOG], dtype=np.float32)
_MATKEYS = sorted({k for t in _CATALOG for k in t.needs_mat})
_MAT = np.zeros((N_TECH, len(_MATKEYS)), dtype=np.float32)
_MI = {k: i for i, k in enumerate(_MATKEYS)}
for t in _CATALOG:
    for k, v in t.needs_mat.items():
        _MAT[t.tid, _MI[k]] = v
_BIOME_REQ = [t.needs_biome for t in _CATALOG]
MAT_KEYS = _MATKEYS

EFF_KEYS = sorted({k for t in _CATALOG for k in t.effects})
_EI = {k: i for i, k in enumerate(EFF_KEYS)}
_EFF = np.zeros((N_TECH, len(EFF_KEYS)), dtype=np.float32)
for t in _CATALOG:
    for k, v in t.effects.items():
        _EFF[t.tid, _EI[k]] = v

# ── чьими руками держится знание ────────────────────────────────────────────
# Каждое умение народа кто-то физически умеет. Здесь — к какому людскому делу
# (домену мастерства из agents.DOMAINS) относится каждое знание: если умирают
# последние мастера этого дела, знание перестаёт быть живым.
# Домен выбирается по весу: чему знание служит сильнее всего — и что при этом
# делают руки. Не «правило поверх правила», а взвешенный максимум.
_DOM_EFFECT_W = {
    "war": {"military": 1.0, "siege": 1.3, "defense": 0.9},
    "letters": {"literacy": 1.6, "info": 1.1, "retention": 1.3},
    "heal": {"health": 1.0, "plague_resist": 1.5},
    "trade": {"trade": 1.2, "trade_range": 1.1, "trade_good": 0.9,
              "prestige_goods": 0.8},
    "ritual": {"legitimacy": 1.45, "meaning": 1.9, "cohesion": 1.1},
    "rule": {"admin": 1.2, "complexity": 1.0, "surplus_extract": 1.0,
             "scale": 1.0, "inequality": 0.35},
    "build": {"labor": 1.0, "urban": 1.3, "defense": 0.5},
    "farm": {"yield": 1.3, "fertility": 1.0, "soil_restore": 1.0, "food": 0.75,
             "storage": 0.9, "famine_buffer": 1.0, "mode:horticulture": 1.3,
             "mode:agrarian": 1.3, "mode:intensive": 1.3, "mode:pastoral": 1.3},
    "forage": {"marine_bonus": 1.3, "mobility": 0.7, "sea": 0.9},
}
# ремесло опознаётся не по пользе для общества, а по тому, ЧТО делают руки
_DOM_GIVES_W = {
    "craft": {"smelt": 1.7, "cure": 1.1, "weave": 1.1, "ferment": 1.1,
              "heat": 0.9, "grind": 0.7, "contain": 0.95, "cut": 0.35,
              "bind": 0.35},
    "ritual": {"signal": 0.7},
    "heal": {"cure": 0.4},
    "build": {"lever": 0.7, "shelter": 0.8, "traction": 0.5},
    "letters": {"record": 1.4, "count": 1.2, "measure": 0.9, "predict": 1.0},
    "war": {"project": 0.8, "armor": 1.0, "pierce": 0.4},
    "forage": {"float": 0.6, "propel": 0.5},
    "farm": {"irrigate": 1.2, "store": 0.5},
    "rule": {"organize": 1.2, "signal": 0.6},
    "trade": {"carry": 0.6},
}
_DOM_NAMES = tuple(sorted(set(_DOM_EFFECT_W) | set(_DOM_GIVES_W)))

TECH_DOMAIN = ["craft"] * N_TECH
for _t in _CATALOG:
    _best, _bs = "craft", 0.30          # порог: иначе всё безымянное — ремесло
    for _d in _DOM_NAMES:
        _s = sum(w * float(_t.effects.get(k, 0.0))
                 for k, w in _DOM_EFFECT_W.get(_d, {}).items())
        _s += sum(w * float(_t.gives.get(a, 0.0))
                  for a, w in _DOM_GIVES_W.get(_d, {}).items())
        if _s > _bs:
            _best, _bs = _d, _s
    TECH_DOMAIN[_t.tid] = _best


def forget_domain(rep: "Repertoire", domain: str, strength: float = 0.3) -> None:
    """Умер последний мастер — знания этого дела теряют хватку.

    Не стирает знание разом: подтачивает хватку, а добьёт обычное забвение.
    Так и выглядит настоящая утрата ремесла — не событие, а вымирание рук.
    """
    if strength <= 0 or not rep.known.any():
        return
    sel = np.array([i for i in range(N_TECH)
                    if TECH_DOMAIN[i] == domain and rep.known[i]], dtype=np.int64)
    if sel.size == 0:
        return
    rep.grip[sel] = np.maximum(0.0, rep.grip[sel]
                               - float(strength) * (0.35 + 0.65 * _LOSSY[sel]))
    rep.touch()


# ────────────────────────────────────────────────────────────────────────────
#  Состояние знаний народа
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class Repertoire:
    """Что народ умеет и насколько крепко это держится."""
    known: np.ndarray = field(default_factory=lambda: np.zeros(N_TECH, dtype=bool))
    grip: np.ndarray = field(default_factory=lambda: np.zeros(N_TECH, dtype=np.float32))
    # grip — «укоренённость»: сколько носителей/поколений владеют. <0.15 → риск утраты
    discovered_by: dict = field(default_factory=dict)     # tid -> (year, aid, name)
    local_name: dict = field(default_factory=dict)        # tid -> имя на своём языке
    _stamp: int = -1
    _cache_aff: object = None
    _cache_eff: object = None

    def touch(self):
        self._stamp = -1

    def _refresh(self):
        if not self.known.any():
            self._cache_aff = np.zeros(len(AFFORDANCES), dtype=np.float32)
            self._cache_eff = np.zeros(len(EFF_KEYS), dtype=np.float32)
        else:
            self._cache_aff = _GIVES[self.known].max(axis=0)
            w = np.minimum(1.0, 0.35 + self.grip[self.known])
            self._cache_eff = (_EFF[self.known] * w[:, None]).sum(axis=0)
        self._stamp = 1

    def affordances(self) -> np.ndarray:
        if self._stamp != 1:
            self._refresh()
        return self._cache_aff

    def copy(self) -> "Repertoire":
        r = Repertoire(self.known.copy(), self.grip.copy(),
                       dict(self.discovered_by), dict(self.local_name))
        r.touch()
        return r

    def count(self) -> int:
        return int(self.known.sum())

    def effect(self, key: str) -> float:
        if self._stamp != 1:
            self._refresh()
        i = _EI.get(key)
        return float(self._cache_eff[i]) if i is not None else 0.0

    def effects(self) -> dict:
        if self._stamp != 1:
            self._refresh()
        return {k: float(self._cache_eff[i]) for k, i in _EI.items()}

    def has(self, key: str) -> bool:
        t = _BY_KEY.get(key)
        return bool(t and self.known[t.tid])


def starting_repertoire() -> Repertoire:
    r = Repertoire()
    for k in _START:
        tid = _BY_KEY[k].tid
        r.known[tid] = True
        r.grip[tid] = 1.0
    r.touch()
    return r


# ────────────────────────────────────────────────────────────────────────────
#  Достижимость: что физически возможно ЗДЕСЬ И СЕЙЧАС
# ────────────────────────────────────────────────────────────────────────────
def reachable_mask(rep: Repertoire, materials: dict, pop: float, surplus: float,
                   sedentism: float, biomes: set) -> np.ndarray:
    """Булев вектор: какие знания в принципе могут быть открыты в этих условиях."""
    aff = rep.affordances()
    ok = ~rep.known
    # аффордансы
    ok &= (_NEEDS <= aff[None, :] + 1e-6).all(axis=1)
    # социальный масштаб
    ok &= (_POP <= pop)
    ok &= (_SUR <= surplus)
    ok &= (_SED <= sedentism)
    # материалы
    if _MATKEYS:
        have = materials if isinstance(materials, np.ndarray) else \
            np.array([materials.get(k, 0.0) for k in _MATKEYS], dtype=np.float32)
        ok &= (_MAT <= have[None, :] + 1e-6).all(axis=1)
    # биом
    for tid in np.flatnonzero(ok):
        req = _BIOME_REQ[tid]
        if req and not (set(req) & biomes):
            ok[tid] = False
    return ok


def demand_vector(demand: dict) -> np.ndarray:
    """Перевод нужды народа в вектор по ключам эффектов."""
    v = np.zeros(len(EFF_KEYS), dtype=np.float32)
    for k, val in demand.items():
        i = _EI.get(k)
        if i is not None:
            v[i] = val
    return v


def discovery_weights(rep: Repertoire, mask: np.ndarray,
                      demand: np.ndarray | None = None,
                      hint: np.ndarray | None = None) -> np.ndarray:
    """Вес шанса нащупать именно это знание.

    Два множителя, и оба — не сценарий, а поведение:
      • близость к освоенному: новое рождается из соседства уже понятого,
        а не из воздуха (рекомбинация);
      • нужда: люди возятся с тем, что болит. Голодный ищет, чем накормить,
        а не как считать звёзды. Поэтому одна и та же планета даёт разный
        порядок открытий в зависимости от того, что жмёт народ.
    """
    if not mask.any():
        return np.zeros(N_TECH, dtype=np.float32)
    aff = rep.affordances()
    slack = np.clip(aff[None, :] - _NEEDS, 0, None).sum(axis=1)
    proximity = 1.0 / (1.0 + slack)
    w = proximity / (0.25 + _DIFF) ** 1.6
    if demand is not None:
        w = w * (1.0 + 3.2 * np.clip(_EFF @ demand, 0, None))
    if hint is not None:
        # то, что уже видели у соседей, ищется целенаправленно, а не наугад
        w = w * np.where(hint, 4.0, 1.0)
    w = w * mask
    s = w.sum()
    return w / s if s > 0 else w


# ────────────────────────────────────────────────────────────────────────────
#  Открытие, распространение, забвение
# ────────────────────────────────────────────────────────────────────────────
def knowledge_ceiling(tech_scale: float) -> float:
    """Сколько разных умений общество такого масштаба вообще способно держать.

    Носителей мало — специализироваться некому, и каждое следующее умение отнимает
    людей у предыдущих. Община в триста человек держит десятки умений, город в
    двадцать тысяч — под сотню, держава в миллионы — весь доступный свод.
    Отсюда же берутся тёмные века: когда города пустеют, потолок падает,
    и знания начинают осыпаться сверху.
    """
    return 6.0 * math.log10(max(tech_scale, 20.0)) ** 2


def carrying_knowledge(tech_scale: float, n_known: int) -> float:
    cap = knowledge_ceiling(tech_scale)
    return float(np.clip(1.0 - (max(1, n_known) / cap) ** 3, 0.015, 1.0))


def attempt_discovery(rng, rep: Repertoire, mask: np.ndarray, innovator_quality: float,
                      exposure: float = 0.0, demand: np.ndarray | None = None,
                      headroom: float = 1.0, hint: np.ndarray | None = None) -> int | None:
    """Одна попытка изобретения. Возвращает tid или None."""
    w = discovery_weights(rep, mask, demand, hint)
    if w.sum() <= 0:
        return None
    tid = int(rng.choice(N_TECH, p=w))
    t = _CATALOG[tid]
    seen_it = bool(hint is not None and hint[tid])
    p = innovator_quality * (0.55 + exposure) * headroom \
        * (1.9 if seen_it else 1.0) / (t.difficulty ** 2.15)
    p = min(0.7, p)
    return tid if rng.random() < p else None


def learn(rep: Repertoire, tid: int, grip: float = 0.35):
    rep.known[tid] = True
    rep.grip[tid] = max(rep.grip[tid], grip)
    rep.touch()


def reinforce(rep: Repertoire, pop: float, retention: float, dt: float = 1.0):
    """Знание крепнет от использования и от институтов памяти."""
    if not rep.known.any():
        return
    idx = rep.known
    scale = 0.012 * dt * (0.5 + retention) * (0.4 + min(1.6, math.log10(max(pop, 10)) / 2.2))
    rep.grip[idx] = np.minimum(1.0, rep.grip[idx] + scale)
    rep.touch()


def erode(rng, rep: Repertoire, stress: float, pop: float, retention: float) -> list[int]:
    """Забвение. Сложные и редко используемые знания теряются первыми.

    Именно это делает «тёмные века» настоящими: народ может физически
    разучиться плавить бронзу и писать.
    """
    lost = []
    if not rep.known.any():
        return lost
    idx = np.flatnonzero(rep.known)
    pop_floor = _POP[idx]
    # знание не удержать, если носителей стало меньше, чем нужно для передачи
    too_few = pop < pop_floor * 0.6
    decay = 0.010 * stress * _LOSSY[idx] * (1.4 - min(1.0, retention))
    decay = decay + np.where(too_few, 0.09 * _LOSSY[idx], 0.0)
    over = max(0.0, idx.size - knowledge_ceiling(pop))
    if over > 0:
        # что не помещается в общество — осыпается, начиная с самого сложного
        decay = decay + 0.05 * _LOSSY[idx] * min(1.0, over / max(1.0, idx.size)) \
            * (0.35 + 0.65 * _DIFF[idx] / 5.0)
    rep.grip[idx] = np.maximum(0.0, rep.grip[idx] - decay)
    rep.touch()
    fragile = idx[rep.grip[idx] < 0.06]
    for tid in fragile:
        if rng.random() < 0.30 * _LOSSY[tid] + (0.35 if pop < _POP[tid] * 0.5 else 0.0):
            rep.known[tid] = False
            rep.grip[tid] = 0.0
            rep.discovered_by.pop(int(tid), None)
            lost.append(int(tid))
    return lost


_ECO_BOUND = np.zeros(N_TECH, dtype=np.float32)
for _t in _CATALOG:
    _ECO_BOUND[_t.tid] = min(1.0, sum(abs(_t.effects.get(k, 0.0)) for k in
                                      ("yield", "food", "soil_restore", "marine_bonus"))
                             + (0.8 if any(k.startswith("mode:") for k in _t.effects) else 0.0))


def diffuse(rng, dst: Repertoire, src: Repertoire, contact: float, openness: float,
            materials: dict, pop: float, surplus: float, sedentism: float,
            biomes: set, max_items: int = 3, eco_gap: float = 0.0) -> list[int]:
    """Заимствование у соседа. Берут только то, что можешь воспроизвести."""
    cand = np.flatnonzero(src.known & ~dst.known)
    if cand.size == 0:
        return []
    ok = reachable_mask(dst, materials, pop, surplus, sedentism, biomes)
    # заимствование мягче изобретения: часть требований может быть скопирована
    aff = dst.affordances()
    near = (_NEEDS[cand] <= aff[None, :] + 0.16).all(axis=1)
    cand = cand[near | ok[cand]]
    if cand.size == 0:
        return []
    got = []
    rng.shuffle(cand)
    for tid in cand[:max_items * 3]:
        t = _CATALOG[tid]
        # хозяйственное знание привязано к климату: пшеница не переезжает в тайгу,
        # а через широты её приходится приручать заново. Отсюда — преимущество
        # материков, вытянутых по широте.
        eco = 1.0 / (1.0 + eco_gap * _ECO_BOUND[tid] * 5.5)
        p = contact * openness * eco * src.grip[tid] / (0.5 + t.difficulty * 0.55)
        if rng.random() < min(0.6, p):
            learn(dst, int(tid), grip=0.22)
            got.append(int(tid))
            if len(got) >= max_items:
                break
    return got


def available_modes(rep: Repertoire) -> set:
    m = {"forager"}
    if rep.effect("sedentism") > 0.2 or rep.has("sedentism"):
        m.add("complex_forager")
    for t in _CATALOG:
        if not rep.known[t.tid]:
            continue
        for k in t.effects:
            if k.startswith("mode:"):
                m.add(k[5:])
    if "horticulture" in m and rep.has("ard_plough"):
        m.add("agrarian")
    if "agrarian" in m and rep.has("irrigation"):
        m.add("intensive")
    return m


def available_forms(rep: Repertoire) -> set:
    f = {"band", "tribe", "bigman"}
    for t in _CATALOG:
        if not rep.known[t.tid]:
            continue
        for k in t.effects:
            if k.startswith("form:"):
                f.add(k[5:])
    return f


def tech_name(tid: int) -> str:
    return _CATALOG[tid].name


def tech_key(tid: int) -> str:
    return _CATALOG[tid].key


def era_of(rep: Repertoire) -> str:
    """Грубая эпоха народа — для летописи."""
    order = ["информационная эпоха", "современность", "промышленная эпоха",
             "новое время", "средневековье", "античность", "железо", "бронза",
             "халколит", "неолит", "мезолит", "палеолит"]
    have = {_CATALOG[t].era_hint for t in np.flatnonzero(rep.known)}
    counts = {e: sum(1 for t in np.flatnonzero(rep.known) if _CATALOG[t].era_hint == e)
              for e in order}
    for e in order:
        if counts.get(e, 0) >= 3:
            return e
    for e in order:
        if e in have:
            return e
    return "палеолит"


def summarize(rep: Repertoire, limit: int = 12) -> list[str]:
    ids = np.flatnonzero(rep.known)
    ids = sorted(ids, key=lambda t: -_DIFF[t])[:limit]
    return [_CATALOG[t].name for t in ids]


if __name__ == "__main__":
    print(f"знаний в каталоге: {N_TECH}")
    print(f"стартовых (палеолит): {len(_START)}")
    r = starting_repertoire()
    print("стартовые аффордансы:",
          {a: round(float(v), 2) for a, v in zip(AFFORDANCES, r.affordances()) if v > 0})
    mats = {"flint": 0.5, "timber": 0.5, "clay": 0.4, "wild_grains": 0.6, "soil": 0.6,
            "stone": 0.5, "copper": 0.4, "tin": 0.0, "iron": 0.4, "salt": 0.3,
            "dom_herd": 0.5, "dom_draft": 0.0, "river": 0.5, "wild_pulses": 0.4,
            "wild_roots": 0.3, "fauna_large": 0.4, "silver": 0.2, "coal": 0.2}
    m = reachable_mask(r, mats, 60, 0.0, 0.0, {TEMPERATE_GRASSLAND, MEDITERRANEAN})
    print(f"достижимо сразу: {int(m.sum())} —", [_CATALOG[t].name for t in np.flatnonzero(m)][:14])
    print("\nбез олова и тягловых животных недостижимы навсегда:")
    for k in ("bronze_tin", "chariot", "riding", "ard_plough", "cart"):
        t = _BY_KEY[k]
        blocked = [mk for mk, mv in t.needs_mat.items() if mats.get(mk, 0) < mv]
        print(f"  {t.name:32s} упирается в: {blocked or '—'}")
