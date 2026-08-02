"""
TERRA — лица мира.

Люди в симуляции описаны числами: год рождения, черты характера, ремесло,
что они успели сделать, во что был одет их народ и чем он владел. Этого
достаточно, чтобы собрать словесный портрет конкретного человека — не
«первобытного мужчины вообще», а вот этого, с именем, возрастом и делом.

Модуль превращает запись из книги мира в подробное описание внешности,
пригодное для фотореалистичной съёмки. Всё, что в описании, выведено из
состояния симуляции: одежда — из освоенных ремёсел, украшения — из руд,
которые народ добывал, орудие в руках — из того, что он умел делать,
лицо и осанка — из черт характера и прожитой жизни.

    python -m terra.portrait runs/terra-1            # показать словесные портреты
    python -m terra.portrait runs/terra-1 --json     # то же машиночитаемо
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

# ── что народ носит, исходя из освоенных ремёсел ────────────────────────────
GARMENT = [
    ("wool", "плотная шерстяная накидка ручной работы, окрашенная в приглушённый "
             "охристо-красный, заколотая на плече"),
    ("weave", "домотканая рубаха из грубого растительного волокна, перехваченная поясом"),
    ("tailored_clothing", "сшитая по фигуре одежда из мягко выделанной шкуры, "
                          "швы стянуты жилами, по краю бахрома"),
    ("hide_work", "необработанная шкура, наброшенная и подвязанная ремнём"),
]
ORNAMENT = [
    ("gold", "тяжёлая литая гривна тусклого золота на шее"),
    ("silver", "серебряные подвески, потемневшие от времени"),
    ("bronze_tin", "бронзовая фибула с прочерченным узором"),
    ("copper_smelt", "кованые медные кольца на предплечье, позеленевшие по краям"),
    ("obsidian", "нить с чёрными обсидиановыми пластинками"),
    ("salting", "нитка речных раковин и просверленных зубов зверя"),
]
IMPLEMENT = {
    "chief": [("codified_law", "глиняная табличка с записью, придерживаемая у груди"),
              ("bronze_tin", "бронзовый жезл-навершие"),
              ("megalith", "посох с резной головкой"),
              (None, "древко копья, поставленное перед собой")],
    "priest": [("moralizing_god", "курильница с тлеющей смолой"),
               ("priesthood", "костяная гадательная пластина"),
               (None, "пучок трав и охряная краска на ладонях")],
    "scribe": [("writing", "тростниковая палочка и сырая глиняная табличка"),
               (None, "связка счётных бирок")],
    "artisan": [("iron_bloom", "закопчённые клещи и заготовка из железа"),
                ("copper_smelt", "литейная форма и слиток меди"),
                ("pottery", "необожжённый сосуд в руках, пальцы в глине"),
                (None, "кремнёвый отщеп и отбойник")],
    "warrior": [("steel", "клинок с наваренным лезвием"),
                ("bronze_tin", "бронзовый топор на длинной рукояти"),
                ("bow", "лук и колчан за плечом"),
                (None, "копьё с каменным наконечником")],
    "healer": [("surgery", "набор бронзовых игл в кожаном свёртке"),
               (None, "связка сушёных корней и трав")],
    "trader": [("coinage", "кожаный кошель с монетами"),
               (None, "связка мерных гирек")],
    "farmer": [("ard_plough", "рукоять сохи, ладони в мозолях"),
               (None, "мотыга с каменным лезвием")],
    "hunter": [("bow", "лук и связка стрел"),
               (None, "копьеметалка")],
    "commoner": [("quern", "зернотёрка и горсть зерна"),
                 (None, "плетёная корзина")],
}
BIOME_SETTING = {
    2: "стылая тундра под низким серым небом",
    3: "хвойный лес, воздух в дымке",
    4: "широколиственный лес поздним летом",
    5: "открытая степь, ветер в сухой траве",
    6: "средиземноморский склон, оливковый свет",
    7: "каменистая пустыня в жарком мареве",
    8: "полупустыня, выгоревшая до охры",
    9: "саванна на закате, длинные тени",
    10: "тропический лес, влажный рассеянный свет",
    11: "горный склон, разреженный холодный воздух",
    12: "заболоченная пойма в утреннем тумане",
}
ERA_LOOK = {
    "палеолит": "глубоко обветренная кожа, спутанные волосы, лицо человека, "
                "который всю жизнь провёл под открытым небом",
    "мезолит": "обветренное лицо, волосы стянуты жильной нитью",
    "неолит": "загрубевшие руки земледельца, коротко обрезанные волосы",
    "халколит": "первые следы достатка: чистая одежда, ухоженная борода",
    "бронза": "осанка человека, привыкшего распоряжаться, аккуратно убранные волосы",
    "железо": "жёсткое, собранное лицо, коротко остриженные волосы",
    "античность": "выбритое или коротко подстриженное лицо, ткань хорошей выделки",
    "средневековье": "покрытая голова, одежда с отделкой",
    "новое время": "строгий покрой, следы городской жизни на лице",
}
# черты характера → что видно на лице
TRAIT_FACE = {
    "aggression": ("тяжёлый прямой взгляд, сжатая челюсть, старый шрам через бровь",
                   "спокойное, незлое лицо"),
    "curiosity": ("живой внимательный взгляд, чуть приподнятые брови", ""),
    "ambition": ("подобранная, напряжённая осанка, взгляд поверх собеседника", ""),
    "empathy": ("мягкие складки у глаз, лицо человека, к которому идут за помощью", ""),
    "piety": ("отрешённый сосредоточенный взгляд, ритуальная роспись на скулах", ""),
    "patience": ("неспешное, тяжеловесное спокойствие", ""),
    "diligence": ("натруженные кисти рук, въевшаяся под ногти работа", ""),
    "risk": ("следы давних переломов, обветренное до красноты лицо", ""),
}


def _age_look(age: int, sex: int) -> str:
    m = sex == 1
    who = "мужчина" if m else "женщина"
    if age < 22:
        return f"{who} немногим за двадцать, ещё без глубоких морщин"
    if age < 35:
        return f"{who} около тридцати, в полной силе"
    if age < 50:
        return f"{who} за сорок, обветренное лицо, первая седина"
    if age < 65:
        return f"{who} под шестьдесят, глубокие морщины, поредевшие волосы"
    return (f"{who} глубоко {'пожилой' if m else 'пожилая'}, "
            f"для своего времени редкий долгожитель")


def describe(person: dict, known_keys: set, biome: int | None,
             polity_name: str, era: str, seed: int = 0) -> dict:
    """Собрать словесный портрет по записи из книги мира."""
    rnd = random.Random(seed or person.get("aid", 0))
    tr = person.get("traits", {})
    role = person.get("role", "commoner")
    age = person.get("age") or (
        (person.get("died") or person.get("last_seen", 0)) - person.get("born", 0))
    age = max(14, int(age))
    sex = int(person.get("sex", 1))

    garment = next((g for k, g in GARMENT if k in known_keys),
                   "накидка из невыделанной шкуры")
    orn = next((o for k, o in ORNAMENT if k in known_keys), None)
    impl_list = IMPLEMENT.get(role, IMPLEMENT["commoner"])
    implement = next((v for k, v in impl_list if k is None or k in known_keys),
                     impl_list[-1][1])

    face = [ERA_LOOK.get(era, "обветренное лицо")]
    for t, (hi, lo) in TRAIT_FACE.items():
        v = tr.get(t, 0.5)
        if v > 0.72 and hi:
            face.append(hi)
        elif v < 0.28 and lo:
            face.append(lo)
    rnd.shuffle(face)
    face = face[:4]

    setting = BIOME_SETTING.get(biome, "открытая местность под ровным светом")
    deeds = [d["text"] for d in person.get("deeds", [])][:2]

    ru = (f"{_age_look(age, sex)} из народа {polity_name}. "
          f"{', '.join(face)}. {'Одет' if sex == 1 else 'Одета'}: {garment}"
          + (f"; {orn}" if orn else "")
          + f". В руках {implement}. Вокруг — {setting}.")

    prompt = (
        "Photorealistic documentary portrait, tight head-and-shoulders framing from "
        "mid-chest up, shot on medium format film, 85mm lens, shallow depth of field, "
        "natural available light, muted earth palette, extremely detailed skin texture "
        "with pores, sweat and dirt, fully clothed, no makeup, no modern objects, "
        "no text, no jewellery beyond what is described. "
        f"Subject: {_en_age(age, sex)} of a {_en_era(era)} people, "
        f"{_en_role(role)}. "
        f"{_en_face(tr)} "
        f"Wearing {_en_garment(known_keys)}"
        + (f", {_en_ornament(known_keys)}" if orn else "")
        + f". Holding {_en_implement(role, known_keys)}. "
        f"Background: {_en_setting(biome)}, softly out of focus. "
        "Direct eye contact with the camera, calm unposed expression, "
        "the dignity of an ordinary person photographed as they are."
    )
    return {
        "aid": person.get("aid"), "name": person.get("name"), "polity": polity_name,
        "era": era, "role": role, "age": age, "sex": sex,
        "born": person.get("born"), "died": person.get("died"),
        "deeds": deeds, "ru": ru, "prompt": prompt,
        "traits": tr, "beliefs": person.get("beliefs", {}),
    }


# ── английские куски для модели изображений ────────────────────────────────
def _en_age(age, sex):
    w = "man" if sex == 1 else "woman"
    if age < 22:
        return f"a {w} in his early twenties" if sex else f"a {w} in her early twenties"
    if age < 35:
        return f"a {w} around thirty"
    if age < 50:
        return f"a weathered {w} in his forties" if sex else f"a weathered {w} in her forties"
    if age < 65:
        return f"an aging {w} near sixty, deeply lined face"
    return f"a very old {w}, rare survivor for this age"


_ERA_EN = {"палеолит": "late Ice Age hunter-gatherer", "мезолит": "Mesolithic",
           "неолит": "early Neolithic farming", "халколит": "Copper Age",
           "бронза": "Bronze Age", "железо": "Iron Age",
           "античность": "classical antiquity", "средневековье": "medieval",
           "новое время": "early modern"}


def _en_era(e):
    return _ERA_EN.get(e, "prehistoric")


_ROLE_EN = {"chief": "a chieftain, bearing authority", "priest": "a ritual specialist",
            "scribe": "a scribe", "artisan": "a craftsman with working hands",
            "warrior": "a fighter", "healer": "a healer", "trader": "a trader",
            "farmer": "a farmer", "hunter": "a hunter", "commoner": "an ordinary villager",
            "elder": "an elder"}


def _en_role(r):
    return _ROLE_EN.get(r, "an ordinary person")


def _en_face(tr):
    out = []
    if tr.get("aggression", 0.5) > 0.72:
        out.append("hard level stare, set jaw, an old scar through one eyebrow")
    if tr.get("curiosity", 0.5) > 0.72:
        out.append("alert searching eyes")
    if tr.get("ambition", 0.5) > 0.72:
        out.append("upright guarded posture")
    if tr.get("empathy", 0.5) > 0.72:
        out.append("soft creases at the eyes")
    if tr.get("piety", 0.5) > 0.72:
        out.append("ochre ritual marks across the cheekbones, inward gaze")
    if tr.get("diligence", 0.5) > 0.72:
        out.append("thick calloused hands, dirt worked into the nails")
    return " ".join(out) or "plain unremarkable features."


def _en_garment(k):
    if "wool" in k:
        return "a thick hand-woven wool cloak dyed dull ochre-red, pinned at the shoulder"
    if "weave" in k or "basket" in k:
        return "a coarse plant-fibre tunic belted at the waist"
    if "tailored_clothing" in k:
        return "close-fitted hide clothing sewn with sinew, fringed at the hem"
    return "an untanned hide wrap tied with a leather cord"


def _en_ornament(k):
    if "gold" in k:
        return "a heavy dull-gold neck ring"
    if "bronze_tin" in k:
        return "an incised bronze cloak-pin"
    if "copper_smelt" in k:
        return "hammered copper arm rings, green at the edges"
    return "a strung necklace of river shell and drilled animal teeth"


def _en_implement(role, k):
    if role == "chief":
        return "a clay tablet held against the chest" if "codified_law" in k \
            else "a spear shaft planted upright"
    if role == "priest":
        return "a smoking resin censer" if "moralizing_god" in k else "a bundle of dried herbs"
    if role == "scribe":
        return "a reed stylus and wet clay tablet"
    if role == "artisan":
        if "iron_bloom" in k:
            return "soot-blackened tongs and an iron billet"
        if "pottery" in k:
            return "an unfired clay vessel, fingers wet with slip"
        return "a flint core and hammerstone"
    if role == "warrior":
        return "a bronze axe on a long haft" if "bronze_tin" in k else "a stone-tipped spear"
    return "a grinding stone and a handful of grain"


def _en_setting(b):
    return {2: "frozen tundra under low grey sky", 3: "hazy conifer forest",
            4: "late-summer broadleaf woodland", 5: "open steppe, wind in dry grass",
            6: "Mediterranean hillside in olive light", 7: "stony desert in heat shimmer",
            8: "sun-bleached semi-desert", 9: "savanna at low sun, long shadows",
            10: "humid rainforest, diffuse green light", 11: "high mountain slope, thin cold air",
            12: "marshy floodplain in morning mist"}.get(b, "open ground under even light")


# ── отбор героев из прогона ────────────────────────────────────────────────
def pick(run_dir, n: int = 8) -> list[dict]:
    """Взять самых значимых людей мира, по одному из разных эпох и народов."""
    run_dir = Path(run_dir)
    people = []
    pf = run_dir / "people.jsonl"
    if pf.exists():
        for line in pf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    people.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not people:
        return []

    # вес: значимость дел + власть + почёт
    def score(p):
        d = p.get("deeds", [])
        w = sum(2.0 if x["kind"] == "discovery" else 1.4 if x["kind"] == "rule" else 1.0
                for x in d)
        return w + 1.6 * p.get("power", 0) + 0.8 * p.get("prestige", 0)

    people.sort(key=score, reverse=True)
    # мир должен быть представлен разными эпохами и народами, а не одной державой
    out, seen_era, seen_pol = [], {}, set()
    for p in people:
        e = p.get("era", "?")
        if seen_era.get(e, 0) >= max(1, n // 4) or p.get("polity") in seen_pol:
            continue
        seen_era[e] = seen_era.get(e, 0) + 1
        seen_pol.add(p.get("polity"))
        out.append(p)
        if len(out) >= n:
            break
    for p in people:
        if len(out) >= n:
            break
        if p not in out:
            out.append(p)
    return out


def portraits(run_dir, n: int = 8) -> list[dict]:
    """Полные портреты: словесный русский и промпт для съёмки."""
    from . import knowledge as kn
    run_dir = Path(run_dir)
    chosen = pick(run_dir, n)
    if not chosen:
        return []
    # биом и набор ремёсел народа на момент жизни человека — из снимков
    snaps = []
    sf = run_dir / "snapshots.jsonl"
    if sf.exists():
        for line in sf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                snaps.append(json.loads(line))
    out = []
    for p in chosen:
        year = p.get("born", 0)
        snap = min(snaps, key=lambda s: abs(s["year"] - year)) if snaps else None
        pol = None
        if snap:
            pol = next((q for q in snap["polities"] if q["pid"] == p.get("polity")), None)
        era = p.get("era", (pol or {}).get("era", "неолит"))
        n_tech = (pol or {}).get("tech", 14)
        # какие ремёсла у народа этого уровня уже есть — по порядку сложности
        keys = {t.key for t in sorted(kn.CATALOG, key=lambda t: t.difficulty)[:n_tech]}
        out.append(describe(p, keys, _biome_of(run_dir, p),
                            p.get("polity_name") or (pol or {}).get("name", "?"), era))
    return out


_BIOME_CACHE = {}


def _biome_of(run_dir, person) -> int | None:
    key = str(run_dir)
    if key not in _BIOME_CACHE:
        try:
            from .world import load_world
            w = load_world(str(Path(run_dir) / "world"))
            _BIOME_CACHE[key] = w
        except Exception:
            _BIOME_CACHE[key] = None
    w = _BIOME_CACHE[key]
    if w is None:
        return None
    import numpy as np
    sf = Path(run_dir) / "snapshots.jsonl"
    if not sf.exists():
        return None
    import base64
    best = None
    for line in sf.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        if best is None or abs(s["year"] - person.get("born", 0)) < abs(best["year"] - person.get("born", 0)):
            best = s
    if best is None:
        return None
    cm = np.frombuffer(base64.b64decode(best["culture_map"]), dtype=np.int16)
    own = np.flatnonzero(cm == (person.get("polity", -1) % 32000))
    if own.size == 0:
        return None
    b = w.biome.ravel()[own]
    return int(np.bincount(b).argmax())


def main():
    ap = argparse.ArgumentParser("terra.portrait")
    ap.add_argument("run")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ps = portraits(a.run, a.n)
    if a.json:
        print(json.dumps(ps, ensure_ascii=False, indent=2))
        return
    if not ps:
        print("в этом прогоне нет книги людей (people.jsonl)")
        return
    for p in ps:
        yr = lambda y: f"{abs(y)} {'до н. э.' if y < 0 else 'н. э.'}"
        print(f"\n── {p['name']} ({p['polity']}, {p['era']}, {yr(p['born'])}) ──")
        for d in p["deeds"]:
            print(f"   · {d}")
        print(f"   {p['ru']}")


if __name__ == "__main__":
    main()
