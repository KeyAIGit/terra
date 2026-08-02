"""
TERRA — лёгкий обозреватель мира.

Глобус и большой дашборд весят десятки мегабайт и требуют WebGL. Там, где
их не открыть — в предпросмотре, на телефоне, в чужом браузере, — нужен
файл, который откроется наверняка: обычный canvas, обычный JavaScript,
никаких модулей, потоков распаковки и трёхмерной графики. Пара мегабайт.

    python3 -m terra.compact runs/terra-1
"""
from __future__ import annotations

import argparse
import base64
import gzip
import html
import json
import math
from pathlib import Path

import numpy as np

from .contracts import BIOME_COLORS, BIOME_NAMES, OCEAN

MODE_RU = {"forager": "охотники-собиратели", "complex_forager": "оседлые собиратели",
           "horticulture": "мотыжное земледелие", "pastoral": "скотоводы",
           "agrarian": "пашенное земледелие", "intensive": "ирригационное хозяйство"}
FORM_RU = {"band": "община", "tribe": "племя", "bigman": "вождество бигменов",
           "chiefdom": "вождество", "citystate": "город-государство",
           "kingdom": "царство", "empire": "держава", "republic": "республика",
           "confederation": "союз"}
KIND_RU = {"origin": "появление", "discovery": "открытие", "diffusion": "заимствование",
           "loss": "утрата", "city": "город", "build": "постройка", "war": "война",
           "contact": "встреча", "decision": "решение", "fission": "раскол",
           "merge": "слияние", "extinction": "исчезновение", "epidemic": "мор",
           "rule": "правление", "death": "смерть", "reform": "устройство",
           "mode": "хозяйство", "form": "устройство", "collapse": "обрушение",
           "religion": "боги", "fork": "ветвление"}
KIND_COLOR = {"collapse": "#e5484d", "discovery": "#e8c547", "war": "#d97757",
              "city": "#4f9ecf", "mode": "#7bc47f", "religion": "#b48ce0",
              "loss": "#c98a3b", "epidemic": "#8f7fd6", "extinction": "#8a94a6",
              "origin": "#dfe5ee", "rule": "#9fb3c8", "decision": "#5fbfa8"}


def _yr(y) -> str:
    y = int(y)
    return f"{abs(y)} {'до н. э.' if y < 0 else 'н. э.'}"


def _read_jsonl(p: Path, limit: int | None = None) -> list:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
            if limit and len(out) >= limit:
                break
    return out


def _png(rgb: np.ndarray) -> str:
    """Минимальный PNG без сторонних библиотек. rgb — (H, W, 3) uint8."""
    import struct
    import zlib
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    return base64.b64encode(png).decode()


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rle(a: np.ndarray) -> list:
    """Сжатие карты владений: territories идут кусками, поэтому RLE их душит."""
    out, cur, n = [], int(a[0]), 0
    for v in a:
        v = int(v)
        if v == cur:
            n += 1
        else:
            out.append(cur)
            out.append(n)
            cur, n = v, 1
    out.append(cur)
    out.append(n)
    return out


def build_compact(run_dir, out_path=None, max_frames: int = 46,
                  max_events: int = 900) -> Path:
    run_dir = Path(run_dir)
    out = Path(out_path) if out_path else run_dir / "compact.html"
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    timeline = _read_jsonl(run_dir / "timeline.jsonl")
    snaps = _read_jsonl(run_dir / "snapshots.jsonl")
    chron = _read_jsonl(run_dir / "chronicle.jsonl")
    people = _read_jsonl(run_dir / "people.jsonl")

    from .world import load_world
    w = load_world(str(run_dir / "world"))
    H, W = w.height, w.width

    # ── подложка: биомы с лёгкой светотенью ──
    biome = w.biome.ravel()
    rgb = np.zeros((H * W, 3), dtype=np.uint8)
    for b, c in BIOME_COLORS.items():
        rgb[biome == b] = _hex(c)
    elev = w.elevation.ravel()
    land = w.is_land.ravel()
    sh = np.zeros(H * W, dtype=np.float32)
    e2 = w.elevation.astype(np.float32)
    gy, gx = np.gradient(e2)
    sh = np.clip(1.0 + (gx - gy).ravel() / 900.0, 0.72, 1.35)
    sh[~land] = 1.0
    rgb = np.clip(rgb.astype(np.float32) * sh[:, None], 0, 255).astype(np.uint8)
    base_png = _png(rgb.reshape(H, W, 3))

    # ── кадры владений ──
    step = max(1, len(snaps) // max_frames)
    frames = snaps[::step]
    if frames and frames[-1] is not snaps[-1]:
        frames.append(snaps[-1])
    fdata = []
    for s in frames:
        cm = np.frombuffer(base64.b64decode(s["culture_map"]), dtype=np.int16)
        ids = [p["pid"] for p in s["polities"]]
        cols = {p["pid"] % 32000: p["color"] for p in s["polities"]}
        uniq = sorted(set(int(v) for v in np.unique(cm) if v >= 0))
        remap = {v: i + 1 for i, v in enumerate(uniq[:250])}
        idx = np.zeros(cm.size, dtype=np.uint8)
        for v, i in remap.items():
            idx[cm == v] = i
        pal = ["#000000"] * (len(remap) + 1)
        for v, i in remap.items():
            pal[i] = cols.get(v, "#888888")
        top = sorted(s["polities"], key=lambda p: -p["pop"])[:14]
        fdata.append({
            "y": s["year"], "r": _rle(idx), "p": pal,
            "c": [[c["x"], c["y"], int(c["pop"]), c["name"]]
                  for c in sorted(s.get("settlements", []),
                                  key=lambda c: -c["pop"])[:60]],
            "t": [[p["name"], int(p["pop"]), MODE_RU.get(p["mode"], p["mode"]),
                   FORM_RU.get(p["form"], p["form"]), p["tech"],
                   p.get("capital") or "", ", ".join(p.get("gods", [])[:2])]
                  for p in top],
        })

    # ── летопись: самое весомое, равномерно по времени ──
    chron.sort(key=lambda e: (-e["weight"], e["year"]))
    keep = chron[:max_events]
    keep.sort(key=lambda e: e["year"])
    ev = [[e["year"], e["kind"], e["text"], round(e["weight"], 1),
           e.get("x"), e.get("y")] for e in keep]

    # ── замечательные люди ──
    def pscore(p):
        d = p.get("deeds", [])
        return (sum(2.0 if x["kind"] == "discovery" else 1.3 for x in d)
                + 1.5 * p.get("power", 0) + 0.7 * p.get("prestige", 0))
    people.sort(key=pscore, reverse=True)
    ppl = [[p.get("name", "?"), p.get("polity_name", "?"), p.get("born", 0),
            p.get("died"), p.get("era", ""),
            [d["text"] for d in p.get("deeds", [])][:3]]
           for p in people[:120]]

    tl = [[t["year"], round(t["pop"]), t["polities"], t["tech_max"],
           t.get("cities", 0), round(t.get("complexity", 0), 3),
           round(t.get("largest_city", 0))] for t in timeline]

    payload = {"meta": {"id": meta["run_id"], "seed": meta["config"]["seed"],
                        "stats": meta["stats"], "H": H, "W": W},
               "frames": fdata, "events": ev, "people": ppl, "timeline": tl}
    blob = base64.b64encode(gzip.compress(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), 9)).decode()

    doc = _TEMPLATE.replace("__BASE__", base_png).replace("__DATA__", blob)
    doc = doc.replace("__TITLE__", html.escape(str(meta["run_id"])))
    out.write_text(doc, encoding="utf-8")
    return out


# ────────────────────────────────────────────────────────────────────────────
_TEMPLATE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TERRA — __TITLE__</title>
<style>
:root{--bg:#0d1117;--pan:#151b24;--ln:#242c38;--tx:#dfe5ee;--dim:#8e9aad;--acc:#c9a227}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.55 -apple-system,
 BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-x:hidden}
header{padding:14px 18px;border-bottom:1px solid var(--ln);display:flex;
 flex-wrap:wrap;gap:16px;align-items:baseline}
h1{margin:0;font-size:17px;font-weight:600;letter-spacing:.3px}
h1 b{color:var(--acc);font-weight:600}
.k{color:var(--dim);font-size:12px}.k b{color:var(--tx);font-weight:600}
main{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;padding:14px 18px 40px;
 max-width:1500px;margin:0 auto}
@media(max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--pan);border:1px solid var(--ln);border-radius:10px;padding:12px 14px}
.card h2{margin:0 0 9px;font-size:11px;text-transform:uppercase;letter-spacing:1px;
 color:var(--dim);font-weight:600}
#wrap{position:relative;background:#0a0d12;border-radius:8px;overflow:hidden}
canvas{display:block;width:100%;height:auto;image-rendering:auto}
#tip{position:absolute;pointer-events:none;background:#0b0f16ee;border:1px solid var(--ln);
 border-radius:6px;padding:6px 9px;font-size:12px;display:none;max-width:240px;z-index:5}
#bar{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
button{background:#1d2532;color:var(--tx);border:1px solid var(--ln);border-radius:6px;
 padding:5px 11px;cursor:pointer;font-size:13px}
button:hover{background:#27313f}
input[type=range]{flex:1;min-width:180px;accent-color:var(--acc)}
#yr{font-variant-numeric:tabular-nums;min-width:120px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;color:var(--dim);font-weight:600;padding:3px 6px 5px;
 border-bottom:1px solid var(--ln);white-space:nowrap}
td{padding:3px 6px;border-bottom:1px solid #1b222c}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.sw{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
#log{max-height:420px;overflow:auto;font-size:12.5px}
.e{padding:5px 0;border-bottom:1px solid #1b222c;cursor:pointer}
.e:hover{background:#1a212b}
.e .y{color:var(--dim);font-variant-numeric:tabular-nums;margin-right:7px}
.e .t{display:inline-block;font-size:10px;padding:1px 5px;border-radius:3px;
 margin-right:6px;color:#0d1117;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.chip{font-size:10.5px;padding:2px 7px;border-radius:9px;border:1px solid var(--ln);
 cursor:pointer;color:var(--dim)}
.chip.on{background:#243040;color:var(--tx);border-color:#3a475a}
.ppl{max-height:300px;overflow:auto;font-size:12.5px}
.p1{padding:6px 0;border-bottom:1px solid #1b222c}
.p1 b{color:var(--tx)}.p1 i{color:var(--dim);font-style:normal}
.p1 ul{margin:3px 0 0 16px;padding:0;color:#d9c98f}
svg{width:100%;height:auto;display:block}
.note{color:var(--dim);font-size:11.5px;margin-top:8px}
</style></head><body>
<header>
  <h1>TERRA · <b>__TITLE__</b></h1>
  <span class="k">сид <b id="sd"></b></span>
  <span class="k">народов <b id="np"></b></span>
  <span class="k">людей <b id="pp"></b></span>
  <span class="k">открытий <b id="ds"></b></span>
  <span class="k">войн <b id="ws"></b></span>
  <span class="k">обрушений держав <b id="cs"></b></span>
  <span class="k">утрачено умений <b id="ls"></b></span>
</header>
<main>
 <div>
  <div class="card">
    <h2>Карта мира</h2>
    <div id="wrap"><canvas id="cv"></canvas><div id="tip"></div></div>
    <div id="bar">
      <button id="pl">▶</button><button id="pv">◀</button><button id="nx">▶|</button>
      <input type="range" id="sl" min="0" value="0">
      <span id="yr"></span>
    </div>
    <div class="note">Клик по карте — что в этой клетке. Цвет — владения народов,
      кружки — города (размер по населению).</div>
  </div>
  <div class="card" style="margin-top:14px">
    <h2>Крупнейшие народы</h2>
    <div style="overflow:auto"><table id="tb"></table></div>
  </div>
  <div class="card" style="margin-top:14px">
    <h2>Ход мира</h2>
    <svg id="ch" viewBox="0 0 800 220" preserveAspectRatio="none"></svg>
    <div class="note" id="chl"></div>
  </div>
 </div>
 <div>
  <div class="card">
    <h2>Летопись</h2>
    <div class="chips" id="cp"></div>
    <div id="log"></div>
  </div>
  <div class="card" style="margin-top:14px">
    <h2>Замечательные люди</h2>
    <div class="ppl" id="pl2"></div>
  </div>
 </div>
</main>
<script>
var BASE="__BASE__", RAW="__DATA__";
function unb64(s){var b=atob(s),a=new Uint8Array(b.length);for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a}
// распаковка gzip своими руками — без DecompressionStream, работает везде
function inflate(d){
  // пропускаем заголовок gzip
  var p=10, f=d[3];
  if(f&4){p+=2+(d[p]|d[p+1]<<8)}
  if(f&8){while(d[p++]);} if(f&16){while(d[p++]);} if(f&2)p+=2;
  return raw_inflate(d,p);
}
function raw_inflate(d,p){
  var out=[],bp=p*8;
  function bit(){var b=(d[bp>>3]>>(bp&7))&1;bp++;return b}
  function bits(n){var v=0;for(var i=0;i<n;i++)v|=bit()<<i;return v}
  function build(l){
    var mx=0,i;for(i=0;i<l.length;i++)if(l[i]>mx)mx=l[i];
    var bl=new Array(mx+1).fill(0);for(i=0;i<l.length;i++)if(l[i])bl[l[i]]++;
    var code=0,nxt=new Array(mx+1).fill(0);
    for(i=1;i<=mx;i++){code=(code+bl[i-1])<<1;nxt[i]=code}
    var map={};for(i=0;i<l.length;i++)if(l[i])map[l[i]+"_"+(nxt[l[i]]++)]=i;
    return {map:map,mx:mx};
  }
  function dec(t){var c=0;for(var n=1;n<=t.mx;n++){c=(c<<1)|bit();var v=t.map[n+"_"+c];if(v!==undefined)return v}return -1}
  var LB=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258],
      LE=[0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0],
      DB=[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577],
      DE=[0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
  for(;;){
    var last=bit(), type=bits(2), lt, dt, i;
    if(type===0){
      bp=(bp+7)&~7; var o=bp>>3, len=d[o]|(d[o+1]<<8); o+=4;
      for(i=0;i<len;i++)out.push(d[o+i]); bp=(o+len)*8;
    } else {
      if(type===1){
        var ll=[];for(i=0;i<144;i++)ll.push(8);for(;i<256;i++)ll.push(9);
        for(;i<280;i++)ll.push(7);for(;i<288;i++)ll.push(8);
        lt=build(ll); var dl=[];for(i=0;i<30;i++)dl.push(5); dt=build(dl);
      } else {
        var hl=bits(5)+257, hd=bits(5)+1, hc=bits(4)+4,
            ord=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15],
            cl=new Array(19).fill(0);
        for(i=0;i<hc;i++)cl[ord[i]]=bits(3);
        var ct=build(cl), lens=[], prev=0;
        while(lens.length<hl+hd){
          var s=dec(ct);
          if(s<16){lens.push(s);prev=s}
          else if(s===16){var r=bits(2)+3;while(r--)lens.push(prev)}
          else if(s===17){var r2=bits(3)+3;while(r2--)lens.push(0)}
          else {var r3=bits(7)+11;while(r3--)lens.push(0)}
        }
        lt=build(lens.slice(0,hl)); dt=build(lens.slice(hl));
      }
      for(;;){
        var s2=dec(lt);
        if(s2===256)break;
        if(s2<256){out.push(s2)}
        else{
          var li=s2-257, len2=LB[li]+bits(LE[li]),
              ds=dec(dt), dist=DB[ds]+bits(DE[ds]), st=out.length-dist;
          for(i=0;i<len2;i++)out.push(out[st+i]);
        }
      }
    }
    if(last)break;
  }
  return new Uint8Array(out);
}
var D=JSON.parse(new TextDecoder().decode(inflate(unb64(RAW))));
var H=D.meta.H, W=D.meta.W, F=D.frames, cur=0, playing=null;
var SC=Math.max(3, Math.floor(1100/W));
var cv=document.getElementById("cv"), cx=cv.getContext("2d");
cv.width=W*SC; cv.height=H*SC;
var img=new Image(); img.src="data:image/png;base64,"+BASE;
function unrle(r){var a=new Uint8Array(H*W),k=0;for(var i=0;i<r.length;i+=2){var v=r[i],n=r[i+1];for(var j=0;j<n;j++)a[k++]=v}return a}
var cache={};
function ownAt(f){if(!cache[f])cache[f]=unrle(F[f].r);return cache[f]}
function draw(){
  var f=F[cur], own=ownAt(cur);
  cx.imageSmoothingEnabled=false;
  cx.drawImage(img,0,0,cv.width,cv.height);
  cx.globalAlpha=.62;
  for(var y=0;y<H;y++)for(var x=0;x<W;x++){
    var v=own[y*W+x]; if(!v)continue;
    cx.fillStyle=f.p[v]; cx.fillRect(x*SC,y*SC,SC,SC);
  }
  cx.globalAlpha=1;
  // границы владений
  cx.strokeStyle="rgba(10,13,18,.55)";cx.lineWidth=1;
  for(var y2=0;y2<H;y2++)for(var x2=0;x2<W;x2++){
    var v2=own[y2*W+x2]; if(!v2)continue;
    var r=own[y2*W+((x2+1)%W)], b=y2+1<H?own[(y2+1)*W+x2]:0;
    cx.beginPath();
    if(r!==v2){cx.moveTo((x2+1)*SC,y2*SC);cx.lineTo((x2+1)*SC,(y2+1)*SC)}
    if(b!==v2){cx.moveTo(x2*SC,(y2+1)*SC);cx.lineTo((x2+1)*SC,(y2+1)*SC)}
    cx.stroke();
  }
  for(var i=0;i<f.c.length;i++){
    var c=f.c[i], rr=Math.max(1.6,Math.log10(Math.max(c[2],10))*1.5);
    cx.beginPath();cx.arc(c[0]*SC+SC/2,c[1]*SC+SC/2,rr*SC/3.2,0,6.284);
    cx.fillStyle="rgba(255,236,190,.92)";cx.fill();
    cx.strokeStyle="rgba(40,25,10,.8)";cx.lineWidth=.8;cx.stroke();
  }
  cx.font=(SC*2.6)+"px sans-serif";cx.fillStyle="#fff8e6";
  cx.shadowColor="#000";cx.shadowBlur=4;
  for(var i2=0;i2<Math.min(7,f.c.length);i2++){
    var c2=f.c[i2]; if(c2[2]<40000)continue;
    cx.fillText(c2[3],c2[0]*SC+SC*1.4,c2[1]*SC+SC*0.6);
  }
  cx.shadowBlur=0;
  document.getElementById("yr").textContent=yrs(f.y);
  var t=D.timeline.reduce(function(a,b){return Math.abs(b[0]-f.y)<Math.abs(a[0]-f.y)?b:a});
  document.getElementById("np").textContent=t[2];
  document.getElementById("pp").textContent=num(t[1]);
  var h="<tr><th>народ</th><th>людей</th><th>хозяйство</th><th>устройство</th><th>знаний</th><th>столица</th><th>боги</th></tr>";
  for(var j=0;j<f.t.length;j++){var r2=f.t[j];
    h+="<tr><td><span class='sw' style='background:"+(f.p[j+1]||"#888")+"'></span>"+esc(r2[0])+
       "</td><td class='n'>"+num(r2[1])+"</td><td>"+esc(r2[2])+"</td><td>"+esc(r2[3])+
       "</td><td class='n'>"+r2[4]+"</td><td>"+esc(r2[5])+"</td><td>"+esc(r2[6])+"</td></tr>"}
  document.getElementById("tb").innerHTML=h;
  renderLog();
}
function yrs(y){return Math.abs(y)+(y<0?" до н. э.":" н. э.")}
function num(n){return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g," ")}
function esc(s){return String(s==null?"":s).replace(/[&<>]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;"}[c]})}

var KR={"origin": "появление", "discovery": "открытие", "diffusion": "заимствование", "loss": "утрата", "city": "город", "build": "постройка", "war": "война", "contact": "встреча", "decision": "решение", "fission": "раскол", "merge": "слияние", "extinction": "исчезновение", "epidemic": "мор", "rule": "правление", "death": "смерть", "reform": "устройство", "mode": "хозяйство", "form": "устройство", "collapse": "обрушение", "religion": "боги", "fork": "ветвление"}, KC={"collapse": "#e5484d", "discovery": "#e8c547", "war": "#d97757", "city": "#4f9ecf", "mode": "#7bc47f", "religion": "#b48ce0", "loss": "#c98a3b", "epidemic": "#8f7fd6", "extinction": "#8a94a6", "origin": "#dfe5ee", "rule": "#9fb3c8", "decision": "#5fbfa8"}, off={};
var cp=document.getElementById("cp");
var kinds=[];D.events.forEach(function(e){if(kinds.indexOf(e[1])<0)kinds.push(e[1])});
kinds.sort();
cp.innerHTML=kinds.map(function(k){return "<span class='chip on' data-k='"+k+"'>"+(KR[k]||k)+"</span>"}).join("");
cp.onclick=function(ev){var t=ev.target;if(!t.dataset.k)return;
  off[t.dataset.k]=!off[t.dataset.k];t.classList.toggle("on");renderLog()};
function renderLog(){
  var y=F[cur].y, near=D.events.filter(function(e){return !off[e[1]]});
  var i0=0;for(var i=0;i<near.length;i++){if(near[i][0]<=y)i0=i}
  var slice=near.slice(Math.max(0,i0-24),i0+26).reverse();
  document.getElementById("log").innerHTML=slice.map(function(e){
    return "<div class='e' data-y='"+e[0]+"'><span class='y'>"+yrs(e[0])+"</span>"+
      "<span class='t' style='background:"+(KC[e[1]]||"#5a6572")+"'>"+(KR[e[1]]||e[1])+"</span>"+
      esc(e[2])+"</div>"}).join("");
}
document.getElementById("log").onclick=function(ev){
  var d=ev.target.closest(".e"); if(!d)return;
  var ty=+d.dataset.y, best=0;
  for(var i=0;i<F.length;i++)if(Math.abs(F[i].y-ty)<Math.abs(F[best].y-ty))best=i;
  cur=best;document.getElementById("sl").value=cur;draw();
};
document.getElementById("pl2").innerHTML=D.people.slice(0,60).map(function(p){
  return "<div class='p1'><b>"+esc(p[0])+"</b> <i>· "+esc(p[1])+" · "+esc(p[4])+
    " · "+yrs(p[2])+"</i>"+(p[5].length?"<ul>"+p[5].map(function(d){return "<li>"+esc(d)+"</li>"}).join("")+"</ul>":"")+"</div>"}).join("");

// графики
(function(){
  var T=D.timeline, sv=document.getElementById("ch"), Wd=800,Hd=220,pad=6;
  function path(get,color,lg){
    var mx=0;T.forEach(function(r){var v=get(r);if(v>mx)mx=v});
    if(mx<=0)return "";
    var y0=T[0][0], y1=T[T.length-1][0];
    var d="";T.forEach(function(r,i){
      var x=pad+(r[0]-y0)/(y1-y0)*(Wd-2*pad);
      var v=get(r); if(lg)v=Math.log10(Math.max(v,1))/Math.log10(mx); else v=v/mx;
      var y=Hd-pad-v*(Hd-2*pad);
      d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1)});
    return "<path d='"+d+"' fill='none' stroke='"+color+"' stroke-width='1.8'/>";
  }
  sv.innerHTML=path(function(r){return r[1]},"#c9a227",true)
             +path(function(r){return r[3]},"#4f9ecf",false)
             +path(function(r){return r[2]},"#7bc47f",false)
             +path(function(r){return r[6]},"#d97757",true);
  document.getElementById("chl").innerHTML=
    "<span style='color:#c9a227'>— население (лог)</span> &nbsp; "+
    "<span style='color:#4f9ecf'>— знаний у сильнейшего</span> &nbsp; "+
    "<span style='color:#7bc47f'>— народов</span> &nbsp; "+
    "<span style='color:#d97757'>— крупнейший город (лог)</span>";
})();

var sl=document.getElementById("sl"); sl.max=F.length-1;
sl.oninput=function(){cur=+sl.value;draw()};
document.getElementById("pv").onclick=function(){cur=Math.max(0,cur-1);sl.value=cur;draw()};
document.getElementById("nx").onclick=function(){cur=Math.min(F.length-1,cur+1);sl.value=cur;draw()};
document.getElementById("pl").onclick=function(){
  var b=this;
  if(playing){clearInterval(playing);playing=null;b.textContent="▶";return}
  b.textContent="❚❚";
  playing=setInterval(function(){cur=(cur+1)%F.length;sl.value=cur;draw()},420);
};
cv.onclick=function(e){
  var r=cv.getBoundingClientRect();
  var x=Math.floor((e.clientX-r.left)/r.width*W), y=Math.floor((e.clientY-r.top)/r.height*H);
  var own=ownAt(cur), v=own[y*W+x], f=F[cur];
  var nm="ничья земля";
  if(v){var i=0;for(var j=0;j<f.t.length;j++){} nm="владение (цвет "+f.p[v]+")";
    for(var j2=0;j2<f.t.length;j2++)if(f.p[j2+1]===f.p[v]){nm=f.t[j2][0]+" — "+f.t[j2][2];break}}
  var city="";
  for(var c=0;c<f.c.length;c++)if(Math.abs(f.c[c][0]-x)<1&&Math.abs(f.c[c][1]-y)<1)
    city="<br>город <b>"+esc(f.c[c][3])+"</b>, "+num(f.c[c][2])+" жителей";
  var t=document.getElementById("tip");
  t.innerHTML="<b>"+yrs(f.y)+"</b><br>"+esc(nm)+city;
  t.style.display="block";
  t.style.left=Math.min(r.width-250,(e.clientX-r.left)+10)+"px";
  t.style.top=((e.clientY-r.top)+10)+"px";
  setTimeout(function(){t.style.display="none"},4200);
};
document.getElementById("sd").textContent=D.meta.seed;
var S=D.meta.stats;
document.getElementById("ds").textContent=S.discoveries;
document.getElementById("ws").textContent=S.wars;
document.getElementById("cs").textContent=S.collapses;
document.getElementById("ls").textContent=S.losses;
img.onload=function(){draw()};
if(img.complete)draw();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser("terra.compact")
    ap.add_argument("run")
    ap.add_argument("-o", "--out")
    ap.add_argument("--frames", type=int, default=46)
    ap.add_argument("--events", type=int, default=900)
    a = ap.parse_args()
    p = build_compact(a.run, a.out, a.frames, a.events)
    print(f"{p} — {p.stat().st_size/1048576:.2f} МБ")


if __name__ == "__main__":
    main()
