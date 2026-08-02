"""
TERRA — галерея лиц.

Собирает одну самодостаточную страницу: фотографии людей этого мира рядом
с их досье из симуляции — кто они, из какого народа, что успели сделать,
какой у них был характер и во что они верили.

Фотографии — внешние: их порождает модель изображений по описанию из
`portrait.py`. Модуль лишь принимает готовые файлы, ужимает их и вшивает
в HTML, чтобы страница открывалась где угодно и без сети.

    build_gallery(run_dir, items, out_path)
        items — список словарей от portrait.portraits(), у каждого
        дополнительно ключ "image" с путём к файлу фотографии.
"""
from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

TRAIT_RU = {
    "curiosity": "любопытство", "risk": "склонность к риску", "aggression": "агрессия",
    "sociability": "общительность", "conformity": "конформизм", "ambition": "амбиции",
    "patience": "терпение", "empathy": "эмпатия", "piety": "набожность",
    "diligence": "усердие",
}
BELIEF_RU = {
    "elsewhere": "«там лучше, чем здесь»", "danger": "«чужие опасны»",
    "novelty": "«новое работает»", "trust": "«своим можно верить»",
    "authority": "«власть законна»", "divine": "«миром правят высшие силы»",
    "scarcity": "«еды не хватит»",
}
ROLE_RU = {
    "commoner": "общинник", "elder": "старейшина", "hunter": "охотник",
    "farmer": "земледелец", "healer": "знахарь", "artisan": "ремесленник",
    "priest": "жрец", "warrior": "воин", "trader": "торговец",
    "scribe": "писец", "chief": "вождь", "rebel": "смутьян",
}


def _yr(y) -> str:
    if y is None:
        return "—"
    return f"{abs(int(y))} {'до н. э.' if y < 0 else 'н. э.'}"


def _img_b64(path, max_w=760, quality=80) -> str:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return base64.b64encode(buf.getvalue()).decode()


def _bar(v: float, label: str) -> str:
    pct = max(0, min(100, round(float(v) * 100)))
    hot = "hot" if v > 0.72 else ("cold" if v < 0.28 else "")
    return (f'<div class="tr"><span class="tl">{html.escape(label)}</span>'
            f'<span class="tb"><i class="{hot}" style="width:{pct}%"></i></span>'
            f'<span class="tv">{pct}</span></div>')


def build_gallery(run_dir, items: list[dict], out_path=None, title="Лица мира") -> Path:
    run_dir = Path(run_dir)
    out = Path(out_path) if out_path else run_dir / "gallery.html"
    meta = {}
    rj = run_dir / "run.json"
    if rj.exists():
        meta = json.loads(rj.read_text(encoding="utf-8"))

    cards = []
    for it in items:
        img = ""
        if it.get("image") and Path(it["image"]).exists():
            img = (f'<img alt="{html.escape(it.get("name", ""))}" '
                   f'src="data:image/jpeg;base64,{_img_b64(it["image"])}">')
        else:
            img = '<div class="noimg">фотография не сделана</div>'
        deeds = "".join(f"<li>{html.escape(d)}</li>" for d in it.get("deeds", []))
        traits = "".join(_bar(v, TRAIT_RU.get(k, k))
                         for k, v in sorted(it.get("traits", {}).items(),
                                            key=lambda kv: -kv[1])[:6])
        beliefs = "".join(_bar(v, BELIEF_RU.get(k, k))
                          for k, v in sorted(it.get("beliefs", {}).items(),
                                             key=lambda kv: -kv[1])[:4])
        life = _yr(it.get("born"))
        if it.get("died"):
            life += f" — {_yr(it['died'])}"
        cards.append(f"""
<article class="card">
  <div class="ph">{img}</div>
  <div class="txt">
    <h2>{html.escape(it.get('name', '—'))}</h2>
    <p class="sub">{html.escape(it.get('polity', '—'))} · {html.escape(ROLE_RU.get(it.get('role',''), it.get('role','')))}
       · {html.escape(it.get('era', ''))} · {life} · {it.get('age', '?')} лет</p>
    {f'<ul class="deeds">{deeds}</ul>' if deeds else ''}
    <p class="ru">{html.escape(it.get('ru', ''))}</p>
    <div class="cols">
      <div><h3>характер</h3>{traits}</div>
      <div><h3>во что верил</h3>{beliefs}</div>
    </div>
  </div>
</article>""")

    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — TERRA</title>
<style>
:root{{--bg:#0e1116;--pan:#161b23;--ln:#242c38;--tx:#dfe5ee;--dim:#8e9aad;--acc:#c9a227}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif}}
header{{padding:38px 28px 22px;border-bottom:1px solid var(--ln);max-width:1180px;margin:0 auto}}
h1{{margin:0 0 6px;font-size:27px;font-weight:600;letter-spacing:.2px}}
header p{{margin:0;color:var(--dim);max-width:70ch}}
main{{max-width:1180px;margin:0 auto;padding:26px 28px 70px;
 display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:22px}}
.card{{background:var(--pan);border:1px solid var(--ln);border-radius:12px;overflow:hidden;
 display:flex;flex-direction:column}}
.ph{{background:#0a0d12;aspect-ratio:3/4;overflow:hidden;display:flex;align-items:center;
 justify-content:center}}
.ph img{{width:100%;height:100%;object-fit:cover;display:block}}
.noimg{{color:var(--dim);font-size:13px}}
.txt{{padding:18px 20px 20px}}
h2{{margin:0 0 3px;font-size:21px;font-weight:600}}
.sub{{margin:0 0 12px;color:var(--dim);font-size:13px}}
.deeds{{margin:0 0 12px;padding-left:18px;color:#e8d9a8}}
.deeds li{{margin:2px 0}}
.ru{{margin:0 0 16px;color:#c3ccda;font-size:14px}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
h3{{margin:0 0 7px;font-size:11px;text-transform:uppercase;letter-spacing:.9px;color:var(--dim);
 font-weight:600}}
.tr{{display:flex;align-items:center;gap:7px;margin:3px 0;font-size:12px}}
.tl{{flex:0 0 108px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tb{{flex:1;height:5px;background:#0c1017;border-radius:3px;overflow:hidden}}
.tb i{{display:block;height:100%;background:#5b7fa6}}
.tb i.hot{{background:var(--acc)}} .tb i.cold{{background:#48566a}}
.tv{{flex:0 0 22px;text-align:right;color:var(--dim);font-variant-numeric:tabular-nums}}
footer{{max-width:1180px;margin:0 auto;padding:0 28px 50px;color:var(--dim);font-size:13px;
 border-top:1px solid var(--ln);padding-top:20px}}
@media(max-width:520px){{main{{grid-template-columns:1fr;padding:18px}}.cols{{grid-template-columns:1fr}}}}
</style></head><body>
<header>
  <h1>{html.escape(title)}</h1>
  <p>Люди из мира <b>{html.escape(meta.get('run_id', '—'))}</b> (сид {meta.get('config', {}).get('seed', '?')}).
  Каждое лицо снято по описанию, целиком выведенному из состояния симуляции: возраст —
  из года рождения и смерти, одежда — из ремёсел, освоенных их народом, украшения — из руд,
  которые он добывал, орудие — из того, что он умел делать, выражение лица и осанка —
  из черт характера. Ничего не дописано от руки.</p>
</header>
<main>{''.join(cards)}</main>
<footer>Всего в книге мира {meta.get('stats', {}).get('junctures', '—')} разрешённых развилок;
здесь показаны {len(items)} человек, отобранные по значимости дел, из разных эпох и разных народов.</footer>
</body></html>"""
    out.write_text(doc, encoding="utf-8")
    return out


if __name__ == "__main__":
    import argparse
    from .portrait import portraits
    ap = argparse.ArgumentParser("terra.gallery")
    ap.add_argument("run")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--images", help="каталог с файлами <aid>.png")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    items = portraits(a.run, a.n)
    if a.images:
        d = Path(a.images)
        for it in items:
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                f = d / f"{it['aid']}{ext}"
                if f.exists():
                    it["image"] = str(f)
                    break
    print(build_gallery(a.run, items, a.out))
