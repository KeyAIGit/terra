"""
TERRA — мультивселенная: реестр запущенных миров и сравнение их судеб.

Каждый мир детерминирован: код плюс сид дают одну и ту же историю до
последнего имени. Значит, «другая вселенная» — это ровно другой сид или
другой параметр, а не другая случайность. Отсюда простая, но неожиданно
сильная возможность: запустить много вселенных и посмотреть, что в них
СОВПАДАЕТ, а что расходится.

Совпадающее — это то, что вытекает из физики и человеческой природы
(земледелие приходит туда, где есть крупнозёрные злаки; письмо рождается
под давлением учёта; сложные державы рушатся, когда содержание сложности
перестаёт окупаться). Расходящееся — это история как таковая: кто именно
первым выплавил медь, чей язык лёг в основу полумира, где встала столица.

Этот модуль ничего не симулирует. Он только читает готовые прогоны и
складывает из них карту вселенных.
"""
from __future__ import annotations

import gzip
import json
import math
import os
from pathlib import Path

# Знания-вехи: по ним удобно сравнивать судьбы миров.
# (ключ технологии, человеческое имя вехи)
MILESTONES = [
    ("cultivation", "первый посев"),
    ("domestication_plant", "одомашненный злак"),
    ("herding", "скотоводство"),
    ("pottery", "керамика"),
    ("sedentism", "оседлость"),
    ("copper_smelt", "выплавка меди"),
    ("bronze", "бронза"),
    ("proto_writing", "протописьмо"),
    ("writing", "письменность"),
    ("wheel", "колесо"),
    ("city_wall", "городская стена"),
    ("codified_law", "писаный закон"),
    ("coinage", "чеканная монета"),
    ("steel", "сталь"),
    ("alphabet", "алфавит"),
    ("philosophy", "философия"),
    ("printing", "печать"),
]

FORM_ORDER = ("band", "tribe", "bigman", "chiefdom", "citystate", "republic",
              "confederation", "kingdom", "empire")


def _read_jsonl(path: Path, limit: int | None = None):
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(out) >= limit:
                break
    return out


def fingerprint(run_dir: Path) -> dict | None:
    """Отпечаток вселенной: чем этот мир кончил и когда что в нём случилось."""
    run_dir = Path(run_dir)
    rj = run_dir / "run.json"
    if not rj.exists():
        return None
    meta = json.loads(rj.read_text(encoding="utf-8"))
    cfg = meta.get("config", {})
    tl = _read_jsonl(run_dir / "timeline.jsonl")
    if not tl:
        return None
    last = tl[-1]

    # когда какая веха впервые случилась — из летописи открытий
    firsts: dict[str, dict] = {}
    peak_pop = 0.0
    for ev in _read_jsonl(run_dir / "chronicle.jsonl"):
        if ev.get("kind") == "discovery":
            key = (ev.get("data") or {}).get("tech") or ev.get("tech")
            if key and key not in firsts:
                firsts[key] = {"year": ev["year"], "text": ev.get("text", "")}
    for row in tl:
        peak_pop = max(peak_pop, float(row.get("pop", 0)))

    # какие формы обществ мир вообще успел изобрести
    forms_seen = set()
    max_city = 0
    for row in tl:
        forms_seen.update((row.get("forms") or {}).keys())
        max_city = max(max_city, int(row.get("largest_city") or 0))

    people = _read_jsonl(run_dir / "people.jsonl")
    n_taught = sum(1 for p in people if (p.get("life") or {}).get("taught", 0) > 0)
    scars = {}
    for p in people:
        for s, v in ((p.get("life") or {}).get("scars") or {}).items():
            scars[s] = scars.get(s, 0) + 1

    return {
        # имя вселенной — это папка: run_id мог остаться от предка при копии
        "name": run_dir.name,
        "run_id": meta.get("run_id"),
        "seed": cfg.get("seed"),
        "year_start": cfg.get("year_start"),
        "year_now": last.get("year"),
        "params": {k: v for k, v in cfg.items()
                   if k in ("climate_severity", "war_appetite", "disease_severity",
                            "diffusion_rate", "innovation_rate", "seed_polities",
                            "resolver")},
        "forked_from": meta.get("forked_from"),
        "fork_year": meta.get("fork_year"),
        "pop_now": float(last.get("pop", 0)),
        "pop_peak": peak_pop,
        "polities": int(last.get("polities", 0)),
        "tech_max": int(last.get("tech_max", 0)),
        "literacy": float(last.get("literacy", 0)),
        "largest_city": max_city,
        "max_polity_pop": float(last.get("max_polity_pop", 0)),
        "era": last.get("era", ""),
        "forms_seen": [f for f in FORM_ORDER if f in forms_seen],
        "stats": {k[2:]: int(last.get(k, 0)) for k in
                  ("n_discoveries", "n_losses", "n_wars", "n_fissions",
                   "n_extinctions", "n_epidemics", "n_collapses")},
        "milestones": {key: firsts.get(key) for key, _ in MILESTONES},
        "people": len(people),
        "teachers": n_taught,
        "scarred": scars,
        "timeline": [{"year": r["year"], "pop": r["pop"], "tech": r.get("tech_max", 0),
                      "polities": r.get("polities", 0)}
                     for r in tl[:: max(1, len(tl) // 260)]],
    }


def scan(runs_root: str | Path = "runs") -> list[dict]:
    """Все вселенные, какие есть на диске."""
    root = Path(runs_root)
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        fp = fingerprint(d)
        if fp:
            out.append(fp)
    return out


def divergence(a: dict, b: dict) -> dict:
    """Насколько две вселенные разошлись — по вехам и по итогу."""
    diffs = []
    for key, human in MILESTONES:
        ya, yb = a["milestones"].get(key), b["milestones"].get(key)
        if ya is None and yb is None:
            continue
        if ya is None or yb is None:
            diffs.append({"what": human, "a": ya and ya["year"], "b": yb and yb["year"],
                          "gap": None, "only": "b" if ya is None else "a"})
        else:
            diffs.append({"what": human, "a": ya["year"], "b": yb["year"],
                          "gap": yb["year"] - ya["year"], "only": None})
    gaps = [d["gap"] for d in diffs if d["gap"] is not None]
    return {
        "a": a["name"], "b": b["name"],
        "same_seed": a.get("seed") == b.get("seed"),
        "fork_year": b.get("fork_year") if b.get("forked_from") == a["name"] else None,
        "milestone_diffs": diffs,
        "mean_gap": (sum(abs(g) for g in gaps) / len(gaps)) if gaps else None,
        "pop_ratio": (b["pop_now"] / a["pop_now"]) if a["pop_now"] else None,
        "tech_delta": b["tech_max"] - a["tech_max"],
    }


def _fmt_year(y) -> str:
    if y is None:
        return "—"
    y = int(y)
    return f"{abs(y)} до н. э." if y < 0 else f"{y} н. э."


def _fmt_pop(p) -> str:
    p = float(p or 0)
    if p >= 1e6:
        return f"{p / 1e6:.1f} млн"
    if p >= 1e3:
        return f"{p / 1e3:.0f} тыс."
    return f"{p:.0f}"


def build_multiverse(runs_root: str | Path = "runs",
                     out_path: str | Path = "runs/multiverse.html") -> Path:
    """Собирает страницу-обзор всех вселенных (самодостаточный HTML)."""
    unis = scan(runs_root)
    out_path = Path(out_path)
    data = json.dumps(unis, ensure_ascii=False)

    rows = []
    for u in unis:
        ms = " ".join(
            f"<span class='ms {'on' if u['milestones'].get(k) else 'off'}' "
            f"title='{h}: {_fmt_year((u['milestones'].get(k) or {}).get('year'))}'>"
            f"{h[:1].upper()}</span>"
            for k, h in MILESTONES)
        forms = " → ".join(u["forms_seen"][-4:]) or "—"
        rows.append(
            f"<tr><td class='nm'>{u['name']}"
            + (f"<div class='sub'>ветвь от {u['forked_from']} "
               f"({_fmt_year(u['fork_year'])})</div>" if u.get("forked_from") else "")
            + f"</td><td>{u['seed']}</td><td>{_fmt_year(u['year_now'])}</td>"
            f"<td>{_fmt_pop(u['pop_now'])}</td><td>{u['polities']}</td>"
            f"<td>{u['tech_max']}</td><td>{u['largest_city'] or '—'}</td>"
            f"<td>{u['stats']['collapses']}</td>"
            f"<td class='forms'>{forms}</td><td class='msc'>{ms}</td></tr>")

    html = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>TERRA — мультивселенная</title>
<style>
 body{{background:#0b0d12;color:#dfe3ea;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
      margin:0;padding:28px 30px 60px}}
 h1{{font-weight:600;letter-spacing:.2px;margin:0 0 6px}}
 .lead{{color:#94a0b4;max-width:70ch;margin:0 0 22px}}
 table{{border-collapse:collapse;width:100%;font-size:14px}}
 th,td{{padding:8px 10px;border-bottom:1px solid #1c2130;text-align:left;vertical-align:top}}
 th{{color:#8c98ac;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
 .nm{{font-weight:600}} .sub{{color:#7b8699;font-size:12px;font-weight:400}}
 .forms{{color:#9fb0c8;font-size:13px}}
 .ms{{display:inline-block;width:17px;height:17px;line-height:17px;text-align:center;
      border-radius:4px;font-size:10px;margin-right:2px}}
 .ms.on{{background:#2f6f4f;color:#d6ffe8}} .ms.off{{background:#1b2030;color:#3d4658}}
 .msc{{white-space:nowrap}}
 canvas{{margin-top:26px;background:#0e111a;border:1px solid #1c2130;border-radius:8px}}
 .note{{color:#7b8699;font-size:13px;margin-top:14px;max-width:80ch}}
</style>
<h1>Мультивселенная TERRA</h1>
<p class="lead">Каждая вселенная детерминирована: тот же сид — та же история, до последнего
имени. Различаются они только начальным сидом или одним изменённым параметром.
Что повторяется во всех — идёт от физики и человеческой природы; что расходится —
и есть история.</p>
<table><thead><tr><th>вселенная</th><th>сид</th><th>год</th><th>людей</th>
<th>народов</th><th>знаний</th><th>крупнейший город</th><th>крушений</th>
<th>формы власти</th><th>вехи</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan=10>прогонов пока нет</td></tr>'}</tbody></table>
<canvas id="c" width="1180" height="340"></canvas>
<p class="note">Кривые — численность людей по годам в каждой вселенной (логарифмическая шкала).
Наведите на строку таблицы, чтобы подсветить её кривую.</p>
<script>
const U = {data};
const c = document.getElementById('c'), g = c.getContext('2d');
const pal = ['#6ea8fe','#7ddba1','#ffb86b','#ff7b8a','#c792ea','#78dce8','#e6db74','#a1efe4'];
function draw(hi){{
  g.clearRect(0,0,c.width,c.height);
  let ys=[], xs=[];
  U.forEach(u=>u.timeline.forEach(p=>{{xs.push(p.year); ys.push(Math.max(1,p.pop));}}));
  if(!xs.length) return;
  const x0=Math.min(...xs), x1=Math.max(...xs);
  const y0=Math.log10(Math.min(...ys)), y1=Math.log10(Math.max(...ys));
  const px=v=>60+(v-x0)/(x1-x0||1)*(c.width-90);
  const py=v=>c.height-34-(Math.log10(Math.max(1,v))-y0)/((y1-y0)||1)*(c.height-64);
  g.strokeStyle='#1c2130'; g.fillStyle='#6b7688'; g.font='11px sans-serif';
  for(let k=Math.ceil(y0);k<=y1;k++){{
    const y=py(Math.pow(10,k));
    g.beginPath(); g.moveTo(56,y); g.lineTo(c.width-26,y); g.stroke();
    g.fillText('10^'+k, 12, y+4);
  }}
  U.forEach((u,i)=>{{
    g.strokeStyle=pal[i%pal.length]; g.globalAlpha=(hi==null||hi===i)?1:.25;
    g.lineWidth=(hi===i)?2.4:1.4; g.beginPath();
    u.timeline.forEach((p,k)=>{{k?g.lineTo(px(p.year),py(p.pop)):g.moveTo(px(p.year),py(p.pop));}});
    g.stroke();
  }});
  g.globalAlpha=1;
}}
draw(null);
document.querySelectorAll('tbody tr').forEach((tr,i)=>{{
  tr.onmouseenter=()=>draw(i); tr.onmouseleave=()=>draw(null);
}});
</script></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def registry_json(runs_root: str | Path = "runs",
                  out_path: str | Path = "runs/multiverse.json") -> Path:
    """Машиночитаемый реестр вселенных (для витрины и внешних инструментов)."""
    out = Path(out_path)
    out.write_text(json.dumps(scan(runs_root), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "runs"
    p = build_multiverse(root)
    j = registry_json(root)
    uni = scan(root)
    print(f"вселенных: {len(uni)}")
    for u in uni:
        print(f"  {u['name']:<16} сид {u['seed']:<4} до {_fmt_year(u['year_now']):<14} "
              f"{_fmt_pop(u['pop_now']):>9}  знаний {u['tech_max']:>3}  "
              f"крушений {u['stats']['collapses']}")
    print(f"страница: {p}\nреестр: {j}")
