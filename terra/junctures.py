"""
TERRA — переломные точки.

Большую часть времени люди действуют по своим склонностям, и это считается
быстро. Но иногда народ упирается в развилку, где алгоритма мало: голод, из
которого несколько выходов; смерть правителя; первая встреча с чужаками;
раскол; решение построить то, чего ещё никто не строил.

В такие моменты конкретный человек получает слово. Симуляция собирает пакет
«что он видит» и передаёт его решателю. Решателей три:

  heuristic — встроенный, детерминированный, работает всегда и офлайн;
  api       — настоящая LLM через Anthropic API, если есть ключ;
  oracle    — файловый протокол: симуляция пишет развилки на диск и ждёт,
              пока их разрешит внешний агент (в том числе Claude в этой сессии).

Решение записывается обратно в мир и меняет траекторию.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np

from . import agents as ag
from .contracts import Juncture

# ────────────────────────────────────────────────────────────────────────────
#  Каталог развилок
# ────────────────────────────────────────────────────────────────────────────
OPTIONS = {
    "crisis": [
        ("endure", "терпеть и урезать доли", "выживут не все, но народ не распадётся"),
        ("migrate", "увести народ прочь", "разрыв с землёй предков, риск гибели в пути"),
        ("intensify", "выжать из земли больше", "урожай сейчас, истощение потом"),
        ("raid", "отнять у соседей", "еда сейчас, кровная вражда навсегда"),
        ("sacrifice", "умилостивить высшие силы", "сплочение и покорность, еды не прибавится"),
        ("reform", "переменить порядок", "власть слабеет, но общество становится гибче"),
    ],
    "succession": [
        ("heir", "передать наследнику по крови", "преемственность, но наследник может быть негоден"),
        ("strongest", "отдать сильнейшему", "способный правитель, но прецедент захвата"),
        ("council", "решать сообща", "власть рассеивается, зато никто не свергнут"),
        ("priest", "спросить у жрецов", "жречество усиливается"),
        ("split", "разделить между претендентами", "мир сейчас, две державы потом"),
    ],
    "contact": [
        ("trade", "торговать", "чужие вещи, чужие болезни, чужие мысли"),
        ("attack", "ударить первыми", "добыча и вражда"),
        ("avoid", "держаться в стороне", "безопасно и глухо"),
        ("absorb", "породниться и слиться", "народ меняется, но растёт"),
        ("tribute", "потребовать дани", "богатство и восстание"),
    ],
    "schism": [
        ("let_go", "отпустить с миром", "два народа, общая память"),
        ("suppress", "подавить силой", "единство ценой крови"),
        ("concede", "уступить недовольным", "власть слабеет, раскол не случается"),
        ("purge", "истребить смутьянов", "страх вместо согласия"),
    ],
    "innovation": [
        ("pursue", "довести замысел до конца", "новое умение, потраченные годы"),
        ("share", "открыть всем", "быстро разойдётся, изобретатель не возвысится"),
        ("hoard", "утаить для своих", "власть и богатство, знание хрупко"),
        ("abandon", "бросить затею", "ничего не изменится"),
    ],
    "expansion": [
        ("settle", "занять новую землю", "рост и растянутые связи"),
        ("cross", "уйти за воду", "неизвестность, изоляция, новый мир"),
        ("consolidate", "укрепить своё", "прочность вместо роста"),
        ("conquer", "взять чужое", "война"),
    ],
    "reform": [
        ("centralize", "собрать власть в одних руках", "порядок и налог, ненависть низов"),
        ("distribute", "разделить власть", "устойчивость, медленные решения"),
        ("codify", "записать законы", "предсказуемость, конец произволу"),
        ("sacralize", "освятить власть", "покорность, косность"),
        ("nothing", "оставить как есть", "инерция"),
    ],
}

KIND_RU = {
    "crisis": "бедствие", "succession": "престолонаследие", "contact": "встреча",
    "schism": "раскол", "innovation": "замысел", "expansion": "исход",
    "reform": "переустройство",
}


# ────────────────────────────────────────────────────────────────────────────
#  Сборка пакета
# ────────────────────────────────────────────────────────────────────────────
def build(jid: str, year: int, kind: str, poly, person_i: int, co: ag.Cohort,
          name: str, ctx: dict) -> Juncture:
    opts = [{"key": k, "label": lb, "consequence_hint": c} for k, lb, c in OPTIONS[kind]]
    bad = set(ctx.get("drop_options", {}).get(kind, ()))
    if bad:
        opts = [o for o in opts if o["key"] not in bad] or opts[:1]
    tr = {t: round(float(co.traits[person_i, i]), 2) for i, t in enumerate(ag.TRAITS)}
    bel = {b: round(float(co.belief[person_i, i]), 2) for i, b in enumerate(ag.BELIEFS)}
    need = {n: round(float(co.needs[person_i, i]), 2) for i, n in enumerate(ag.NEEDS)}
    sit = _situation_text(kind, poly, name, year, ctx)
    return Juncture(
        jid=jid, year=year, kind=kind, polity=poly.pid, person=int(person_i),
        situation=sit, options=opts,
        context={
            "person_name": name, "person_role": ag.ROLE_RU[ag.ROLES[int(co.role[person_i])]],
            "person_age": int(year - co.born[person_i]),
            "traits": tr, "beliefs": bel, "needs": need,
            "polity_name": poly.name, "pop": int(poly.pop), "form": poly.form,
            "subsistence": poly.subsistence, "cohesion": round(poly.cohesion, 2),
            "legitimacy": round(poly.legitimacy, 2), "surplus": round(poly.surplus, 3),
            "complexity": round(poly.complexity, 2), "inequality": round(poly.inequality, 2),
            **{k: v for k, v in ctx.items() if k != "drop_options"},
        },
    )


def _situation_text(kind, poly, name, year, ctx) -> str:
    era = f"{abs(year)} {'до н. э.' if year < 0 else 'н. э.'}"
    who = f"{name}, {ctx.get('role_ru', 'человек')} народа {poly.name}"
    if kind == "crisis":
        return (f"{era}. {who}. Народ насчитывает {int(poly.pop)} душ и живёт "
                f"{ctx.get('mode_ru', '')}. Запасов хватает на {ctx.get('food_ratio', 0):.0%} нужды. "
                f"{ctx.get('cause', 'Земля перестала кормить.')} Люди ждут решения.")
    if kind == "succession":
        return (f"{era}. Умер {ctx.get('predecessor', 'прежний правитель')} народа {poly.name}. "
                f"{who} — среди тех, кто может занять его место. "
                f"Претендентов {ctx.get('claimants', 2)}, войско колеблется, "
                f"законность власти оценивается как {poly.legitimacy:.0%}.")
    if kind == "contact":
        return (f"{era}. {who}. Впервые встречены чужаки — народ {ctx.get('other_name', 'неизвестных')}, "
                f"числом около {ctx.get('other_pop', 0)}, живущий {ctx.get('other_mode', '')}. "
                f"Они владеют тем, чего мы не знаем: {ctx.get('their_tech', '—')}. "
                f"Наши считают чужих {'опасными' if ctx.get('danger', 0.5) > 0.55 else 'скорее безобидными'}.")
    if kind == "schism":
        return (f"{era}. {who}. Народ разросся до {int(poly.pop)} душ и держится на {poly.cohesion:.0%} "
                f"согласия. {ctx.get('cause', 'Дальние роды больше не слушают.')} "
                f"Раскол назрел.")
    if kind == "innovation":
        return (f"{era}. {who}. В руках у него замысел: {ctx.get('tech_name', 'нечто новое')}. "
                f"Никто прежде такого не делал. Народ сыт на {ctx.get('food_ratio', 1):.0%}, "
                f"досуга {'хватает' if poly.surplus > 0.04 else 'почти нет'}.")
    if kind == "expansion":
        return (f"{era}. {who}. Перед народом открылась земля: {ctx.get('target', 'новые угодья')}. "
                f"Своя земля {'переполнена' if ctx.get('crowding', 0) > 0.8 else 'ещё держит'}, "
                f"людей {int(poly.pop)}.")
    if kind == "reform":
        return (f"{era}. {who}. Народ {poly.name} стал слишком велик для прежних порядков: "
                f"{int(poly.pop)} душ, сложность {poly.complexity:.0%}, "
                f"неравенство {poly.inequality:.0%}, законность {poly.legitimacy:.0%}. "
                f"Так дальше не управляется.")
    return f"{era}. {who}."


# ────────────────────────────────────────────────────────────────────────────
#  Решатель 1 — эвристический (всегда доступен, детерминирован)
# ────────────────────────────────────────────────────────────────────────────
def resolve_heuristic(rng, j: Juncture, co: ag.Cohort) -> dict:
    """Человек решает по своему характеру и своим убеждениям."""
    i = j.person
    T = {t: float(co.traits[i, k]) for k, t in enumerate(ag.TRAITS)}
    B = {b: float(co.belief[i, k]) for k, b in enumerate(ag.BELIEFS)}
    N = {n: float(co.needs[i, k]) for k, n in enumerate(ag.NEEDS)}
    c = j.context
    S = {}

    if j.kind == "crisis":
        S = {
            "endure": 0.6 + 1.2 * T["patience"] + 0.8 * T["conformity"] - 0.6 * N["food"],
            "migrate": 1.4 * B["elsewhere"] + 1.1 * T["risk"] + 1.0 * N["food"] - 0.9 * c.get("sedentism", 0),
            "intensify": 1.3 * T["diligence"] + 0.9 * N["food"] + 0.7 * c.get("surplus_possible", 0.3),
            "raid": 1.6 * T["aggression"] + 1.0 * N["food"] - 1.2 * T["empathy"] + 0.8 * c.get("neighbor_wealth", 0),
            "sacrifice": 1.8 * T["piety"] + 1.0 * B["divine"] + 0.5 * N["meaning"],
            "reform": 1.2 * T["curiosity"] + 0.9 * (1 - B["authority"]) + 0.8 * (1 - c.get("legitimacy", 0.5)),
        }
    elif j.kind == "succession":
        S = {
            "heir": 1.5 * B["authority"] + 0.9 * T["conformity"] + 0.7 * c.get("legitimacy", 0.5),
            "strongest": 1.4 * T["ambition"] + 1.0 * T["aggression"] - 0.6 * B["authority"],
            "council": 1.2 * T["sociability"] + 1.0 * T["empathy"] - 0.9 * T["ambition"],
            "priest": 1.6 * T["piety"] + 1.0 * B["divine"],
            "split": 0.8 * T["empathy"] + 0.9 * (1 - c.get("cohesion", 0.6)),
        }
    elif j.kind == "contact":
        S = {
            "trade": 1.5 * T["sociability"] + 1.2 * T["curiosity"] - 1.4 * B["danger"],
            "attack": 1.7 * T["aggression"] + 1.3 * B["danger"] - 1.1 * T["empathy"] + 0.6 * N["food"],
            "avoid": 1.2 * B["danger"] + 0.9 * T["conformity"] - 0.8 * T["curiosity"],
            "absorb": 1.2 * T["empathy"] + 0.9 * T["sociability"] - 0.9 * B["danger"],
            "tribute": 1.4 * T["ambition"] + 0.9 * T["aggression"] + 0.7 * c.get("strength_ratio", 1.0),
        }
    elif j.kind == "schism":
        S = {
            "let_go": 1.3 * T["empathy"] + 0.8 * (1 - T["ambition"]),
            "suppress": 1.6 * T["aggression"] + 1.2 * T["ambition"] - 1.0 * T["empathy"],
            "concede": 1.2 * T["sociability"] + 0.9 * T["patience"] - 0.7 * T["ambition"],
            "purge": 1.8 * T["aggression"] - 1.5 * T["empathy"] + 0.8 * (1 - c.get("legitimacy", 0.5)),
        }
    elif j.kind == "innovation":
        S = {
            "pursue": 1.8 * T["curiosity"] + 1.0 * T["patience"] + 0.8 * B["novelty"] - 1.0 * N["food"],
            "share": 1.3 * T["empathy"] + 1.0 * T["sociability"] - 0.7 * T["ambition"],
            "hoard": 1.5 * T["ambition"] + 0.9 * (1 - T["empathy"]),
            "abandon": 1.4 * T["conformity"] + 1.0 * N["food"] - 1.2 * T["curiosity"],
        }
    elif j.kind == "expansion":
        S = {
            "settle": 1.3 * T["risk"] + 1.0 * B["elsewhere"] + 0.9 * c.get("crowding", 0),
            "cross": 1.6 * T["risk"] + 1.3 * T["curiosity"] + 0.7 * c.get("crowding", 0) - 1.0 * B["danger"],
            "consolidate": 1.3 * T["patience"] + 0.9 * (1 - T["risk"]),
            "conquer": 1.6 * T["aggression"] + 1.1 * T["ambition"] - 1.0 * T["empathy"],
        }
    elif j.kind == "reform":
        S = {
            "centralize": 1.5 * T["ambition"] + 1.0 * B["authority"] - 0.8 * T["empathy"],
            "distribute": 1.3 * T["empathy"] + 1.0 * T["sociability"] - 0.9 * T["ambition"],
            "codify": 1.4 * T["patience"] + 1.1 * T["diligence"] + 0.7 * c.get("literacy", 0),
            "sacralize": 1.7 * T["piety"] + 1.1 * B["divine"],
            "nothing": 1.2 * T["conformity"] - 0.8 * T["curiosity"],
        }

    keys = [o["key"] for o in j.options]
    v = np.array([S.get(k, 0.0) for k in keys], dtype=np.float64)
    v = v / 0.42
    v -= v.max()
    p = np.exp(v)
    p /= p.sum()
    ch = keys[int((p.cumsum() > rng.random()).argmax())]
    return {"choice": ch, "reasoning": "решение по складу характера и убеждениям", "by": "heuristic"}


# ────────────────────────────────────────────────────────────────────────────
#  Решатель 2 — настоящая LLM через API
# ────────────────────────────────────────────────────────────────────────────
_SYS = """Ты — сознание одного человека в симуляции истории. Ты НЕ помощник и НЕ рассказчик.

Тебе дают: кто ты, что ты видишь, во что ты веришь, чего тебе не хватает — и список
доступных решений. Ты выбираешь одно, исходя ИЗ СВОЕГО характера и СВОЕЙ картины мира,
а не из того, что было бы разумно или что случилось в реальной истории.

Ты не знаешь будущего. Ты не знаешь, что бывает «правильно». Ты можешь ошибаться,
и часто будешь. Люди с высокой piety выбирают жертвоприношение даже когда оно не
поможет. Люди с низкой curiosity отвергают новое. Люди с высокой ambition рвутся к власти
через кровь. Играй свой характер честно, включая его слабости.

Ответ — строго JSON: {"choice": "<ключ>", "reasoning": "<одно предложение от первого лица>"}"""


def resolve_api(j: Juncture, model: str = "claude-3-5-haiku-latest",
                timeout: float = 30.0) -> dict | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    c = j.context
    opts = "\n".join(f'  {o["key"]}: {o["label"]} — {o["consequence_hint"]}' for o in j.options)
    msg = (f"ТЫ: {c['person_name']}, {c['person_role']}, {c['person_age']} лет.\n"
           f"ХАРАКТЕР: {json.dumps(c['traits'], ensure_ascii=False)}\n"
           f"ВО ЧТО ВЕРИШЬ: {json.dumps(c['beliefs'], ensure_ascii=False)}\n"
           f"ЧЕГО НЕ ХВАТАЕТ: {json.dumps(c['needs'], ensure_ascii=False)}\n\n"
           f"ЧТО ПРОИСХОДИТ:\n{j.situation}\n\nРЕШЕНИЯ:\n{opts}")
    try:
        cl = anthropic.Anthropic(api_key=key, timeout=timeout)
        r = cl.messages.create(model=model, max_tokens=220, system=_SYS,
                               messages=[{"role": "user", "content": msg}])
        txt = r.content[0].text
        s, e = txt.find("{"), txt.rfind("}")
        d = json.loads(txt[s:e + 1])
        valid = {o["key"] for o in j.options}
        if d.get("choice") in valid:
            return {"choice": d["choice"], "reasoning": d.get("reasoning", ""), "by": "api"}
    except Exception:
        return None
    return None


# ────────────────────────────────────────────────────────────────────────────
#  Решатель 3 — файловый оракул (внешний агент, в т.ч. Claude в сессии)
# ────────────────────────────────────────────────────────────────────────────
class OracleBridge:
    """Симуляция выкладывает развилки в файл и ждёт ответа.

    Так «думать» за ключевых людей может любой внешний разум — в том числе
    Claude, запущенный рядом. Если ответа нет за `wait`, берётся эвристика,
    и мир не останавливается.
    """

    def __init__(self, run_dir: Path, wait: float = 0.0):
        self.dir = Path(run_dir) / "oracle"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.wait = wait
        self.cache: dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self):
        f = self.dir / "resolved.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    self.cache[d["jid"]] = d
                except json.JSONDecodeError:
                    pass

    def ask(self, batch: list[Juncture]) -> dict[str, dict]:
        got = {}
        pending = []
        for j in batch:
            if j.jid in self.cache:
                got[j.jid] = self.cache[j.jid]
            else:
                pending.append(j)
        if not pending:
            return got
        f = self.dir / "pending.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            for j in pending:
                fh.write(json.dumps({
                    "jid": j.jid, "year": j.year, "kind": j.kind, "polity": j.polity,
                    "situation": j.situation, "options": j.options, "context": j.context,
                }, ensure_ascii=False) + "\n")
        if self.wait > 0:
            deadline = time.time() + self.wait
            while time.time() < deadline:
                time.sleep(0.5)
                self._load_cache()
                if all(j.jid in self.cache for j in pending):
                    break
            for j in pending:
                if j.jid in self.cache:
                    got[j.jid] = self.cache[j.jid]
        return got


def make_jid(run_id: str, year: int, kind: str, pid: int, aid: int) -> str:
    h = hashlib.blake2b(f"{run_id}|{year}|{kind}|{pid}|{aid}".encode(), digest_size=6)
    return h.hexdigest()


# ────────────────────────────────────────────────────────────────────────────
#  Диспетчер
# ────────────────────────────────────────────────────────────────────────────
class Resolver:
    def __init__(self, mode: str = "heuristic", run_dir: Path | None = None,
                 model: str = "claude-3-5-haiku-latest", oracle_wait: float = 0.0,
                 budget: int = 400):
        self.mode = mode
        self.model = model
        self.budget = budget
        self.used = 0
        self.bridge = OracleBridge(run_dir, oracle_wait) if (mode == "oracle" and run_dir) else None
        self.stats = {"heuristic": 0, "api": 0, "oracle": 0}

    def resolve(self, rng, batch: list[Juncture], co: ag.Cohort):
        if not batch:
            return
        deep = []
        if self.mode in ("api", "oracle") and self.used < self.budget:
            # на глубокое обдумывание идут самые весомые развилки
            batch_sorted = sorted(batch, key=lambda j: -_weight(j))
            k = min(len(batch_sorted), self.budget - self.used)
            deep = batch_sorted[:k]
        deep_ids = {id(j) for j in deep}

        if deep and self.mode == "oracle" and self.bridge:
            got = self.bridge.ask(deep)
            for j in deep:
                if j.jid in got:
                    d = got[j.jid]
                    if d.get("choice") in {o["key"] for o in j.options}:
                        j.resolution = {"choice": d["choice"],
                                        "reasoning": d.get("reasoning", ""), "by": "oracle"}
                        self.stats["oracle"] += 1
                        self.used += 1
        elif deep and self.mode == "api":
            for j in deep:
                r = resolve_api(j, self.model)
                if r:
                    j.resolution = r
                    self.stats["api"] += 1
                    self.used += 1

        for j in batch:
            if j.resolution is None:
                j.resolution = resolve_heuristic(rng, j, co)
                self.stats["heuristic"] += 1


def _weight(j: Juncture) -> float:
    base = {"crisis": 3.0, "schism": 2.6, "succession": 2.2, "contact": 2.4,
            "reform": 2.0, "expansion": 1.6, "innovation": 1.4}.get(j.kind, 1.0)
    return base * (1.0 + np.log10(max(10, j.context.get("pop", 100))) / 3.0)
