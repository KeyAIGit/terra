"""
TERRA — сборка одностраничного HTML-дашборда наблюдателя за миром.

Читает каталог прогона (run.json, world.npz/json, timeline.jsonl,
snapshots.jsonl, chronicle.jsonl) и собирает ОДИН самодостаточный HTML-файл:
все данные вшиты в документ как JSON, вся отрисовка — canvas + чистый JS.
Ни одной внешней ссылки, ни одного обращения к хранилищу браузера.

Использование:
    from terra.report import build_report
    build_report("runs/testreport")            # -> runs/testreport/report.html

    python -m terra.report runs/testreport [выходной_файл.html]
"""
from __future__ import annotations

import base64
import gzip
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from terra.contracts import BIOME_COLORS, BIOME_NAMES
from terra.society import FORM_RU, MODE_RU
from terra.world import load_world

# ────────────────────────────────────────────────────────────────────────────
#  Ограничители размера
# ────────────────────────────────────────────────────────────────────────────
MAX_FRAMES = 220            # не более стольких кадров карты в отчёте
MIN_FRAMES = 40             # ниже этого не прореживаем, даже если тяжело
MAX_EVENTS = 9000           # не более стольких событий летописи
TARGET_BYTES = 14_000_000   # целевой потолок размера готового HTML, ~14 МБ

# ────────────────────────────────────────────────────────────────────────────
#  Палитры и русские подписи
# ────────────────────────────────────────────────────────────────────────────
MODE_ORDER = ("forager", "complex_forager", "horticulture",
              "pastoral", "agrarian", "intensive")
# короткие подписи — для узкой таблицы народов (полные остаются в подсказке)
MODE_SHORT = {
    "forager": "собиратели", "complex_forager": "осёдл. собир.",
    "horticulture": "мотыжное", "pastoral": "скотоводы",
    "agrarian": "пашенное", "intensive": "ирригация",
}
FORM_SHORT = {
    "band": "община", "tribe": "племя", "bigman": "бигмены",
    "chiefdom": "вождество", "citystate": "город-гос.", "kingdom": "царство",
    "empire": "держава", "republic": "республика", "confederation": "союз",
}
MODE_COLORS = {
    "forager": "#6c8ea4",
    "complex_forager": "#4f9d8b",
    "horticulture": "#8fb04a",
    "pastoral": "#c9a15c",
    "agrarian": "#d2a24c",
    "intensive": "#c2643f",
}

FORM_ORDER = ("band", "tribe", "bigman", "chiefdom", "citystate",
              "kingdom", "empire", "republic", "confederation")
FORM_COLORS = {
    "band": "#5d7f93",
    "tribe": "#4e9b86",
    "bigman": "#7fa84c",
    "chiefdom": "#b39a45",
    "citystate": "#d08b4a",
    "kingdom": "#c4603f",
    "empire": "#a4444f",
    "republic": "#8a5fa8",
    "confederation": "#5f74b5",
}

ERA_ORDER = ("палеолит", "мезолит", "неолит", "халколит", "бронза",
             "железо", "античность", "средневековье", "новое время")
# короткие подписи эпох — для узкого столбца в таблице народов
ERA_SHORT = {
    "палеолит": "палеол.", "мезолит": "мезол.", "неолит": "неол.",
    "халколит": "халкол.", "бронза": "бронза", "железо": "железо",
    "античность": "антич.", "средневековье": "средн.", "новое время": "новое",
}
ERA_COLORS = {
    "палеолит": "#43505c",
    "мезолит": "#4d6a63",
    "неолит": "#5c7f4a",
    "халколит": "#8a7a3e",
    "бронза": "#a2733c",
    "железо": "#8d5a48",
    "античность": "#9c5566",
    "средневековье": "#6a5590",
    "новое время": "#4a6ea8",
}

KIND_RU = {
    "origin": "появление", "form": "устройство", "mode": "хозяйство",
    "discovery": "открытие", "diffusion": "заимствование", "loss": "утрата",
    "city": "город", "build": "постройка", "war": "война", "contact": "встреча",
    "decision": "решение", "fission": "раскол", "merge": "слияние",
    "extinction": "исчезновение", "epidemic": "эпидемия", "rule": "правление",
    "death": "смерть",
}
KIND_COLORS = {
    "origin": "#6f9ec4", "form": "#8f86c0", "mode": "#7fae72",
    "discovery": "#d4b45c", "diffusion": "#9fbf6a", "loss": "#a86a6a",
    "city": "#c98f4e", "build": "#b8925c", "war": "#c4544a",
    "contact": "#5fa8a0", "decision": "#c07fb0", "fission": "#b06a9a",
    "merge": "#5f8fb0", "extinction": "#8a5b5b", "epidemic": "#8fae4a",
    "rule": "#a0a0b8", "death": "#7a8490",
}

# порядок видов в ленте фильтров — от «крупных» к «мелким»
KIND_ORDER = ("origin", "discovery", "diffusion", "loss", "city", "build",
              "war", "contact", "decision", "fission", "merge", "extinction",
              "epidemic", "rule", "death", "form", "mode")


# ────────────────────────────────────────────────────────────────────────────
#  Мелкие утилиты
# ────────────────────────────────────────────────────────────────────────────
def _read_jsonl(path: Path) -> list[dict]:
    """Прочитать jsonl, молча пропуская битые строки."""
    out: list[dict] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _b64(a: np.ndarray) -> str:
    """Плоский массив -> base64 сырых байт (little-endian, как пишет numpy)."""
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


def _ru_year(y: int) -> str:
    """8000 до н. э. / 500 н. э."""
    y = int(y)
    if y < 0:
        return f"{-y} до н. э."
    return f"{y} н. э."


def _num(x: float) -> str:
    """Число с неразрывными пробелами между разрядами."""
    return f"{int(round(x)):,}".replace(",", " ")


def _hillshade(elev: np.ndarray, is_land: np.ndarray) -> np.ndarray:
    """Светотень по высоте: uint8, 128 — нейтрально, свет с северо-запада."""
    e = np.nan_to_num(np.asarray(elev, dtype=np.float32))
    gy, gx = np.gradient(e)
    # свет с северо-запада: освещены западные и северные склоны
    s = (-gx - gy) * 0.5
    scale = float(np.std(np.abs(s[is_land]))) if np.any(is_land) else 1.0
    scale = scale * 2.6 + 1e-6
    s = np.clip(s / scale, -1.0, 1.0)
    sh = np.clip(128.0 + s * 74.0, 0, 255).astype(np.uint8)
    sh[~np.asarray(is_land, dtype=bool)] = 128
    return sh


# ────────────────────────────────────────────────────────────────────────────
#  Языки и родство
# ────────────────────────────────────────────────────────────────────────────
# значения для сравнительно-исторической таблицы (все есть в lang.BASIC_MEANINGS)
COGNATE_MEANINGS = ("вода", "огонь", "солнце", "земля", "камень", "дерево",
                    "мать", "отец", "рука", "конь", "дом", "бог")
# что показываем в паспорте языка
PASSPORT_MEANINGS = ("вода", "огонь", "солнце", "луна", "земля", "камень",
                     "человек", "мать", "отец", "рука", "сердце", "конь",
                     "дом", "хлеб", "бог", "царь", "война", "путь")
THEO_DOMAINS = ("небо", "буря", "плодородие", "война", "солнце", "мудрость")

MAX_FAM_DEFAULT = 12        # сколько семей показываем по умолчанию
MAX_LANGS_IN_TABLE = 10     # столбцов в таблице когнатов
MAX_PEOPLE = 700            # карточек в панели «Люди»
PEOPLE_PER_POLITY = 5       # сперва по стольку от каждого народа — для разнообразия


def _hsl_hex(h: float, s: float, li: float) -> str:
    """HSL (0..360, 0..1, 0..1) -> #rrggbb."""
    c = (1 - abs(2 * li - 1)) * s
    hp = (h % 360) / 60.0
    x = c * (1 - abs(hp % 2 - 1))
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x),
               (0, x, c), (x, 0, c), (c, 0, x)][int(hp) % 6]
    m = li - c / 2
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, int(round((v + m) * 255)))) for v in (r, g, b))


def _lev_ratio(a: str, b: str) -> float:
    """Похожесть двух записей слова, 0..1 (1 — совпадают)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (0 if ca == b[j - 1] else 1))
        prev = cur
    return max(0.0, 1.0 - prev[lb] / max(la, lb))


def _polity_facts(snaps: list[dict]) -> dict[int, dict]:
    """pid -> {имя, население, уклад, форма, эпоха, первый и последний год}.

    Снимки урезаны до крупнейших народов, поэтому берём последнее, что видели.
    """
    out: dict[int, dict] = {}
    for s in snaps:
        yr = int(s.get("year", 0))
        for p in (s.get("polities") or []):
            try:
                pid = int(p.get("pid", -1))
            except (TypeError, ValueError):
                continue
            r = out.get(pid)
            if r is None:
                r = out[pid] = {"name": p.get("name", "—"), "y0": yr, "y1": yr,
                                "pop": 0, "mode": "", "form": "", "era": "",
                                "color": p.get("color", "#888888")}
            r["name"] = p.get("name", r["name"])
            r["y1"] = yr
            r["pop"] = int(p.get("pop", 0) or 0)
            r["mode"] = p.get("mode", r["mode"])
            r["form"] = p.get("form", r["form"])
            r["era"] = p.get("era", r["era"])
            r["color"] = p.get("color", r["color"])
    return out


def _collect_lang(run_dir: Path, snaps: list[dict],
                  year_start: int, year_end: int) -> dict[str, Any] | None:
    """Родословная языков: дерево семей, когнаты, расхождения, паспорта.

    Возвращает None, если lects.json.gz нет или он непригоден (старые прогоны).
    """
    path = run_dir / "lects.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        from terra.lang import Lect
    except Exception:
        return None

    facts = _polity_facts(snaps)

    # ── живые языки ────────────────────────────────────────────────────────
    lects: dict[int, Any] = {}
    info: dict[int, dict] = {}
    for k, v in raw.items():
        try:
            pid = int(k)
            lect = Lect.from_dict(v["lect"])
        except Exception:
            continue
        f = facts.get(pid, {})
        lects[pid] = lect
        info[pid] = {
            "pid": pid,
            "name": v.get("name") or f.get("name") or f"№{pid}",
            "parent": v.get("parent"),
            "born": int(v.get("born", year_start)),
            "fam": str(v["lect"].get("root_seed", pid)),
            "lname": str(v["lect"].get("name") or ""),
            "pop": int(f.get("pop", 0) or 0),
            "mode": f.get("mode", ""),
            "form": f.get("form", ""),
            "era": f.get("era", ""),
            "gen": int(v["lect"].get("generations", 0) or 0),
        }
    if not info:
        return None

    # ── узлы дерева: живые + восстановленные вымершие предки ───────────────
    alive = set(info)
    nodes: dict[str, dict] = {}
    for pid, r in info.items():
        nodes[str(pid)] = dict(r, id=str(pid), alive=True, par=None)
    for pid, r in info.items():
        par = r["parent"]
        if par is None:
            continue
        par = int(par)
        if par in alive:
            nodes[str(pid)]["par"] = str(par)
            continue
        gid = "g%d" % par
        g = nodes.get(gid)
        if g is None:
            gf = facts.get(par, {})
            g = nodes[gid] = {
                "id": gid, "pid": par, "alive": False, "par": None,
                "name": gf.get("name") or f"†{par}",
                "fam": r["fam"], "pop": 0, "mode": "", "form": "", "era": "",
                "gen": 0, "born": min(int(gf.get("y0", r["born"])), r["born"] - 10),
            }
        nodes[str(pid)]["par"] = gid

    # вымерший предок цепляется к живому корню своей семьи, если он один
    fam_roots: dict[str, list[str]] = defaultdict(list)
    for n in nodes.values():
        if n["alive"] and n["parent"] is None:
            fam_roots[n["fam"]].append(n["id"])
    for n in list(nodes.values()):
        if n["alive"] or n["par"] is not None:
            continue
        roots = fam_roots.get(n["fam"]) or []
        if len(roots) == 1 and nodes[roots[0]]["born"] < n["born"]:
            n["par"] = roots[0]

    # ── семьи ──────────────────────────────────────────────────────────────
    fams: dict[str, list[str]] = defaultdict(list)
    for n in nodes.values():
        fams[n["fam"]].append(n["id"])
    kids: dict[str, list[str]] = defaultdict(list)
    for n in nodes.values():
        if n["par"]:
            kids[n["par"]].append(n["id"])

    fam_list = []
    for fid, ids in fams.items():
        live = [i for i in ids if nodes[i]["alive"]]
        if not live:
            continue
        pop = sum(nodes[i]["pop"] for i in live)
        big = max(live, key=lambda i: (nodes[i]["pop"], -nodes[i]["born"]))
        fam_list.append({"fid": fid, "ids": ids, "live": live,
                         "pop": pop, "n": len(live), "big": big})
    fam_list.sort(key=lambda f: (-f["pop"], -f["n"], f["fid"]))

    out_fams = []
    for rank, f in enumerate(fam_list):
        hue = (rank * 47.0 + 12.0) % 360.0
        color = _hsl_hex(hue, 0.46, 0.62)
        roots = [i for i in f["ids"] if nodes[i]["par"] is None]
        roots.sort(key=lambda i: (nodes[i]["born"], nodes[i]["name"]))

        order: list[str] = []
        ycoord: dict[str, float] = {}
        row = [0]
        seen: set[str] = set()

        def visit(nid: str) -> None:
            if nid in seen:
                return
            seen.add(nid)
            n = nodes[nid]
            if n["alive"]:
                ycoord[nid] = float(row[0])
                row[0] += 1
                order.append(nid)
            ch = sorted(kids.get(nid, []),
                        key=lambda c: (nodes[c]["born"], nodes[c]["name"]))
            for c in ch:
                visit(c)
            if not n["alive"]:
                ys = [ycoord[c] for c in ch if c in ycoord]
                ycoord[nid] = (sum(ys) / len(ys)) if ys else float(row[0])
                order.append(nid)

        for r in roots:
            visit(r)

        idx = {nid: i for i, nid in enumerate(order)}
        nn = []
        for nid in order:
            n = nodes[nid]
            if n["alive"]:
                end = year_end
            else:
                ch = kids.get(nid, [])
                end = max([nodes[c]["born"] for c in ch] or [n["born"] + 10])
            nn.append({
                "i": idx[nid], "p": idx.get(n["par"], -1) if n["par"] else -1,
                "pid": n["pid"], "nm": n["name"], "b": int(n["born"]),
                "e": int(end), "y": round(ycoord.get(nid, 0.0), 3),
                "al": 1 if n["alive"] else 0, "pop": int(n["pop"]),
                "g": int(n["gen"]),
            })
        out_fams.append({
            "fid": f["fid"], "nm": nodes[f["big"]]["name"], "col": color,
            "pop": int(f["pop"]), "n": int(f["n"]), "rows": int(row[0]),
            "nodes": nn,
        })

    # ── таблицы когнатов и матрицы расхождения ─────────────────────────────
    def _group(gid: str, label: str, pids: list[int], fam_col: str) -> dict:
        pids = pids[:MAX_LANGS_IN_TABLE]
        langs = [{"pid": p, "nm": info[p]["name"], "pop": info[p]["pop"],
                  "b": info[p]["born"]} for p in pids]
        rows, sims = [], []
        for m in COGNATE_MEANINGS:
            ws = []
            for p in pids:
                try:
                    ws.append(lects[p].word(m))
                except Exception:
                    ws.append("—")
            rows.append([m] + ws)
            sims.append([round(_lev_ratio(ws[0], w), 3) for w in ws])
        dist, cog = [], []
        for a in pids:
            dr, cr = [], []
            for b in pids:
                if a == b:
                    dr.append(0.0)
                    cr.append(1.0)
                else:
                    try:
                        dr.append(round(float(lects[a].distance(lects[b])), 3))
                        cr.append(round(float(lects[a].cognate_share(lects[b])), 3))
                    except Exception:
                        dr.append(1.0)
                        cr.append(0.0)
            dist.append(dr)
            cog.append(cr)
        return {"id": gid, "label": label, "col": fam_col, "langs": langs,
                "rows": rows, "sim": sims, "dist": dist, "cog": cog}

    groups = []
    for f in out_fams:
        if f["n"] < 2:
            continue
        pids = sorted((n["pid"] for n in f["nodes"] if n["al"]),
                      key=lambda p: -info[p]["pop"])
        groups.append(_group(
            "f" + f["fid"],
            f'Семья {f["nm"]} — {f["n"]} яз., {nfmt_py(f["pop"])} чел.',
            pids, f["col"]))
    groups.sort(key=lambda g: (-len(g["langs"]),
                               -sum(x["pop"] for x in g["langs"])))
    # сводная выборка: по одному языку из крупнейших семей — они не родственны
    mixed_pids = []
    for f in out_fams[:MAX_LANGS_IN_TABLE]:
        live = [n["pid"] for n in f["nodes"] if n["al"]]
        if live:
            mixed_pids.append(max(live, key=lambda p: info[p]["pop"]))
    if len(mixed_pids) >= 2:
        groups.append(_group("mixed",
                             "Сводная: по языку из крупнейших семей (неродственные)",
                             mixed_pids, "#8b9bab"))

    # ── паспорта языков ────────────────────────────────────────────────────
    passports = {}
    for pid, lect in lects.items():
        r = info[pid]
        # сид устойчив между сборками: только числа, никакого hash() строк
        try:
            fseed = int(r["fam"])
        except (TypeError, ValueError):
            fseed = 0
        rng = random.Random((fseed * 1000003 + pid * 7919) & 0x7FFFFFFF)
        words = []
        for m in PASSPORT_MEANINGS:
            try:
                words.append([m, lect.word(m)])
            except Exception:
                pass
        men = [lect.person_name(rng, 1, "chief") for _ in range(2)]
        men += [lect.person_name(rng, 1) for _ in range(2)]
        women = [lect.person_name(rng, 0) for _ in range(3)]
        places = []
        for kind, ru in (("settlement", "город"), ("settlement", "город"),
                         ("river", "река"), ("mountain", "гора"),
                         ("region", "земля")):
            try:
                nm, gl = lect.place_name(rng, kind, with_gloss=True)
                places.append([nm, ru, gl])
            except Exception:
                pass
        gods = []
        for dom in THEO_DOMAINS[:4]:
            try:
                nm, gl = lect.theonym(rng, dom, with_gloss=True)
                gods.append([nm, dom, gl])
            except Exception:
                pass
        try:
            ethn = lect.ethnonym(rng)
        except Exception:
            ethn = ""
        try:
            pas = lect.passport()
        except Exception:
            pas = ""
        passports[str(pid)] = {
            "nm": r["name"], "ln": r.get("lname", ""),
            "fam": r["fam"], "pop": r["pop"],
            "b": r["born"], "gen": r["gen"], "ethn": ethn, "pass": pas,
            "w": words, "men": men, "women": women, "pl": places, "gods": gods,
        }

    top = [f["fid"] for f in out_fams if f["n"] >= 2][:MAX_FAM_DEFAULT]
    if not top:
        top = [f["fid"] for f in out_fams[:MAX_FAM_DEFAULT]]
    born_all = [n["b"] for f in out_fams for n in f["nodes"]]
    return {
        "fams": out_fams,
        "top": top,
        "groups": groups,
        "pass": passports,
        "nLects": len(info),
        "nFams": len(out_fams),
        "y0": int(min(born_all) if born_all else year_start),
        "y1": int(max(born_all) if born_all else year_end),
        "yEnd": int(year_end),
    }


# ────────────────────────────────────────────────────────────────────────────
#  Замечательные люди
# ────────────────────────────────────────────────────────────────────────────
_RX_DISC = re.compile(r"^(?P<nm>.+?) из народа .+? впервые \S+: (?P<what>.+?)\.?$")
_RX_DEAD = re.compile(r"^(?P<nm>.+?) умер(?:ла)? в (?P<age>\d+) лет")
_RX_RULE = re.compile(r"^(?P<ti>\S+) (?P<nm>.+?) встал[аи]? во главе народа ")
_RX_DEC = re.compile(r"^(?P<nm>\S+) (?:увёл|повёл|принёс|переменил|усмирил|"
                     r"истребил|велел) ")


def _pick(row: dict, keys: tuple[str, ...]) -> Any:
    """Первое непустое значение из перечисленных ключей."""
    for k in keys:
        v = row.get(k)
        if v is not None and v != "" and v != []:
            return v
    return None


def _as_text(v: Any) -> str:
    """Пункт «что сделал» из строки или словаря произвольной формы."""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        t = _pick(v, ("text", "what", "name", "title", "desc", "описание"))
        y = _pick(v, ("year", "y", "год"))
        t = str(t) if t is not None else json.dumps(v, ensure_ascii=False)[:120]
        return f"{t} ({_ru_year(int(y))})" if isinstance(y, (int, float)) else t
    return str(v)


def _read_people_file(run_dir: Path) -> dict[int, dict]:
    """Необязательный people.jsonl — более богатый источник о людях.

    Схема заранее не известна, поэтому читаем терпимо: берём то, что узнали,
    остальное молча пропускаем. Отсутствие файла — не ошибка.
    """
    path = run_dir / "people.jsonl"
    if not path.exists():
        return {}
    out: dict[int, dict] = {}
    for row in _read_jsonl(path):
        if not isinstance(row, dict):
            continue
        aid = _pick(row, ("aid", "id", "person", "person_id"))
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        rec: dict[str, Any] = {}
        for dst, keys in (("nm", ("name", "nm", "имя", "full_name")),
                          ("ti", ("title", "ti", "rank", "титул", "role_ru")),
                          ("pn", ("polity_name", "people", "народ", "culture"))):
            v = _pick(row, keys)
            if isinstance(v, str) and v.strip():
                rec[dst] = v.strip()
        v = _pick(row, ("polity", "pid", "poly"))
        if isinstance(v, (int, float)):
            rec["p"] = int(v)
        for dst, keys in (("y0", ("born", "y0", "birth", "year_born", "year")),
                          ("y1", ("died", "y1", "death", "year_died"))):
            v = _pick(row, keys)
            if isinstance(v, (int, float)):
                rec[dst] = int(v)
        v = _pick(row, ("age", "возраст"))
        if isinstance(v, (int, float)):
            rec["age"] = int(v)
        deeds = _pick(row, ("deeds", "acts", "events", "notes", "дела", "сделал"))
        if isinstance(deeds, (list, tuple)):
            rec["extra"] = [t for t in (_as_text(d) for d in deeds[:6]) if t]
        elif isinstance(deeds, str) and deeds.strip():
            rec["extra"] = [deeds.strip()]
        if rec:
            out[aid] = rec
    return out


def _collect_people(chron: list[dict], facts: dict[int, dict], era_at,
                    rich: dict[int, dict] | None = None
                    ) -> tuple[list[dict], set[int], int]:
    """Свести события с полем person в карточки людей.

    Возвращает (карточки, множество aid отобранных людей).
    """
    ppl: dict[int, dict] = {}

    def slot(aid: int) -> dict:
        r = ppl.get(aid)
        if r is None:
            r = ppl[aid] = {"a": aid, "nm": "", "ti": "", "p": None,
                            "y0": 10 ** 9, "y1": -10 ** 9, "sc": 0.0,
                            "inv": [], "rule": None, "age": None,
                            "dec": [], "ne": 0}
        return r

    by_name: dict[tuple, list[int]] = defaultdict(list)
    for e in chron:
        aid = e.get("person")
        if aid is None:
            continue
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        r = slot(aid)
        yr = int(e.get("year", 0))
        kind = e.get("kind", "")
        txt = str(e.get("text", ""))
        r["y0"] = min(r["y0"], yr)
        r["y1"] = max(r["y1"], yr)
        r["ne"] += 1
        r["sc"] += float(e.get("weight", 1.0) or 1.0)
        if e.get("polity") is not None:
            r["p"] = int(e["polity"])
        if kind == "discovery":
            m = _RX_DISC.match(txt)
            if m:
                r["nm"] = r["nm"] or m.group("nm")
                r["inv"].append([yr, m.group("what")])
        elif kind == "rule":
            m = _RX_RULE.match(txt)
            if m:
                r["nm"] = r["nm"] or m.group("nm")
                r["ti"] = r["ti"] or m.group("ti")
                r["rule"] = yr
        elif kind == "death":
            m = _RX_DEAD.match(txt)
            if m:
                r["nm"] = r["nm"] or m.group("nm")
                r["age"] = int(m.group("age"))
    for aid, r in ppl.items():
        if r["nm"] and r["p"] is not None:
            by_name[(r["p"], r["nm"])].append(aid)

    # решения на развилках person не пишут — привязываем их по имени и народу
    for e in chron:
        if e.get("kind") != "decision" or e.get("person") is not None:
            continue
        pid = e.get("polity")
        if pid is None:
            continue
        m = _RX_DEC.match(str(e.get("text", "")))
        if not m:
            continue
        cand = by_name.get((int(pid), m.group("nm")))
        if not cand or len(cand) != 1:
            continue
        r = ppl[cand[0]]
        yr = int(e.get("year", 0))
        if yr < r["y0"] - 90 or yr > r["y1"] + 90:
            continue
        r["dec"].append([yr, str(e.get("text", ""))])
        r["sc"] += float(e.get("weight", 1.0) or 1.0) * 0.7
        r["ne"] += 1
        e["_person"] = r["a"]

    # ── необязательный people.jsonl поверх летописи ────────────────────────
    for aid, rec in (rich or {}).items():
        r = slot(int(aid))
        for k in ("nm", "ti", "p", "age"):
            if rec.get(k) is not None:
                r[k] = rec[k]
        if rec.get("y0") is not None:
            r["y0"] = min(r["y0"], rec["y0"])
        if rec.get("y1") is not None:
            r["y1"] = max(r["y1"], rec["y1"])
        r["sc"] += 3.0          # кого отдельно описали в people.jsonl — тот заметен
        if rec.get("extra"):
            r["ex"] = list(rec["extra"])
            r["sc"] += 1.2 * len(rec["extra"])
        if rec.get("pn"):
            r["pnFix"] = rec["pn"]
        if r["y0"] > r["y1"]:                       # только из файла, без летописи
            r["y0"] = r["y1"] = rec.get("y0", rec.get("y1", 0)) or 0

    out = []
    for aid, r in ppl.items():
        if not r["nm"]:
            continue
        pid = r["p"]
        f = facts.get(pid, {}) if pid is not None else {}
        # заметность: вес событий плюс надбавки за изобретения, власть, решения
        r["sc"] = round(r["sc"] + 1.6 * len(r["inv"]) + 0.9 * len(r["dec"])
                        + (0.8 if r["rule"] is not None else 0.0)
                        + 0.5 * max(0, r["ne"] - 1), 2)
        r["pn"] = r.pop("pnFix", None) or f.get("name", "—")
        r["col"] = f.get("color", "#8b9bab")
        r["era"] = era_at(r["y0"], pid)
        r["inv"].sort()
        r["dec"].sort()
        del r["ne"]
        out.append(r)
    out.sort(key=lambda r: (-r["sc"], r["y0"]))
    # люди из people.jsonl описаны отдельно и намеренно — им бронь на половину
    # мест; дальше обычный отбор
    picked, taken = [], set()
    if rich:
        for r in out:
            if r["a"] in rich and len(picked) < MAX_PEOPLE // 2:
                picked.append(r)
                taken.add(r["a"])
    # чтобы список не выродился в хронику двух-трёх держав, берём сперва по
    # нескольку самых заметных от каждого народа, а остаток — по общему счёту
    per: dict[Any, int] = defaultdict(int)
    rest = []
    for r in picked:
        per[r["p"]] += 1
    for r in out:
        if r["a"] in taken:
            continue
        if per[r["p"]] < PEOPLE_PER_POLITY and len(picked) < MAX_PEOPLE:
            per[r["p"]] += 1
            picked.append(r)
        else:
            rest.append(r)
    picked.extend(rest[:max(0, MAX_PEOPLE - len(picked))])
    picked.sort(key=lambda r: (-r["sc"], r["y0"]))
    return picked, {r["a"] for r in picked}, len(out)


# ────────────────────────────────────────────────────────────────────────────
#  Сбор данных прогона
# ────────────────────────────────────────────────────────────────────────────
def _collect(run_dir: Path) -> dict[str, Any]:
    """Собрать компактный payload для встраивания в HTML."""
    run = {}
    rj = run_dir / "run.json"
    if rj.exists():
        run = json.loads(rj.read_text(encoding="utf-8"))
    cfg = dict(run.get("config") or {})

    w = load_world(str(run_dir / "world"))
    H, W = int(w.height), int(w.width)
    is_land = np.asarray(w.is_land, dtype=bool)
    biome = np.asarray(w.biome, dtype=np.int8)
    elev = np.nan_to_num(np.asarray(w.elevation, dtype=np.float32))
    shade = _hillshade(elev, is_land)

    def _u8(field, lo=0.0, hi=1.0):
        v = getattr(w, field, None)
        if v is None:
            return np.zeros(H * W, dtype=np.uint8)
        v = np.nan_to_num(np.asarray(v, dtype=np.float32))
        v = np.clip((v - lo) / (hi - lo + 1e-9), 0, 1)
        return (v * 255).astype(np.uint8).ravel()

    world_pack = {
        "w": W, "h": H,
        "biome": _b64(biome.ravel()),
        "elev": _b64(np.clip(elev, -12000, 12000).astype(np.int16).ravel()),
        "land": _b64(is_land.astype(np.uint8).ravel()),
        "shade": _b64(shade.ravel()),
        "river": _b64(_u8("river")),   # для прорисовки рек на рельефе
        "soil": _b64(_u8("soil")),     # для всплывающей подсказки
    }

    timeline = _read_jsonl(run_dir / "timeline.jsonl")
    snaps = _read_jsonl(run_dir / "snapshots.jsonl")
    chron = _read_jsonl(run_dir / "chronicle.jsonl")

    # Симулятор снимает последний год дважды (в цикле и после него) — убираем
    # дубли по годам, оставляя последнюю запись, и упорядочиваем по времени.
    def _dedup(rows):
        seen = {}
        for r in rows:
            seen[int(r.get("year", 0))] = r
        return [seen[y] for y in sorted(seen)]

    snaps = _dedup(snaps)
    timeline = _dedup(timeline)

    # ── кадры ──────────────────────────────────────────────────────────────
    def _frame(s: dict) -> dict:
        pol = []
        for p in (s.get("polities") or []):
            pol.append({
                "pid": int(p.get("pid", -1)),
                "name": p.get("name", "—"),
                "color": p.get("color", "#888888"),
                "pop": int(p.get("pop", 0)),
                "mode": p.get("mode", "forager"),
                "form": p.get("form", "band"),
                "cells": int(p.get("cells", 0)),
                "tech": int(p.get("tech", 0)),
                "cx": round(float(p.get("complexity", 0.0)), 3),
                "iq": round(float(p.get("ineq", 0.0)), 3),
                "coh": round(float(p.get("coh", 0.0)), 3),
                "era": p.get("era", "—"),
            })
        st = []
        for c in (s.get("settlements") or []):
            st.append({
                "n": c.get("name", "—"),
                "y": int(c.get("y", 0)), "x": int(c.get("x", 0)),
                "p": int(c.get("pop", 0)),
                "t": str(c.get("tier", "")),   # ранг поселения — русская строка
                "c": int(c.get("culture", -1)) if c.get("culture") is not None else -1,
                "w": round(float(c.get("walls", 0.0)), 2),
                "m": int(c.get("mon", 0)),
            })
        return {"year": int(s.get("year", 0)), "cm": s.get("culture_map", ""),
                "pol": pol, "set": st}

    n_all = len(snaps)
    frames = [_frame(s) for s in snaps]
    if not frames:
        # прогон без снимков: даём один пустой кадр, чтобы страница жила
        frames = [{"year": int(cfg.get("year_start", 0)),
                   "cm": _b64(np.full(H * W, -1, dtype=np.int16)),
                   "pol": [], "set": []}]

    # ── языки, родство и люди ──────────────────────────────────────────────
    year_start0 = int(cfg.get("year_start", (snaps[0]["year"] if snaps else 0)))
    year_end0 = int(run.get("year", cfg.get("year_end", 0)))
    facts = _polity_facts(snaps)

    # эпоха конкретного народа в конкретный год — по ближайшему снимку;
    # мировая «ведущая эпоха» из timeline слишком груба для карточек людей
    era_track: dict[int, list[tuple[int, str]]] = defaultdict(list)
    world_era: list[tuple[int, str]] = []
    for s in snaps:
        yr = int(s.get("year", 0))
        for p in (s.get("polities") or []):
            e = p.get("era")
            if e:
                era_track[int(p.get("pid", -1))].append((yr, e))
    for t in timeline:
        world_era.append((int(t.get("year", 0)), t.get("era", "—")))

    def _closest(track: list[tuple[int, str]], y: int) -> str:
        best, bd = "—", 10 ** 12
        for ty, e in track:
            d = abs(ty - y)
            if d < bd:
                bd, best = d, e
        return best

    def era_at(y: int, pid: int | None = None) -> str:
        """Эпоха: своя у народа, если он известен, иначе мировая."""
        if pid is not None and era_track.get(pid):
            return _closest(era_track[pid], y)
        return _closest(world_era, y)

    lang = None
    try:
        lang = _collect_lang(run_dir, snaps, year_start0, year_end0)
    except Exception:
        lang = None
    try:
        rich = _read_people_file(run_dir)
    except Exception:
        rich = {}
    try:
        people, keep_aids, n_people_all = _collect_people(chron, facts, era_at, rich)
    except Exception:
        people, keep_aids, n_people_all = [], set(), 0

    # ── летопись ───────────────────────────────────────────────────────────
    chron.sort(key=lambda e: (int(e.get("year", 0)), -float(e.get("weight", 0))))
    ev_trunc = False
    if len(chron) > MAX_EVENTS:
        # события «замечательных людей» держим всегда — иначе карточка людей
        # ссылалась бы на выброшенные строки летописи
        forced = {i for i, e in enumerate(chron)
                  if (e.get("person") in keep_aids
                      or e.get("_person") in keep_aids)}
        rest = [i for i in range(len(chron)) if i not in forced]
        rest.sort(key=lambda i: -float(chron[i].get("weight", 0)))
        keep = forced | set(rest[:max(0, MAX_EVENTS - len(forced))])
        chron = [e for i, e in enumerate(chron) if i in keep]
        ev_trunc = True
    events = []
    for e in chron:
        y = e.get("y")
        x = e.get("x")
        aid = e.get("person")
        if aid is None:
            aid = e.get("_person")
        events.append({
            "yr": int(e.get("year", 0)),
            "k": e.get("kind", "—"),
            "t": e.get("text", ""),
            "w": round(float(e.get("weight", 1.0)), 2),
            "p": int(e["polity"]) if e.get("polity") is not None else None,
            "cy": int(y) if y is not None else None,
            "cx": int(x) if x is not None else None,
            "pe": int(aid) if aid is not None and int(aid) in keep_aids else None,
        })

    # ── прореживание кадров под бюджет размера ─────────────────────────────
    # Считаем ВЕСЬ вес кадра (карта культур + список народов + поселения),
    # а не только карту: при 200 народах списки весят больше самой карты.
    def _jsz(obj) -> int:
        return len(json.dumps(obj, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8"))

    other = (_jsz(world_pack) + _jsz(timeline) + _jsz(events)
             + _jsz(lang) + _jsz(people)
             + len(_CSS.encode("utf-8")) + len(_JS.encode("utf-8")) + 16000)
    budget = max(1_500_000, TARGET_BYTES - other)
    thinned = False
    if frames:
        costs = [_jsz(f) for f in frames]
        avg = max(1.0, sum(costs) / len(costs))
        limit = max(MIN_FRAMES, min(MAX_FRAMES, int(budget // avg)))
        if len(frames) > limit:
            idx = np.unique(np.linspace(0, len(frames) - 1, limit).round().astype(int))
            frames = [frames[i] for i in idx]
            thinned = True

    # ── шапка ──────────────────────────────────────────────────────────────
    stats = dict(run.get("stats") or {})
    last_tl = timeline[-1] if timeline else {}
    years = [int(f["year"]) for f in frames] or [int(cfg.get("year_start", 0))]
    head = {
        "run_id": run.get("run_id") or run_dir.name,
        "seed": cfg.get("seed"),
        "year_start": int(cfg.get("year_start", years[0])),
        "year_end": int(run.get("year", cfg.get("year_end", years[-1]))),
        "resolver": cfg.get("resolver") or "—",
        "resolver_model": cfg.get("resolver_model") or "",
        "resolver_stats": run.get("resolver") or {},
        "n_polities_ever": int(run.get("n_polities_ever", 0) or 0),
        "pop_end": float(last_tl.get("pop", 0.0)),
        "tech_max": int(last_tl.get("tech_max", 0)),
        "wars": int(stats.get("wars", 0) or 0),
        "epidemics": int(stats.get("epidemics", 0) or 0),
        "fissions": int(stats.get("fissions", 0) or 0),
        "extinctions": int(stats.get("extinctions", 0) or 0),
        "discoveries": int(stats.get("discoveries", 0) or 0),
        "junctures": int(stats.get("junctures", 0) or 0),
        "era_end": last_tl.get("era", "—"),
        "frames": len(frames),
        "frames_all": n_all,
        "thinned": thinned,
        "events": len(events),
        "events_trunc": ev_trunc,
        "n_people": len(people),
        "n_people_all": int(n_people_all),
        "n_lects": (lang or {}).get("nLects", 0),
        "n_fams": (lang or {}).get("nFams", 0),
    }

    # ── демография на опорные годы (для шапки) ─────────────────────────────
    marks = [y for y in (-10000, -5000, -2000, 0) if year_start0 < y < year_end0]
    demo = []
    if timeline:
        for y in marks + [year_end0]:
            best = min(timeline, key=lambda t: abs(int(t.get("year", 0)) - y))
            demo.append([int(best.get("year", 0)), float(best.get("pop", 0.0))])
        seen_y = set()
        demo = [d for d in demo if not (d[0] in seen_y or seen_y.add(d[0]))]
    head["demo"] = demo

    return {
        "head": head,
        "world": world_pack,
        "frames": frames,
        "timeline": timeline,
        "events": events,
        "lang": lang,
        "people": people,
        "biomeNames": {str(k): v for k, v in BIOME_NAMES.items()},
        "biomeColors": {str(k): v for k, v in BIOME_COLORS.items()},
        "modeRu": MODE_RU, "modeOrder": list(MODE_ORDER), "modeColors": MODE_COLORS,
        "modeShort": MODE_SHORT, "formShort": FORM_SHORT,
        "formRu": FORM_RU, "formOrder": list(FORM_ORDER), "formColors": FORM_COLORS,
        "eraOrder": list(ERA_ORDER), "eraColors": ERA_COLORS,
        "eraShort": ERA_SHORT,
        "kindRu": KIND_RU, "kindColors": KIND_COLORS, "kindOrder": list(KIND_ORDER),
    }


# ────────────────────────────────────────────────────────────────────────────
#  CSS
# ────────────────────────────────────────────────────────────────────────────
_CSS = r"""
:root{
  --bg:#0c1116; --bg2:#111922; --panel:#131c25; --line:#1f2c38;
  --ink:#c7d3dd; --ink2:#8b9bab; --ink3:#5f7183;
  --acc:#7fb3d5; --acc2:#c8a96e; --warn:#c4685a;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--acc)}
h1,h2,h3{margin:0;font-weight:600;letter-spacing:.01em}
.wrap{max-width:1640px;margin:0 auto;padding:18px 20px 60px}

/* шапка */
.hdr{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}
.hdr h1{font-size:20px;letter-spacing:.06em;text-transform:uppercase;color:#e2ecf4}
.hdr .sub{color:var(--ink3);font-size:12.5px;margin-top:3px}
.facts{display:flex;flex-wrap:wrap;gap:9px;margin-top:13px}
.fact{background:var(--panel);border:1px solid var(--line);border-radius:5px;
  padding:7px 12px;min-width:104px}
.fact b{display:block;font-size:17px;color:#e6eef5;font-weight:600;
  font-variant-numeric:tabular-nums}
.fact span{display:block;font-size:11px;color:var(--ink3);margin-top:2px;
  letter-spacing:.03em}
.note{margin-top:9px;font-size:11.5px;color:var(--acc2);opacity:.85}

/* сетка */
.grid{display:grid;grid-template-columns:minmax(0,1fr) 500px;gap:16px;align-items:start}
@media(max-width:1240px){.grid{grid-template-columns:minmax(0,1fr)}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;
  padding:12px 13px;margin-bottom:16px}
.panel>h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:10px}

/* карта */
#mapbox{position:relative;background:#070b0f;border-radius:5px;overflow:hidden;
  border:1px solid var(--line)}
#map{display:block;width:100%;cursor:crosshair}
#tip{position:absolute;pointer-events:none;display:none;z-index:9;
  background:rgba(9,14,19,.95);border:1px solid #2b3d4d;border-radius:5px;
  padding:7px 10px;font-size:12px;max-width:270px;line-height:1.45;
  box-shadow:0 6px 22px rgba(0,0,0,.55)}
#tip .th{color:#e6eef5;font-weight:600;margin-bottom:3px}
#tip .tr{color:var(--ink2)}
#tip .tr b{color:var(--ink);font-weight:500}

/* время */
.timebar{display:flex;align-items:center;gap:9px;margin-top:11px;flex-wrap:wrap}
.btn{background:#1a2530;border:1px solid #27384a;color:var(--ink);
  border-radius:4px;padding:5px 11px;cursor:pointer;font-size:13px;
  font-family:inherit;line-height:1.2}
.btn:hover{background:#22303e;border-color:#35506a}
.btn.on{background:#25455e;border-color:#3d7098;color:#dbeaf5}
#slider{flex:1;min-width:220px;accent-color:var(--acc);cursor:pointer}
#yearlab{font-variant-numeric:tabular-nums;color:#e6eef5;font-size:14px;
  min-width:132px;text-align:right;letter-spacing:.02em}
.spd{color:var(--ink3);font-size:11.5px}

/* слои */
.layers{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:11px;
  padding-top:11px;border-top:1px solid var(--line)}
.layers label{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;
  color:var(--ink2);cursor:pointer;user-select:none}
.layers input{accent-color:var(--acc);cursor:pointer;margin:0}

/* эпохи */
#erabox{margin-top:12px}
#era{display:block;width:100%;height:46px}
.eralegend{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:7px}
.eralegend span{font-size:11px;color:var(--ink3);display:inline-flex;
  align-items:center;gap:5px}
.sw{width:9px;height:9px;border-radius:2px;display:inline-block;flex:none}

/* таблица народов */
.tabwrap{max-height:376px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:11.1px;
  font-variant-numeric:tabular-nums;table-layout:fixed}
th{position:sticky;top:0;background:#16212c;color:var(--ink2);text-align:right;
  padding:6px 3px;font-weight:600;cursor:pointer;user-select:none;
  border-bottom:1px solid var(--line);white-space:nowrap;font-size:10.5px;
  letter-spacing:.02em}
th:first-child,td:first-child{text-align:left}
th:hover{color:var(--acc)}
th.sorted{color:var(--acc)}
td{padding:4px 3px;text-align:right;border-bottom:1px solid #17222c;
  color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
tbody tr{cursor:pointer}
tbody tr:hover{background:#18242f}
tbody tr.sel{background:#1e3648}
tbody tr.sel td{color:#dceaf4}
td.nm{color:var(--ink)}
#phead th:nth-child(1){width:24%}
#phead th:nth-child(2){width:14%}
#phead th:nth-child(3){width:16%}
#phead th:nth-child(4){width:15%}
#phead th:nth-child(5){width:12%}
#phead th:nth-child(6),#phead th:nth-child(7){width:6%}
#phead th:nth-child(8),#phead th:nth-child(9){width:7.5%}
.cogwrap table,#matbox table{table-layout:auto}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;
  margin-right:6px;vertical-align:middle;flex:none}

/* летопись */
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:9px}
.chip{font-size:11px;padding:2.5px 8px;border-radius:11px;cursor:pointer;
  border:1px solid #26343f;color:var(--ink3);background:#141d26;user-select:none}
.chip.on{color:#0d141a;font-weight:600;border-color:transparent}
.wrow{display:flex;align-items:center;gap:9px;margin-bottom:9px;font-size:11.5px;
  color:var(--ink3)}
.wrow input{flex:1;accent-color:var(--acc2);cursor:pointer}
#feed{max-height:432px;overflow:auto}
.ev{padding:5px 8px;border-left:2px solid #2a3844;margin-bottom:3px;
  border-radius:0 3px 3px 0;font-size:12.2px;line-height:1.42}
.ev:hover{background:#18242f}
.ev.near{background:#17242e;border-left-color:var(--acc)}
.ev.geo{cursor:pointer}
.ev .y{color:var(--ink3);font-size:10.5px;font-variant-numeric:tabular-nums;
  letter-spacing:.02em}
.ev .k{font-size:10px;text-transform:uppercase;letter-spacing:.06em;
  margin-left:7px}
.ev .t{color:var(--ink2);margin-top:1px}
.ev.near .t{color:var(--ink)}

/* графики */
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(370px,1fr));
  gap:14px;align-items:start}
.ch{background:var(--panel);border:1px solid var(--line);border-radius:6px;
  padding:11px 12px 8px}
.ch h3{font-size:11.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:8px}
.ch canvas{display:block;width:100%;height:186px}
.leg{display:flex;flex-wrap:wrap;gap:4px 11px;margin-top:7px}
.leg span{font-size:10.5px;color:var(--ink3);display:inline-flex;
  align-items:center;gap:5px}
/* ── общие крупные секции (языки, люди) ── */
.sec{background:var(--panel);border:1px solid var(--line);border-radius:6px;
  padding:13px 14px;margin-bottom:16px}
.sec>h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:4px}
.sec .cap{font-size:11.5px;color:var(--ink3);margin-bottom:11px}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px}
.bar label{font-size:11.5px;color:var(--ink3)}
select{background:#16212c;border:1px solid #27384a;color:var(--ink);
  border-radius:4px;padding:4px 7px;font:12.5px/1.2 inherit;max-width:100%;
  cursor:pointer}
select:hover{border-color:#35506a}
h4{margin:0 0 5px;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600}

/* ── дендрограмма ── */
.langgrid{display:grid;grid-template-columns:minmax(0,1fr) 392px;gap:14px;
  align-items:start}
@media(max-width:1180px){.langgrid{grid-template-columns:minmax(0,1fr)}}
#treeaxisbox{height:26px}
#treeaxisbox svg{display:block}
#treebox{max-height:648px;overflow-x:hidden;overflow-y:scroll;
  border:1px solid var(--line);border-radius:5px;background:#101821}
#tree{display:block}
#tree text{font:11.5px "Segoe UI",Roboto,Arial,sans-serif}
#tree text.fam{font-size:11.5px;font-weight:600;letter-spacing:.04em}
#tree text.leaf{fill:#c7d3dd}
#tree text.dim{fill:#5f7183;font-size:10px}
#tree text.ghost{fill:#6d7f90;font-size:9.5px;font-style:italic}
#tree rect.hit{fill:transparent;cursor:pointer}
#tree rect.hit:hover{fill:rgba(127,179,213,.10)}
#tree rect.sel{fill:rgba(127,179,213,.16)}
#treeaxis text{font:10px "Segoe UI",Roboto,Arial,sans-serif;fill:#5f7183}

/* ── паспорт языка ── */
#lpass{background:#101821;border:1px solid var(--line);border-radius:5px;
  padding:11px 12px;max-height:712px;overflow:auto}
#lpass .lpt{font-size:15px;color:#e6eef5;font-weight:600}
#lpass .lps{font-size:11.5px;color:var(--ink3);margin:2px 0 9px}
#lpass pre{margin:0 0 11px;font:10.8px/1.5 "Consolas","DejaVu Sans Mono",monospace;
  white-space:pre-wrap;color:var(--ink2);background:#0d141b;border-radius:4px;
  padding:8px 9px;border:1px solid #1a2531}
.wgrid{display:grid;grid-template-columns:1fr 1fr;gap:3px 7px;margin-bottom:11px}
.wgrid div{font-size:11.6px;color:var(--ink3);display:flex;
  justify-content:space-between;gap:8px;background:#0d141b;border-radius:3px;
  padding:2.5px 7px;border:1px solid #18222c}
.wgrid b{color:#d6e3ec;font-weight:500;
  font-family:"Consolas","DejaVu Sans Mono",monospace}
.nlist{font-size:12px;color:var(--ink2);margin-bottom:9px;line-height:1.6}
.nlist b{color:#d6e3ec;font-weight:500}
.nlist i{color:var(--ink3);font-style:normal;font-size:10.5px}

/* ── таблица когнатов и матрица ── */
.langgrid2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);
  gap:14px;align-items:start;margin-top:14px;padding-top:13px;
  border-top:1px solid var(--line)}
@media(max-width:1180px){.langgrid2{grid-template-columns:minmax(0,1fr)}}
.cogwrap{overflow:auto;max-height:420px}
table.cog{font-size:12px;width:100%}
table.cog th{text-align:center;font-size:10.5px;background:#16212c;
  padding:5px 5px;cursor:default}
table.cog th:first-child{text-align:left}
table.cog td{text-align:center;padding:3px 5px;color:#d3e0ea;
  font-family:"Consolas","DejaVu Sans Mono",monospace;font-size:12px}
table.cog td:first-child{text-align:left;color:var(--ink3);
  font-family:inherit;font-size:11.5px}
table.mx{font-size:11px;width:100%}
table.mx th{padding:4px 3px;font-size:10px;cursor:default;text-align:center}
table.mx th:first-child{text-align:right}
table.mx td{text-align:center;padding:4px 3px;color:#0e151b;font-weight:600;
  font-variant-numeric:tabular-nums}
table.mx td.lb{background:transparent;color:var(--ink2);text-align:right;
  font-weight:400;max-width:130px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;font-size:11px}

/* ── люди ── */
#plist{display:grid;grid-template-columns:repeat(auto-fill,minmax(252px,1fr));
  gap:9px;max-height:560px;overflow:auto;padding-right:3px}
.pcard{background:#101821;border:1px solid var(--line);border-radius:5px;
  padding:8px 10px;cursor:pointer;border-left-width:3px}
.pcard:hover{background:#16222d;border-color:#2f4759}
.pcard.sel{background:#1c3243;border-color:#3d7098}
.pcard .ph{font-size:13.5px;color:#e2ecf4;font-weight:600}
.pcard .ph i{font-style:normal;color:var(--acc2);font-weight:400;font-size:11.5px}
.pcard .ps{font-size:10.8px;color:var(--ink3);margin:2px 0 5px}
.pcard .pa{font-size:11.5px;color:var(--ink2);line-height:1.45}
.pcard .pa span{color:var(--ink3)}
.empty{color:var(--ink3);font-size:12px;padding:10px 2px}

.foot{margin-top:26px;padding-top:12px;border-top:1px solid var(--line);
  color:var(--ink3);font-size:11.5px}
.demo{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:10px;font-size:12px;
  color:var(--ink3)}
.demo b{color:#d6e3ec;font-weight:600;font-variant-numeric:tabular-nums}
.demo .dl{color:var(--ink2);letter-spacing:.03em;text-transform:uppercase;
  font-size:10.5px;margin-right:2px}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:#0e151c}
::-webkit-scrollbar-thumb{background:#25333f;border-radius:5px}
::-webkit-scrollbar-thumb:hover{background:#32475a}
"""

# ────────────────────────────────────────────────────────────────────────────
#  JS
# ────────────────────────────────────────────────────────────────────────────
_JS = r"""
'use strict';
var D = JSON.parse(document.getElementById('terra-data').textContent);

/* ── утилиты ──────────────────────────────────────────────────────────── */
function b64bytes(s){
  var bin = atob(s), n = bin.length, u = new Uint8Array(n);
  for (var i=0;i<n;i++) u[i] = bin.charCodeAt(i);
  return u;
}
function asI16(s){ var u = b64bytes(s); return new Int16Array(u.buffer, 0, (u.length/2)|0); }
function asI8(s){ var u = b64bytes(s); return new Int8Array(u.buffer, 0, u.length); }
function ruYear(y){ return y < 0 ? (-y) + ' до н. э.' : y + ' н. э.'; }
function axYear(y){ return y < 0 ? '−' + (-y) : '' + y; }
function nfmt(v){
  v = Math.round(v);
  if (Math.abs(v) >= 1e9) return (v/1e9).toFixed(2) + ' млрд';
  if (Math.abs(v) >= 1e6) return (v/1e6).toFixed(2) + ' млн';
  if (Math.abs(v) >= 1e4) return (v/1e3).toFixed(0) + ' тыс.';
  return ('' + v).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}
function hex2rgb(h){
  if (!h || h.charAt(0) !== '#' || h.length < 7) return [136,136,136];
  return [parseInt(h.substr(1,2),16), parseInt(h.substr(3,2),16), parseInt(h.substr(5,2),16)];
}
function el(id){ return document.getElementById(id); }
function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
/* цвет эпохи, осветлённый до читаемого на тёмном фоне */
function shiftEra(era){
  var c = hex2rgb(D.eraColors[era] || '#8b9bab');
  return 'rgb(' + Math.round(c[0]*0.45+150) + ',' + Math.round(c[1]*0.45+150) +
         ',' + Math.round(c[2]*0.45+150) + ')';
}
function mix(a, b, t){
  return 'rgb(' + Math.round(a[0]+(b[0]-a[0])*t) + ',' +
         Math.round(a[1]+(b[1]-a[1])*t) + ',' + Math.round(a[2]+(b[2]-a[2])*t) + ')';
}

/* ── мир ──────────────────────────────────────────────────────────────── */
var WD = D.world, W = WD.w, H = WD.h, NC = W*H;
var biome = asI8(WD.biome);
var elev  = asI16(WD.elev);
var land  = b64bytes(WD.land);
var shade = b64bytes(WD.shade);
var river = b64bytes(WD.river);
var soil  = b64bytes(WD.soil);

var biomeRGB = {}, biomeName = {};
for (var k in D.biomeColors) biomeRGB[k] = hex2rgb(D.biomeColors[k]);
for (var k2 in D.biomeNames) biomeName[k2] = D.biomeNames[k2];

var FR = D.frames, NF = FR.length;
var TL = D.timeline, EV = D.events;
var cmCache = new Array(NF);
function cmOf(i){
  if (!cmCache[i]) cmCache[i] = asI16(FR[i].cm);
  return cmCache[i];
}
var polMapCache = new Array(NF);
function polMap(i){
  if (!polMapCache[i]){
    var m = new Map(), ps = FR[i].pol;
    for (var j=0;j<ps.length;j++) m.set(((ps[j].pid % 32000)+32000)%32000, ps[j]);
    polMapCache[i] = m;
  }
  return polMapCache[i];
}

/* ── состояние ────────────────────────────────────────────────────────── */
var S = {
  f: NF - 1,            // текущий кадр
  play: false, timer: null, speed: 1,
  L: {peoples:true, sett:true, biomes:true, relief:true, mode:false, form:false},
  selPid: null,         // подсвеченный народ (pid как в снапшоте)
  mark: null,           // {y,x} — отметка от клика по событию
  sortKey: 'pop', sortDir: -1,
  kinds: {}, minW: 2.2,
  modeFilter: '',       // уклад в таблице народов
  miles: false,         // «только вехи» в летописи
  person: null,         // выбранный человек (aid) — летопись сужена до него
  famMode: 'top',       // какие семьи в дендрограмме: top | all
  lect: null,           // язык, чей паспорт открыт
  grp: null,            // группа языков для таблицы когнатов
  era: '', pol: ''      // фильтры панели людей
};
for (var ki=0; ki<D.kindOrder.length; ki++) S.kinds[D.kindOrder[ki]] = true;

/* ── карта: базовый слой ──────────────────────────────────────────────── */
var baseCv = document.createElement('canvas');
baseCv.width = W; baseCv.height = H;
var baseCtx = baseCv.getContext('2d');
var baseImg = baseCtx.createImageData(W, H);
var terrCv = document.createElement('canvas');
terrCv.width = W; terrCv.height = H;
var terrCtx = terrCv.getContext('2d');
var terrImg = terrCtx.createImageData(W, H);

var eMin = 0, eMax = 1;
(function(){
  var mn = 1e9, mx = -1e9;
  for (var i=0;i<NC;i++){ if (land[i]){ var v = elev[i]; if (v<mn) mn=v; if (v>mx) mx=v; } }
  eMin = mn; eMax = Math.max(mx, mn+1);
})();

function reliefRGB(v){
  var t = (v - eMin) / (eMax - eMin);
  t = t < 0 ? 0 : (t > 1 ? 1 : t);
  // гипсометрическая шкала: тёмно-зелёное низменное -> охра -> серо-белые вершины
  var stops = [[0,[46,66,54]],[0.35,[96,104,66]],[0.62,[140,124,84]],
               [0.84,[150,142,132]],[1,[226,230,234]]];
  for (var i=1;i<stops.length;i++){
    if (t <= stops[i][0]){
      var a = stops[i-1], b = stops[i];
      var u = (t - a[0]) / (b[0] - a[0] + 1e-9);
      return [a[1][0]+(b[1][0]-a[1][0])*u, a[1][1]+(b[1][1]-a[1][1])*u,
              a[1][2]+(b[1][2]-a[1][2])*u];
    }
  }
  return stops[stops.length-1][1];
}

function buildBase(){
  var d = baseImg.data;
  for (var i=0;i<NC;i++){
    var r, g, b;
    if (!land[i]){
      var bi = biome[i], oc = biomeRGB['' + bi] || [27,58,92];
      r = oc[0]; g = oc[1]; b = oc[2];
      // лёгкая глубинная градация океана
      var dep = (elev[i] + 6000) / 6000;
      dep = dep < 0 ? 0 : (dep > 1 ? 1 : dep);
      var kk = 0.72 + 0.34 * dep;
      r *= kk; g *= kk; b *= kk;
    } else if (S.L.biomes){
      var c = biomeRGB['' + biome[i]] || [110,110,110];
      r = c[0]; g = c[1]; b = c[2];
    } else if (S.L.relief){
      var rc = reliefRGB(elev[i]);
      r = rc[0]; g = rc[1]; b = rc[2];
    } else {
      r = 74; g = 82; b = 88;
    }
    if (S.L.relief && land[i]){
      var f = shade[i] / 128;
      // смягчаем, чтобы биомы оставались узнаваемыми
      f = 1 + (f - 1) * (S.L.biomes ? 0.62 : 0.9);
      r *= f; g *= f; b *= f;
      if (river[i] > 140){ r = r*0.72 + 42*0.28; g = g*0.72 + 92*0.28; b = b*0.72 + 128*0.28; }
    }
    var o = i*4;
    d[o]   = r < 0 ? 0 : (r > 255 ? 255 : r);
    d[o+1] = g < 0 ? 0 : (g > 255 ? 255 : g);
    d[o+2] = b < 0 ? 0 : (b > 255 ? 255 : b);
    d[o+3] = 255;
  }
  baseCtx.putImageData(baseImg, 0, 0);
}

/* Симулятор перечисляет в снапшоте только 200 крупнейших народов, а карта
   культур покрывает все. Мелкие народы, которых нет в списке, красим
   нейтральным цветом — иначе половина обжитой земли выглядела бы пустой. */
var MINOR_RGB = [116, 129, 141];

/* заливка территорий текущего кадра */
function buildTerr(f){
  var d = terrImg.data, cm = cmOf(f), pm = polMap(f);
  var byMode = S.L.mode, byForm = !byMode && S.L.form;
  var showT = S.L.peoples || byMode || byForm;
  var colCache = new Map();
  for (var i=0;i<NC;i++){
    var o = i*4;
    d[o+3] = 0;
    if (!showT) continue;
    var pid = cm[i];
    if (pid < 0) continue;
    var p = pm.get(((pid % 32000)+32000)%32000);
    var c, a;
    if (!p){
      c = MINOR_RGB;
      a = (S.selPid !== null) ? 46 : 84;
    } else {
      var key = byMode ? ('m'+p.mode) : (byForm ? ('f'+p.form) : ('p'+pid));
      c = colCache.get(key);
      if (!c){
        var hexc = byMode ? (D.modeColors[p.mode] || '#888')
                 : (byForm ? (D.formColors[p.form] || '#888') : (p.color || '#888'));
        c = hex2rgb(hexc);
        colCache.set(key, c);
      }
      a = 128;
      if (S.selPid !== null && p.pid === S.selPid) a = 208;
      else if (S.selPid !== null) a = 74;
    }
    d[o] = c[0]; d[o+1] = c[1]; d[o+2] = c[2]; d[o+3] = a;
  }
  terrCtx.putImageData(terrImg, 0, 0);
}

/* сколько всего народов на карте кадра (включая не попавших в список) */
var onMapCache = new Array(NF);
function onMapCount(f){
  if (onMapCache[f] === undefined){
    var cm = cmOf(f), seen = new Set();
    for (var i=0;i<NC;i++){ var v = cm[i]; if (v >= 0) seen.add(v); }
    onMapCache[f] = seen.size;
  }
  return onMapCache[f];
}

/* ── карта: отрисовка ─────────────────────────────────────────────────── */
var cv = el('map'), ctx = cv.getContext('2d');
var CELL = 6, DPR = Math.min(window.devicePixelRatio || 1, 2);

function fitMap(){
  var box = el('mapbox');
  var avail = box.clientWidth || 900;
  CELL = Math.max(2, avail / W);
  var cssW = Math.round(CELL * W), cssH = Math.round(CELL * H);
  cv.style.width = cssW + 'px';
  cv.style.height = cssH + 'px';
  cv.width = Math.round(cssW * DPR);
  cv.height = Math.round(cssH * DPR);
}

function drawMap(){
  var f = S.f, fr = FR[f];
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  var cw = cv.width / DPR, chh = cv.height / DPR;
  ctx.clearRect(0, 0, cw, chh);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(baseCv, 0, 0, cw, chh);
  buildTerr(f);
  ctx.drawImage(terrCv, 0, 0, cw, chh);
  ctx.imageSmoothingEnabled = true;

  var sx = cw / W, sy = chh / H;
  var cm = cmOf(f), pm = polMap(f);

  /* границы владений */
  if (S.L.peoples || S.L.mode || S.L.form){
    ctx.lineWidth = Math.max(0.6, sx * 0.16);
    ctx.strokeStyle = 'rgba(10,15,20,.72)';
    ctx.beginPath();
    for (var y=0;y<H;y++){
      for (var x=0;x<W;x++){
        var i = y*W + x, a = cm[i];
        if (x+1 < W){
          var b = cm[i+1];
          if (a !== b){ ctx.moveTo((x+1)*sx, y*sy); ctx.lineTo((x+1)*sx, (y+1)*sy); }
        }
        if (y+1 < H){
          var c2 = cm[i+W];
          if (a !== c2){ ctx.moveTo(x*sx, (y+1)*sy); ctx.lineTo((x+1)*sx, (y+1)*sy); }
        }
      }
    }
    ctx.stroke();
  }

  /* контур выбранного народа */
  if (S.selPid !== null){
    var sel = ((S.selPid % 32000)+32000)%32000;
    ctx.lineWidth = Math.max(1.4, sx * 0.34);
    ctx.strokeStyle = '#f0e0b0';
    ctx.beginPath();
    for (var y2=0;y2<H;y2++){
      for (var x2=0;x2<W;x2++){
        var j = y2*W + x2;
        if (cm[j] !== sel) continue;
        if (x2 === 0 || cm[j-1] !== sel){ ctx.moveTo(x2*sx, y2*sy); ctx.lineTo(x2*sx, (y2+1)*sy); }
        if (x2 === W-1 || cm[j+1] !== sel){ ctx.moveTo((x2+1)*sx, y2*sy); ctx.lineTo((x2+1)*sx, (y2+1)*sy); }
        if (y2 === 0 || cm[j-W] !== sel){ ctx.moveTo(x2*sx, y2*sy); ctx.lineTo((x2+1)*sx, y2*sy); }
        if (y2 === H-1 || cm[j+W] !== sel){ ctx.moveTo(x2*sx, (y2+1)*sy); ctx.lineTo((x2+1)*sx, (y2+1)*sy); }
      }
    }
    ctx.stroke();
  }

  /* поселения */
  if (S.L.sett){
    var st = fr.set.slice().sort(function(a,b){ return a.p - b.p; });
    for (var s=0;s<st.length;s++){
      var c = st[s];
      var r = 1.4 + 2.1 * Math.log10(1 + c.p / 250);
      r = Math.max(1.6, Math.min(13, r * Math.max(0.55, sx/6)));
      var px = (c.x + 0.5) * sx, py = (c.y + 0.5) * sy;
      ctx.beginPath(); ctx.arc(px, py, r, 0, 6.2832);
      ctx.fillStyle = c.p > 12000 ? 'rgba(240,222,180,.94)'
                    : (c.p > 3000 ? 'rgba(226,196,140,.9)' : 'rgba(206,178,130,.82)');
      ctx.fill();
      ctx.lineWidth = Math.max(0.5, r * 0.22);
      ctx.strokeStyle = 'rgba(24,16,10,.85)';
      ctx.stroke();
      if (c.w > 0){
        ctx.beginPath(); ctx.arc(px, py, r + Math.max(1.2, r*0.42), 0, 6.2832);
        ctx.lineWidth = Math.max(0.6, r * 0.2);
        ctx.strokeStyle = 'rgba(235,205,150,.75)';
        ctx.stroke();
      }
    }
    /* подписи крупнейших */
    var big = fr.set.slice().sort(function(a,b){ return b.p - a.p; }).slice(0, 16);
    var boxes = [];
    ctx.font = '600 11px "Segoe UI",Arial,sans-serif';
    ctx.textBaseline = 'middle';
    for (var t=0;t<big.length;t++){
      var g = big[t];
      if (g.p < 900) break;
      var gx = (g.x + 0.5) * sx, gy = (g.y + 0.5) * sy;
      var tw = ctx.measureText(g.n).width;
      var bx = gx + 7, by = gy;
      if (bx + tw > cw - 4) bx = gx - 7 - tw;
      var bb = [bx-2, by-7, tw+4, 14], hit = false;
      for (var q=0;q<boxes.length;q++){
        var o2 = boxes[q];
        if (bb[0] < o2[0]+o2[2] && bb[0]+bb[2] > o2[0] && bb[1] < o2[1]+o2[3] && bb[1]+bb[3] > o2[1]){ hit = true; break; }
      }
      if (hit) continue;
      boxes.push(bb);
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(8,12,16,.82)';
      ctx.strokeText(g.n, bx, by);
      ctx.fillStyle = '#f2e8d6';
      ctx.fillText(g.n, bx, by);
    }
  }

  /* отметка от летописи */
  if (S.mark){
    var mx = (S.mark.x + 0.5) * sx, my = (S.mark.y + 0.5) * sy;
    ctx.strokeStyle = '#e8b45c'; ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.arc(mx, my, Math.max(7, sx*1.7), 0, 6.2832); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(mx - sx*3.2, my); ctx.lineTo(mx - sx*1.1, my);
    ctx.moveTo(mx + sx*1.1, my); ctx.lineTo(mx + sx*3.2, my);
    ctx.moveTo(mx, my - sy*3.2); ctx.lineTo(mx, my - sy*1.1);
    ctx.moveTo(mx, my + sy*1.1); ctx.lineTo(mx, my + sy*3.2);
    ctx.stroke();
  }
}

/* ── подсказка при наведении ──────────────────────────────────────────── */
var tip = el('tip');
cv.addEventListener('mousemove', function(e){
  var r = cv.getBoundingClientRect();
  var x = Math.floor((e.clientX - r.left) / r.width * W);
  var y = Math.floor((e.clientY - r.top) / r.height * H);
  if (x < 0 || y < 0 || x >= W || y >= H){ tip.style.display = 'none'; return; }
  var i = y*W + x, cm = cmOf(S.f), pm = polMap(S.f);
  var h = '<div class="th">' + esc(biomeName['' + biome[i]] || '—') + '</div>';
  h += '<div class="tr">высота <b>' + elev[i] + ' м</b>';
  if (land[i]) h += ' · почва <b>' + (soil[i]/255).toFixed(2) + '</b>';
  h += '</div>';
  var pid = cm[i];
  if (pid >= 0){
    var p = pm.get(((pid % 32000)+32000)%32000);
    if (p){
      h += '<div class="th" style="margin-top:5px">' + esc(p.name) + '</div>';
      h += '<div class="tr">людей <b>' + nfmt(p.pop) + '</b></div>';
      h += '<div class="tr">' + esc(D.modeRu[p.mode] || p.mode) + ' · ' +
           esc(D.formRu[p.form] || p.form) + '</div>';
      h += '<div class="tr">знаний <b>' + p.tech + '</b> · ' + esc(p.era) + '</div>';
    } else {
      h += '<div class="th" style="margin-top:5px">мелкий народ</div>';
      h += '<div class="tr">не входит в список крупнейших,<br>подробностей нет</div>';
    }
  } else if (land[i]) {
    h += '<div class="tr">ничья земля</div>';
  }
  var st = FR[S.f].set, near = null;
  for (var s=0;s<st.length;s++){ if (st[s].y === y && st[s].x === x){ near = st[s]; break; } }
  if (near){
    h += '<div class="tr" style="margin-top:4px">' + esc(near.t || 'поселение') +
         ' <b>' + esc(near.n) + '</b>, ' + nfmt(near.p) +
         (near.w > 0 ? ', со стенами' : '') +
         (near.m > 0 ? ', памятников: ' + near.m : '') + '</div>';
  }
  tip.innerHTML = h;
  tip.style.display = 'block';
  var bw = tip.offsetWidth, bh = tip.offsetHeight;
  var lx = e.clientX - r.left + 14, ly = e.clientY - r.top + 14;
  if (lx + bw > r.width) lx = e.clientX - r.left - bw - 12;
  if (ly + bh > r.height) ly = e.clientY - r.top - bh - 12;
  tip.style.left = Math.max(0, lx) + 'px';
  tip.style.top = Math.max(0, ly) + 'px';
});
cv.addEventListener('mouseleave', function(){ tip.style.display = 'none'; });
cv.addEventListener('click', function(e){
  var r = cv.getBoundingClientRect();
  var x = Math.floor((e.clientX - r.left) / r.width * W);
  var y = Math.floor((e.clientY - r.top) / r.height * H);
  if (x < 0 || y < 0 || x >= W || y >= H) return;
  var pid = cmOf(S.f)[y*W + x];
  if (pid < 0){ S.selPid = null; }
  else {
    var p = polMap(S.f).get(((pid % 32000)+32000)%32000);
    S.selPid = (p && p.pid !== S.selPid) ? p.pid : null;
  }
  S.mark = null;
  renderPeoples(); drawMap();
});

/* ── панель народов ───────────────────────────────────────────────────── */
var COLS = [
  {k:'name', t:'народ',     n:0},
  {k:'pop',  t:'людей',     n:1},
  {k:'mode', t:'хозяйство', n:0},
  {k:'form', t:'форма',     n:0},
  {k:'era',  t:'эпоха',     n:0},
  {k:'cells',t:'кл.',       n:1},
  {k:'tech', t:'зн.',       n:1},
  {k:'cx',   t:'слож.',     n:1},
  {k:'iq',   t:'нер.',      n:1}
];
/* фильтр по укладу над таблицей народов */
(function(){
  var sel = el('modesel');
  for (var i=0;i<D.modeOrder.length;i++){
    var m = D.modeOrder[i];
    var o = document.createElement('option');
    o.value = m; o.textContent = D.modeRu[m] || m;
    sel.appendChild(o);
  }
  sel.addEventListener('change', function(){
    S.modeFilter = this.value;
    renderPeoples();
  });
})();
(function(){
  var tr = el('phead');
  for (var i=0;i<COLS.length;i++){
    var th = document.createElement('th');
    th.textContent = COLS[i].t;
    th.dataset.k = COLS[i].k;
    th.addEventListener('click', function(){
      var k = this.dataset.k;
      if (S.sortKey === k) S.sortDir = -S.sortDir;
      else { S.sortKey = k; S.sortDir = (k === 'name' || k === 'mode' || k === 'form') ? 1 : -1; }
      renderPeoples();
    });
    tr.appendChild(th);
  }
})();

function renderPeoples(){
  var ps = FR[S.f].pol.slice();
  var nAll = ps.length;
  if (S.modeFilter){
    ps = ps.filter(function(p){ return p.mode === S.modeFilter; });
  }
  var k = S.sortKey, dir = S.sortDir;
  ps.sort(function(a,b){
    var va = a[k], vb = b[k];
    if (k === 'mode'){ va = D.modeShort[a.mode] || a.mode; vb = D.modeShort[b.mode] || b.mode; }
    if (k === 'form'){ va = D.formShort[a.form] || a.form; vb = D.formShort[b.form] || b.form; }
    if (k === 'era'){ va = D.eraOrder.indexOf(a.era); vb = D.eraOrder.indexOf(b.era); }
    if (typeof va === 'string') return dir * va.localeCompare(vb, 'ru');
    return dir * ((va || 0) - (vb || 0));
  });
  var ths = el('phead').children;
  for (var i=0;i<ths.length;i++)
    ths[i].className = (ths[i].dataset.k === k) ? 'sorted' : '';
  var h = [];
  for (var j=0;j<ps.length;j++){
    var p = ps[j];
    h.push('<tr data-pid="' + p.pid + '"' + (p.pid === S.selPid ? ' class="sel"' : '') + '>' +
      '<td class="nm"><span class="dot" style="background:' + esc(p.color) + '"></span>' + esc(p.name) + '</td>' +
      '<td>' + nfmt(p.pop) + '</td>' +
      '<td title="' + esc(D.modeRu[p.mode] || p.mode) + '">' +
        esc(D.modeShort[p.mode] || p.mode) + '</td>' +
      '<td title="' + esc(D.formRu[p.form] || p.form) + '">' +
        esc(D.formShort[p.form] || p.form) + '</td>' +
      '<td title="' + esc(p.era) + '" style="color:' +
        (D.eraColors[p.era] ? shiftEra(p.era) : 'var(--ink2)') + '">' +
        esc(D.eraShort[p.era] || p.era) + '</td>' +
      '<td>' + p.cells + '</td><td>' + p.tech + '</td>' +
      '<td>' + p.cx.toFixed(2) + '</td><td>' + p.iq.toFixed(2) + '</td></tr>');
  }
  var tb = el('pbody');
  tb.innerHTML = h.join('');
  var total = onMapCount(S.f);
  el('pcount').textContent = ps.length
    ? (S.modeFilter ? ('по укладу: ' + ps.length + ' из ' + nAll)
       : (total > nAll ? ('крупнейших ' + nAll + ' из ' + total)
                       : ('народов: ' + nAll)))
    : (S.modeFilter ? 'по укладу народов нет' : 'народов нет');
  el('pnote').innerHTML = (total > nAll)
    ? ('<i class="sw" style="background:rgb(116,129,141)"></i>прочие ' +
       (total - nAll) + ' народов — серым на карте, снимок их не описывает')
    : '';
  var rows = tb.children;
  for (var q=0;q<rows.length;q++){
    rows[q].addEventListener('click', function(){
      var pid = parseInt(this.dataset.pid, 10);
      S.selPid = (S.selPid === pid) ? null : pid;
      S.mark = null;
      renderPeoples(); drawMap();
    });
  }
}

/* ── летопись ─────────────────────────────────────────────────────────── */
(function(){
  var box = el('chips');
  for (var i=0;i<D.kindOrder.length;i++){
    var kd = D.kindOrder[i];
    var c = document.createElement('span');
    c.className = 'chip on';
    c.textContent = D.kindRu[kd] || kd;
    c.dataset.k = kd;
    c.style.background = D.kindColors[kd] || '#888';
    c.style.color = '#0d141a';
    box.appendChild(c);
    c.addEventListener('click', function(){
      var kk = this.dataset.k;
      S.kinds[kk] = !S.kinds[kk];
      if (S.kinds[kk]){
        this.className = 'chip on';
        this.style.background = D.kindColors[kk] || '#888';
        this.style.color = '#0d141a';
      } else {
        this.className = 'chip';
        this.style.background = '';
        this.style.color = '';
      }
      renderFeed();
    });
  }
})();

function renderFeed(){
  var yr = FR[S.f].year;
  var span = NF > 1 ? Math.abs(FR[Math.min(NF-1, S.f+1)].year - yr) || 100 : 100;
  var lo = yr - span * 2.2, hi = yr + span * 2.2;
  var h = [], shown = 0, firstNear = -1;
  var pf = el('pfilter');
  if (S.person !== null){
    var pr = PMAP[S.person];
    pf.style.display = '';
    pf.innerHTML = 'только события человека: <b>' + esc(pr ? pr.nm : S.person) +
      '</b> · <span class="chip" id="pfoff" style="color:var(--acc)">показать всю летопись</span>';
    el('pfoff').addEventListener('click', function(){
      S.person = null; renderFeed(); renderPersons();
    });
  } else {
    pf.style.display = 'none'; pf.innerHTML = '';
  }
  for (var i=0;i<EV.length;i++){
    var e = EV[i];
    if (S.person !== null){
      if (e.pe !== S.person) continue;
    } else {
      if (!S.kinds[e.k]) continue;
      if (e.w < (S.miles ? Math.max(S.minW, 3.2) : S.minW)) continue;
    }
    var near = (e.yr >= lo && e.yr <= hi);
    var geo = (e.cy !== null && e.cx !== null);
    if (near && firstNear < 0) firstNear = shown;
    shown++;
    h.push('<div class="ev' + (near ? ' near' : '') + (geo ? ' geo' : '') +
      '" data-i="' + i + '" style="border-left-color:' + (D.kindColors[e.k] || '#2a3844') + '">' +
      '<div><span class="y">' + ruYear(e.yr) + '</span>' +
      '<span class="k" style="color:' + (D.kindColors[e.k] || '#888') + '">' +
      esc(D.kindRu[e.k] || e.k) + '</span></div>' +
      '<div class="t">' + esc(e.t) + '</div></div>');
  }
  var feed = el('feed');
  feed.innerHTML = h.join('') || '<div class="ev"><div class="t">Событий по фильтру нет.</div></div>';
  el('evcount').textContent = 'событий: ' + shown;
  var rows = feed.getElementsByClassName('ev');
  for (var q=0;q<rows.length;q++){
    if (!rows[q].dataset.i) continue;
    rows[q].addEventListener('click', function(){
      var e2 = EV[parseInt(this.dataset.i, 10)];
      if (e2.cy === null || e2.cx === null) return;
      S.mark = {y:e2.cy, x:e2.cx};
      var best = 0, bd = 1e18;
      for (var z=0;z<NF;z++){
        var dd = Math.abs(FR[z].year - e2.yr);
        if (dd < bd){ bd = dd; best = z; }
      }
      S.selPid = null;
      setFrame(best, true);
    });
  }
  if (firstNear >= 0 && rows[firstNear]){
    var t = rows[firstNear];
    feed.scrollTop = Math.max(0, t.offsetTop - feed.clientHeight * 0.34);
  }
}

el('wslider').addEventListener('input', function(){
  S.minW = parseFloat(this.value);
  el('wlab').textContent = S.minW.toFixed(1);
  S.miles = false;
  el('milestones').className = 'btn';
  renderFeed();
});
el('milestones').addEventListener('click', function(){
  S.miles = !S.miles;
  this.className = S.miles ? 'btn on' : 'btn';
  renderFeed();
});

/* ── графики ──────────────────────────────────────────────────────────── */
var YRS = TL.map(function(t){ return t.year; });
var PAD = {l:52, r:9, t:10, b:22};

function prep(cvs){
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var w = cvs.clientWidth || 360, h = cvs.clientHeight || 186;
  cvs.width = Math.round(w * dpr); cvs.height = Math.round(h * dpr);
  var c = cvs.getContext('2d');
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  return {c:c, w:w, h:h, iw:w - PAD.l - PAD.r, ih:h - PAD.t - PAD.b};
}

function axes(g, xmin, xmax, ymin, ymax, log, yfmt){
  var c = g.c;
  c.font = '10px "Segoe UI",Arial,sans-serif';
  c.strokeStyle = '#1e2a35'; c.lineWidth = 1;
  c.fillStyle = '#5f7183';
  var i;
  /* горизонтальная сетка */
  var ticks = [];
  if (log){
    var l0 = Math.floor(Math.log10(Math.max(1, ymin))), l1 = Math.ceil(Math.log10(Math.max(10, ymax)));
    for (i=l0;i<=l1;i++) ticks.push(Math.pow(10, i));
  } else {
    for (i=0;i<=4;i++) ticks.push(ymin + (ymax-ymin) * i/4);
  }
  c.textAlign = 'right'; c.textBaseline = 'middle';
  for (i=0;i<ticks.length;i++){
    var v = ticks[i];
    /* доля БЕЗ обрезки: засечку вне диапазона рисовать нельзя, иначе
       она прилипнет к краю и соврёт о масштабе */
    var t0 = yraw(v, ymin, ymax, log);
    if (t0 < -0.002 || t0 > 1.002) continue;
    var yy = PAD.t + g.ih - g.ih * t0;
    c.beginPath(); c.moveTo(PAD.l, yy); c.lineTo(PAD.l + g.iw, yy); c.stroke();
    c.fillText(yfmt ? yfmt(v) : nfmt(v), PAD.l - 6, yy);
  }
  /* вертикальные подписи — годы; крайние прижаты к краям, чтобы не срезались */
  c.textBaseline = 'top';
  var n = Math.max(2, Math.min(6, Math.floor(g.iw / 74)));
  for (i=0;i<=n;i++){
    var yv = xmin + (xmax - xmin) * i/n;
    var xx = PAD.l + g.iw * i/n;
    c.strokeStyle = '#182430';
    c.beginPath(); c.moveTo(xx, PAD.t); c.lineTo(xx, PAD.t + g.ih); c.stroke();
    c.fillStyle = '#5f7183';
    c.textAlign = (i === 0) ? 'left' : (i === n ? 'right' : 'center');
    c.fillText(axYear(Math.round(yv)), xx, PAD.t + g.ih + 5);
  }
  c.strokeStyle = '#2a3946';
  c.beginPath();
  c.moveTo(PAD.l, PAD.t); c.lineTo(PAD.l, PAD.t + g.ih); c.lineTo(PAD.l + g.iw, PAD.t + g.ih);
  c.stroke();
}

/* доля высоты без обрезки — нужна, чтобы отбрасывать засечки вне поля */
function yraw(v, ymin, ymax, log){
  if (log){
    var a = Math.log10(Math.max(1, ymin)), b = Math.log10(Math.max(10, ymax));
    return (Math.log10(Math.max(1, v)) - a) / (b - a + 1e-9);
  }
  return (v - ymin) / (ymax - ymin + 1e-9);
}
function yscale(v, ymin, ymax, log){
  var t = yraw(v, ymin, ymax, log);
  return t < 0 ? 0 : (t > 1 ? 1 : t);
}

function marker(g, xmin, xmax){
  var yr = FR[S.f].year;
  var t = (yr - xmin) / (xmax - xmin + 1e-9);
  if (t < 0 || t > 1) return;
  var x = PAD.l + g.iw * t;
  g.c.strokeStyle = 'rgba(200,169,110,.75)'; g.c.lineWidth = 1;
  g.c.beginPath(); g.c.moveTo(x, PAD.t); g.c.lineTo(x, PAD.t + g.ih); g.c.stroke();
}

function lineChart(id, series, log, yfmt){
  var cvs = el(id); if (!cvs) return;
  var g = prep(cvs);
  if (!YRS.length) return;
  var xmin = YRS[0], xmax = YRS[YRS.length-1];
  var ymin = log ? 1 : 0, ymax = 1;
  for (var s=0;s<series.length;s++)
    for (var i=0;i<series[s].v.length;i++)
      if (series[s].v[i] > ymax) ymax = series[s].v[i];
  ymax *= 1.08;
  axes(g, xmin, xmax, ymin, ymax, log, yfmt);
  for (var s2=0;s2<series.length;s2++){
    var sr = series[s2];
    g.c.strokeStyle = sr.c; g.c.lineWidth = 1.6;
    g.c.beginPath();
    var started = false;
    for (var i2=0;i2<YRS.length;i2++){
      var x = PAD.l + g.iw * (YRS[i2]-xmin)/(xmax-xmin+1e-9);
      var y = PAD.t + g.ih - g.ih * yscale(sr.v[i2], ymin, ymax, log);
      if (!started){ g.c.moveTo(x, y); started = true; } else g.c.lineTo(x, y);
    }
    g.c.stroke();
  }
  marker(g, xmin, xmax);
}

function areaChart(id, keys, colors, names, rows){
  var cvs = el(id); if (!cvs) return;
  var g = prep(cvs);
  if (!YRS.length) return;
  var xmin = YRS[0], xmax = YRS[YRS.length-1];
  axes(g, xmin, xmax, 0, 1, false, function(v){ return Math.round(v*100) + '%'; });
  var acc = new Array(YRS.length);
  for (var i=0;i<acc.length;i++) acc[i] = 0;
  for (var k=0;k<keys.length;k++){
    var key = keys[k];
    g.c.fillStyle = colors[key] || '#666';
    g.c.beginPath();
    var pts = [];
    for (var i2=0;i2<YRS.length;i2++){
      var row = rows[i2] || {}, tot = 0;
      for (var q=0;q<keys.length;q++) tot += (row[keys[q]] || 0);
      var share = tot > 0 ? (row[key] || 0) / tot : 0;
      pts.push([acc[i2], acc[i2] + share]);
      acc[i2] += share;
    }
    for (var a=0;a<YRS.length;a++){
      var x = PAD.l + g.iw * (YRS[a]-xmin)/(xmax-xmin+1e-9);
      var y = PAD.t + g.ih - g.ih * pts[a][1];
      if (a === 0) g.c.moveTo(x, y); else g.c.lineTo(x, y);
    }
    for (var b=YRS.length-1;b>=0;b--){
      var x2 = PAD.l + g.iw * (YRS[b]-xmin)/(xmax-xmin+1e-9);
      var y2 = PAD.t + g.ih - g.ih * pts[b][0];
      g.c.lineTo(x2, y2);
    }
    g.c.closePath(); g.c.fill();
  }
  marker(g, xmin, xmax);
}

function barChart(id, series){
  var cvs = el(id); if (!cvs) return;
  var g = prep(cvs);
  if (!YRS.length) return;
  var xmin = YRS[0], xmax = YRS[YRS.length-1];
  var ymax = 1;
  for (var s=0;s<series.length;s++)
    for (var i=0;i<series[s].v.length;i++)
      if (series[s].v[i] > ymax) ymax = series[s].v[i];
  ymax *= 1.1;
  axes(g, xmin, xmax, 0, ymax, false, function(v){ return nfmt(v); });
  var n = YRS.length, slot = g.iw / Math.max(1, n);
  var bw = Math.max(0.7, (slot - 1) / series.length);
  for (var s2=0;s2<series.length;s2++){
    g.c.fillStyle = series[s2].c;
    for (var i2=0;i2<n;i2++){
      var v = series[s2].v[i2] || 0;
      if (v <= 0) continue;
      var hh = g.ih * (v / ymax);
      var x = PAD.l + g.iw * (YRS[i2]-xmin)/(xmax-xmin+1e-9) - slot/2 + s2*bw;
      g.c.fillRect(x, PAD.t + g.ih - hh, bw, hh);
    }
  }
  marker(g, xmin, xmax);
}

function legend(id, items){
  var b = el(id); if (!b) return;
  var h = [];
  for (var i=0;i<items.length;i++)
    h.push('<span><i class="sw" style="background:' + items[i][1] + '"></i>' + esc(items[i][0]) + '</span>');
  b.innerHTML = h.join('');
}

function col(name){ return TL.map(function(t){ return +(t[name] || 0); }); }
function diffcol(name){
  var v = col(name), out = [];
  for (var i=0;i<v.length;i++) out.push(i === 0 ? v[0] : Math.max(0, v[i] - v[i-1]));
  return out;
}

function drawCharts(){
  lineChart('c_pop', [{v:col('pop'), c:'#7fb3d5'}], true, nfmt);
  lineChart('c_pol', [{v:col('polities'), c:'#c8a96e'}], false, function(v){ return Math.round(v); });
  lineChart('c_tech', [{v:col('tech_max'), c:'#d4b45c'}, {v:col('tech_mean'), c:'#5f9e8f'}],
            false, function(v){ return Math.round(v); });
  areaChart('c_mode', D.modeOrder, D.modeColors, D.modeRu, TL.map(function(t){ return t.modes || {}; }));
  areaChart('c_form', D.formOrder, D.formColors, D.formRu, TL.map(function(t){ return t.forms || {}; }));
  barChart('c_ev', [
    {v:diffcol('n_discoveries'), c:'#d4b45c'},
    {v:diffcol('n_losses'), c:'#a86a6a'},
    {v:diffcol('n_wars'), c:'#c4544a'},
    {v:diffcol('n_epidemics'), c:'#8fae4a'}
  ]);
}

/* ── полоса эпох ──────────────────────────────────────────────────────── */
function drawEra(){
  var cvs = el('era');
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var w = cvs.clientWidth || 800, h = cvs.clientHeight || 46;
  cvs.width = Math.round(w*dpr); cvs.height = Math.round(h*dpr);
  var c = cvs.getContext('2d');
  c.setTransform(dpr,0,0,dpr,0,0);
  c.clearRect(0,0,w,h);
  if (!TL.length) return;
  var xmin = YRS[0], xmax = YRS[YRS.length-1], sp = (xmax-xmin) || 1;
  var runs = [], cur = null;
  for (var i=0;i<TL.length;i++){
    var e = TL[i].era || '—';
    if (!cur || cur.e !== e){ cur = {e:e, a:YRS[i], b:YRS[i]}; runs.push(cur); }
    else cur.b = YRS[i];
  }
  for (var r=0;r<runs.length;r++){
    var rn = runs[r];
    var b = (r+1 < runs.length) ? runs[r+1].a : xmax;
    var x0 = (rn.a - xmin)/sp * w, x1 = (b - xmin)/sp * w;
    c.fillStyle = D.eraColors[rn.e] || '#3a4652';
    c.fillRect(x0, 0, Math.max(1, x1-x0), 24);
    var wdt = x1 - x0;
    if (wdt > 52){
      c.font = '600 10px "Segoe UI",Arial,sans-serif';
      c.fillStyle = 'rgba(255,255,255,.92)';
      c.textAlign = 'center'; c.textBaseline = 'middle';
      c.fillText(rn.e, (x0+x1)/2, 12);
    }
    if (r > 0){
      c.strokeStyle = '#2a3946'; c.lineWidth = 1;
      c.beginPath(); c.moveTo(x0, 0); c.lineTo(x0, 24); c.stroke();
    }
  }
  /* подписи годов: сперва крайние, затем границы эпох — но только те,
     что не налезают на уже написанное (иначе на коротких эпохах каша) */
  c.font = '10px "Segoe UI",Arial,sans-serif';
  c.textBaseline = 'top'; c.fillStyle = '#5f7183';
  c.textAlign = 'left';
  c.fillText(axYear(xmin), 1, 27);
  var lastRight = 1 + c.measureText(axYear(xmin)).width + 7;
  c.textAlign = 'right';
  c.fillText(axYear(xmax), w - 1, 27);
  var rightStart = w - 1 - c.measureText(axYear(xmax)).width - 7;
  c.textAlign = 'left'; c.fillStyle = '#7d8ea0';
  for (var r3=1;r3<runs.length;r3++){
    var xb = (runs[r3].a - xmin)/sp * w;
    var lab = axYear(runs[r3].a), lw = c.measureText(lab).width;
    if (xb + 2 < lastRight || xb + 2 + lw > rightStart) continue;
    c.fillText(lab, xb + 2, 27);
    lastRight = xb + 2 + lw + 7;
  }
  /* курсор текущего года */
  var t = (FR[S.f].year - xmin)/sp;
  t = t < 0 ? 0 : (t > 1 ? 1 : t);
  c.strokeStyle = '#e8d3a0'; c.lineWidth = 1.6;
  c.beginPath(); c.moveTo(t*w, 0); c.lineTo(t*w, 24); c.stroke();
}

/* ── время ────────────────────────────────────────────────────────────── */
var slider = el('slider');
slider.min = 0; slider.max = Math.max(0, NF-1); slider.value = S.f;

function setFrame(i, sync){
  S.f = Math.max(0, Math.min(NF-1, i));
  if (sync) slider.value = S.f;
  el('yearlab').textContent = ruYear(FR[S.f].year);
  drawMap(); renderPeoples(); renderFeed(); drawCharts(); drawEra();
}
slider.addEventListener('input', function(){
  S.mark = null;
  setFrame(parseInt(this.value, 10), false);
});
el('prev').addEventListener('click', function(){ stop(); setFrame(S.f-1, true); });
el('next').addEventListener('click', function(){ stop(); setFrame(S.f+1, true); });
function stop(){
  S.play = false;
  if (S.timer){ clearInterval(S.timer); S.timer = null; }
  el('play').textContent = '▶ играть';
  el('play').className = 'btn';
}
function start(){
  S.play = true;
  el('play').textContent = '❚❚ пауза';
  el('play').className = 'btn on';
  if (S.timer) clearInterval(S.timer);
  S.timer = setInterval(function(){
    if (S.f >= NF-1){ setFrame(0, true); }
    else setFrame(S.f+1, true);
  }, Math.max(40, 620 / S.speed));
}
el('play').addEventListener('click', function(){ S.play ? stop() : start(); });
el('speed').addEventListener('click', function(){
  var sp = [1, 2, 4, 8];
  S.speed = sp[(sp.indexOf(S.speed) + 1) % sp.length];
  this.textContent = '×' + S.speed;
  if (S.play) start();
});
document.addEventListener('keydown', function(e){
  if (e.key === 'ArrowLeft'){ stop(); setFrame(S.f-1, true); }
  else if (e.key === 'ArrowRight'){ stop(); setFrame(S.f+1, true); }
  else if (e.key === ' '){ e.preventDefault(); S.play ? stop() : start(); }
});

/* ── слои ─────────────────────────────────────────────────────────────── */
var LAYERS = [
  ['peoples', 'народы'], ['sett', 'поселения'], ['biomes', 'биомы'],
  ['relief', 'рельеф'], ['mode', 'способ хозяйства'], ['form', 'форма правления']
];
(function(){
  var box = el('layers');
  for (var i=0;i<LAYERS.length;i++){
    var id = LAYERS[i][0];
    var lb = document.createElement('label');
    var inp = document.createElement('input');
    inp.type = 'checkbox'; inp.checked = S.L[id]; inp.dataset.l = id;
    lb.appendChild(inp);
    lb.appendChild(document.createTextNode(LAYERS[i][1]));
    box.appendChild(lb);
    inp.addEventListener('change', function(){
      var key = this.dataset.l;
      S.L[key] = this.checked;
      /* хозяйство и форма — взаимоисключающие заливки */
      if (this.checked && (key === 'mode' || key === 'form')){
        var other = key === 'mode' ? 'form' : 'mode';
        S.L[other] = false;
        var ins = box.getElementsByTagName('input');
        for (var q=0;q<ins.length;q++) if (ins[q].dataset.l === other) ins[q].checked = false;
      }
      if (key === 'biomes' || key === 'relief') buildBase();
      drawMap();
    });
  }
})();

/* ── языки и родство ──────────────────────────────────────────────────── */
var LG = D.lang || null;
var LFAM = {}, GRP = {};
var TREE = {x0:32, labW:198, rowH:16, headH:21, gap:8, top:6, split:0.62};

function cut(s, n){
  s = String(s);
  return s.length > n ? (s.slice(0, n-1) + '…') : s;
}
/* «946 — 930 до н. э.» вместо двух полных подписей */
function yrRange(a, b){
  if (a === b) return ruYear(a);
  if (a < 0 && b < 0) return (-a) + ' — ' + (-b) + ' до н. э.';
  if (a >= 0 && b >= 0) return a + ' — ' + b + ' н. э.';
  return ruYear(a) + ' — ' + ruYear(b);
}
/* шкала времени дендрограммы: окно расхождения растянуто, «наши дни» сжаты */
function mkX(w){
  var x0 = TREE.x0, xEnd = Math.max(x0 + 80, w - TREE.labW);
  var xA = x0 + (xEnd - x0) * TREE.split;
  var a = LG.y0, b = LG.y1, c = LG.yEnd;
  if (b <= a) b = a + 1;
  if (c <= b) c = b + 1;
  return {x0:x0, xA:xA, xEnd:xEnd, a:a, b:b, c:c, w:w,
    f: function(y){
      if (y <= a) return x0;
      if (y >= c) return xEnd;
      if (y <= b) return x0 + (xA - x0) * (y - a) / (b - a);
      return xA + (xEnd - xA) * (y - b) / (c - b);
    }};
}
function treeWidth(){
  var box = el('treebox');
  return Math.max(560, (box.clientWidth || 900) - 2);
}
function drawTreeAxis(){
  var w = treeWidth(), X = mkX(w), s = [];
  var span = X.b - X.a;
  var steps = [5,10,20,25,50,100,200,250,500,1000,2000,2500,5000,10000,20000];
  var st = steps[steps.length-1];
  for (var i=0;i<steps.length;i++){ if (span / steps[i] <= 7){ st = steps[i]; break; } }
  s.push('<line x1="'+X.x0+'" y1="21.5" x2="'+X.xEnd+'" y2="21.5" stroke="#27384a"/>');
  for (var y = Math.ceil(X.a/st)*st; y <= X.b + 0.5; y += st){
    var x = X.f(y);
    s.push('<line x1="'+x.toFixed(1)+'" y1="16" x2="'+x.toFixed(1)+'" y2="21.5" stroke="#33485c"/>');
    s.push('<text x="'+x.toFixed(1)+'" y="12" text-anchor="middle">'+axYear(y)+'</text>');
  }
  s.push('<line x1="'+X.xA.toFixed(1)+'" y1="2" x2="'+X.xA.toFixed(1)+
         '" y2="21.5" stroke="#3b5568" stroke-dasharray="2 3"/>');
  s.push('<text x="'+((X.xA + X.xEnd)/2).toFixed(1)+'" y="12" text-anchor="middle">'+
         'время сжато → ' + axYear(X.c) + '</text>');
  s.push('<text x="'+(X.xEnd + 7)+'" y="12">живые языки</text>');
  el('treeaxisbox').innerHTML = '<svg width="'+w+'" height="26" viewBox="0 0 '+w+' 26">'
    + s.join('') + '</svg>';
}
function renderTree(){
  if (!LG) return;
  var w = treeWidth(), X = mkX(w);
  var fams = [];
  if (S.famMode === 'top'){
    for (var t=0;t<LG.top.length;t++) if (LFAM[LG.top[t]]) fams.push(LFAM[LG.top[t]]);
  } else fams = LG.fams;
  var y = TREE.top, body = [], hits = [], nl = 0;
  for (var i=0;i<fams.length;i++){
    var F = fams[i];
    var blockH = TREE.headH + F.rows * TREE.rowH + 3;
    body.push('<rect x="0" y="'+y+'" width="'+w+'" height="'+blockH+'" fill="'+
              (i % 2 ? '#101821' : '#131d27')+'"/>');
    body.push('<rect x="0" y="'+y+'" width="3" height="'+blockH+'" fill="'+F.col+'"/>');
    body.push('<text class="fam" x="11" y="'+(y+14)+'" fill="'+F.col+'">'+
              esc(cut(F.nm, 30))+'</text>');
    body.push('<text class="dim" x="'+(w-6)+'" y="'+(y+14)+'" text-anchor="end">'+
              F.n+' яз. · '+nfmt(F.pop)+' чел.</text>');
    var base = y + TREE.headH;
    for (var j=0;j<F.nodes.length;j++){
      var n = F.nodes[j];
      var ny = base + n.y * TREE.rowH + TREE.rowH * 0.5;
      var x1 = X.f(n.b), x2 = n.al ? X.xEnd : Math.max(X.f(n.e), X.f(n.b) + 8);
      body.push('<line x1="'+x1.toFixed(1)+'" y1="'+ny.toFixed(1)+'" x2="'+x2.toFixed(1)+
        '" y2="'+ny.toFixed(1)+'" stroke="'+F.col+'" stroke-width="'+(n.al?1.7:1.2)+'"'+
        (n.al ? '' : ' stroke-dasharray="3 3" opacity=".65"')+'/>');
      if (n.p >= 0){
        var pn = F.nodes[n.p];
        var py = base + pn.y * TREE.rowH + TREE.rowH * 0.5;
        body.push('<line x1="'+x1.toFixed(1)+'" y1="'+py.toFixed(1)+'" x2="'+x1.toFixed(1)+
          '" y2="'+ny.toFixed(1)+'" stroke="'+F.col+'" stroke-width="1.1" opacity=".85"/>');
        body.push('<circle cx="'+x1.toFixed(1)+'" cy="'+py.toFixed(1)+'" r="1.9" fill="'+F.col+'"/>');
      }
      if (n.al){
        nl++;
        var selc = (S.lect === String(n.pid)) ? ' sel' : '';
        body.push('<text class="leaf" x="'+(X.xEnd+8)+'" y="'+(ny+4).toFixed(1)+'">'+
                  esc(cut(n.nm, 16))+'</text>');
        body.push('<text class="dim" x="'+(w-6)+'" y="'+(ny+4).toFixed(1)+
                  '" text-anchor="end">'+nfmt(n.pop)+'</text>');
        hits.push('<rect class="hit'+selc+'" data-pid="'+n.pid+'" x="0" y="'+
          (ny - TREE.rowH/2).toFixed(1)+'" width="'+w+'" height="'+TREE.rowH+
          '"><title>'+esc(n.nm)+' · обособился в '+ruYear(n.b)+' · '+nfmt(n.pop)+
          ' чел.</title></rect>');
      } else {
        body.push('<text class="ghost" x="'+(x1+3).toFixed(1)+'" y="'+(ny-3).toFixed(1)+
                  '">†'+esc(cut(n.nm, 14))+'</text>');
      }
    }
    y += blockH + TREE.gap;
  }
  var H2 = y + 4;
  el('treebox').innerHTML = '<svg id="tree" width="'+w+'" height="'+H2+
    '" viewBox="0 0 '+w+' '+H2+'">' + body.join('') + hits.join('') + '</svg>';
  var rs = el('treebox').getElementsByClassName('hit');
  for (var q=0;q<rs.length;q++){
    rs[q].addEventListener('click', function(){
      S.lect = this.dataset.pid;
      renderTree(); renderPassport();
    });
  }
  el('treehint').textContent = 'семей: ' + fams.length + ', языков: ' + nl;
  drawTreeAxis();
}
function renderPassport(){
  if (!LG) return;
  var box = el('lpass'), P = S.lect ? LG.pass[S.lect] : null;
  if (!P){
    box.innerHTML = '<h4>Паспорт языка</h4><div class="lps">Щёлкните по ветви ' +
      'в дереве слева — здесь появятся звуковой строй, грамматика, словарь, ' +
      'личные имена, топонимы и имена богов этого языка.</div>';
    return;
  }
  var F = LFAM[P.fam];
  var h = '<div class="lpt">' + esc(P.nm) +
    (P.ln ? ' <span style="font-size:12px;color:var(--acc2);font-weight:400">язык ' +
            esc(P.ln) + '</span>' : '') + '</div><div class="lps">семья ' +
    esc(F ? F.nm : P.fam) + ' · носителей ' + nfmt(P.pop) + ' · обособился в ' +
    ruYear(P.b) + ' · поколений от праязыка: ' + P.gen +
    (P.ethn ? (' · самоназвание ' + esc(P.ethn)) : '') + '</div>';
  h += '<pre>' + esc(P.pass) + '</pre>';
  h += '<h4>Словарь</h4><div class="wgrid">';
  for (var i=0;i<P.w.length;i++)
    h += '<div>' + esc(P.w[i][0]) + '<b>' + esc(P.w[i][1]) + '</b></div>';
  h += '</div>';
  h += '<h4>Имена людей</h4><div class="nlist">мужские: <b>' +
       P.men.map(esc).join('</b>, <b>') + '</b><br>женские: <b>' +
       P.women.map(esc).join('</b>, <b>') + '</b></div>';
  if (P.pl.length){
    h += '<h4>Топонимы</h4><div class="nlist">';
    for (var k=0;k<P.pl.length;k++)
      h += '<b>' + esc(P.pl[k][0]) + '</b> <i>(' + esc(P.pl[k][1]) + ', букв. «' +
           esc(P.pl[k][2]) + '»)</i><br>';
    h += '</div>';
  }
  if (P.gods.length){
    h += '<h4>Имена богов</h4><div class="nlist">';
    for (var g=0;g<P.gods.length;g++)
      h += '<b>' + esc(P.gods[g][0]) + '</b> <i>(' + esc(P.gods[g][1]) + ', букв. «' +
           esc(P.gods[g][2]) + '»)</i><br>';
    h += '</div>';
  }
  box.innerHTML = h;
}
function simCol(t){ return mix([120,138,153], [232,242,249], t); }
function distCol(d){
  return d < 0.5 ? mix([126,190,142], [219,196,110], d/0.5)
                 : mix([219,196,110], [200,105,90], (d-0.5)/0.5);
}
function renderCog(){
  var g = GRP[S.grp];
  if (!g){ el('cogbox').innerHTML = '<div class="empty">Нет данных.</div>'; return; }
  var L = g.langs, h = '<table class="cog"><thead><tr><th>значение</th>';
  for (var i=0;i<L.length;i++)
    h += '<th style="color:' + g.col + '" title="' + esc(L[i].nm) + ' · ' +
         nfmt(L[i].pop) + ' чел.">' + esc(cut(L[i].nm, 12)) + '</th>';
  h += '</tr></thead><tbody>';
  for (var r=0;r<g.rows.length;r++){
    h += '<tr><td>' + esc(g.rows[r][0]) + '</td>';
    for (var c=0;c<L.length;c++){
      var s = g.sim[r][c];
      h += '<td style="color:' + simCol(s) + ';background:rgba(127,179,213,' +
           (0.03 + s * 0.13).toFixed(3) + ')">' + esc(g.rows[r][c+1]) + '</td>';
    }
    h += '</tr>';
  }
  el('cogbox').innerHTML = h + '</tbody></table>';
}
function renderMat(){
  var g = GRP[S.grp];
  if (!g){ el('matbox').innerHTML = '<div class="empty">Нет данных.</div>'; return; }
  /* столбцы нумеруем: имена языков длинные и в шапке не читаются */
  var L = g.langs, h = '<table class="mx"><thead><tr><th></th>';
  for (var i=0;i<L.length;i++)
    h += '<th title="' + esc(L[i].nm) + '">' + (i+1) + '</th>';
  h += '</tr></thead><tbody>';
  for (var a=0;a<L.length;a++){
    h += '<tr><td class="lb" title="' + esc(L[a].nm) + '">' + (a+1) + '. ' +
         esc(cut(L[a].nm, 15)) + '</td>';
    for (var b=0;b<L.length;b++){
      var d = g.dist[a][b];
      h += '<td style="background:' + distCol(d) + '" title="' + esc(L[a].nm) + ' ↔ ' +
           esc(L[b].nm) + ': расхождение ' + d.toFixed(2) + ', общих когнатов ' +
           Math.round(g.cog[a][b]*100) + '%">' + d.toFixed(2) + '</td>';
    }
    h += '</tr>';
  }
  el('matbox').innerHTML = h + '</tbody></table>';
}
(function(){
  if (!LG || !LG.fams.length){
    var ls = el('langsec'); if (ls) ls.style.display = 'none';
    return;
  }
  for (var i=0;i<LG.fams.length;i++) LFAM[LG.fams[i].fid] = LG.fams[i];
  for (var j=0;j<LG.groups.length;j++) GRP[LG.groups[j].id] = LG.groups[j];
  el('langcap').innerHTML = 'Живых языков на конец прогона: <b>' + LG.nLects +
    '</b>, семей: <b>' + LG.nFams + '</b>. По горизонтали — год, когда ветвь ' +
    'обособилась; вправо ветви тянутся до конца прогона. Каждой семье — свой ' +
    'оттенок; пунктир и † — вымерший народ-посредник, восстановленный по родословной.';
  var sel = el('famsel');
  for (var k=0;k<LG.groups.length;k++){
    var o = document.createElement('option');
    o.value = LG.groups[k].id; o.textContent = LG.groups[k].label;
    sel.appendChild(o);
  }
  S.grp = LG.groups.length ? LG.groups[0].id : null;
  sel.value = S.grp || '';
  /* открываем паспорт самого многолюдного языка из первой показанной семьи —
     чтобы панель справа не встречала читателя пустотой */
  var f0 = LFAM[LG.top[0]] || LG.fams[0], bestN = null;
  if (f0) for (var m=0;m<f0.nodes.length;m++){
    var nd = f0.nodes[m];
    if (nd.al && (!bestN || nd.pop > bestN.pop)) bestN = nd;
  }
  if (bestN) S.lect = String(bestN.pid);
  sel.addEventListener('change', function(){
    S.grp = this.value; renderCog(); renderMat();
  });
  el('famtop').addEventListener('click', function(){
    S.famMode = 'top';
    this.className = 'btn on'; el('famall').className = 'btn';
    el('treebox').scrollTop = 0; renderTree();
  });
  el('famall').addEventListener('click', function(){
    S.famMode = 'all';
    this.className = 'btn on'; el('famtop').className = 'btn';
    el('treebox').scrollTop = 0; renderTree();
  });
  renderTree(); renderPassport(); renderCog(); renderMat();
})();

/* ── замечательные люди ───────────────────────────────────────────────── */
var PEOPLE = D.people || [], PMAP = {};
function renderPersons(){
  var out = [], shown = 0;
  for (var i=0;i<PEOPLE.length;i++){
    var r = PEOPLE[i];
    if (S.era && r.era !== S.era) continue;
    if (S.pol && r.pn !== S.pol) continue;
    shown++;
    var acts = [];
    for (var q=0;q<r.inv.length && q<4;q++)
      acts.push('<div>◆ впервые: <b style="color:#d4b45c;font-weight:500">' +
                esc(r.inv[q][1]) + '</b> <span>(' + ruYear(r.inv[q][0]) + ')</span></div>');
    if (r.rule !== null)
      acts.push('<div>♛ встал во главе народа <span>(' + ruYear(r.rule) + ')</span></div>');
    for (var w=0;w<r.dec.length && w<2;w++)
      acts.push('<div>⚖ ' + esc(r.dec[w][1]) + '</div>');
    if (r.ex) for (var x=0;x<r.ex.length;x++)
      acts.push('<div>· ' + esc(r.ex[x]) + '</div>');
    if (r.age !== null && r.age !== undefined)
      acts.push('<div>† умер в ' + r.age + ' лет</div>');
    if (!acts.length) acts.push('<div><span>упомянут в летописи</span></div>');
    out.push('<div class="pcard' + (S.person === r.a ? ' sel' : '') +
      '" data-a="' + r.a + '" style="border-left-color:' + esc(r.col) + '">' +
      '<div class="ph">' + (r.ti ? '<i>' + esc(r.ti) + '</i> ' : '') + esc(r.nm) + '</div>' +
      '<div class="ps">' + esc(r.pn) + ' · ' + esc(r.era) + ' · ' +
      yrRange(r.y0, r.y1) + '</div>' +
      '<div class="pa">' + acts.join('') + '</div></div>');
  }
  el('plist').innerHTML = out.join('') ||
    '<div class="empty">По этому фильтру никого нет.</div>';
  el('pnum').textContent = 'показано ' + shown + ' из ' + PEOPLE.length;
  var cards = el('plist').getElementsByClassName('pcard');
  for (var c=0;c<cards.length;c++){
    cards[c].addEventListener('click', function(){
      var aid = parseInt(this.dataset.a, 10);
      var r = PMAP[aid];
      if (S.person === aid){ S.person = null; renderPersons(); renderFeed(); return; }
      S.person = aid;
      S.selPid = (r && r.p !== null) ? r.p : null;
      S.mark = null;
      var best = 0, bd = 1e18;
      for (var z=0;z<NF;z++){
        var dd = Math.abs(FR[z].year - r.y0);
        if (dd < bd){ bd = dd; best = z; }
      }
      stop();
      setFrame(best, true);
      renderPersons();
      var fd = el('feed');
      if (fd && fd.scrollIntoView) fd.scrollIntoView({block:'center'});
    });
  }
}
(function(){
  if (!PEOPLE.length){
    var ps = el('peoplesec'); if (ps) ps.style.display = 'none';
    return;
  }
  for (var i=0;i<PEOPLE.length;i++) PMAP[PEOPLE[i].a] = PEOPLE[i];
  var eras = [], pols = [], se = {}, sp = {};
  for (var j=0;j<PEOPLE.length;j++){
    if (PEOPLE[j].era && !se[PEOPLE[j].era]){ se[PEOPLE[j].era] = 1; eras.push(PEOPLE[j].era); }
    if (PEOPLE[j].pn && !sp[PEOPLE[j].pn]){ sp[PEOPLE[j].pn] = 1; pols.push(PEOPLE[j].pn); }
  }
  eras.sort(function(a,b){ return D.eraOrder.indexOf(a) - D.eraOrder.indexOf(b); });
  pols.sort(function(a,b){ return a.localeCompare(b, 'ru'); });
  var es = el('erasel'), pl = el('polsel');
  for (var a=0;a<eras.length;a++){
    var o = document.createElement('option'); o.value = eras[a]; o.textContent = eras[a];
    es.appendChild(o);
  }
  for (var b=0;b<pols.length;b++){
    var o2 = document.createElement('option'); o2.value = pols[b]; o2.textContent = pols[b];
    pl.appendChild(o2);
  }
  es.addEventListener('change', function(){ S.era = this.value; renderPersons(); });
  pl.addEventListener('change', function(){ S.pol = this.value; renderPersons(); });
  el('pclear').addEventListener('click', function(){
    S.era = ''; S.pol = ''; S.person = null;
    es.value = ''; pl.value = '';
    renderPersons(); renderFeed();
  });
  el('peoplecap').innerHTML = 'Люди, чьи имена летопись сохранила: изобретатели, ' +
    'правители, те, кто решал на развилках. Отобрано <b>' + PEOPLE.length +
    '</b> самых заметных из ' + D.head.n_people_all + ' названных по имени, ' +
    'по весу упоминаний. Щелчок по карточке сужает летопись до его событий ' +
    'и переводит карту на его год.';
  renderPersons();
})();

/* ── старт ────────────────────────────────────────────────────────────── */
legend('l_tech', [['максимум', '#d4b45c'], ['среднее', '#5f9e8f']]);
legend('l_ev', [['открытия', '#d4b45c'], ['утраты', '#a86a6a'],
                ['войны', '#c4544a'], ['эпидемии', '#8fae4a']]);
(function(){
  var mi = [], fi = [];
  for (var i=0;i<D.modeOrder.length;i++)
    mi.push([D.modeRu[D.modeOrder[i]] || D.modeOrder[i], D.modeColors[D.modeOrder[i]]]);
  for (var j=0;j<D.formOrder.length;j++)
    fi.push([D.formRu[D.formOrder[j]] || D.formOrder[j], D.formColors[D.formOrder[j]]]);
  legend('l_mode', mi);
  legend('l_form', fi);
  var er = [];
  for (var q=0;q<D.eraOrder.length;q++) er.push([D.eraOrder[q], D.eraColors[D.eraOrder[q]]]);
  legend('eralegend', er);
})();

var _rt = null;
window.addEventListener('resize', function(){
  if (_rt) clearTimeout(_rt);
  _rt = setTimeout(function(){
    fitMap(); drawMap(); drawCharts(); drawEra();
    if (LG) renderTree();
  }, 140);
});

fitMap();
buildBase();
setFrame(NF - 1, true);
"""


# ────────────────────────────────────────────────────────────────────────────
#  Сборка HTML
# ────────────────────────────────────────────────────────────────────────────
def _head_html(h: dict) -> str:
    """Шапка отчёта."""
    facts = [
        (_num(h["n_polities_ever"]), "народов было"),
        (nfmt_py(h["pop_end"]), "людей на конец"),
        (_num(h["tech_max"]), "знаний (максимум)"),
        (_num(h["wars"]), "войн"),
        (_num(h["epidemics"]), "эпидемий"),
        (_num(h["fissions"]), "расколов"),
        (_num(h["extinctions"]), "исчезновений"),
        (_num(h["discoveries"]), "открытий"),
    ]
    fh = "".join(
        f'<div class="fact"><b>{v}</b><span>{t}</span></div>' for v, t in facts
    )
    res = h.get("resolver") or "—"
    model = h.get("resolver_model") or ""
    rs = h.get("resolver_stats") or {}
    rstat = ""
    if isinstance(rs, dict) and rs:
        parts = [f"{k}: {v}" for k, v in list(rs.items())[:6]]
        rstat = " · " + ", ".join(parts)
    notes = []
    if h.get("thinned"):
        notes.append(
            f"Кадры прорежены: показано {h['frames']} из {h['frames_all']} "
            f"снятых лет, равномерно по времени."
        )
    if h.get("events_trunc"):
        notes.append(
            f"Летопись усечена до {h['events']} самых значимых событий."
        )
    note = ('<div class="note">' + " ".join(notes) + "</div>") if notes else ""
    demo = ""
    if h.get("demo"):
        cells = "".join(
            f'<span><span class="dl">{esc_py(_ru_year(y))}</span> '
            f"<b>{esc_py(nfmt_py(p))}</b></span>"
            for y, p in h["demo"]
        )
        demo = f'<div class="demo"><span class="dl">людей в мире:</span>{cells}</div>'
    return (
        '<header class="hdr">'
        f'<h1>TERRA · {esc_py(h["run_id"])}</h1>'
        f'<div class="sub">сид {esc_py(h.get("seed"))} · '
        f'{esc_py(_ru_year(h["year_start"]))} — {esc_py(_ru_year(h["year_end"]))} · '
        f'эпоха на конец: {esc_py(h.get("era_end", "—"))} · '
        f'развилки решает: {esc_py(res)}{esc_py(model and " (" + str(model) + ")")}'
        f'{esc_py(rstat)} · развилок: {_num(h.get("junctures", 0))}</div>'
        f'<div class="facts">{fh}</div>{demo}{note}</header>'
    )


def nfmt_py(v: float) -> str:
    """Человекочитаемое большое число (для шапки)."""
    v = float(v)
    if abs(v) >= 1e9:
        return f"{v/1e9:.2f} млрд"
    if abs(v) >= 1e6:
        return f"{v/1e6:.2f} млн"
    if abs(v) >= 1e4:
        return f"{v/1e3:.0f} тыс."
    return _num(v)


def esc_py(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_BODY = """
<div class="wrap">
__HEAD__
<div class="grid">
  <div>
    <div class="panel">
      <h2>Карта мира</h2>
      <div id="mapbox"><canvas id="map"></canvas><div id="tip"></div></div>
      <div class="timebar">
        <button class="btn" id="prev" title="предыдущий кадр">◀</button>
        <button class="btn" id="play">▶ играть</button>
        <button class="btn" id="next" title="следующий кадр">▶</button>
        <input type="range" id="slider" min="0" max="1" value="0">
        <button class="btn" id="speed" title="скорость">×1</button>
        <span id="yearlab">—</span>
      </div>
      <div class="layers" id="layers"></div>
      <div id="erabox">
        <h2 style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;
                   color:var(--ink2);margin-bottom:6px">Ведущая эпоха</h2>
        <canvas id="era"></canvas>
        <div class="eralegend" id="eralegend"></div>
      </div>
    </div>
  </div>
  <div>
    <div class="panel">
      <h2>Народы <span id="pcount" style="float:right;font-size:10.5px;
          letter-spacing:0;text-transform:none;color:var(--ink3)"></span></h2>
      <div class="bar" style="margin-bottom:8px">
        <label for="modesel">уклад</label>
        <select id="modesel"><option value="">все уклады</option></select>
      </div>
      <div class="tabwrap"><table>
        <thead><tr id="phead"></tr></thead><tbody id="pbody"></tbody>
      </table></div>
      <div id="pnote" style="margin-top:7px;font-size:10.5px;color:var(--ink3);
           display:flex;align-items:center;gap:5px"></div>
    </div>
    <div class="panel">
      <h2>Летопись <span id="evcount" style="float:right;font-size:10.5px;
          letter-spacing:0;text-transform:none;color:var(--ink3)"></span></h2>
      <div class="chips" id="chips"></div>
      <div class="wrow">значимость от <input type="range" id="wslider" min="0"
        max="5" step="0.1" value="2.2"><b id="wlab">2.2</b>
        <button class="btn" id="milestones" style="padding:3px 9px;font-size:11.5px"
          title="показывать только события со значимостью 3.2 и выше">только вехи</button>
      </div>
      <div id="pfilter" style="display:none;margin-bottom:8px;font-size:11.5px;
           color:var(--acc2)"></div>
      <div id="feed"></div>
    </div>
  </div>
</div>

<div class="sec" id="langsec">
  <h2>Языки и родство</h2>
  <div class="cap" id="langcap"></div>
  <div class="langgrid">
    <div>
      <div class="bar">
        <button class="btn on" id="famtop">крупнейшие семьи</button>
        <button class="btn" id="famall">показать все</button>
        <span class="spd" id="treehint"></span>
      </div>
      <div id="treeaxisbox"></div>
      <div id="treebox"></div>
    </div>
    <div id="lpass"></div>
  </div>
  <div class="langgrid2">
    <div>
      <div class="bar">
        <label for="famsel">сравнение слов в семье</label>
        <select id="famsel"></select>
      </div>
      <div class="cogwrap"><div id="cogbox"></div></div>
      <div class="cap" style="margin:8px 0 0">Ярче — ближе к форме первого
        столбца; правильные звуковые соответствия видны по столбцам.</div>
    </div>
    <div>
      <h4>Матрица расхождения</h4>
      <div id="matbox"></div>
      <div class="cap" style="margin:8px 0 0">Утрата взаимопонятности, 0 — тот же
        язык, 1 — ничего общего. В подсказке — доля общих когнатов.</div>
    </div>
  </div>
</div>

<div class="sec" id="peoplesec">
  <h2>Замечательные люди этого мира</h2>
  <div class="cap" id="peoplecap"></div>
  <div class="bar">
    <label for="erasel">эпоха</label>
    <select id="erasel"><option value="">все эпохи</option></select>
    <label for="polsel">народ</label>
    <select id="polsel"><option value="">все народы</option></select>
    <button class="btn" id="pclear">сбросить</button>
    <span class="spd" id="pnum"></span>
  </div>
  <div id="plist"></div>
</div>

<div class="charts">
  <div class="ch"><h3>Население мира (лог. шкала)</h3><canvas id="c_pop"></canvas></div>
  <div class="ch"><h3>Число народов</h3><canvas id="c_pol"></canvas></div>
  <div class="ch"><h3>Знания</h3><canvas id="c_tech"></canvas>
    <div class="leg" id="l_tech"></div></div>
  <div class="ch"><h3>Доля людей по способам хозяйства</h3><canvas id="c_mode"></canvas>
    <div class="leg" id="l_mode"></div></div>
  <div class="ch"><h3>Доля людей по формам правления</h3><canvas id="c_form"></canvas>
    <div class="leg" id="l_form"></div></div>
  <div class="ch"><h3>События за период</h3><canvas id="c_ev"></canvas>
    <div class="leg" id="l_ev"></div></div>
</div>

<div class="foot">TERRA — симулятор цивилизации. Отчёт самодостаточен:
все данные вшиты в этот файл, сеть не нужна.</div>
</div>
"""


def _render(payload: dict) -> str:
    """Собрать HTML-строку целиком."""
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # чтобы </script> внутри строк не оборвал блок данных
    data = data.replace("</", "<\\/")
    body = _BODY.replace("__HEAD__", _head_html(payload["head"]))
    return (
        "<!DOCTYPE html>\n<html lang=\"ru\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        f"<title>TERRA · {esc_py(payload['head']['run_id'])}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f"{body}\n"
        f'<script id="terra-data" type="application/json">{data}</script>\n'
        f"<script>{_JS}</script>\n</body>\n</html>\n"
    )


# ────────────────────────────────────────────────────────────────────────────
#  Публичный вход
# ────────────────────────────────────────────────────────────────────────────
def build_report(run_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Собрать одностраничный HTML-отчёт по каталогу прогона.

    run_dir  — каталог с run.json / world.* / *.jsonl
    out_path — куда положить html (по умолчанию <run_dir>/report.html)
    Возвращает путь к записанному файлу.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"нет каталога прогона: {run_dir}")
    out = Path(out_path) if out_path else (run_dir / "report.html")
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = _collect(run_dir)
    html = _render(payload)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("использование: python -m terra.report <каталог_прогона> [файл.html]")
        raise SystemExit(2)
    _out = build_report(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    _mb = _out.stat().st_size / 1e6
    print(f"отчёт собран: {_out}  ({_mb:.2f} МБ)")
