# CSS, разметка и JS-приложение обозревателя твина (twin/view.py).
# Всё на ванильном three.js (вшитая сборка); данные приходят из TWIN_GZ.

CSS = """
html,body{margin:0;height:100%;overflow:hidden;background:#0b0e13;
  font:14px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif;color:#e8e6df}
#c3d{position:fixed;inset:0}
.panel{position:fixed;background:rgba(12,16,22,.82);backdrop-filter:blur(6px);
  border:1px solid rgba(255,255,255,.09);border-radius:10px;padding:10px 14px;
  z-index:5}
#hud{left:14px;top:14px;max-width:340px}
#hud h1{font-size:16px;margin:0 0 4px;font-weight:600}
#hud .dim{color:#9aa3ad;font-size:12px}
#hud .wx{margin-top:6px;font-size:13px}
#ctl{right:14px;top:14px;text-align:right}
#ctl input[type=range]{width:150px;vertical-align:middle}
#ctl label{font-size:12px;color:#9aa3ad}
#help{left:14px;bottom:14px;font-size:12px;color:#9aa3ad}
#info{right:14px;bottom:14px;max-width:300px;display:none}
#info b{font-size:14px}
#info .dim{color:#9aa3ad;font-size:12px}
#boot{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  flex-direction:column;background:#0b0e13;z-index:9;transition:opacity .5s}
#boot.gone{opacity:0;pointer-events:none}
#boot .t{color:#9aa3ad;margin-top:10px;font-size:13px}
#err{display:none;position:fixed;left:50%;top:40%;transform:translate(-50%,-50%);
  background:#3a1518;border:1px solid #a33;border-radius:10px;padding:16px 20px;
  z-index:10;max-width:70%}
.spin{width:38px;height:38px;border-radius:50%;border:3px solid #22303c;
  border-top-color:#7ab0d6;animation:sp 1s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
"""

BODY = """
<canvas id="c3d"></canvas>
<div id="boot"><div class="spin"></div><div class="t" id="bootT">распаковка данных…</div></div>
<div id="err" class="panel"></div>
<div id="hud" class="panel">
  <h1 id="hTitle"></h1>
  <div class="dim" id="hMeta"></div>
  <div class="wx" id="hWx"></div>
  <div class="dim" id="hSrc" style="margin-top:6px"></div>
</div>
<div id="ctl" class="panel">
  <label>время суток <input type="range" id="tod" min="5.5" max="20.5" step="0.1" value="15"></label>
  <span id="todV" class="dim">15:00</span><br>
  <label>год <input type="range" id="yr" min="1850" max="2026" step="1" value="2026"></label>
  <b id="yrV">сегодня</b>
  <div class="dim" id="yrN"></div>
  <div class="dim" id="yrNote" style="display:none;max-width:230px;margin-top:4px"></div>
  <label style="user-select:none"><input type="checkbox" id="unk" checked> здания без года</label><br>
  <label style="user-select:none"><input type="checkbox" id="lbl" checked> подписи мест</label>
</div>
<div id="help" class="panel">ЛКМ-тянуть — осмотреться · WASD — лететь · Q/E — вниз/вверх ·
 Shift — быстрее · колесо — скорость · клик по зданию — что это</div>
<div id="info" class="panel"><b id="iName"></b><div class="dim" id="iMeta"></div></div>
"""

APP_JS = r"""
'use strict';
function $(id){ return document.getElementById(id); }
function fail(e){
  var el = $('err');
  el.style.display = 'block';
  el.innerHTML = '<b>Не удалось построить сцену.</b><br>' +
    String(e && e.message || e).replace(/</g,'&lt;');
  $('boot').classList.add('gone');
  throw e;
}
function b64bytes(s){
  var bin = atob(s), n = bin.length, a = new Uint8Array(n);
  for (var i = 0; i < n; i++) a[i] = bin.charCodeAt(i);
  return a;
}
function ungzip(b64){
  var u8 = b64bytes(b64);
  if (typeof DecompressionStream === 'undefined')
    return Promise.reject(new Error('браузер не умеет DecompressionStream'));
  var st = new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'));
  var rd = st.getReader(), parts = [], total = 0;
  function pump(){
    return rd.read().then(function(r){
      if (r.done){
        var all = new Uint8Array(total), o = 0;
        for (var i = 0; i < parts.length; i++){ all.set(parts[i], o); o += parts[i].length; }
        return JSON.parse(new TextDecoder('utf-8').decode(all));
      }
      parts.push(r.value); total += r.value.length;
      return pump();
    });
  }
  return pump();
}
function boot(t){ $('bootT').textContent = t; return new Promise(function(res){
  requestAnimationFrame(function(){ requestAnimationFrame(res); }); }); }

// ── глобальное состояние ────────────────────────────────────────────────────
var S = null;                       // данные сцены
var renderer, scene, camera, sun, hemi, amb;
var TER = null;                     // {elev:Int16Array, surf, nx,nz,x0,z0,dx,dz}
var bigMesh = null, bigOwner = null, instMesh = null;
var labels = [];
var U_YEAR = { value: 3000 };       // общий uniform машины времени
var U_UNK = { value: 1 };           // показывать ли здания без года в реестре
var PAL = [                         // цвета классов зданий
  [0.78, 0.72, 0.62],   // жильё — тёплый песочный
  [0.62, 0.68, 0.74],   // коммерция — голубо-серый
  [0.58, 0.56, 0.52],   // промышленность
  [0.80, 0.76, 0.68],   // храмы и гражданские
  [0.72, 0.62, 0.55],   // школы/больницы
  [0.68, 0.66, 0.62]    // прочее
];

// Здание, построенное позже выбранного года, схлопывается в точку прямо в
// вершинном шейдере: один uniform на движение слайдера, геометрия не трогается.
// Год 0 — реестр молчит; такие здания показываем или прячем по выбору игрока.
function yearFiltered(mat){
  mat.onBeforeCompile = function(shader){
    shader.uniforms.uYear = U_YEAR;
    shader.uniforms.uUnk = U_UNK;
    shader.vertexShader =
      'attribute float aYear;\nuniform float uYear;\nuniform float uUnk;\n'
      + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      '#include <begin_vertex>\n'
      + '  bool tooNew = aYear > uYear + 0.5;\n'
      + '  bool hidUnk = aYear < 0.5 && uUnk < 0.5;\n'
      + '  if (tooNew || hidUnk) transformed = vec3(0.0);');
  };
  return mat;
}
function builtBy(year, y){
  if (!y) return U_UNK.value > 0.5;
  return y <= year;
}

function gH(x, z){                  // высота рельефа в точке (м)
  var fx = (x*10 - TER.x0) / TER.dx, fz = (z*10 - TER.z0) / TER.dz;
  var j = Math.max(0, Math.min(TER.nx - 2, Math.floor(fx)));
  var i = Math.max(0, Math.min(TER.nz - 2, Math.floor(fz)));
  var tx = Math.max(0, Math.min(1, fx - j)), tz = Math.max(0, Math.min(1, fz - i));
  var e = TER.elev, n = TER.nx;
  var a = e[i*n+j], b = e[i*n+j+1], c = e[(i+1)*n+j], d = e[(i+1)*n+j+1];
  return (a*(1-tx)*(1-tz) + b*tx*(1-tz) + c*(1-tx)*tz + d*tx*tz) / 10;
}

// ── рельеф ──────────────────────────────────────────────────────────────────
function buildTerrain(){
  var t = S.terrain;
  TER = { elev: new Int16Array(t.elev), surf: new Uint8Array(t.surf),
          nx: t.nx, nz: t.nz, x0: t.x0, z0: t.z0, dx: t.dx, dz: t.dz };
  var nx = t.nx, nz = t.nz;
  var pos = new Float32Array(nx*nz*3), col = new Float32Array(nx*nz*3);
  var k = 0;
  for (var i = 0; i < nz; i++){
    for (var j = 0; j < nx; j++){
      var e = TER.elev[i*nx+j] / 10;
      pos[k]   = (t.x0 + j*t.dx) / 10;
      pos[k+1] = e;
      pos[k+2] = (t.z0 + i*t.dz) / 10;
      var s = TER.surf[i*nx+j];
      var r, g, b;
      if (s === 3){ r = 0.16; g = 0.24; b = 0.30; }              // дно
      else if (s === 1){ r = 0.30; g = 0.44; b = 0.24; }         // зелень
      else if (s === 2){ r = 0.76; g = 0.70; b = 0.55; }         // песок
      else {                                                     // город/земля
        var h01 = Math.max(0, Math.min(1, e/260));
        r = 0.44 + 0.14*h01; g = 0.43 + 0.11*h01; b = 0.40 + 0.08*h01;
      }
      col[k] = r; col[k+1] = g; col[k+2] = b;
      k += 3;
    }
  }
  var idx = new Uint32Array((nx-1)*(nz-1)*6), q = 0;
  for (var i2 = 0; i2 < nz-1; i2++){
    for (var j2 = 0; j2 < nx-1; j2++){
      var a2 = i2*nx+j2, b2 = a2+1, c2 = a2+nx, d2 = c2+1;
      idx[q++] = a2; idx[q++] = c2; idx[q++] = b2;
      idx[q++] = b2; idx[q++] = c2; idx[q++] = d2;
    }
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  geo.computeVertexNormals();
  var mat = new THREE.MeshLambertMaterial({ vertexColors: true });
  scene.add(new THREE.Mesh(geo, mat));

  // водная гладь: океан и залив
  var wgeo = new THREE.PlaneGeometry(60000, 60000);
  var wmat = new THREE.MeshPhongMaterial({ color: 0x2e6f9e, transparent: true,
    opacity: 0.93, shininess: 90, specular: 0x557799 });
  var wm = new THREE.Mesh(wgeo, wmat);
  wm.rotation.x = -Math.PI/2;
  wm.position.y = 0.35;
  scene.add(wm);
}

// ── здания ──────────────────────────────────────────────────────────────────
function shade(c, f){ return [c[0]*f, c[1]*f, c[2]*f]; }
function buildBig(){
  var pos = [], col = [], owner = [], yrs = [];
  for (var bi = 0; bi < S.big.length; bi++){
    var b = S.big[bi];
    var ring = b.p, n = ring.length;
    if (n < 3) continue;
    var by = b.y || 0;
    var v0 = pos.length / 3;
    var g = b.g/10, h = b.h/10, top = g + h;
    var base = PAL[b.c] || PAL[5];
    var vec2 = [];
    for (var i = 0; i < n; i++) vec2.push(new THREE.Vector2(ring[i][0]/10, ring[i][1]/10));
    // крыша: triangulateShape МУТИРУЕТ вход (снимает замыкающие дубли),
    // поэтому триангулируем копию, а стены строим по исходному кольцу
    var triPts = vec2.slice(), tris;
    try { tris = THREE.ShapeUtils.triangulateShape(triPts, []); }
    catch(e){ tris = []; }
    var rc = shade(base, 0.82);
    for (var ti = 0; ti < tris.length; ti++){
      var tr = tris[ti];
      var pa = triPts[tr[0]], pb = triPts[tr[1]], pc = triPts[tr[2]];
      if (!pa || !pb || !pc) continue;
      pos.push(pa.x, top, pa.y, pb.x, top, pb.y, pc.x, top, pc.y);
      col.push(rc[0], rc[1], rc[2], rc[0], rc[1], rc[2], rc[0], rc[1], rc[2]);
      owner.push(bi);
    }
    // стены
    for (var i2 = 0; i2 < n; i2++){
      var p1 = vec2[i2], p2 = vec2[(i2+1)%n];
      var dx = p2.x - p1.x, dz = p2.y - p1.y;
      var len = Math.sqrt(dx*dx + dz*dz) || 1;
      // освещённость грани: псевдосолнце с юго-запада
      var f = 0.62 + 0.30 * Math.max(0, (-dz/len)*0.8 + (dx/len)*0.4);
      var wc = shade(base, f);
      pos.push(p1.x, g, p1.y,  p2.x, g, p2.y,  p2.x, top, p2.y);
      pos.push(p1.x, g, p1.y,  p2.x, top, p2.y,  p1.x, top, p1.y);
      for (var v2 = 0; v2 < 6; v2++) col.push(wc[0], wc[1], wc[2]);
      owner.push(bi); owner.push(bi);
    }
    for (var v3 = v0; v3 < pos.length / 3; v3++) yrs.push(by);
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(col), 3));
  geo.setAttribute('aYear', new THREE.BufferAttribute(new Float32Array(yrs), 1));
  geo.computeVertexNormals();
  bigOwner = owner;
  var mat = yearFiltered(new THREE.MeshLambertMaterial({
    vertexColors: true, side: THREE.DoubleSide }));
  bigMesh = new THREE.Mesh(geo, mat);
  scene.add(bigMesh);
}
function buildSmall(){
  var arr = S.small, n = arr.length;
  if (!n) return;
  var geo = new THREE.BoxGeometry(1, 1, 1);
  var yrs = new Float32Array(n);
  for (var yi = 0; yi < n; yi++) yrs[yi] = arr[yi][8] || 0;
  geo.setAttribute('aYear', new THREE.InstancedBufferAttribute(yrs, 1));
  var mat = yearFiltered(new THREE.MeshLambertMaterial());
  instMesh = new THREE.InstancedMesh(geo, mat, n);
  var m = new THREE.Matrix4(), q = new THREE.Quaternion(),
      p = new THREE.Vector3(), sc = new THREE.Vector3(),
      up = new THREE.Vector3(0, 1, 0), c = new THREE.Color();
  for (var i = 0; i < n; i++){
    var s = arr[i];
    var cx = s[0]/10, cz = s[1]/10, hw = s[2]/10, hd = s[3]/10;
    var ang = -s[4] * Math.PI/180, h = s[5]/10, g = s[6]/10;
    p.set(cx, g + h/2, cz);
    q.setFromAxisAngle(up, ang);
    sc.set(Math.max(hw*2, 1.5), h, Math.max(hd*2, 1.5));
    m.compose(p, q, sc);
    instMesh.setMatrixAt(i, m);
    var base = PAL[s[7]] || PAL[5];
    var f = 0.86 + 0.14 * (((i * 2654435761) >>> 24) / 255);
    c.setRGB(base[0]*f, base[1]*f, base[2]*f);
    instMesh.setColorAt(i, c);
  }
  instMesh.instanceMatrix.needsUpdate = true;
  if (instMesh.instanceColor) instMesh.instanceColor.needsUpdate = true;
  scene.add(instMesh);
}

// ── дороги ──────────────────────────────────────────────────────────────────
function roadColor(w){
  if (w >= 110) return [0.62, 0.63, 0.65];
  if (w >= 70)  return [0.44, 0.45, 0.47];
  if (w >= 45)  return [0.33, 0.34, 0.36];
  return [0.52, 0.48, 0.42];
}
function buildRoads(){
  var pos = [], col = [];
  for (var ri = 0; ri < S.roads.length; ri++){
    var rd = S.roads[ri], w = rd.w/20, pts = rd.p;
    var c = roadColor(rd.w);
    for (var i = 0; i < pts.length - 1; i++){
      var x1 = pts[i][0]/10,  z1 = pts[i][1]/10;
      var x2 = pts[i+1][0]/10, z2 = pts[i+1][1]/10;
      var dx = x2-x1, dz = z2-z1, len = Math.sqrt(dx*dx+dz*dz);
      if (len < 0.01) continue;
      var px = -dz/len*w, pz = dx/len*w;
      var y1 = gH(x1, z1) + 0.9, y2 = gH(x2, z2) + 0.9;
      pos.push(x1+px, y1, z1+pz,  x1-px, y1, z1-pz,  x2+px, y2, z2+pz);
      pos.push(x1-px, y1, z1-pz,  x2-px, y2, z2-pz,  x2+px, y2, z2+pz);
      for (var v = 0; v < 6; v++) col.push(c[0], c[1], c[2]);
    }
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(col), 3));
  var mat = new THREE.MeshBasicMaterial({ vertexColors: true });
  scene.add(new THREE.Mesh(geo, mat));
}

// ── озёра ───────────────────────────────────────────────────────────────────
function buildLakes(){
  for (var li = 0; li < S.lakes.length; li++){
    var lk = S.lakes[li];
    var sh = new THREE.Shape();
    for (var i = 0; i < lk.p.length; i++){
      var x = lk.p[i][0]/10, z = lk.p[i][1]/10;
      if (i === 0) sh.moveTo(x, z); else sh.lineTo(x, z);
    }
    var geo = new THREE.ShapeGeometry(sh);
    geo.rotateX(Math.PI/2);
    var mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
      color: 0x2e6f9e, transparent: true, opacity: 0.9, shininess: 80,
      side: THREE.DoubleSide }));
    mesh.position.y = lk.g/10;
    scene.add(mesh);
  }
}

// ── подписи ─────────────────────────────────────────────────────────────────
function makeLabel(text, x, y, z, big){
  var cv = document.createElement('canvas');
  var px = big ? 30 : 22;
  var ctx = cv.getContext('2d');
  ctx.font = '600 ' + px + 'px -apple-system, Segoe UI, sans-serif';
  var w = Math.ceil(ctx.measureText(text).width) + 22;
  cv.width = w; cv.height = px + 18;
  ctx = cv.getContext('2d');
  ctx.font = '600 ' + px + 'px -apple-system, Segoe UI, sans-serif';
  ctx.fillStyle = 'rgba(10,14,18,0.66)';
  ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.fillStyle = '#f0ede4';
  ctx.fillText(text, 11, px + 4);
  var tex = new THREE.Texture(cv);
  tex.needsUpdate = true;
  var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex,
    depthTest: false, transparent: true }));
  var k = big ? 0.9 : 0.62;
  sp.scale.set(cv.width * k, cv.height * k, 1);
  sp.position.set(x, y, z);
  scene.add(sp);
  labels.push(sp);
  return sp;
}
function buildLabels(){
  var named = [];
  for (var i = 0; i < S.big.length; i++)
    if (S.big[i].n) named.push(S.big[i]);
  named.sort(function(a, b){ return b.h - a.h; });
  for (var j = 0; j < Math.min(24, named.length); j++){
    var b = named[j];
    var cx = 0, cz = 0;
    for (var v = 0; v < b.p.length; v++){ cx += b.p[v][0]; cz += b.p[v][1]; }
    cx /= b.p.length * 10; cz /= b.p.length * 10;
    var sp = makeLabel(b.n, cx, b.g/10 + b.h/10 + 26, cz, true);
    sp.userData.year = b.y || 0;      // подпись гаснет вместе со зданием
  }
  for (var k2 = 0; k2 < Math.min(20, S.pois.length); k2++){
    var p = S.pois[k2];
    makeLabel(p[2], p[0]/10, gH(p[0]/10, p[1]/10) + 16, p[1]/10, false);
  }
}

// ── машина времени ──────────────────────────────────────────────────────────
function applyYear(){
  var y = parseInt($('yr').value, 10);
  var tm = S.head.time_machine || {};
  U_YEAR.value = y;
  U_UNK.value = $('unk').checked ? 1 : 0;
  var standing = 0;
  for (var i = 0; i < S.big.length; i++)
    if (builtBy(y, S.big[i].y)) standing++;
  for (var j = 0; j < S.small.length; j++)
    if (builtBy(y, S.small[j][8])) standing++;
  $('yrV').textContent = y >= (tm.max || 2026) ? 'сегодня' : String(y);
  $('yrN').textContent = 'зданий ' + standing.toLocaleString('ru-RU')
    + (tm.unknown ? ' · без года в реестре ' + tm.unknown.toLocaleString('ru-RU') : '');
  var note = $('yrNote'), txt = '';
  if (y < 1906){
    txt = 'до пожара 1906 года: центр отстроен заново, у его зданий год 1906 '
        + 'и позже — этот слой достраивается по картам Сэнборна';
  } else if (y <= 1901 + 5 && tm.placeholder_1900){
    txt = 'в реестре ' + tm.placeholder_1900.toLocaleString('ru-RU')
        + ' участков помечены 1900 годом — это отметка «старое», а не дата';
  }
  note.textContent = txt;
  note.style.display = txt ? 'block' : 'none';
  for (var k = 0; k < labels.length; k++){
    var want = $('lbl').checked && builtBy(y, labels[k].userData.year || 0);
    labels[k].visible = want;
  }
}

// ── солнце и небо ───────────────────────────────────────────────────────────
function applyTime(){
  var t = parseFloat($('tod').value);
  $('todV').textContent = String(Math.floor(t)).padStart(2, '0') + ':' +
    String(Math.round((t % 1) * 60)).padStart(2, '0');
  var f = (t - 5.5) / 15;                       // 0..1 за день
  var el = Math.sin(f * Math.PI) * 1.08;        // высота солнца
  var az = (0.25 + 0.5 * f) * 2 * Math.PI;      // восток -> запад
  var sunV = new THREE.Vector3(Math.cos(az) * Math.cos(el * Math.PI/2), Math.sin(el * Math.PI/2),
                               -Math.sin(az) * Math.cos(el * Math.PI/2));
  sun.position.copy(sunV.multiplyScalar(20000));
  var day = Math.max(0, Math.min(1, el * 1.6));
  var warm = Math.max(0, 1 - el * 2.2);
  sun.color.setRGB(1.0, 0.96 - warm * 0.3, 0.88 - warm * 0.45);
  sun.intensity = 0.4 + 2.0 * day;
  hemi.intensity = 0.25 + 0.75 * day;
  var sky = new THREE.Color().setRGB(
    0.34 + 0.28 * day + warm * 0.24 * day,
    0.44 + 0.28 * day - warm * 0.06 * day,
    0.62 + 0.24 * day - warm * 0.24 * day);
  if (day <= 0.02) sky.setRGB(0.05, 0.06, 0.10);
  scene.background = sky;
  scene.fog.color.copy(sky);
}

// ── управление ──────────────────────────────────────────────────────────────
var yaw = -2.25, pitch = -0.34, speed = 220;
var keys = {};
function setupControls(){
  var cv = renderer.domElement, drag = false, lx = 0, ly = 0;
  cv.addEventListener('mousedown', function(e){ drag = true; lx = e.clientX; ly = e.clientY; });
  window.addEventListener('mouseup', function(){ drag = false; });
  window.addEventListener('mousemove', function(e){
    if (!drag) return;
    yaw   -= (e.clientX - lx) * 0.004;
    pitch -= (e.clientY - ly) * 0.004;
    pitch = Math.max(-1.45, Math.min(1.45, pitch));
    lx = e.clientX; ly = e.clientY;
  });
  window.addEventListener('keydown', function(e){ keys[e.code] = true; });
  window.addEventListener('keyup', function(e){ keys[e.code] = false; });
  cv.addEventListener('wheel', function(e){
    speed *= (e.deltaY > 0 ? 0.85 : 1.18);
    speed = Math.max(15, Math.min(3000, speed));
  }, { passive: true });
  cv.addEventListener('click', onPick);
  $('tod').addEventListener('input', applyTime);
  $('yr').addEventListener('input', applyYear);
  $('lbl').addEventListener('change', applyYear);
  $('unk').addEventListener('change', applyYear);
}
function stepCamera(dt){
  var dir = new THREE.Vector3(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch),
                              Math.cos(yaw) * Math.cos(pitch));
  var right = new THREE.Vector3(Math.sin(yaw - Math.PI/2), 0, Math.cos(yaw - Math.PI/2));
  var v = speed * dt * (keys['ShiftLeft'] || keys['ShiftRight'] ? 3.2 : 1);
  if (keys['KeyW']) camera.position.addScaledVector(dir, v);
  if (keys['KeyS']) camera.position.addScaledVector(dir, -v);
  if (keys['KeyA']) camera.position.addScaledVector(right, -v);
  if (keys['KeyD']) camera.position.addScaledVector(right, v);
  if (keys['KeyQ']) camera.position.y -= v;
  if (keys['KeyE']) camera.position.y += v;
  var minY = gH(camera.position.x, camera.position.z) + 2.2;
  if (camera.position.y < minY) camera.position.y = minY;
  camera.lookAt(camera.position.clone().add(dir));
}

// ── клик по зданию ──────────────────────────────────────────────────────────
var ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
function onPick(e){
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  ray.setFromCamera(mouse, camera);
  var meshes = [];
  if (bigMesh) meshes.push(bigMesh);
  if (instMesh) meshes.push(instMesh);
  // луч не знает про фильтр года (он живёт в шейдере) — отсеиваем сами
  var hits = ray.intersectObjects(meshes, false).filter(function(h){
    var y = parseInt($('yr').value, 10);
    if (h.object === bigMesh && bigOwner){
      var b = S.big[bigOwner[h.faceIndex]];
      return b && builtBy(y, b.y);
    }
    if (h.object === instMesh){
      var s = S.small[h.instanceId];
      return s && builtBy(y, s[8]);
    }
    return true;
  });
  if (!hits.length){ $('info').style.display = 'none'; return; }
  var h = hits[0], name = '', meta = '';
  if (h.object === bigMesh && bigOwner){
    var b = S.big[bigOwner[h.faceIndex]];
    if (!b) return;
    name = b.n || 'Здание';
    meta = 'высота ' + (b.h/10).toFixed(0) + ' м';
    meta += b.y ? (' · построено ' + b.y + (b.yt ? ' (вывод: нет в лидарной '
                   + 'съёмке города, значит новее её)' : ''))
                : ' · года постройки нет в реестре';
    var src = b.id.indexOf('sfbld:') === 0 ? 'DataSF (лидар)' : 'OpenStreetMap';
    meta += '<br><span style="color:#88929c">' + b.id + ' · ' + src + '</span>';
  } else if (h.object === instMesh){
    var s = S.small[h.instanceId];
    if (!s) return;
    name = 'Здание';
    meta = 'высота ~' + (s[5]/10).toFixed(0) + ' м'
         + (s[8] ? ' · построено ' + s[8] : ' · года постройки нет в реестре')
         + '<br><span style="color:#88929c">DataSF · лидар</span>';
  }
  $('iName').textContent = name;
  $('iMeta').innerHTML = meta;
  $('info').style.display = 'block';
}

// ── HUD ─────────────────────────────────────────────────────────────────────
function fillHud(){
  var h = S.head;
  $('hTitle').textContent = h.title;
  var c = h.counts;
  $('hMeta').textContent = 'слепок настоящего от ' + h.date + ' · зданий ' +
    (c.big + c.small).toLocaleString('ru-RU') + ' · дорог ' +
    c.roads.toLocaleString('ru-RU');
  var w = h.weather || {};
  var parts = [];
  if (w.temp_c != null) parts.push(w.temp_c + ' °C');
  if (w.wind_kmh != null) parts.push('ветер ' + w.wind_kmh + ' км/ч');
  if (w.text) parts.push(w.text);
  $('hWx').textContent = parts.length ? 'Сейчас: ' + parts.join(' · ') :
    'Погода: нет данных';
  var src = [];
  for (var i = 0; i < (h.sources || []).length; i++) src.push(h.sources[i].name);
  $('hSrc').textContent = 'Данные: ' + src.join(' · ');
}

// ── запуск ──────────────────────────────────────────────────────────────────
function start(){
  renderer = new THREE.WebGLRenderer({ canvas: $('c3d'), antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(window.innerWidth, window.innerHeight);
  scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x9db8cc, 4000, 26000);
  camera = new THREE.PerspectiveCamera(58, window.innerWidth/window.innerHeight, 1, 90000);
  camera.position.set(3400, 520, -900);
  sun = new THREE.DirectionalLight(0xffffff, 2.0);
  scene.add(sun);
  hemi = new THREE.HemisphereLight(0xbcd3e8, 0x4a4238, 0.9);
  scene.add(hemi);
  window.addEventListener('resize', function(){
    camera.aspect = window.innerWidth/window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  var chain = Promise.resolve();
  chain = chain.then(function(){ return boot('рельеф города…'); }).then(buildTerrain);
  chain = chain.then(function(){ return boot('крупные здания…'); }).then(buildBig);
  chain = chain.then(function(){ return boot('квартальная застройка…'); }).then(buildSmall);
  chain = chain.then(function(){ return boot('улицы…'); }).then(buildRoads);
  chain = chain.then(function(){ return boot('вода и парки…'); }).then(buildLakes);
  chain = chain.then(function(){ return boot('подписи…'); }).then(buildLabels);
  chain = chain.then(function(){
    var tm = S.head.time_machine;
    if (tm){
      $('yr').min = tm.min; $('yr').max = tm.max; $('yr').value = tm.max;
    }
    fillHud(); setupControls(); applyTime(); applyYear();
    $('boot').classList.add('gone');
    var clock = new THREE.Clock();
    (function tick(){
      requestAnimationFrame(tick);
      stepCamera(Math.min(clock.getDelta(), 0.1));
      renderer.render(scene, camera);
    })();
    window.TWIN_READY = true;
  });
  return chain;
}

ungzip(TWIN_GZ).then(function(data){ S = data; return start(); }).catch(fail);
"""
