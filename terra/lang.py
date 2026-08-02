"""
TERRA — эмерджентные языки.

Каждая культура несёт свой идиом (`Lect`). Языки рождаются из праязыка,
ветвятся вместе с народами и дрейфуют во времени по РЕГУЛЯРНЫМ звуковым
законам, поэтому через тысячи лет потомки одного корня остаются
узнаваемо родственными, но звучат по-разному.

Модуль ни от чего в TERRA не зависит: только stdlib + numpy.
Полный детерминизм: всё выводится из seed либо из переданного random.Random.

Внутреннее представление слова — СПИСОК СЕГМЕНТОВ (фонем), например
    ["k", "e", "r", "a"]
Гласный сегмент может нести модификаторы: долготу "ː", назальность "̃",
тон ("˥" / "˧" / "˩"). Звуковые законы работают именно по сегментам —
поэтому изменение регулярно и одинаково бьёт по всему лексикону.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import unicodedata
from typing import Any, Iterable, Sequence

import numpy as np

LECT_SCHEMA = 1

__all__ = [
    "Lect",
    "romanize",
    "distance_matrix",
    "BASIC_MEANINGS",
    "STABLE_CORE",
    "SOUND_LAWS",
    "CONSONANTS",
    "VOWEL_CORES",
    "GOD_DOMAINS",
    "PLACE_HEADS",
    "AFFIX_KEYS",
    "LECT_SCHEMA",
]

# ────────────────────────────────────────────────────────────────────────────
#  Фонетический инвентарь мира
# ────────────────────────────────────────────────────────────────────────────
# согласный -> (место, способ, звонкость, сонорность)
CONSONANTS: dict[str, tuple[str, str, bool, int]] = {
    "p":  ("labial",     "stop",      False, 0),
    "b":  ("labial",     "stop",      True,  0),
    "t":  ("dental",     "stop",      False, 0),
    "d":  ("dental",     "stop",      True,  0),
    "k":  ("velar",      "stop",      False, 0),
    "g":  ("velar",      "stop",      True,  0),
    "q":  ("uvular",     "stop",      False, 0),
    "ʔ":  ("glottal",    "stop",      False, 0),
    "ts": ("dental",     "affricate", False, 0),
    "dz": ("dental",     "affricate", True,  0),
    "tʃ": ("palatal",    "affricate", False, 0),
    "dʒ": ("palatal",    "affricate", True,  0),
    "f":  ("labial",     "fricative", False, 1),
    "v":  ("labial",     "fricative", True,  1),
    "θ":  ("dental",     "fricative", False, 1),
    "ð":  ("dental",     "fricative", True,  1),
    "s":  ("alveolar",   "fricative", False, 1),
    "z":  ("alveolar",   "fricative", True,  1),
    "ʃ":  ("palatal",    "fricative", False, 1),
    "ʒ":  ("palatal",    "fricative", True,  1),
    "x":  ("velar",      "fricative", False, 1),
    "ɣ":  ("velar",      "fricative", True,  1),
    "ħ":  ("pharyngeal", "fricative", False, 1),
    "h":  ("glottal",    "fricative", False, 1),
    "ɬ":  ("alveolar",   "latfric",   False, 1),
    "m":  ("labial",     "nasal",     True,  2),
    "n":  ("dental",     "nasal",     True,  2),
    "ɲ":  ("palatal",    "nasal",     True,  2),
    "ŋ":  ("velar",      "nasal",     True,  2),
    "l":  ("alveolar",   "lateral",   True,  3),
    "ʎ":  ("palatal",    "lateral",   True,  3),
    "r":  ("alveolar",   "trill",     True,  3),
    "ɾ":  ("alveolar",   "tap",       True,  3),
    "w":  ("labial",     "glide",     True,  4),
    "j":  ("palatal",    "glide",     True,  4),
}

NASAL_CONS = frozenset(("m", "n", "ɲ", "ŋ"))
LIQUIDS = frozenset(("l", "r", "ɾ", "ʎ"))

# частотность согласных — чем выше, тем чаще встречается в корнях
CFREQ: dict[str, float] = {
    "t": 10, "k": 9, "n": 9, "p": 8, "m": 8, "s": 8, "l": 7, "r": 7, "ɾ": 6,
    "j": 5.5, "w": 5, "b": 5, "d": 5, "g": 4, "h": 4, "f": 3, "ʃ": 3, "x": 3,
    "ʔ": 2.2, "ŋ": 2, "z": 2, "v": 2, "tʃ": 2, "ts": 2, "ɲ": 1.6, "dʒ": 1.5,
    "q": 1.5, "θ": 1.1, "ð": 1.0, "ɣ": 1.0, "ħ": 1.0, "ʒ": 1.0, "dz": 0.9,
    "ɬ": 0.8, "ʎ": 0.8,
}

VOWEL_CORES = ("i", "e", "ɛ", "a", "ɔ", "o", "u", "ə", "ɨ", "y")
VOWEL_START = frozenset(VOWEL_CORES)
VFREQ = {"a": 10, "i": 8, "u": 7, "e": 6, "o": 6, "ə": 4, "ɛ": 3, "ɔ": 3, "ɨ": 3, "y": 2}

FRONT_CORES = frozenset(("i", "e", "ɛ", "y"))

DIPHTHONGS = ("ai", "au", "ei", "oi", "ou", "ia", "ua")

# модификаторы гласного сегмента
LONG = "ː"
NASAL_MARK = "̃"
TONE_CHARS = ("˥", "˧", "˩")
MODS = frozenset((LONG, NASAL_MARK)) | frozenset(TONE_CHARS)

# реалистичные системы гласных: (набор, вес)
VOWEL_SYSTEMS: tuple[tuple[tuple[str, ...], float], ...] = (
    (("i", "a", "u"), 0.15),
    (("i", "e", "a", "o", "u"), 0.38),
    (("i", "e", "a", "o", "u", "ə"), 0.11),
    (("i", "ɨ", "e", "a", "o", "u"), 0.10),
    (("i", "e", "ɛ", "a", "ɔ", "o", "u"), 0.18),
    (("i", "y", "e", "a", "o", "u"), 0.08),
)

# слоговые шаблоны: (слоты, вес, кластер в начале, кластер в конце)
#   "C" — обязательный согласный, "c" — необязательный, "V" — ядро
SYLLABLE_TEMPLATES: tuple[tuple[tuple[str, ...], float, bool, bool], ...] = (
    (("C", "V"), 0.17, False, False),
    (("C", "V", "c"), 0.15, False, False),
    (("C", "V", "C"), 0.19, False, False),
    (("c", "V", "c"), 0.19, False, False),
    (("C", "V", "c"), 0.11, True, False),
    (("C", "V", "C"), 0.09, False, True),
    (("c", "V", "c"), 0.10, True, True),
)

# ────────────────────────────────────────────────────────────────────────────
#  Романизация: внутренняя фонема -> читаемая латиница
# ────────────────────────────────────────────────────────────────────────────
ROMAN_CONS = {
    "ʃ": "š", "ʒ": "ž", "tʃ": "č", "dʒ": "ǰ", "ts": "c", "dz": "dz",
    "θ": "þ", "ð": "ð", "x": "x", "ɣ": "ġ", "ħ": "ħ", "ʔ": "ʔ",
    "ɲ": "ń", "ŋ": "ŋ", "ʎ": "ľ", "ɬ": "ł", "ɾ": "r", "j": "y",
}
ROMAN_VOW = {"ɛ": "ɛ", "ɔ": "ɔ", "ə": "ë", "ɨ": "ï", "y": "ü"}
_LONG_MAP = {"a": "ā", "e": "ē", "i": "ī", "o": "ō", "u": "ū", "ü": "ǖ"}
_NAS_MAP = {"a": "ã", "e": "ẽ", "i": "ĩ", "o": "õ", "u": "ũ", "ë": "ə̃"}
_HIGH_MAP = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "ü": "ǘ", "ɛ": "ɛ́", "ɔ": "ɔ́"}
_LOW_MAP = {"a": "à", "e": "è", "i": "ì", "o": "ò", "u": "ù", "ü": "ǜ", "ɛ": "ɛ̀", "ɔ": "ɔ̀"}

# порядок разбора при токенизации строки обратно в сегменты
_MULTI = ("tʃ", "dʒ", "ts", "dz") + DIPHTHONGS


# ────────────────────────────────────────────────────────────────────────────
#  Базовый словарь (сокращённый список Сводеша + культурная лексика TERRA)
# ────────────────────────────────────────────────────────────────────────────
BASIC_MEANINGS: tuple[str, ...] = (
    # стихии и ландшафт
    "вода", "огонь", "солнце", "луна", "звезда", "небо", "земля", "гора", "река",
    "озеро", "море", "камень", "песок", "дождь", "снег", "ветер", "дым",
    "ночь", "день", "год", "зима",
    # живое
    "дерево", "лес", "трава", "лист", "корень", "зерно", "хлеб", "цветок",
    "бык", "корова", "овца", "конь", "собака", "свинья", "птица", "рыба",
    "змея", "волк", "медведь", "олень", "пчела",
    # человек и тело
    "человек", "мужчина", "женщина", "мать", "отец", "сын", "дочь", "ребёнок",
    "голова", "глаз", "ухо", "рот", "зуб", "язык", "рука", "нога",
    "сердце", "кровь", "кость", "кожа", "волос", "имя",
    # общество
    "дом", "деревня", "город", "стена", "очаг", "поле", "стадо", "путь", "мост",
    "лодка", "колесо", "вождь", "царь", "жрец", "бог", "дух", "предок", "народ",
    "племя", "враг", "друг", "гость", "война", "мир", "закон", "дар", "раб",
    # вещество и ремесло
    "соль", "медь", "золото", "серебро", "железо", "глина", "горшок", "ткань",
    "верёвка", "нож", "топор", "копьё", "лук", "стрела", "щит", "плуг", "серп",
    "масло", "мёд", "молоко", "шерсть",
    # действия
    "есть", "пить", "спать", "умереть", "убить", "идти", "дать", "взять",
    "говорить", "слышать", "видеть", "знать", "считать", "писать", "петь",
    "пахать", "ковать", "строить", "торговать", "молиться",
    # свойства и числа
    "большой", "малый", "длинный", "широкий", "высокий", "новый", "старый",
    "белый", "чёрный", "красный", "холодный", "горячий", "святой",
    "сильный", "быстрый", "острый", "глубокий", "один", "два", "три",
)

# устойчивое ядро — эти значения реже вытесняются заимствованием/новацией
STABLE_CORE = frozenset((
    "вода", "огонь", "солнце", "луна", "камень", "кровь", "кость", "мать", "отец",
    "глаз", "ухо", "зуб", "рука", "нога", "сердце", "имя", "земля", "небо",
    "ночь", "день", "один", "два", "три", "есть", "пить", "умереть", "идти",
    "новый", "старый", "человек", "дом", "путь",
))

GOD_DOMAINS: dict[str, tuple[str, ...]] = {
    "небо":        ("небо", "высокий", "отец", "светлый"),
    "буря":        ("дождь", "ветер", "гора", "сильный"),
    "плодородие":  ("зерно", "поле", "мать", "молоко"),
    "смерть":      ("умереть", "ночь", "земля", "чёрный"),
    "война":       ("война", "копьё", "волк", "железо"),
    "солнце":      ("солнце", "день", "золото", "глаз"),
    "море":        ("море", "вода", "лодка", "глубокий"),
    "очаг":        ("очаг", "огонь", "дом", "мать"),
    "ремесло":     ("ковать", "медь", "рука", "строить"),
    "мудрость":    ("знать", "слово", "старый", "звезда"),
}
_DOMAIN_ALIASES = {
    "sky": "небо", "storm": "буря", "fertility": "плодородие", "death": "смерть",
    "war": "война", "sun": "солнце", "sea": "море", "hearth": "очаг",
    "craft": "ремесло", "wisdom": "мудрость",
}
DIVINE_HEADS = ("бог", "отец", "мать", "владыка", "дух")
DIVINE_EPITHETS = ("сильный", "святой", "высокий", "светлый", "белый", "старый",
                   "большой", "мудрый", "щедрый", "грозный", "золото", "древний")

# именной запас: элементы личных имён
NAME_STOCK_M = ("волк", "медведь", "конь", "бык", "камень", "копьё", "сильный",
                "гора", "огонь", "война", "железо", "щит", "острый", "быстрый",
                "орёл", "слава", "топор", "высокий")
NAME_STOCK_F = ("цветок", "звезда", "луна", "мёд", "вода", "светлый", "птица",
                "олень", "добрый", "заря", "дар", "молоко", "шерсть", "святой",
                "красный", "пчела", "лист", "тихий")
NAME_STOCK_N = ("солнце", "небо", "река", "дерево", "белый", "новый", "путь",
                "золото", "день", "земля", "гость", "мир")

EPITHETS = ("сильный", "быстрый", "святой", "высокий", "белый", "чёрный",
            "красный", "старый", "острый", "большой", "мудрый", "щедрый")

PLACE_HEADS: dict[str, tuple[str, ...]] = {
    "settlement": ("дом", "город", "деревня", "стена", "очаг", "мост", "крепость"),
    "river":      ("река", "вода"),
    "mountain":   ("гора", "камень"),
    "region":     ("земля", "поле", "страна"),
    "sea":        ("море", "вода"),
    "island":     ("остров", "земля"),
}
PLACE_MODS: dict[str, tuple[str, ...]] = {
    "settlement": ("новый", "старый", "высокий", "белый", "святой", "большой",
                   "соль", "медь", "бык", "мост", "вождь", "чёрный"),
    "river":      ("широкий", "быстрый", "глубокий", "белый", "чёрный",
                   "холодный", "большой", "рыба", "золото", "длинный"),
    "mountain":   ("высокий", "белый", "чёрный", "святой", "большой", "снег",
                   "огонь", "медь", "волк", "острый"),
    "region":     ("широкий", "большой", "чёрный", "старый", "святой",
                   "зерно", "конь", "лес", "холодный"),
    "sea":        ("большой", "чёрный", "белый", "холодный", "глубокий", "соль"),
    "island":     ("малый", "святой", "далёкий", "птица", "белый", "длинный"),
}

TITLE_RECIPE: dict[str, tuple[str, ...]] = {
    "band":          ("старый", "человек"),
    "tribe":         ("говорить", "человек"),
    "bigman":        ("большой", "человек"),
    "chiefdom":      ("вождь",),
    "citystate":     ("город", "вождь"),
    "kingdom":       ("царь",),
    "empire":        ("царь", "царь"),
    "republic":      ("народ", "говорить"),
    "confederation": ("племя", "вождь"),
}

WORD_ORDERS: tuple[tuple[str, float], ...] = (
    ("SOV", 0.45), ("SVO", 0.40), ("VSO", 0.09),
    ("VOS", 0.03), ("OVS", 0.02), ("OSV", 0.01),
)
MORPH_TYPES: tuple[tuple[str, float], ...] = (
    ("isolating", 0.25), ("agglutinative", 0.45), ("fusional", 0.30),
)
MORPH_CYCLE = {"isolating": "agglutinative", "agglutinative": "fusional", "fusional": "isolating"}

AFFIX_KEYS = ("pl", "gen", "loc", "dim", "aug", "agent", "place",
              "fem", "masc", "adj", "coll", "abst")
AFFIX_RU = {
    "pl": "мн.ч.", "gen": "род.п.", "loc": "мест.п.", "dim": "уменьш.",
    "aug": "увелич.", "agent": "деятель", "place": "место", "fem": "жен.р.",
    "masc": "муж.р.", "adj": "прилаг.", "coll": "собират.", "abst": "отвлеч.",
}


# ────────────────────────────────────────────────────────────────────────────
#  Мелкие утилиты
# ────────────────────────────────────────────────────────────────────────────
def _h64(s: str) -> int:
    """Стабильный (не зависящий от PYTHONHASHSEED) 64-битный хэш строки."""
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def _unit(s: str) -> float:
    """Хэш строки, отображённый в [0, 1)."""
    return (_h64(s) % 1_000_003) / 1_000_003.0


def _is_v(seg: str) -> bool:
    """Гласный ли сегмент."""
    return bool(seg) and seg[0] in VOWEL_START


def _vcore(seg: str) -> str:
    """Ядро гласного без модификаторов: 'ãː' -> 'a', 'ai' -> 'ai'."""
    out = []
    for ch in seg:
        if ch in MODS:
            break
        out.append(ch)
    return "".join(out)


def _vmods(seg: str) -> str:
    return seg[len(_vcore(seg)):]


def _setcore(seg: str, core: str) -> str:
    """Заменить ядро гласного, сохранив долготу/назальность/тон."""
    return core + _vmods(seg)


def _weighted(rng: random.Random, items: Sequence[Any], weights: Sequence[float]) -> Any:
    total = float(sum(weights))
    x = rng.random() * total
    acc = 0.0
    for it, w in zip(items, weights):
        acc += w
        if x < acc:
            return it
    return items[-1]


def _nuclei(segs: Sequence[str]) -> list[int]:
    return [i for i, s in enumerate(segs) if _is_v(s)]


def _stressed(segs: Sequence[str], mode: str) -> set[int]:
    """Индексы ударных слоговых центров."""
    nuc = _nuclei(segs)
    if not nuc:
        return set()
    if mode == "final":
        k = len(nuc) - 1
    elif mode == "penult":
        k = max(0, len(nuc) - 2)
    else:  # initial
        k = 0
    return {nuc[k]}


def _tokenize(word: str) -> list[str]:
    """Разбор фонемной строки обратно в сегменты (для romanize от str)."""
    segs: list[str] = []
    i = 0
    n = len(word)
    while i < n:
        matched = None
        for m in _MULTI:
            if word.startswith(m, i):
                matched = m
                break
        if matched is None:
            matched = word[i]
        i += len(matched)
        while i < n and word[i] in MODS:
            matched += word[i]
            i += 1
        segs.append(matched)
    return segs


def romanize(word: Any) -> str:
    """Перевести слово (список сегментов или фонемную строку) в читаемую латиницу."""
    segs = _tokenize(word) if isinstance(word, str) else list(word)
    out: list[str] = []
    for seg in segs:
        if not seg:
            continue
        if _is_v(seg):
            core = _vcore(seg)
            mods = _vmods(seg)
            base = "".join(ROMAN_VOW.get(ch, ch) for ch in core)
            if NASAL_MARK in mods:
                base = _NAS_MAP.get(base, base + NASAL_MARK) if len(base) == 1 else base + NASAL_MARK
            if LONG in mods:
                base = _LONG_MAP.get(base, base + base) if len(base) == 1 else base + LONG
            if "˥" in mods:
                base = _HIGH_MAP.get(base, base + "́") if len(base) == 1 else base + "́"
            elif "˩" in mods:
                base = _LOW_MAP.get(base, base + "̀") if len(base) == 1 else base + "̀"
            out.append(base)
        else:
            out.append(ROMAN_CONS.get(seg, seg))
    return "".join(out)


def _vwidth(s: str) -> int:
    """Видимая ширина строки: комбинирующие знаки не занимают позиции."""
    return sum(0 if unicodedata.combining(ch) else 1 for ch in s)


def _pad(s: str, w: int) -> str:
    return s + " " * max(0, w - _vwidth(s))


def _cap(s: str) -> str:
    """Заглавная первая буква (без обрушения остального в нижний регистр)."""
    for i, ch in enumerate(s):
        up = ch.upper()
        if up != ch:
            return s[:i] + up + s[i + 1:]
    return s


def _sub_cost(x: str, y: str) -> float:
    """Стоимость подстановки: похожие фонемы дешевле."""
    if x == y:
        return 0.0
    xv, yv = _is_v(x), _is_v(y)
    if xv != yv:
        return 1.0
    if xv:
        cx, cy = _vcore(x)[0], _vcore(y)[0]
        return 0.35 if cx == cy else 0.55
    px, py = CONSONANTS.get(x), CONSONANTS.get(y)
    if px and py:
        if px[0] == py[0] and px[1] == py[1]:
            return 0.30
        if px[0] == py[0]:
            return 0.45
        if px[1] == py[1]:
            return 0.60
    return 1.0


def _lev(a: Sequence[str], b: Sequence[str]) -> float:
    """Взвешенное расстояние Левенштейна по сегментам."""
    if not a and not b:
        return 0.0
    if not a:
        return float(len(b))
    if not b:
        return float(len(a))
    prev = [float(j) for j in range(len(b) + 1)]
    for i, ca in enumerate(a, 1):
        cur = [float(i)]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1.0, cur[j - 1] + 1.0, prev[j - 1] + _sub_cost(ca, cb)))
        prev = cur
    return prev[-1]


# ────────────────────────────────────────────────────────────────────────────
#  Порождение фонологии праязыка
# ────────────────────────────────────────────────────────────────────────────
# порядок «выбрасывания за борт» при слишком богатом инвентаре
_TRIM_ORDER = ("ɬ", "ʎ", "ħ", "ð", "θ", "dz", "ɣ", "ʒ", "ɲ", "ŋ", "q", "ʔ",
               "ts", "v", "z", "x", "dʒ", "tʃ", "f", "h")
# чем добираем слишком бедный инвентарь
_FILL_ORDER = ("t", "k", "p", "n", "m", "s", "l", "j", "w", "r", "h",
               "b", "d", "g", "f", "ʃ", "x", "ŋ", "ts")


def _make_consonants(rng: random.Random) -> list[str]:
    """Инвентарь согласных с оглядкой на импликативные универсалии."""
    inv: set[str] = set()
    # глухие смычные — фундамент любой системы
    for c, p in (("t", 0.99), ("k", 0.97), ("p", 0.92), ("q", 0.16), ("ʔ", 0.26)):
        if rng.random() < p:
            inv.add(c)
    if not ({"t", "k", "p"} & inv):
        inv.add("t")
    # звонкий ряд — только там, где есть глухой соответствующий
    voiced = rng.random() < 0.62
    if voiced:
        for vd, vl in (("b", "p"), ("d", "t"), ("g", "k")):
            if vl in inv and rng.random() < 0.88:
                inv.add(vd)
    # носовые есть почти всегда
    if rng.random() < 0.97:
        inv.add("m")
    if rng.random() < 0.99:
        inv.add("n")
    if not ({"m", "n"} & inv):
        inv.add("n")
    if "k" in inv and rng.random() < 0.42:
        inv.add("ŋ")
    if rng.random() < 0.28:
        inv.add("ɲ")
    # щелевые
    for c, p in (("s", 0.92), ("h", 0.66), ("f", 0.50), ("ʃ", 0.38),
                 ("x", 0.34), ("θ", 0.12), ("ħ", 0.09), ("ɬ", 0.06)):
        if rng.random() < p:
            inv.add(c)
    if voiced:
        for vd, vl, p in (("z", "s", 0.52), ("v", "f", 0.50), ("ʒ", "ʃ", 0.42),
                          ("ɣ", "x", 0.38), ("ð", "θ", 0.55)):
            if vl in inv and rng.random() < p:
                inv.add(vd)
    # аффрикаты: требуют смычного и/или соответствующего щелевого
    if "t" in inv and "s" in inv and rng.random() < 0.30:
        inv.add("ts")
    if "ʃ" in inv and rng.random() < 0.55:
        inv.add("tʃ")
    elif "t" in inv and rng.random() < 0.14:
        inv.add("tʃ")
    if voiced and "tʃ" in inv and rng.random() < 0.50:
        inv.add("dʒ")
    if voiced and "ts" in inv and rng.random() < 0.35:
        inv.add("dz")
    # плавные — хотя бы один обязателен
    if rng.random() < 0.86:
        inv.add("l")
    if rng.random() < 0.82:
        inv.add("r" if rng.random() < 0.70 else "ɾ")
    if not (LIQUIDS & inv):
        inv.add("l" if rng.random() < 0.5 else "r")
    if "l" in inv and rng.random() < 0.08:
        inv.add("ʎ")
    # глайды
    if rng.random() < 0.90:
        inv.add("j")
    if rng.random() < 0.84:
        inv.add("w")

    # подгонка размера в реалистичный коридор 8..26
    for c in _TRIM_ORDER:
        if len(inv) <= 26:
            break
        inv.discard(c)
    for c in _FILL_ORDER:
        if len(inv) >= 8:
            break
        inv.add(c)
    return sorted(inv, key=lambda c: (-CFREQ.get(c, 1.0), c))


def _make_phono(rng: random.Random) -> dict[str, Any]:
    """Полная фонологическая система: инвентари, слог, гармония, тон."""
    cons = _make_consonants(rng)
    vowels = list(_weighted(rng, [v for v, _ in VOWEL_SYSTEMS], [w for _, w in VOWEL_SYSTEMS]))
    slots, _w, oc, cc = _weighted(rng, SYLLABLE_TEMPLATES, [t[1] for t in SYLLABLE_TEMPLATES])
    diph = []
    if rng.random() < 0.38:
        pool = [d for d in DIPHTHONGS if d[0] in vowels and d[1] in vowels]
        rng.shuffle(pool)
        diph = sorted(pool[: rng.randint(1, 3)])
    harmony = "front_back" if (len(vowels) >= 5 and rng.random() < 0.18) else "none"
    tone = rng.random() < 0.24
    n_tones = (2 if rng.random() < 0.55 else 3) if tone else 0
    return {
        "cons": cons,
        "vowels": vowels,
        "diph": diph,
        "slots": list(slots),
        "onset_cluster": bool(oc),
        "coda_cluster": bool(cc),
        "harmony": harmony,
        "tone": bool(tone),
        "n_tones": int(n_tones),
    }


# ────────────────────────────────────────────────────────────────────────────
#  Чеканка корней
# ────────────────────────────────────────────────────────────────────────────
def _pick_c(rng: random.Random, pool: Sequence[str], avoid: str | None = None) -> str:
    cand = [c for c in pool if c != avoid] or list(pool)
    return _weighted(rng, cand, [CFREQ.get(c, 1.0) for c in cand])


def _pick_v(rng: random.Random, phono: dict) -> str:
    vowels = phono["vowels"]
    if phono["diph"] and rng.random() < 0.12:
        return rng.choice(phono["diph"])
    return _weighted(rng, vowels, [VFREQ.get(v, 1.0) for v in vowels])


def _good_onset_cluster(c1: str, c2: str) -> bool:
    """Кластер в начале слога: либо рост сонорности, либо s + смычный."""
    if c1 == c2:
        return False
    f1, f2 = CONSONANTS.get(c1), CONSONANTS.get(c2)
    if not f1 or not f2:
        return False
    if c1 in ("s", "ʃ") and f2[1] in ("stop", "nasal"):
        return True
    return f1[3] <= 1 and f2[3] >= 3


def _good_coda_cluster(c1: str, c2: str) -> bool:
    """Кластер в конце слога: сонант + шумный, падение сонорности."""
    if c1 == c2 or c2 in ("h", "ʔ", "ħ", "ɣ", "ð"):
        return False
    f1, f2 = CONSONANTS.get(c1), CONSONANTS.get(c2)
    if not f1 or not f2:
        return False
    return f1[3] >= 2 and f2[3] <= 1


def _syllable(rng: random.Random, phono: dict, first: bool, last: bool,
              prev: str | None, force_onset: bool = False) -> list[str]:
    cons = phono["cons"]
    segs: list[str] = []
    for slot in phono["slots"]:
        if slot == "V":
            segs.append(_pick_v(rng, phono))
            continue
        onset = not any(_is_v(s) for s in segs)   # ядро ещё не пройдено -> это инициаль
        if onset:
            need = slot == "C" or force_onset     # зияния между слогами избегаем
            p = 0.84 if first else 0.92
            if need or rng.random() < p:
                c = _pick_c(rng, cons, avoid=prev)
                segs.append(c)
                if phono["onset_cluster"] and rng.random() < 0.26:
                    opts = [x for x in cons if _good_onset_cluster(c, x)]
                    if opts:
                        segs.append(_weighted(rng, opts, [CFREQ.get(x, 1.0) for x in opts]))
        else:
            need = slot == "C"
            p = 0.50 if last else 0.38
            if need or rng.random() < p:
                c = _pick_c(rng, cons, avoid=segs[-1] if segs else None)
                segs.append(c)
                if phono["coda_cluster"] and last and rng.random() < 0.22:
                    opts = [x for x in cons if _good_coda_cluster(c, x)]
                    if opts:
                        segs.append(_weighted(rng, opts, [CFREQ.get(x, 1.0) for x in opts]))
    return segs


def _harmony_maps(vowels: Sequence[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Пары гармонии переднего/заднего ряда, ограниченные наличным инвентарём."""
    candidates = (("i", "ɨ"), ("i", "u"), ("e", "o"), ("e", "a"), ("ɛ", "ɔ"), ("y", "u"))
    f2b: dict[str, str] = {}
    for f, b in candidates:
        if f in vowels and b in vowels and f not in f2b:
            f2b[f] = b
    b2f = {b: f for f, b in f2b.items() if b not in f2b}
    return f2b, b2f


def _harmonize(segs: list[str], phono: dict, back: bool) -> list[str]:
    if phono.get("harmony") != "front_back":
        return segs
    f2b, b2f = _harmony_maps(phono["vowels"])
    mp = f2b if back else b2f
    out = []
    for s in segs:
        if _is_v(s):
            core = _vcore(s)
            if len(core) == 1 and core in mp:
                s = _setcore(s, mp[core])
        out.append(s)
    return out


def _assign_tones(segs: list[str], n_tones: int) -> list[str]:
    """Тоногенез: тон слога определяется характером следующего согласного.

    Звонкий/сонорный после гласного даёт низкий тон, глухой — высокий,
    открытый слог — средний. Это реальный механизм и он полностью
    детерминирован, поэтому переживает любое переигрывание истории.
    """
    if n_tones < 2:
        return segs
    out = list(segs)
    for i, s in enumerate(out):
        if not _is_v(s):
            continue
        if any(ch in TONE_CHARS for ch in s):
            continue
        nxt = out[i + 1] if i + 1 < len(out) else None
        if nxt is None or _is_v(nxt):
            tone = "˧" if n_tones >= 3 else "˥"
        else:
            feats = CONSONANTS.get(nxt)
            if feats is None:
                tone = "˧" if n_tones >= 3 else "˥"
            elif feats[2]:
                tone = "˩"
            else:
                tone = "˥"
        out[i] = s + tone
    return out


def _coin(seed_int: int, phono: dict) -> list[str]:
    """Отчеканить новый корень по данной фонологии. Детерминировано от seed."""
    rng = random.Random(seed_int & 0x7FFFFFFFFFFFFFFF)
    n_syl = _weighted(rng, (1, 2, 3), (0.34, 0.56, 0.10))
    segs: list[str] = []
    prev: str | None = None
    open_syl = False
    for i in range(n_syl):
        syl = _syllable(rng, phono, first=(i == 0), last=(i == n_syl - 1),
                        prev=prev, force_onset=open_syl)
        open_syl = bool(syl) and _is_v(syl[-1])
        prev = None if open_syl else (syl[-1] if syl else None)
        segs.extend(syl)
    if not any(_is_v(s) for s in segs):
        segs.append(_pick_v(rng, phono))
    segs = _harmonize(segs, phono, back=(rng.random() < 0.5))
    segs = _assign_tones(segs, phono.get("n_tones", 0) if phono.get("tone") else 0)
    segs = _repair(segs)
    # односложных огрызков не бывает: наращиваем до произносимого минимума
    while len(segs) < 2:
        if rng.random() < 0.6:
            segs.insert(0, _pick_c(rng, phono["cons"]))
        else:
            segs.append(_pick_c(rng, phono["cons"]))
        segs = _repair(segs)
    return segs


def _coin_affix(rng: random.Random, phono: dict, kind: str) -> list[str]:
    """Короткий грамматический показатель: V, CV, VC или CVC."""
    cons = phono["cons"]
    shape = _weighted(rng, ("V", "CV", "VC", "CVC"), (0.20, 0.42, 0.22, 0.16))
    segs: list[str] = []
    for ch in shape:
        if ch == "V":
            v = _weighted(rng, phono["vowels"], [VFREQ.get(x, 1.0) for x in phono["vowels"]])
            segs.append(v)
        else:
            segs.append(_pick_c(rng, cons, avoid=segs[-1] if segs else None))
    return segs


# ────────────────────────────────────────────────────────────────────────────
#  Фонотактический ремонт
#  Вызывается после КАЖДОГО звукового закона. Полностью детерминирован,
#  поэтому ленивое переигрывание истории даёт тот же результат, что и
#  пошаговое применение к кэшу.
# ────────────────────────────────────────────────────────────────────────────
def _fallback_vowel(segs: Sequence[str]) -> str:
    for s in segs:
        if _is_v(s):
            core = _vcore(s)
            if len(core) == 1:
                return core
    return "a"


def _repair(segs: Sequence[str]) -> list[str]:
    out = [s for s in segs if s]
    if not out:
        return ["a"]

    # 1. дегеминация: одинаковые согласные подряд стягиваются
    tmp: list[str] = []
    for s in out:
        if tmp and s == tmp[-1] and not _is_v(s):
            continue
        tmp.append(s)
    out = tmp

    # 2. без гласного слова не бывает
    if not any(_is_v(s) for s in out):
        out.insert(len(out) // 2 + (len(out) % 2), "a")

    fb = _fallback_vowel(out)

    # 3. зияние: слияние либо стяжение в дифтонг
    tmp = []
    for s in out:
        if tmp and _is_v(s) and _is_v(tmp[-1]):
            prev = tmp[-1]
            pc, sc = _vcore(prev), _vcore(s)
            if pc == sc:
                mods = "".join(dict.fromkeys(_vmods(prev) + _vmods(s)))
                if LONG not in mods:
                    mods += LONG
                tmp[-1] = pc + mods
            elif len(pc) == 1 and len(sc) == 1 and (pc + sc) in DIPHTHONGS:
                tmp[-1] = pc + sc + _vmods(prev)
            else:
                tmp[-1] = prev  # выпадение второго гласного (элизия)
            continue
        tmp.append(s)
    out = tmp

    # 4. стечения согласных: не более двух подряд
    tmp = []
    run = 0
    for s in out:
        if _is_v(s):
            run = 0
            tmp.append(s)
            continue
        run += 1
        if run > 2:
            continue          # лишние срединные согласные выпадают
        tmp.append(s)
    out = tmp

    # 5. невозможная инициаль -> вставной гласный между согласными
    if len(out) >= 2 and not _is_v(out[0]) and not _is_v(out[1]):
        if not _good_onset_cluster(out[0], out[1]):
            out = [out[0], fb] + out[1:]

    # 6. невозможная финаль -> вставной гласный
    if len(out) >= 2 and not _is_v(out[-1]) and not _is_v(out[-2]):
        if not _good_coda_cluster(out[-2], out[-1]):
            out = out[:-1] + [fb, out[-1]]

    # 7. срединные стечения с растущей сонорностью разводим по слогам корректно —
    #    достаточно проверить, что кластер вообще произносим
    tmp = []
    i = 0
    while i < len(out):
        if (i + 1 < len(out) and not _is_v(out[i]) and not _is_v(out[i + 1])
                and i > 0 and not _good_coda_cluster(out[i], out[i + 1])
                and not _good_onset_cluster(out[i], out[i + 1])):
            f1 = CONSONANTS.get(out[i])
            f2 = CONSONANTS.get(out[i + 1])
            if f1 and f2 and f1[3] == f2[3] and f1[1] == f2[1] == "stop":
                tmp.append(out[i + 1])   # ассимиляция: первый смычный выпадает
                i += 2
                continue
        tmp.append(out[i])
        i += 1
    out = tmp

    if not any(_is_v(s) for s in out):
        out.append("a")
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Контексты звуковых законов
# ────────────────────────────────────────────────────────────────────────────
def _next_nucleus_front(segs: Sequence[str], i: int) -> bool:
    for k in range(i + 1, len(segs)):
        if segs[k] == "j":
            return True
        if _is_v(segs[k]):
            return _vcore(segs[k])[0] in FRONT_CORES
    return False


def _ctx_ok(segs: Sequence[str], i: int, ctx: str, stressed: set[int]) -> bool:
    prev = segs[i - 1] if i > 0 else None
    nxt = segs[i + 1] if i + 1 < len(segs) else None
    if ctx == "any":
        return True
    if ctx == "intervocalic":
        return prev is not None and nxt is not None and _is_v(prev) and _is_v(nxt)
    if ctx == "before_front":
        return nxt is not None and ((_is_v(nxt) and _vcore(nxt)[0] in FRONT_CORES) or nxt == "j")
    if ctx == "coda":
        return nxt is None or not _is_v(nxt)
    if ctx == "final":
        return nxt is None
    if ctx == "initial":
        return i == 0
    if ctx == "not_initial":
        return i > 0
    if ctx == "before_cons":
        return nxt is not None and not _is_v(nxt)
    if ctx == "after_vowel":
        return prev is not None and _is_v(prev)
    if ctx == "after_nasal":
        return prev in NASAL_CONS
    if ctx == "unstressed":
        return i not in stressed
    if ctx == "stressed":
        return i in stressed
    if ctx == "final_unstressed":
        return nxt is None and i not in stressed
    if ctx == "next_syll_front":
        return _next_nucleus_front(segs, i)
    return True


# ────────────────────────────────────────────────────────────────────────────
#  Движки звуковых изменений
# ────────────────────────────────────────────────────────────────────────────
def _eng_map(segs: list[str], rec: dict) -> list[str]:
    """Общий движок: X -> Y в контексте C. Пустой Y = выпадение."""
    mp: dict[str, str] = rec["map"]
    ctx: str = rec["ctx"]
    stressed = _stressed(segs, rec.get("stress", "initial"))
    out: list[str] = []
    for i, s in enumerate(segs):
        key = _vcore(s) if _is_v(s) else s
        if key in mp and _ctx_ok(segs, i, ctx, stressed):
            tgt = mp[key]
            if tgt == "":
                continue
            out.append(_setcore(s, tgt) if _is_v(s) else tgt)
        else:
            out.append(s)
    return out


def _eng_vdelete(segs: list[str], rec: dict) -> list[str]:
    """Апокопа (отпадение конечного) и синкопа (выпадение срединного)."""
    targets = set(rec["targets"])
    stressed = _stressed(segs, rec.get("stress", "initial"))
    nuc = _nuclei(segs)
    mode = rec["mode"]
    drop: set[int] = set()
    if mode == "apocope":
        if len(nuc) >= 2:
            last = nuc[-1]
            if last not in stressed and _vcore(segs[last]) in targets and LONG not in _vmods(segs[last]):
                drop.add(last)
    else:  # syncope
        if len(nuc) >= 3:
            for pos in range(1, len(nuc) - 1):
                i = nuc[pos]
                if i in stressed or _vcore(segs[i]) not in targets:
                    continue
                if LONG in _vmods(segs[i]):
                    continue
                if i == 0 or i + 1 >= len(segs):
                    continue
                if _is_v(segs[i - 1]) or _is_v(segs[i + 1]):
                    continue
                drop.add(i)
                if len(nuc) - len(drop) < 2:
                    drop.discard(i)
                    break
    if not drop:
        return list(segs)
    return [s for i, s in enumerate(segs) if i not in drop]


def _eng_nasalize(segs: list[str], rec: dict) -> list[str]:
    """V + N -> назализованный V (носовой перед согласным / в исходе исчезает)."""
    out: list[str] = []
    i = 0
    n = len(segs)
    while i < n:
        s = segs[i]
        if (_is_v(s) and i + 1 < n and segs[i + 1] in NASAL_CONS
                and (i + 2 >= n or not _is_v(segs[i + 2]))):
            mods = _vmods(s)
            if NASAL_MARK not in mods:
                s = _vcore(s) + NASAL_MARK + mods
            out.append(s)
            i += 2
            continue
        out.append(s)
        i += 1
    return out


def _eng_metathesis(segs: list[str], rec: dict) -> list[str]:
    """Метатеза плавных: CVrC -> CrVC (по славянскому образцу)."""
    liq = set(rec["liquids"])
    out = list(segs)
    i = 0
    while i + 2 < len(out):
        if (not _is_v(out[i]) and out[i] not in liq and _is_v(out[i + 1])
                and out[i + 2] in liq
                and (i + 3 >= len(out) or not _is_v(out[i + 3]))):
            out[i + 1], out[i + 2] = out[i + 2], out[i + 1]
            i += 3
            continue
        i += 1
    return out


def _eng_finalc(segs: list[str], rec: dict) -> list[str]:
    """Отпадение конечного согласного заданных классов."""
    classes = set(rec["classes"])
    if len(segs) < 2 or _is_v(segs[-1]):
        return list(segs)
    feats = CONSONANTS.get(segs[-1])
    if feats and (feats[1] in classes or "all" in classes):
        rest = segs[:-1]
        if any(_is_v(s) for s in rest):
            return list(rest)
    return list(segs)


def _eng_cluster(segs: list[str], rec: dict) -> list[str]:
    """Упрощение стечений."""
    mode = rec["mode"]
    out: list[str] = []
    i = 0
    n = len(segs)
    while i < n:
        s = segs[i]
        nxt = segs[i + 1] if i + 1 < n else None
        if nxt is not None and not _is_v(s) and not _is_v(nxt):
            f1, f2 = CONSONANTS.get(s), CONSONANTS.get(nxt)
            if mode == "drop_first" and f1 and f2 and f1[1] in ("stop", "affricate") \
                    and f2[1] in ("stop", "affricate", "nasal") and i > 0:
                i += 1
                continue
            if mode == "assim_nasal" and s in NASAL_CONS and f2 and f2[1] in ("stop", "affricate"):
                place = f2[0]
                repl = {"labial": "m", "dental": "n", "alveolar": "n",
                        "palatal": "ɲ", "velar": "ŋ", "uvular": "ŋ"}.get(place, s)
                out.append(repl)
                i += 1
                continue
            if mode == "drop_s" and s in ("s", "ʃ") and f2 and f2[1] in ("stop", "nasal") and i > 0:
                i += 1
                continue
        out.append(s)
        i += 1
    return out


def _eng_length(segs: list[str], rec: dict) -> list[str]:
    """Удлинение ударного в открытом слоге / утрата долготы."""
    if rec["mode"] == "shorten":
        return [(_vcore(s) + _vmods(s).replace(LONG, "")) if _is_v(s) else s for s in segs]
    stressed = _stressed(segs, rec.get("stress", "initial"))
    out = list(segs)
    for i in list(stressed):
        s = out[i]
        if not _is_v(s) or LONG in _vmods(s):
            continue
        # открытый слог: следующий за согласным идёт гласный либо слово кончилось гласным
        if i + 1 >= len(out) or (i + 2 < len(out) and _is_v(out[i + 2])):
            out[i] = _vcore(s) + LONG + _vmods(s)
    return out


def _eng_prothesis(segs: list[str], rec: dict) -> list[str]:
    """Протеза: гласный перед начальным s + согласный."""
    trig = set(rec["triggers"])
    if len(segs) >= 2 and segs[0] in trig and not _is_v(segs[1]):
        return [rec["vowel"]] + list(segs)
    return list(segs)


def _eng_detone(segs: list[str], rec: dict) -> list[str]:
    """Утрата тона."""
    out = []
    for s in segs:
        if _is_v(s):
            s = "".join(ch for ch in s if ch not in TONE_CHARS)
        out.append(s)
    return out


def _eng_tonogenesis(segs: list[str], rec: dict) -> list[str]:
    return _assign_tones(list(segs), int(rec["n_tones"]))


_ENGINES = {
    "map": _eng_map,
    "vdelete": _eng_vdelete,
    "nasalize": _eng_nasalize,
    "metathesis": _eng_metathesis,
    "finalc": _eng_finalc,
    "cluster": _eng_cluster,
    "length": _eng_length,
    "prothesis": _eng_prothesis,
    "detone": _eng_detone,
    "tonogenesis": _eng_tonogenesis,
}


def _step(segs: list[str], rec: dict) -> list[str]:
    """Применить одну запись истории и починить фонотактику.

    Действует ограничение на минимальное слово: закон не срабатывает, если
    его результат оказался бы короче двух сегментов. Это реальное явление
    (minimal word constraint) и оно не нарушает регулярности — условие
    формулируется через саму форму, а не через список исключений.
    """
    eng = _ENGINES.get(rec.get("engine", ""))
    if eng is None:
        return list(segs)
    out = _repair(eng(list(segs), rec))
    if len(out) < 2 <= len(segs):
        return list(segs)
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Реестр звуковых законов
#  Каждый закон: pick(rng, st) -> параметры или None (если неприменим),
#  after(st, rec) — обновление инвентаря. reductive=True — закон «съедает»
#  материал слова, таких в одной ветви допускается не больше одного.
# ────────────────────────────────────────────────────────────────────────────
def _is_vsym(sym: str) -> bool:
    return sym in VOWEL_CORES or sym in DIPHTHONGS


def _after_map(st: dict, rec: dict) -> None:
    mp = rec["map"]
    uncond = rec["ctx"] == "any"
    for src, dst in mp.items():
        if dst:
            (st["vowels"] if _is_vsym(dst) else st["cons"]).add(dst)
        if uncond:
            (st["vowels"] if _is_vsym(src) else st["cons"]).discard(src)
            st["diph"].discard(src)


def _law(key, label, engine, pick, weight=1.0, reductive=False, after=None, repeatable=False):
    return {"key": key, "label": label, "engine": engine, "pick": pick,
            "weight": weight, "reductive": reductive,
            "after": after or _after_map, "repeatable": repeatable}


def _p_palatal(rng, st):
    C = st["cons"]
    if rng.random() < 0.72:
        pairs = (("k", "tʃ"), ("g", "dʒ"), ("x", "ʃ"))
    else:
        pairs = (("t", "ts"), ("d", "dz"), ("k", "tʃ"), ("g", "dʒ"))
    mp = {a: b for a, b in pairs if a in C}
    if not mp:
        return None
    return {"map": mp, "ctx": "before_front",
            "note": "перед передними гласными"}


def _p_voicing(rng, st):
    C = st["cons"]
    mp = {a: b for a, b in (("p", "b"), ("t", "d"), ("k", "g"), ("s", "z"),
                            ("ts", "dz"), ("tʃ", "dʒ"), ("f", "v")) if a in C}
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "intervocalic", "note": "между гласными"}


def _p_spirant(rng, st):
    C = st["cons"]
    mp = {a: b for a, b in (("b", "v"), ("d", "ð"), ("g", "ɣ")) if a in C}
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "intervocalic", "note": "между гласными"}


def _p_coda_spirant(rng, st):
    C = st["cons"]
    mp = {a: b for a, b in (("p", "f"), ("t", "θ"), ("k", "x")) if a in C}
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "coda", "note": "в исходе слога"}


def _p_grimm(rng, st):
    """Передвижение смычных: глухие -> щелевые, звонкие -> глухие."""
    C = st["cons"]
    mp: dict[str, str] = {}
    for a, b in (("b", "p"), ("d", "t"), ("g", "k")):
        if a in C:
            mp[a] = b
    for a, b in (("p", "f"), ("t", "θ"), ("k", "x")):
        if a in C:
            mp[a] = b
    if len(mp) < 3:
        return None
    return {"map": mp, "ctx": "any", "note": "во всех позициях"}


def _p_apocope(rng, st):
    V = st["vowels"]
    if rng.random() < 0.45:
        tg = sorted(V)
    else:
        tg = sorted(v for v in V if v in ("i", "u", "ə", "ɨ", "y", "e", "o"))
    if not tg:
        return None
    return {"mode": "apocope", "targets": tg, "stress": st["stress"],
            "note": "конечный безударный"}


def _p_syncope(rng, st):
    V = st["vowels"]
    tg = sorted(v for v in V if v in ("i", "u", "ə", "ɨ", "y", "e", "o", "a"))
    if not tg:
        return None
    return {"mode": "syncope", "targets": tg, "stress": st["stress"],
            "note": "срединный безударный"}


def _p_nasalize(rng, st):
    if not (NASAL_CONS & st["cons"]):
        return None
    return {"note": "перед согласным и в исходе"}


def _p_rhotacism(rng, st):
    C = st["cons"]
    src = "z" if "z" in C else ("s" if "s" in C else None)
    if src is None:
        return None
    tgt = "r" if "r" in C else ("ɾ" if "ɾ" in C else "r")
    return {"map": {src: tgt}, "ctx": "intervocalic", "note": "между гласными"}


def _p_monophthong(rng, st):
    D = st["diph"]
    if not D:
        return None
    V = st["vowels"]
    table = {"ai": ("ɛ", "e", "a"), "au": ("ɔ", "o", "u"), "ei": ("e", "i"),
             "oi": ("e", "ɛ", "i"), "ou": ("o", "u"), "ia": ("e", "i"), "ua": ("o", "u")}
    mp: dict[str, str] = {}
    for d in D:
        for cand in table.get(d, ()):
            if cand in V:
                mp[d] = cand
                break
    if not mp:
        return None
    return {"map": mp, "ctx": "any", "note": "стяжение дифтонгов"}


def _after_monophthong(st, rec):
    _after_map(st, rec)
    for d in list(rec["map"]):
        st["diph"].discard(d)


def _p_metathesis(rng, st):
    liq = sorted(LIQUIDS & st["cons"])
    if not liq:
        return None
    return {"liquids": liq, "note": "перестановка плавного"}


def _p_debuccal(rng, st):
    C = st["cons"]
    opts = []
    if "s" in C:
        opts.append(({"s": "h"}, "coda"))
    if "x" in C:
        opts.append(({"x": "h"}, "any"))
    if "ħ" in C:
        opts.append(({"ħ": "h"}, "any"))
    if "f" in C:
        opts.append(({"f": "h"}, "initial"))
    if "θ" in C:
        opts.append(({"θ": "h"}, "any"))
    if not opts:
        return None
    mp, ctx = opts[rng.randrange(len(opts))]
    return {"map": mp, "ctx": ctx, "note": "дебуккализация"}


_MERGE_PAIRS = (("ɛ", "e"), ("ɔ", "o"), ("ə", "a"), ("ɨ", "i"), ("y", "i"),
                ("y", "u"), ("o", "u"), ("e", "i"), ("ɛ", "a"), ("ɔ", "a"), ("ə", "e"))


def _p_merge(rng, st):
    V = st["vowels"]
    if len(V) <= 3:
        return None
    cands = [(a, b) for a, b in _MERGE_PAIRS if a in V and b in V]
    if not cands:
        return None
    a, b = cands[rng.randrange(len(cands))]
    return {"map": {a: b}, "ctx": "any", "note": "слияние гласных"}


def _p_finalc(rng, st):
    cls = _weighted(rng, (("stop",), ("nasal",), ("stop", "affricate"), ("all",)),
                    (0.34, 0.22, 0.22, 0.22))
    return {"classes": list(cls), "note": "отпадение конечного согласного"}


def _after_finalc(st, rec):
    if "all" in rec["classes"]:
        st["no_coda"] = True


def _p_cluster(rng, st):
    mode = _weighted(rng, ("drop_first", "assim_nasal", "drop_s"), (0.45, 0.35, 0.20))
    if mode == "assim_nasal" and not (NASAL_CONS & st["cons"]):
        return None
    if mode == "drop_s" and not ({"s", "ʃ"} & st["cons"]):
        return None
    return {"mode": mode, "note": "упрощение стечений"}


def _after_none(st, rec):
    return None


def _p_final_devoice(rng, st):
    C = st["cons"]
    mp = {a: b for a, b in (("b", "p"), ("d", "t"), ("g", "k"), ("z", "s"),
                            ("v", "f"), ("ʒ", "ʃ"), ("dʒ", "tʃ"), ("ð", "θ")) if a in C}
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "final", "note": "оглушение в исходе"}


def _p_umlaut(rng, st):
    V = st["vowels"]
    mp: dict[str, str] = {}
    if "a" in V and "e" in V:
        mp["a"] = "e"
    if "u" in V:
        if "y" in V:
            mp["u"] = "y"
        elif "i" in V:
            mp["u"] = "i"
    if "o" in V and "e" in V:
        mp["o"] = "e"
    if "ɨ" in V and "i" in V:
        mp["ɨ"] = "i"
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "next_syll_front", "note": "перегласовка по следующему слогу"}


def _p_glide_fort(rng, st):
    C = st["cons"]
    mp: dict[str, str] = {}
    if "w" in C and rng.random() < 0.7:
        mp["w"] = "v"
    if "j" in C:
        mp["j"] = "dʒ" if rng.random() < 0.5 else "ʒ"
    if not mp:
        return None
    return {"map": mp, "ctx": "initial", "note": "усиление глайдов в начале"}


def _p_hloss(rng, st):
    C = st["cons"]
    mp = {}
    if "h" in C:
        mp["h"] = ""
    if "ʔ" in C and rng.random() < 0.5:
        mp["ʔ"] = ""
    if not mp:
        return None
    return {"map": mp, "ctx": "any", "note": "утрата придыхания"}


def _p_uvular(rng, st):
    C = st["cons"]
    mp = {}
    if "q" in C:
        mp["q"] = "k" if "k" in C else "ʔ"
    if "ħ" in C:
        mp["ħ"] = "h"
    if not mp:
        return None
    return {"map": mp, "ctx": "any", "note": "утрата увулярных"}


def _p_liquid(rng, st):
    C = st["cons"]
    if "l" in C and "r" in C:
        return {"map": ({"l": "r"} if rng.random() < 0.5 else {"r": "l"}),
                "ctx": "coda", "note": "мена плавных"}
    if "r" in C:
        return {"map": {"r": "ɾ"}, "ctx": "any", "note": "ослабление дрожащего"}
    if "l" in C:
        return {"map": {"l": "r"}, "ctx": "intervocalic", "note": "мена плавных"}
    return None


def _p_nasal_merge(rng, st):
    C = st["cons"]
    mp = {a: "n" for a in ("ŋ", "ɲ") if a in C}
    if not mp or "n" not in C:
        return None
    return {"map": mp, "ctx": "any", "note": "слияние носовых"}


def _p_deaffricate(rng, st):
    C = st["cons"]
    mp = {a: b for a, b in (("tʃ", "ʃ"), ("ts", "s"), ("dʒ", "ʒ"), ("dz", "z")) if a in C}
    if not mp:
        return None
    return {"map": mp, "ctx": "any", "note": "утрата смычки аффрикат"}


def _p_raise(rng, st):
    V = st["vowels"]
    mp = {}
    if "e" in V and "i" in V:
        mp["e"] = "i"
    if "o" in V and "u" in V:
        mp["o"] = "u"
    if "ɛ" in V and "e" in V:
        mp["ɛ"] = "e"
    if "ɔ" in V and "o" in V:
        mp["ɔ"] = "o"
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "stressed", "stress": st["stress"], "note": "сужение под ударением"}


def _p_lower(rng, st):
    V = st["vowels"]
    mp = {}
    if "i" in V and "e" in V:
        mp["i"] = "e"
    if "u" in V and "o" in V:
        mp["u"] = "o"
    if len(mp) < 2:
        return None
    return {"map": mp, "ctx": "unstressed", "stress": st["stress"], "note": "расширение без ударения"}


def _p_assibilate(rng, st):
    C = st["cons"]
    if "t" not in C:
        return None
    tgt = "s" if "s" in C else ("ts" if "ts" in C else "s")
    return {"map": {"t": tgt}, "ctx": "before_front", "note": "ассибиляция перед передними"}


def _p_sibilant(rng, st):
    C = st["cons"]
    if "s" in C and "ʃ" in C and rng.random() < 0.5:
        return {"map": {"ʃ": "s"}, "ctx": "any", "note": "слияние шипящих со свистящими"}
    if "s" in C:
        return {"map": {"s": "ʃ"}, "ctx": "before_cons", "note": "шипящий перед согласным"}
    return None


def _p_length(rng, st):
    mode = "shorten" if rng.random() < 0.45 else "lengthen"
    return {"mode": mode, "stress": st["stress"],
            "note": "утрата долгот" if mode == "shorten" else "удлинение ударного в открытом слоге"}


def _p_prothesis(rng, st):
    C = st["cons"]
    trig = sorted({"s", "ʃ"} & C)
    if not trig:
        return None
    V = st["vowels"]
    v = "e" if "e" in V else ("i" if "i" in V else "a")
    return {"triggers": trig, "vowel": v, "note": "протеза перед sC-"}


SOUND_LAWS: dict[str, dict] = {}
for _spec in (
    _law("palatalization", "палатализация", "map", _p_palatal, 1.5, repeatable=True),
    _law("voicing", "лениция: озвончение интервокальных", "map", _p_voicing, 1.3),
    _law("spirantization", "спирантизация звонких смычных", "map", _p_spirant, 1.1),
    _law("coda_spirantization", "спирантизация в исходе слога", "map", _p_coda_spirant, 0.8),
    _law("stop_shift", "передвижение смычных", "map", _p_grimm, 0.5),
    _law("apocope", "апокопа", "vdelete", _p_apocope, 1.2, reductive=True, after=_after_none),
    _law("syncope", "синкопа", "vdelete", _p_syncope, 0.9, reductive=True, after=_after_none),
    _law("nasalization", "назализация гласных", "nasalize", _p_nasalize, 0.7, after=_after_none),
    _law("rhotacism", "ротацизм", "map", _p_rhotacism, 0.7),
    _law("monophthongization", "монофтонгизация", "map", _p_monophthong, 1.0, after=_after_monophthong),
    _law("metathesis", "метатеза плавных", "metathesis", _p_metathesis, 0.6, after=_after_none),
    _law("debuccalization", "дебуккализация", "map", _p_debuccal, 0.8),
    _law("vowel_merger", "слияние гласных", "map", _p_merge, 1.3, repeatable=True),
    _law("final_loss", "отпадение конечных согласных", "finalc", _p_finalc, 0.9,
         reductive=True, after=_after_finalc),
    _law("cluster_simplification", "упрощение стечений", "cluster", _p_cluster, 0.9, after=_after_none),
    _law("final_devoicing", "оглушение в исходе", "map", _p_final_devoice, 0.8),
    _law("umlaut", "перегласовка (умлаут)", "map", _p_umlaut, 0.8),
    _law("glide_fortition", "усиление глайдов", "map", _p_glide_fort, 0.6),
    _law("h_loss", "утрата h", "map", _p_hloss, 0.7),
    _law("uvular_loss", "утрата увулярных", "map", _p_uvular, 0.6),
    _law("liquid_shift", "мена плавных", "map", _p_liquid, 0.7),
    _law("nasal_merger", "слияние носовых", "map", _p_nasal_merge, 0.6),
    _law("deaffrication", "утрата аффрикат", "map", _p_deaffricate, 0.7),
    _law("vowel_raising", "сужение гласных", "map", _p_raise, 0.9),
    _law("vowel_lowering", "расширение гласных", "map", _p_lower, 0.7),
    _law("assibilation", "ассибиляция", "map", _p_assibilate, 0.7),
    _law("sibilant_shift", "сдвиг сибилянтов", "map", _p_sibilant, 0.7),
    _law("length_change", "перестройка долгот", "length", _p_length, 0.6, after=_after_none),
    _law("prothesis", "протеза", "prothesis", _p_prothesis, 0.4, after=_after_none),
):
    SOUND_LAWS[_spec["key"]] = _spec
del _spec


# ────────────────────────────────────────────────────────────────────────────
#  Lect — конкретный идиом
# ────────────────────────────────────────────────────────────────────────────
class Lect:
    """Язык одной культуры.

    Слово для смысла НЕ хранится «навсегда» — оно ВЫВОДИТСЯ: праформа
    чеканится от (root_seed, meaning), затем по ней прогоняется вся цепочка
    унаследованных звуковых законов. Отсюда и регулярность соответствий,
    и то, что ленивое обращение к новому смыслу даёт ровно тот же результат,
    что и пошаговое ведение полного словаря.
    """

    __slots__ = ("lid", "name", "root_seed", "proto", "phono", "prosody", "morph",
                 "affixes", "history", "stages", "used_laws", "lex", "generations",
                 "depth", "_rom")

    # ── создание ──────────────────────────────────────────────────────────
    def __init__(self) -> None:
        self.lid = "0"
        self.name = ""
        self.root_seed = 0
        self.proto: dict[str, Any] = {}
        self.phono: dict[str, Any] = {}
        self.prosody: dict[str, Any] = {}
        self.morph: dict[str, Any] = {}
        self.affixes: dict[str, list[str]] = {}
        self.history: list[dict] = []
        self.stages: list[dict] = []
        self.used_laws: list[str] = []
        self.lex: dict[str, list[str]] = {}
        self.generations = 0
        self.depth = 0
        self._rom: dict[str, str] = {}

    @classmethod
    def create(cls, seed: int) -> "Lect":
        """Праязык с нуля."""
        rng = random.Random(int(seed) * 6364136223846793005 % (1 << 62))
        self = cls()
        self.lid = str(int(seed))
        self.root_seed = int(seed)
        phono = _make_phono(rng)
        self.proto = json.loads(json.dumps(phono))     # неизменяемый слепок для чеканки корней
        self.phono = phono
        self.prosody = {
            "stress": _weighted(rng, ("initial", "penult", "final"), (0.35, 0.40, 0.25)),
            "harmony": phono["harmony"],
            "tone": phono["tone"],
            "n_tones": phono["n_tones"],
        }
        order = _weighted(rng, [o for o, _ in WORD_ORDERS], [w for _, w in WORD_ORDERS])
        mtype = _weighted(rng, [m for m, _ in MORPH_TYPES], [w for _, w in MORPH_TYPES])
        if mtype == "isolating":
            cases = 0
        else:
            cases = rng.randint(2, 8) if rng.random() < 0.75 else 0
        genders = _weighted(rng, (0, 2, 3, 4), (0.45, 0.28, 0.17, 0.10))
        if mtype == "isolating":
            genders = 0 if rng.random() < 0.8 else genders
        # префиксация чаще у VO-языков, суффиксация — у OV
        pref_p = 0.42 if order in ("VSO", "VOS", "SVO") else 0.16
        self.morph = {
            "type": mtype,
            "order": order,
            "cases": int(cases),
            "genders": int(genders),
            "affix_pos": "prefix" if rng.random() < pref_p else "suffix",
            "compound_order": ("mod-head" if order in ("SOV", "OSV", "OVS")
                               else "head-mod" if order in ("VSO", "VOS")
                               else ("mod-head" if rng.random() < 0.6 else "head-mod")),
        }
        self.affixes = {k: _coin_affix(rng, phono, k) for k in AFFIX_KEYS}
        self.name = self.ethnonym(random.Random(_h64(f"AUTONYM|{self.lid}")))
        return self

    # ── внутреннее: вывод формы ───────────────────────────────────────────
    def _replace_rate(self, meaning: str, base: float) -> float:
        return base * (0.35 if meaning in STABLE_CORE else 1.0)

    def _derive(self, meaning: str, upto: int | None = None) -> list[str]:
        """Проиграть историю от праформы до нужного шага."""
        segs = _coin(_h64(f"ROOT|{self.root_seed}|{meaning}"), self.proto)
        end = len(self.history) if upto is None else upto
        for rec in self.history[:end]:
            if rec.get("engine") == "renew":
                rate = self._replace_rate(meaning, float(rec["rate"]))
                if _unit(f"REPL|{rec['sid']}|{meaning}") < rate:
                    segs = _coin(_h64(f"NEW|{rec['sid']}|{meaning}"), rec["phono"])
                continue
            segs = _step(segs, rec)
        return segs

    def form(self, meaning: str) -> list[str]:
        """Фонемная форма слова (список сегментов). Кэшируется."""
        cached = self.lex.get(meaning)
        if cached is not None:
            return cached
        segs = self._derive(meaning)
        self.lex[meaning] = segs
        return segs

    def word(self, meaning: str) -> str:
        """Слово для смысла в читаемой латинице. Детерминировано и кэшируется."""
        got = self._rom.get(meaning)
        if got is not None:
            return got
        out = romanize(self.form(meaning))
        self._rom[meaning] = out
        return out

    def has(self, meaning: str) -> bool:
        return meaning in self.lex

    # ── словообразование ──────────────────────────────────────────────────
    def _join(self, a: Sequence[str], b: Sequence[str]) -> list[str]:
        """Сложение двух основ со швом."""
        a, b = list(a), list(b)
        if not a:
            return b
        if not b:
            return a
        seam: list[str] = []
        # интерфикс: у агглютинативных и фузионных языков шов часто озвучен
        if self.morph["type"] != "isolating" and not _is_v(a[-1]) and not _is_v(b[0]):
            if not _good_coda_cluster(a[-1], b[0]) and not _good_onset_cluster(a[-1], b[0]):
                V = self.phono["vowels"]
                link = "o" if "o" in V else ("ə" if "ə" in V else ("a" if "a" in V else V[0]))
                seam = [link]
        return _repair(a + seam + b)

    def _bind(self, mod: Sequence[str], head: Sequence[str],
              gm: str, gh: str, limit: int = 11) -> tuple[list[str], str]:
        """Связать определение и вершину по типологии языка.

        Если сложение выходит громоздким, определение отбрасывается —
        имена не должны превращаться в скороговорку.
        """
        mod, head = list(mod), list(head)
        if len(mod) + len(head) > limit:
            return head, gh
        if self.morph["compound_order"] == "mod-head":
            return self._join(mod, head), f"{gm}-{gh}"
        return self._join(head, mod), f"{gh}-{gm}"

    def compound(self, m1: str, m2: str) -> str:
        """Сложение основ по правилам языка.

        Порядок «определение — определяемое» берётся из типологии:
        у OV-языков определение впереди («огонь-камень»), у VO-языков — сзади.
        Второй аргумент — семантическая вершина.
        """
        head, mod = self.form(m2), self.form(m1)
        if self.morph["compound_order"] == "mod-head":
            segs = self._join(mod, head)
        else:
            segs = self._join(head, mod)
        return romanize(segs)

    def compound_form(self, m1: str, m2: str) -> list[str]:
        head, mod = self.form(m2), self.form(m1)
        return (self._join(mod, head) if self.morph["compound_order"] == "mod-head"
                else self._join(head, mod))

    def derive(self, meaning: str, affix: str) -> str:
        """Присоединить грамматический/словообразовательный показатель."""
        base = self.form(meaning)
        aff = self.affixes.get(affix)
        if not aff:
            return romanize(base)
        segs = (self._join(aff, base) if self.morph["affix_pos"] == "prefix"
                else self._join(base, aff))
        return romanize(segs)

    def _affix_form(self, base: Sequence[str], affix: str) -> list[str]:
        aff = self.affixes.get(affix)
        if not aff:
            return list(base)
        return (self._join(aff, base) if self.morph["affix_pos"] == "prefix"
                else self._join(base, aff))

    # ── имена ─────────────────────────────────────────────────────────────
    def person_name(self, rng: random.Random, sex: int, role: str | None = None) -> str:
        """Личное имя. sex: 0 — женский, 1 — мужской (как в contracts.Person)."""
        stock = NAME_STOCK_M if sex else NAME_STOCK_F
        pool = list(stock) + list(NAME_STOCK_N)
        mtype = self.morph["type"]
        noble = role in ("chief", "king", "noble", "priest", "hero", "царь", "вождь", "жрец")

        # двухосновное имя — привилегия знати и фузионно-агглютинативных языков
        dithematic = rng.random() < (0.55 if noble else 0.28) and mtype != "isolating"
        if dithematic:
            m1 = rng.choice(pool)
            m2 = rng.choice([m for m in pool if m != m1])
            f1, f2 = self.form(m1), self.form(m2)
            if len(f1) + len(f2) > 9:       # слишком громоздко — берём одну основу
                dithematic = False
            else:
                segs = self._join(f1, f2)
        if not dithematic:
            segs = list(self.form(rng.choice(pool)))
            if rng.random() < 0.45:
                segs = self._affix_form(segs, "dim" if rng.random() < 0.4 else "agent")

        # родовой показатель — там, где грамматический род вообще есть
        if self.morph["genders"] >= 2 and mtype in ("fusional", "agglutinative"):
            if rng.random() < (0.85 if mtype == "fusional" else 0.5):
                segs = self._affix_form(segs, "fem" if sex == 0 else "masc")

        name = _cap(romanize(segs))

        if noble and rng.random() < 0.55:
            if rng.random() < 0.5:
                # патроним: «сын/дочь такого-то»
                par = self.form(rng.choice(NAME_STOCK_M))
                par = self._affix_form(par, "gen") if self.morph["cases"] else par
                kin = self.form("сын" if sex else "дочь")
                pat = self._join(par, kin) if self.morph["compound_order"] == "mod-head" \
                    else self._join(kin, par)
                name = f"{name} {_cap(romanize(pat))}"
            else:
                # эпитет
                ep = self.form(rng.choice(EPITHETS))
                name = f"{name} {_cap(romanize(ep))}"
        return name

    def ethnonym(self, rng: random.Random) -> str:
        """Самоназвание народа."""
        mode = _weighted(rng, ("people", "speech", "land", "true", "root"),
                         (0.34, 0.18, 0.20, 0.14, 0.14))
        if mode == "people":
            segs = self.form(rng.choice(("человек", "народ", "племя")))
        elif mode == "speech":
            segs = self.form("говорить")
        elif mode == "land":
            segs = self._join(self.form(rng.choice(("земля", "гора", "река", "поле", "лес"))),
                              self.form("человек"))
        elif mode == "true":
            segs = self._join(self.form(rng.choice(("святой", "сильный", "старый", "свободный"))),
                              self.form("человек"))
        else:
            segs = self.form(f"этноним:{rng.randrange(1 << 30)}")
        if rng.random() < 0.7:
            segs = self._affix_form(segs, "coll" if rng.random() < 0.6 else "pl")
        return _cap(romanize(segs))

    def place_name(self, rng: random.Random, kind: str,
                   features: Iterable[str] | None = None, *,
                   with_gloss: bool = False) -> Any:
        """Топоним с прозрачной внутренней формой.

        kind ∈ {settlement, river, mountain, region, sea, island}
        features — подсказки о месте (смыслы вроде «широкий», «соль», «чёрный»).
        """
        kind = kind if kind in PLACE_HEADS else "settlement"
        head_m = rng.choice(PLACE_HEADS[kind])
        feats = [f for f in (features or ()) if isinstance(f, str)]
        mod_m = rng.choice(feats) if (feats and rng.random() < 0.75) else rng.choice(PLACE_MODS[kind])

        simple = rng.random() < 0.22
        if simple:
            segs = self._affix_form(self.form(head_m), "place")
            gloss = f"{head_m}-МЕСТО"
        else:
            segs, gloss = self._bind(self.form(mod_m), self.form(head_m), mod_m, head_m)
            if rng.random() < 0.30 and len(segs) <= 9:
                segs = self._affix_form(segs, "place")
                gloss += "-МЕСТО"
        name = _cap(romanize(segs))
        return (name, gloss) if with_gloss else name

    def theonym(self, rng: random.Random, domain: str, *, with_gloss: bool = False) -> Any:
        """Имя божества по домену (небо, буря, плодородие, смерть, война,
        солнце, море, очаг, ремесло, мудрость)."""
        dom = _DOMAIN_ALIASES.get(domain, domain)
        pool = GOD_DOMAINS.get(dom)
        if pool is None:
            pool = (dom,) if dom else ("бог",)
        core_m = rng.choice(pool)
        shape = _weighted(rng, ("compound", "epithet", "derived"), (0.42, 0.30, 0.28))
        if shape == "compound":
            head_m = rng.choice([h for h in DIVINE_HEADS if h != core_m])
            segs, gloss = self._bind(self.form(core_m), self.form(head_m), core_m, head_m, 10)
        elif shape == "epithet":
            ep_m = rng.choice([e for e in DIVINE_EPITHETS if e != core_m])
            segs, gloss = self._bind(self.form(ep_m), self.form(core_m), ep_m, core_m, 10)
        else:
            segs = self._affix_form(self.form(core_m), rng.choice(("aug", "agent", "abst")))
            gloss = f"{core_m}-ВЕЛ."
        name = _cap(romanize(segs))
        return (name, gloss) if with_gloss else name

    def title(self, rng: random.Random, form: str, *, with_gloss: bool = False) -> Any:
        """Титул правителя для формы правления (см. contracts.POLITY_FORMS)."""
        recipe = TITLE_RECIPE.get(form, TITLE_RECIPE["tribe"])
        if len(recipe) == 1:
            base = self.form(recipe[0])
            gloss = recipe[0]
            if rng.random() < 0.45:
                base = self._affix_form(base, "aug")
                gloss += "-ВЕЛ."
            segs = base
        else:
            m1, m2 = recipe
            a, b = self.form(m1), self.form(m2)
            if form == "empire":
                # «царь царей»: вершина + зависимое в родительном
                dep = self._affix_form(a, "gen") if self.morph["cases"] else self._affix_form(a, "pl")
                segs = self._join(b, dep) if self.morph["compound_order"] == "head-mod" \
                    else self._join(dep, b)
                gloss = f"{m1}-РОД.МН + {m2}"
            elif self.morph["compound_order"] == "mod-head":
                segs, gloss = self._join(a, b), f"{m1}-{m2}"
            else:
                segs, gloss = self._join(b, a), f"{m2}-{m1}"
        name = _cap(romanize(segs))
        return (name, gloss) if with_gloss else name

    # ── диахрония ─────────────────────────────────────────────────────────
    def _state(self) -> dict[str, Any]:
        return {
            "cons": set(self.phono["cons"]),
            "vowels": set(self.phono["vowels"]),
            "diph": set(self.phono["diph"]),
            "stress": self.prosody["stress"],
            "no_coda": False,
        }

    def _sync(self, st: dict) -> None:
        self.phono["cons"] = sorted(st["cons"], key=lambda c: (-CFREQ.get(c, 1.0), c))
        self.phono["vowels"] = [v for v in VOWEL_CORES if v in st["vowels"]] or ["a"]
        self.phono["diph"] = sorted(st["diph"])
        if st.get("no_coda"):
            # язык потерял конечные согласные — новые корни тоже строятся открытыми
            slots = list(self.phono["slots"])
            if len(slots) > 2 and slots[-1] in ("c", "C"):
                slots = slots[:-1]
            self.phono["slots"] = slots or ["C", "V"]
            self.phono["coda_cluster"] = False
        self.phono["harmony"] = self.prosody["harmony"]
        self.phono["tone"] = self.prosody["tone"]
        self.phono["n_tones"] = self.prosody["n_tones"]

    def _choose_laws(self, rng: random.Random, st: dict, n: int) -> list[dict]:
        """Отобрать n применимых законов, обновляя состояние инвентаря."""
        keys = list(SOUND_LAWS)
        chosen: list[dict] = []
        red_budget = 1
        picked_here: set[str] = set()
        for _ in range(n * 12):
            if len(chosen) >= n:
                break
            weights = []
            for k in keys:
                spec = SOUND_LAWS[k]
                w = spec["weight"]
                if k in picked_here:
                    w *= 0.02
                elif k in self.used_laws and not spec["repeatable"]:
                    w *= 0.22
                weights.append(w)
            key = _weighted(rng, keys, weights)
            spec = SOUND_LAWS[key]
            if spec["reductive"] and red_budget <= 0:
                continue
            if key in picked_here:
                continue
            rec = spec["pick"](rng, st)
            if rec is None:
                continue
            rec["key"] = key
            rec["engine"] = spec["engine"]
            rec["label"] = spec["label"]
            spec["after"](st, rec)
            if spec["reductive"]:
                red_budget -= 1
            picked_here.add(key)
            if key not in self.used_laws:
                self.used_laws.append(key)
            chosen.append(rec)
        return chosen

    def _shift_prosody(self, rng: random.Random) -> list[dict]:
        """Дрейф просодии. Возвращает записи истории (тон влияет на форму слова)."""
        recs: list[dict] = []
        if rng.random() < 0.28:
            opts = [s for s in ("initial", "penult", "final") if s != self.prosody["stress"]]
            self.prosody["stress"] = rng.choice(opts)
        if self.prosody["harmony"] == "front_back":
            if rng.random() < 0.22:
                self.prosody["harmony"] = "none"
        elif rng.random() < 0.05 and len(self.phono["vowels"]) >= 5:
            self.prosody["harmony"] = "front_back"
        if self.prosody["tone"]:
            if rng.random() < 0.16:
                self.prosody["tone"] = False
                self.prosody["n_tones"] = 0
                recs.append({"engine": "detone", "key": "tone_loss",
                             "label": "утрата тона", "note": ""})
        elif rng.random() < 0.07:
            n = 2 if rng.random() < 0.6 else 3
            self.prosody["tone"] = True
            self.prosody["n_tones"] = n
            recs.append({"engine": "tonogenesis", "key": "tonogenesis", "n_tones": n,
                         "label": "тоногенез", "note": f"{n} тона"})
        return recs

    def _shift_morphology(self, rng: random.Random) -> None:
        m = self.morph
        if rng.random() < 0.20:
            m["type"] = MORPH_CYCLE[m["type"]]
            if m["type"] == "isolating":
                m["cases"] = 0
                m["genders"] = 0 if rng.random() < 0.7 else m["genders"]
            elif m["cases"] == 0 and rng.random() < 0.6:
                m["cases"] = rng.randint(2, 5)
        if rng.random() < 0.30 and m["type"] != "isolating":
            m["cases"] = max(0, min(9, m["cases"] + rng.choice((-2, -1, 1, 1, 2))))
        if rng.random() < 0.12:
            m["genders"] = max(0, min(6, m["genders"] + rng.choice((-1, 1))))
        if rng.random() < 0.10:
            neigh = {"SOV": "SVO", "SVO": "SOV", "VSO": "SVO",
                     "VOS": "VSO", "OVS": "SOV", "OSV": "SOV"}
            m["order"] = neigh.get(m["order"], "SVO")
            m["compound_order"] = ("mod-head" if m["order"] in ("SOV", "OSV", "OVS")
                                   else "head-mod")
        if rng.random() < 0.10:
            m["affix_pos"] = "prefix" if m["affix_pos"] == "suffix" else "suffix"

    def _evolve(self, rng: random.Random, generations: int, sid: str,
                stage_label: str) -> None:
        """Ядро диахронии: обновить просодию/морфологию, отобрать и применить законы."""
        n = max(1, int(round(generations / 11.0)) + rng.choice((-1, 0, 0, 1)))
        # 1. лексическая новация — часть словаря обновляется до звуковых сдвигов
        rate = 1.0 - math.exp(-generations / 1800.0)
        renew = {"engine": "renew", "key": "lexical_renewal", "sid": sid,
                 "rate": round(rate, 5),
                 "phono": json.loads(json.dumps(self.phono)),
                 "label": "лексическая новация", "note": f"{rate * 100:.1f}% словаря"}
        # 2. просодия и морфология
        pros = self._shift_prosody(rng)
        self._shift_morphology(rng)
        # 3. звуковые законы
        st = self._state()
        laws = self._choose_laws(rng, st, n)
        self._sync(st)

        new_recs = [renew] + pros + laws
        # применяем к уже вычисленному кэшу и к аффиксам — тем же кодом, что и при выводе
        for rec in new_recs:
            if rec["engine"] == "renew":
                for meaning in list(self.lex):
                    r = self._replace_rate(meaning, float(rec["rate"]))
                    if _unit(f"REPL|{rec['sid']}|{meaning}") < r:
                        self.lex[meaning] = _coin(_h64(f"NEW|{rec['sid']}|{meaning}"), rec["phono"])
                continue
            for meaning, segs in self.lex.items():
                self.lex[meaning] = _step(segs, rec)
            for k, segs in self.affixes.items():
                self.affixes[k] = _step(segs, rec) if segs else segs
        self.history.extend(new_recs)
        self._rom.clear()

        # 4. обновление грамматических показателей (грамматикализация)
        arng = random.Random(_h64(f"AFFIX|{sid}"))
        for k in AFFIX_KEYS:
            cur = self.affixes.get(k) or []
            if not cur or len(cur) > 4 or arng.random() < 0.10:
                self.affixes[k] = _coin_affix(arng, self.phono, k)
        self.generations += int(generations)
        self.stages.append({"at": len(self.history), "label": stage_label,
                            "gen": self.generations, "laws": [r["key"] for r in laws]})

    def branch(self, rng: random.Random, generations: int) -> "Lect":
        """Дочерний язык: копия предка, прошедшая свои звуковые изменения."""
        child = Lect.from_dict(self.to_dict())
        suffix = rng.choice("abcdefghijklmnopqrstuvwxyz") + str(rng.randrange(100, 999))
        child.lid = f"{self.lid}.{suffix}"
        child.depth = self.depth + 1
        sid = f"{child.lid}#{len(child.history)}"
        child._evolve(rng, generations, sid, f"{child.lid}")
        child.name = child.ethnonym(random.Random(_h64(f"AUTONYM|{child.lid}")))
        return child

    def drift(self, rng: random.Random, years: int) -> "Lect":
        """Медленная эволюция на месте, без ветвления. Возвращает себя."""
        generations = max(1, int(round(years / 25.0)))
        sid = f"{self.lid}~{len(self.history)}"
        self._evolve(rng, generations, sid, f"{self.lid}+{years}л")
        return self

    # ── измерения ─────────────────────────────────────────────────────────
    def _gram_vector(self) -> dict[str, Any]:
        return {
            "order": self.morph["order"],
            "type": self.morph["type"],
            "cases": self.morph["cases"],
            "genders": self.morph["genders"],
            "affix_pos": self.morph["affix_pos"],
            "stress": self.prosody["stress"],
            "harmony": self.prosody["harmony"],
            "tone": bool(self.prosody["tone"]),
        }

    def distance(self, other: "Lect", probes: Sequence[str] | None = None) -> float:
        """0..1 — оценка утраты взаимопонятности.

        Лексическая часть: нормированное расстояние Левенштейна по общему
        базовому словарю. Грамматическая: расхождение типологических признаков.
        """
        if other is self:
            return 0.0
        probes = probes or BASIC_MEANINGS[:90]
        acc = 0.0
        cnt = 0
        for m in probes:
            a, b = self.form(m), other.form(m)
            if not a or not b:
                continue
            acc += _lev(a, b) / max(len(a), len(b))
            cnt += 1
        lex = acc / cnt if cnt else 1.0

        ga, gb = self._gram_vector(), other._gram_vector()
        gram = 0.0
        gram += 0.28 * (ga["order"] != gb["order"])
        gram += 0.22 * (ga["type"] != gb["type"])
        gram += 0.16 * min(1.0, abs(ga["cases"] - gb["cases"]) / 5.0)
        gram += 0.10 * (bool(ga["genders"]) != bool(gb["genders"]))
        gram += 0.10 * (ga["affix_pos"] != gb["affix_pos"])
        gram += 0.06 * (ga["stress"] != gb["stress"])
        gram += 0.04 * (ga["harmony"] != gb["harmony"])
        gram += 0.04 * (ga["tone"] != gb["tone"])
        return float(min(1.0, max(0.0, 0.78 * lex + 0.22 * gram)))

    def cognate_share(self, other: "Lect", probes: Sequence[str] | None = None,
                      threshold: float = 0.45) -> float:
        """Доля значений, чьи формы ещё узнаваемо родственны."""
        probes = probes or BASIC_MEANINGS[:90]
        hits = 0
        cnt = 0
        for m in probes:
            a, b = self.form(m), other.form(m)
            if not a or not b:
                continue
            cnt += 1
            if _lev(a, b) / max(len(a), len(b)) <= threshold:
                hits += 1
        return hits / cnt if cnt else 0.0

    def _chain(self, probe: str) -> list[str]:
        bounds = [0] + [s["at"] for s in self.stages]
        if not self.stages or bounds[-1] != len(self.history):
            bounds.append(len(self.history))
        forms: list[str] = []
        for k in bounds:
            r = romanize(self._derive(probe, upto=k))
            if not forms or forms[-1] != r:
                forms.append(r)
        return forms

    def family_tree_label(self, probe: str | None = None, *,
                          with_meaning: bool = False) -> str:
        """Читаемая метка родословной: «*ker- > kʲer > šer».

        Если probe задан — берётся именно он. Если нет — выбирается то
        устойчивое слово, чья цепочка нагляднее всего показывает сдвиги.
        """
        if probe is not None:
            best, used = self._chain(probe), probe
        else:
            best, used = [], "камень"
            for m in ("камень", "вода", "огонь", "рука", "мать", "три",
                      "солнце", "кровь", "путь", "зуб"):
                ch = self._chain(m)
                if len(ch) > len(best):
                    best, used = ch, m
                if len(best) >= len(self.stages) + 1:
                    break
        if not best:
            return "—"
        label = " > ".join(["*" + best[0] + "-"] + best[1:])
        return f"«{used}» {label}" if with_meaning else label

    # ── сериализация ──────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        """Полный JSON-совместимый слепок (включая кэш и историю изменений)."""
        return {
            "v": LECT_SCHEMA,
            "lid": self.lid,
            "name": self.name,
            "root_seed": int(self.root_seed),
            "proto": json.loads(json.dumps(self.proto)),
            "phono": json.loads(json.dumps(self.phono)),
            "prosody": dict(self.prosody),
            "morph": dict(self.morph),
            "affixes": {k: list(v) for k, v in self.affixes.items()},
            "history": json.loads(json.dumps(self.history)),
            "stages": json.loads(json.dumps(self.stages)),
            "used_laws": list(self.used_laws),
            "lex": {k: list(v) for k, v in self.lex.items()},
            "generations": int(self.generations),
            "depth": int(self.depth),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Lect":
        self = cls()
        self.lid = d["lid"]
        self.name = d.get("name", "")
        self.root_seed = int(d["root_seed"])
        self.proto = json.loads(json.dumps(d["proto"]))
        self.phono = json.loads(json.dumps(d["phono"]))
        self.prosody = dict(d["prosody"])
        self.morph = dict(d["morph"])
        self.affixes = {k: list(v) for k, v in d.get("affixes", {}).items()}
        self.history = json.loads(json.dumps(d.get("history", [])))
        self.stages = json.loads(json.dumps(d.get("stages", [])))
        self.used_laws = list(d.get("used_laws", []))
        self.lex = {k: list(v) for k, v in d.get("lex", {}).items()}
        self.generations = int(d.get("generations", 0))
        self.depth = int(d.get("depth", 0))
        return self

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kw)

    @classmethod
    def from_json(cls, s: str) -> "Lect":
        return cls.from_dict(json.loads(s))

    # ── описание ──────────────────────────────────────────────────────────
    def syllable_shape(self) -> str:
        s = "".join("(C)" if c == "c" else c for c in self.phono["slots"])
        if self.phono["onset_cluster"]:
            s = "(C)" + s
        if self.phono["coda_cluster"]:
            s = s + "(C)"
        return s

    def passport(self) -> str:
        """Паспорт языка для летописи и отладки."""
        p, pr, m = self.phono, self.prosody, self.morph
        cons = " ".join(p["cons"])
        vows = " ".join(p["vowels"])
        diph = " ".join(p["diph"]) if p["diph"] else "нет"
        tone = f"{pr['n_tones']} тона" if pr["tone"] else "нет"
        harm = "гармония гласных по ряду" if pr["harmony"] == "front_back" else "нет гармонии"
        mtype = {"isolating": "изолирующий", "agglutinative": "агглютинативный",
                 "fusional": "фузионный"}[m["type"]]
        stress = {"initial": "начальное", "penult": "предпоследнее", "final": "конечное"}[pr["stress"]]
        aff = ", ".join(f"{AFFIX_RU[k]}={romanize(self.affixes[k])}"
                        for k in ("pl", "gen", "dim", "agent", "place", "coll")
                        if self.affixes.get(k))
        lines = [
            f"{self.name} [{self.lid}]  —  поколений от праязыка: {self.generations}",
            f"  согласные ({len(p['cons'])}): {cons}",
            f"  гласные ({len(p['vowels'])}): {vows}   дифтонги: {diph}",
            f"  слог: {self.syllable_shape()}   ударение: {stress}   тон: {tone}   {harm}",
            f"  морфология: {mtype}, порядок слов {m['order']}, "
            f"падежей {m['cases']}, родов/классов {m['genders']}, "
            f"{'префиксы' if m['affix_pos'] == 'prefix' else 'суффиксы'}",
            f"  сложение основ: {'определение+вершина' if m['compound_order'] == 'mod-head' else 'вершина+определение'}",
            f"  показатели: {aff}",
        ]
        if self.stages:
            laws = []
            for s in self.stages:
                laws.extend(s.get("laws", []))
            if laws:
                names = [SOUND_LAWS[k]["label"] for k in laws if k in SOUND_LAWS]
                lines.append(f"  звуковые законы ({len(names)}): {'; '.join(names)}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<Lect {self.name} [{self.lid}] gen={self.generations} lex={len(self.lex)}>"


def distance_matrix(lects: Sequence[Lect]) -> np.ndarray:
    """Симметричная матрица попарных расстояний (float32)."""
    n = len(lects)
    out = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            d = lects[i].distance(lects[j])
            out[i, j] = out[j, i] = d
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Демонстрация
# ────────────────────────────────────────────────────────────────────────────
def _table(rows: Sequence[Sequence[str]], sep: str = "  ") -> str:
    n = max(len(r) for r in rows)
    widths = [0] * n
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], _vwidth(c))
    return "\n".join(sep.join(_pad(c, widths[i]) for i, c in enumerate(r)).rstrip() for r in rows)


def _demo() -> None:
    SEED = 7
    proto = Lect.create(SEED)
    rule = "─" * 78

    print(rule)
    print("ПРАЯЗЫК — паспорт")
    print(rule)
    print(proto.passport())
    print()

    print(rule)
    print("15 базовых слов праязыка")
    print(rule)
    show = ("вода", "огонь", "солнце", "камень", "река", "гора", "дом", "мать",
            "кровь", "путь", "зерно", "бык", "небо", "соль", "война")
    rows = [[f"{m}:", proto.word(m)] for m in show]
    print(_table(rows, sep="  "))
    print()
    print("  словосложение:  "
          f"огонь+камень = {proto.compound('огонь', 'камень')}  ·  "
          f"вода+путь = {proto.compound('вода', 'путь')}  ·  "
          f"солнце+дом = {proto.compound('солнце', 'дом')}")
    print()

    # ── ветвление ──
    tier1 = [proto.branch(random.Random(100 + i), 60) for i in range(3)]
    tier2: list[Lect] = []
    labels = ["ПРА"]
    for i, b in enumerate(tier1):
        for k in range(2):
            tier2.append(b.branch(random.Random(200 + i * 10 + k), 80))
            labels.append(f"{chr(65 + i)}{k + 1}")
    langs = [proto] + tier2

    print(rule)
    print("РОДОСЛОВНАЯ: праязык → 3 ветви по 60 поколений → по 2 по 80 поколений")
    print(rule)
    for lab, lg in zip(labels, langs):
        print(f"  {_pad(lab, 4)} {_pad(lg.name, 14)} {lg.lid}")
    print()
    for lab, lg in zip(labels, langs):
        print(f"  {_pad(lab, 4)} {lg.family_tree_label(with_meaning=True)}")
    print()

    # ── таблица когнатов ──
    print(rule)
    print("ТАБЛИЦА КОГНАТОВ  (12 значений × 7 языков)")
    print(rule)
    meanings = ("вода", "огонь", "солнце", "камень", "река", "гора",
                "дом", "мать", "кровь", "путь", "зерно", "бык")
    head = ["значение"] + labels
    rows = [head, ["─" * 8] + ["─" * 6 for _ in labels]]
    for m in meanings:
        rows.append([m] + [lg.word(m) for lg in langs])
    print(_table(rows, sep="   "))
    print()

    # ── расстояния ──
    print(rule)
    print("ПОПАРНЫЕ РАССТОЯНИЯ (0 — один язык, 1 — полная непонятность)")
    print(rule)
    dm = distance_matrix(langs)
    rows = [[""] + labels]
    for i, lab in enumerate(labels):
        rows.append([lab] + [("  ·  " if i == j else f"{dm[i, j]:.2f}") for j in range(len(langs))])
    print(_table(rows, sep="  "))
    print()
    cog = [[""] + labels]
    for i, lab in enumerate(labels):
        cog.append([lab] + [("  ·  " if i == j else f"{langs[i].cognate_share(langs[j]) * 100:3.0f}%")
                            for j in range(len(langs))])
    print("доля узнаваемых когнатов по 90 базовым значениям:")
    print(_table(cog, sep="  "))
    print()

    # ── ономастика ──
    print(rule)
    print("ОНОМАСТИКА")
    print(rule)
    kinds = ("settlement", "river", "mountain", "region")
    domains = ("небо", "война", "плодородие")
    for lab, lg in zip(labels, langs):
        r = random.Random(_h64(f"DEMO|{lg.lid}"))
        men = [lg.person_name(r, 1, "chief" if i == 0 else None) for i in range(3)]
        wom = [lg.person_name(r, 0, "noble" if i == 0 else None) for i in range(3)]
        places = [lg.place_name(r, k, with_gloss=True) for k in kinds]
        gods = [lg.theonym(r, d, with_gloss=True) for d in domains]
        ttl, tgl = lg.title(r, "kingdom", with_gloss=True)
        print(f"[{lab}] {lg.name}  ({lg.morph['order']}, "
              f"{ {'isolating': 'изолир.', 'agglutinative': 'агглют.', 'fusional': 'фузион.'}[lg.morph['type']] })")
        print(f"   мужские:  {', '.join(men)}")
        print(f"   женские:  {', '.join(wom)}")
        print("   топонимы: " + ", ".join(f"{n} ({k}: {g})" for (n, g), k in zip(places, kinds)))
        print("   боги:     " + ", ".join(f"{n} ({d}: {g})" for (n, g), d in zip(gods, domains)))
        print(f"   титул:    {ttl}  ({tgl})")
        print()

    # ── самопроверка ──
    print(rule)
    print("САМОПРОВЕРКА")
    print(rule)
    blob = proto.to_json()
    back = Lect.from_json(blob)
    same_lex = all(back.word(m) == proto.word(m) for m in BASIC_MEANINGS)
    fresh = Lect.create(SEED)
    same_seed = all(fresh.word(m) == proto.word(m) for m in BASIC_MEANINGS)
    lazy_ok = True
    for lg in langs:
        clone = Lect.from_dict({**lg.to_dict(), "lex": {}})   # пустой кэш -> ленивый вывод
        if any(clone.word(m) != lg.word(m) for m in BASIC_MEANINGS):
            lazy_ok = False
            break
    print(f"  значений в базовом списке:      {len(BASIC_MEANINGS)}")
    print(f"  сериализация round-trip:        {'OK' if same_lex else 'ОШИБКА'}")
    print(f"  повтор от того же seed:         {'OK' if same_seed else 'ОШИБКА'}")
    print(f"  ленивый вывод == пошаговый:     {'OK' if lazy_ok else 'ОШИБКА'}")
    print(f"  размер слепка праязыка:         {len(blob)} байт JSON")


if __name__ == "__main__":
    _demo()
