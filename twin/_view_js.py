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
#modes{left:50%;bottom:14px;transform:translateX(-50%);display:flex;gap:6px;
  align-items:center;padding:7px 9px;flex-wrap:wrap;justify-content:center}
#modes button{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.10);
  color:#cfd6dd;border-radius:7px;padding:5px 11px;font:inherit;font-size:12px;
  cursor:pointer}
#modes button:hover{background:rgba(255,255,255,.12)}
#modes button.on{background:#2f6f4f;border-color:#4aa070;color:#f0fff5}
#modes .k{opacity:.45;margin-left:5px;font-size:11px}
#modes .dim{width:100%;text-align:center;font-size:11px;color:#8c96a1;margin-top:2px}
#live{right:14px;top:196px;width:216px;padding:9px 12px}
#live .hd{font-weight:600;margin-bottom:5px}
#live label{display:block;font-size:12.5px;margin:3px 0;user-select:none;cursor:pointer}
#live .n{color:#8c96a1;font-size:11px}
#live .dim{color:#8c96a1;font-size:11px;margin-top:5px}
#live input[type=range]{width:96px;vertical-align:middle}
#tbar{right:14px;bottom:120px;width:190px;padding:8px 10px}
#tbar .ramp{height:11px;border-radius:3px;background:linear-gradient(90deg,
  #00001a 0%, #470073 25%, #d92433 50%, #ff8c00 72%, #ffee59 90%, #fff 100%)}
#tbar .tick{display:flex;justify-content:space-between;font-size:11px;
  color:#c3ccd4;margin-top:3px}
#tbar .dim{font-size:11px;color:#8c96a1;margin-top:2px;text-align:center}
#info{right:14px;bottom:14px;max-width:330px;display:none}
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
  <label style="user-select:none"><input type="checkbox" id="lbl" checked> подписи мест</label><br>
  <label style="user-select:none"><input type="checkbox" id="aer" checked> аэрофотоснимок</label>
  <div class="dim" id="aerSrc" style="font-size:11px"></div>
</div>
<div id="live" class="panel">
  <div class="hd">живой слой <span class="dim" id="liveStamp"></span></div>
  <label><input type="checkbox" id="lAir" checked> борта <span class="n" id="nAir"></span></label>
  <label><input type="checkbox" id="lSat" checked> спутники <span class="n" id="nSat"></span></label>
  <label><input type="checkbox" id="lQ"> толчки за месяц <span class="n" id="nQ"></span></label>
  <label><input type="checkbox" id="lCam"> дорожные камеры <span class="n" id="nCam"></span></label>
  <label><input type="checkbox" id="lRes"> жители <span class="n" id="nRes"></span></label>
  <div class="dim" id="tideTxt"></div>
  <label class="dim">время ×<span id="spdV">1</span>
    <input type="range" id="spd" min="0" max="3" step="1" value="0"></label>
</div>
<div id="tbar" class="panel" style="display:none">
  <div class="ramp"></div>
  <div class="tick"><span id="tLo"></span><span id="tMid"></span><span id="tHi"></span></div>
  <div class="dim">температура поверхности</div>
</div>
<div id="modes" class="panel">
  <button class="on" onclick="setMode(0)">оптика <span class="k">1</span></button>
  <button onclick="setMode(1)">ПНВ <span class="k">2</span></button>
  <button onclick="setMode(2)">тепловизор <span class="k">3</span></button>
  <button onclick="setMode(3)">ЭЛТ <span class="k">4</span></button>
  <div class="dim" id="modeHint"></div>
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
var renderer, scene, camera, sun, hemi, amb, waterMesh;
var groundMesh = null, matClasses = null, matAerial = null, roadMesh = null;
var TER = null;                     // {elev:Int16Array, surf, nx,nz,x0,z0,dx,dz}
var bigMesh = null, bigOwner = null, instMesh = null;
var labels = [];
var U_YEAR = { value: 3000 };       // общий uniform машины времени
var U_UNK = { value: 1 };           // показывать ли здания без года в реестре

// ── сенсоры ─────────────────────────────────────────────────────────────────
// 0 — глаз, 1 — ПНВ, 2 — тепловизор, 3 — ЭЛТ-монитор.
// Тепловизор считает ТЕМПЕРАТУРУ поверхности, а не красит яркость картинки:
// у каждого материала свои альбедо, тепловая инерция и собственное тепло,
// солнце греет по углу падения, ночью отдаёт запасённое за день.
var U_MODE = { value: 0 };
var SUN_WORLD = null;               // направление на солнце в мире (задаётся в start)
var U_SUNV = { value: null };       // оно же в СИСТЕМЕ КАМЕРЫ (пересчёт покадрово)
var U_SUNEL = { value: 0.0 };       // высота солнца 0..1
var U_STORED = { value: 0.0 };      // суточный запас тепла в материалах 0..1
var U_AIRT = { value: 14.0 };
var U_NIGHT = { value: 0.0 };   // 0 день, 1 ночь — для света в окнах       // температура воздуха, °C (данные NOAA)
var MODE_NAMES = ['оптика', 'ПНВ', 'тепловизор', 'ЭЛТ'];

// Классы материалов для теплового расчёта (атрибут aMat):
// 0 земля/город, 1 зелень, 2 песок, 3 вода, 4 асфальт, 10+use — здания.
var M_GROUND = 0, M_GREEN = 1, M_SAND = 2, M_WATER = 3, M_ASPHALT = 4, M_BLD = 10;

var THERMAL_GLSL = [
'void matProps(float m, out float albedo, out float inertia, out float internal){',
'  if (m > 9.5){',                       // здание: внутреннее тепло по назначению
'    float use = m - 10.0;',
'    albedo = 0.30; inertia = 0.78;',
'    internal = use < 0.5 ? 2.5 :',      // жильё
'               use < 1.5 ? 5.2 :',      // контора: вентиляция и серверы
'               use < 2.5 ? 6.5 :',      // промышленность — самая горячая
'               use < 3.5 ? 3.0 :',      // гражданские здания
'               use < 4.5 ? 3.6 : 2.4;', // школы, больницы / прочее
'  } else if (m > 3.5){ albedo = 0.10; inertia = 0.88; internal = 0.0;',
'  } else if (m > 2.5){ albedo = 0.06; inertia = 0.99; internal = 0.0;',
'  } else if (m > 1.5){ albedo = 0.40; inertia = 0.32; internal = 0.0;',
'  } else if (m > 0.5){ albedo = 0.20; inertia = 0.28; internal = -2.2;',
'  } else { albedo = 0.22; inertia = 0.62; internal = 0.6; }',
'}',
'float surfTemp(float m, vec3 nrm, vec3 sunV, float sunEl, float stored, float airT){',
'  float albedo, inertia, internal;',
'  matProps(m, albedo, inertia, internal);',
'  float incid = max(0.0, dot(normalize(nrm), sunV));',
'  float gain = 20.0 * sunEl * (1.0 - albedo) * incid;',
'  float held = 9.0 * inertia * stored;',
'  float cool = 5.0 * (1.0 - sunEl) * (1.0 - inertia);',
'  float night = 1.0 - 0.65 * sunEl;',
'  if (m > 2.5 && m < 3.5) return airT - 1.0 + 0.4 * stored;',  // залив ровный
'  return airT + gain + held + internal * night - cool;',
'}',
'vec3 ironbow(float t){',            // холод -> чёрный, жар -> белый
'  t = clamp(t, 0.0, 1.0);',
'  vec3 c;',
'  if (t < 0.25){ c = mix(vec3(0.0,0.0,0.10), vec3(0.28,0.0,0.45), t/0.25); }',
'  else if (t < 0.5){ c = mix(vec3(0.28,0.0,0.45), vec3(0.85,0.14,0.20), (t-0.25)/0.25); }',
'  else if (t < 0.72){ c = mix(vec3(0.85,0.14,0.20), vec3(1.0,0.55,0.0), (t-0.5)/0.22); }',
'  else if (t < 0.9){ c = mix(vec3(1.0,0.55,0.0), vec3(1.0,0.93,0.35), (t-0.72)/0.18); }',
'  else { c = mix(vec3(1.0,0.93,0.35), vec3(1.0,1.0,1.0), (t-0.9)/0.1); }',
'  return c;',
'}'
].join('\n');

// ── фасады ──────────────────────────────────────────────────────────────────
// Окна не текстура и не выдумка: сетка считается из НАСТОЯЩИХ данных здания —
// высоты (сколько этажей), года постройки (какая эпоха остекления) и
// назначения участка (жильё, контора, склад). Довоенный дом получает узкие
// частые окна, башня 2010-х — сплошную ленту, склад почти глухую стену.
var FACADE_GLSL = [
'struct Fac { float floorH; float winW; float winH; float gap; float glass; float lit; };',
'Fac facadeOf(float use, float year, float h){',
'  Fac f;',
'  bool office = (use > 0.5 && use < 2.5) || use > 4.5;',
'  bool store  = use > 1.5 && use < 2.5;',
'  f.floorH = office ? 3.9 : 3.15;',                 // конторский этаж выше жилого
'  if (year > 1.0 && year < 1945.0){',               // довоенная кладка
'    f.winW = 0.34; f.winH = 0.46; f.gap = 0.22; f.glass = 0.10;',
'  } else if (year < 1980.0){',                      // послевоенный модернизм
'    f.winW = 0.52; f.winH = 0.44; f.gap = 0.14; f.glass = 0.26;',
'  } else if (year < 2005.0){',
'    f.winW = 0.66; f.winH = 0.50; f.gap = 0.10; f.glass = 0.42;',
'  } else {',                                        // стекло нового века
'    f.winW = 0.88; f.winH = 0.66; f.gap = 0.05; f.glass = 0.72;',
'  }',
'  if (store){ f.winW *= 0.35; f.winH *= 0.5; f.glass *= 0.3; }',
'  f.lit = office ? 0.55 : 0.30;',                   // сколько окон горит ночью
'  return f;',
'}',
'float hash21(vec2 p){',
'  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);',
'}',
// Возвращает: x — доля окна (0 стена, 1 стекло), y — свет в окне
'vec2 facadeAt(vec3 wpos, vec3 nrm, float use, float year, float h, float night){',
'  Fac f = facadeOf(use, year, h);',
'  if (abs(nrm.y) > 0.72) return vec2(0.0, 0.0);',   // крыша — не фасад
'  float along = abs(nrm.x) > abs(nrm.z) ? wpos.z : wpos.x;',
'  float floorIdx = floor(wpos.y / f.floorH);',
'  float u = fract(along / 3.4);',
'  float v = fract(wpos.y / f.floorH);',
'  float halfW = f.winW * 0.5, halfH = f.winH * 0.5;',
'  float inW = step(0.5 - halfW, u) * step(u, 0.5 + halfW)',
'            * step(0.55 - halfH, v) * step(v, 0.55 + halfH);',
'  if (wpos.y < f.floorH * 0.9) inW *= 0.55;',       // первый этаж иной
'  float r = hash21(vec2(floor(along / 3.4), floorIdx));',
'  float lit = step(1.0 - f.lit, r) * night * inW;',
'  return vec2(inW * (0.35 + 0.65 * f.glass), lit);',
'}'
].join('\n');

// Прививает материалу тепловой расчёт: температура считается в вершине
// (там есть нормаль), фрагмент только красит. Инстансы и фильтр года
// продолжают работать — мы не подменяем материал, а дополняем его.
function sensorized(mat){
  var prev = mat.onBeforeCompile;
  mat.onBeforeCompile = function(shader){
    if (prev) prev(shader);
    shader.uniforms.uMode = U_MODE;
    shader.uniforms.uSunV = U_SUNV;
    shader.uniforms.uSunEl = U_SUNEL;
    shader.uniforms.uStored = U_STORED;
    shader.uniforms.uAirT = U_AIRT;
    shader.vertexShader =
      'attribute float aMat;\nuniform vec3 uSunV;\nuniform float uSunEl;\n'
      + 'uniform float uStored;\nuniform float uAirT;\nvarying float vTemp;\n'
      + THERMAL_GLSL + '\n' + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace(
      '#include <project_vertex>',
      'vTemp = surfTemp(aMat, normalMatrix * normal, uSunV, uSunEl, uStored, uAirT);\n'
      + '#include <project_vertex>');
    shader.fragmentShader =
      'uniform float uMode;\nuniform float uAirT;\nvarying float vTemp;\n'
      + shader.fragmentShader;
    // последний аккорд фрагмента — подменяем цвет на температурный
    var tail = shader.fragmentShader.indexOf('#include <dithering_fragment>') >= 0
      ? '#include <dithering_fragment>' : '#include <colorspace_fragment>';
    shader.fragmentShader = shader.fragmentShader.replace(tail,
      tail + '\n  if (uMode > 1.5 && uMode < 2.5){\n'
      + '    float lo = uAirT - 8.0, hi = uAirT + 36.0;\n'
      + '    float t = (vTemp - lo) / (hi - lo);\n'
      + '    gl_FragColor = vec4(ironbow(t), 1.0);\n  }');
    shader.fragmentShader = THERMAL_GLSL + '\n' + shader.fragmentShader;
  };
  mat.customProgramCacheKey = function(){ return 'sensorized'; };
  return mat;
}

// Дорисовывает зданию фасад поверх его собственного затенения. Нужны
// атрибуты aMat (назначение), aYear (год) и aGnd (отметка земли у дома —
// иначе этажи считались бы от уровня моря и первый этаж уехал бы на холме).
function facaded(mat){
  var prev = mat.onBeforeCompile;
  mat.onBeforeCompile = function(shader){
    if (prev) prev(shader);
    shader.uniforms.uNight = U_NIGHT;
    shader.vertexShader = 'attribute float aGnd;\nvarying vec3 vWorld;\n'
      + 'varying vec3 vNrmW;\nvarying float vGnd;\n' + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace(
      '#include <project_vertex>',
      '#ifdef USE_INSTANCING\n'
      + '  vWorld = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;\n'
      + '  vNrmW = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);\n'
      + '#else\n'
      + '  vWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;\n'
      + '  vNrmW = normalize(mat3(modelMatrix) * normal);\n'
      + '#endif\n'
      + '  vGnd = aGnd;\n#include <project_vertex>');
    shader.fragmentShader = 'uniform float uNight;\nvarying vec3 vWorld;\n'
      + 'varying vec3 vNrmW;\nvarying float vGnd;\n'
      + FACADE_GLSL + '\n' + shader.fragmentShader;
    var tail = shader.fragmentShader.indexOf('#include <dithering_fragment>') >= 0
      ? '#include <dithering_fragment>' : '#include <colorspace_fragment>';
    shader.fragmentShader = shader.fragmentShader.replace(tail,
      '  if (uMode < 0.5 || uMode > 2.5){\n'
      + '    vec3 lp = vec3(vWorld.x, vWorld.y - vGnd, vWorld.z);\n'
      + '    vec2 fw = facadeAt(lp, vNrmW, aMatF, aYearF, 0.0, uNight);\n'
      + '    vec3 glass = mix(vec3(0.30, 0.38, 0.46), vec3(0.42, 0.55, 0.70),\n'
      + '                     clamp(vNrmW.y * 0.5 + 0.5, 0.0, 1.0));\n'
      + '    gl_FragColor.rgb = mix(gl_FragColor.rgb, glass * (0.55 + 0.75 * (1.0 - uNight)), fw.x * 0.85);\n'
      + '    gl_FragColor.rgb += vec3(1.0, 0.86, 0.58) * fw.y * 0.85;\n'
      + '  }\n' + tail);
    // назначение и год нужны и во фрагменте — прокидываем варьирующими
    shader.vertexShader = shader.vertexShader.replace(
      'vGnd = aGnd;', 'vGnd = aGnd; aMatV = aMat; aYearV = aYear;');
    shader.vertexShader = 'varying float aMatV;\nvarying float aYearV;\n'
      + shader.vertexShader;
    shader.fragmentShader = ('varying float aMatV;\nvarying float aYearV;\n'
      + shader.fragmentShader)
      .replace(/aMatF/g, 'aMatV').replace(/aYearF/g, 'aYearV');
  };
  var oldKey = mat.customProgramCacheKey;
  mat.customProgramCacheKey = function(){
    return (oldKey ? oldKey() : '') + ':facaded';
  };
  return mat;
}

// Однородный материал (вода, дороги) — атрибут aMat одним значением.
function setMat(geo, cls){
  var n = geo.attributes.position.count;
  var a = new Float32Array(n);
  for (var i = 0; i < n; i++) a[i] = cls;
  geo.setAttribute('aMat', new THREE.BufferAttribute(a, 1));
  return geo;
}
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

// Тень отбрасывается ОТДЕЛЬНЫМ проходом со своим материалом глубины — если
// не повторить в нём фильтр года, снесённый в прошлое небоскрёб исчезнет,
// а его тень останется лежать на квартале.
// Теневая камера едет за наблюдателем и меняет охват вместе с высотой полёта:
// у земли резкая тень от карниза, с высоты — мягкая тень квартала.
function updateShadow(){
  if (!sun || !sun.castShadow) return;
  var h = Math.max(40, camera.position.y);
  var span = Math.max(260, Math.min(2600, h * 2.2));
  var ahead = Math.min(900, span * 0.45);
  var dir = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
  var cx = camera.position.x + dir.x * ahead;
  var cz = camera.position.z + dir.z * ahead;
  var cy = gH(cx, cz);
  sun.target.position.set(cx, cy, cz);
  sun.target.updateMatrixWorld();
  sun.position.set(cx + SUN_WORLD.x * 3000, cy + SUN_WORLD.y * 3000,
                   cz + SUN_WORLD.z * 3000);
  var c = sun.shadow.camera;
  if (c.right !== span){
    c.left = -span; c.right = span; c.top = span; c.bottom = -span;
    c.updateProjectionMatrix();
  }
  // ночью тени нет — гасим, чтобы не платить за лишний проход
  sun.castShadow = U_SUNEL.value > 0.06;
}

function shadowDepth(){
  var d = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
  return yearFiltered(d);
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
  var mats = new Float32Array(nx*nz), uvs = new Float32Array(nx*nz*2);
  // Снимок NAIP лежит в Меркаторе, а сетка рельефа — ровная по широте.
  // Без этой поправки фотография сползает относительно земли на десятки метров.
  var bb = S.head.bbox;                       // [lat_min, lon_min, lat_max, lon_max]
  function mercY(lat){
    var r = lat * Math.PI / 180;
    return Math.log(Math.tan(r) + 1 / Math.cos(r));
  }
  var mTop = mercY(bb[2]), mBot = mercY(bb[0]);
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
      mats[i*nx+j] = s;          // 0 земля, 1 зелень, 2 песок, 3 вода
      var lat = bb[2] - (bb[2] - bb[0]) * (i / (nz - 1));
      uvs[(i*nx+j)*2]     = j / (nx - 1);
      uvs[(i*nx+j)*2 + 1] = 1 - (mTop - mercY(lat)) / (mTop - mBot);
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
  geo.setAttribute('aMat', new THREE.BufferAttribute(mats, 1));
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  geo.computeVertexNormals();
  matClasses = sensorized(new THREE.MeshLambertMaterial({ vertexColors: true }));
  groundMesh = new THREE.Mesh(geo, matClasses);
  groundMesh.receiveShadow = true;
  scene.add(groundMesh);
  var texSrc = (typeof TWIN_TEX === 'string' && TWIN_TEX.length > 100) ? TWIN_TEX
             : (typeof TWIN_TEX_URL === 'string' ? TWIN_TEX_URL : '');
  if (texSrc){
    var img = new Image();
    // Снимок может лежать на чужом домене (хостинг уводит файлы на CDN).
    // Без явного запроса CORS WebGL откажется брать такую картинку в текстуру.
    if (texSrc.slice(0, 5) !== 'data:') img.crossOrigin = 'anonymous';
    img.onload = function(){
      var tex = new THREE.Texture(img);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.minFilter = THREE.LinearMipmapLinearFilter;
      tex.magFilter = THREE.LinearFilter;
      tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
      tex.needsUpdate = true;
      matAerial = sensorized(new THREE.MeshLambertMaterial({ map: tex }));
      if ($('yr')) applyAerial();
    };
    img.src = texSrc;
  }

  // водная гладь: океан и залив
  var wgeo = setMat(new THREE.PlaneGeometry(60000, 60000), M_WATER);
  var wmat = sensorized(new THREE.MeshPhongMaterial({ color: 0x2e6f9e,
    transparent: true, opacity: 0.93, shininess: 90, specular: 0x557799 }));
  waterMesh = new THREE.Mesh(wgeo, wmat);
  waterMesh.rotation.x = -Math.PI/2;
  waterMesh.position.y = 0.35;
  scene.add(waterMesh);
}

// ── здания ──────────────────────────────────────────────────────────────────
function shade(c, f){ return [c[0]*f, c[1]*f, c[2]*f]; }
function buildBig(){
  var pos = [], col = [], owner = [], yrs = [], mts = [], gnds = [];
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
    for (var v3 = v0; v3 < pos.length / 3; v3++){
      yrs.push(by); mts.push(M_BLD + b.c); gnds.push(g);
    }
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(col), 3));
  geo.setAttribute('aYear', new THREE.BufferAttribute(new Float32Array(yrs), 1));
  geo.setAttribute('aMat', new THREE.BufferAttribute(new Float32Array(mts), 1));
  geo.setAttribute('aGnd', new THREE.BufferAttribute(new Float32Array(gnds), 1));
  geo.computeVertexNormals();
  bigOwner = owner;
  var mat = facaded(sensorized(yearFiltered(new THREE.MeshLambertMaterial({
    vertexColors: true, side: THREE.DoubleSide }))));
  bigMesh = new THREE.Mesh(geo, mat);
  bigMesh.castShadow = true;
  bigMesh.receiveShadow = true;
  bigMesh.customDepthMaterial = shadowDepth();
  scene.add(bigMesh);
}
function buildSmall(){
  var arr = S.small, n = arr.length;
  if (!n) return;
  var geo = new THREE.BoxGeometry(1, 1, 1);
  var yrs = new Float32Array(n), mts = new Float32Array(n), gnd = new Float32Array(n);
  for (var yi = 0; yi < n; yi++){
    yrs[yi] = arr[yi][8] || 0;
    mts[yi] = M_BLD + arr[yi][7];
    gnd[yi] = arr[yi][6] / 10;
  }
  geo.setAttribute('aYear', new THREE.InstancedBufferAttribute(yrs, 1));
  geo.setAttribute('aMat', new THREE.InstancedBufferAttribute(mts, 1));
  geo.setAttribute('aGnd', new THREE.InstancedBufferAttribute(gnd, 1));
  var mat = facaded(sensorized(yearFiltered(new THREE.MeshLambertMaterial())));
  instMesh = new THREE.InstancedMesh(geo, mat, n);
  instMesh.castShadow = true;
  instMesh.receiveShadow = true;
  instMesh.customDepthMaterial = shadowDepth();
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
  // дороги светятся в тепловизоре: асфальт копит дневное солнце
  var mat = sensorized(new THREE.MeshLambertMaterial({ vertexColors: true }));
  roadMesh = new THREE.Mesh(setMat(geo, M_ASPHALT), mat);
  roadMesh.receiveShadow = true;
  scene.add(roadMesh);
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
    var mesh = new THREE.Mesh(setMat(geo, M_WATER), sensorized(
      new THREE.MeshPhongMaterial({ color: 0x2e6f9e, transparent: true,
        opacity: 0.9, shininess: 80, side: THREE.DoubleSide })));
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

// Снимок — это СЕГОДНЯШНЯЯ земля. В прошлом он врёт: парковка на месте
// снесённого квартала, шоссе там, где его не было. Уезжая назад во времени,
// возвращаемся к раскраске по классам и говорим, почему.
function applyAerial(){
  if (!groundMesh) return;
  var tm = S.head.time_machine || {};
  var y = parseInt($('yr').value, 10);
  var today = y >= (tm.max || 2026);
  var want = $('aer').checked && matAerial && today;
  groundMesh.material = want ? matAerial : matClasses;
  // под фотографией нарисованные ленты дорог только мешают: улицы уже сняты
  if (roadMesh) roadMesh.visible = !want;
  var st = $('aerSrc');
  if (st){
    st.textContent = !matAerial ? ''
      : (today ? (S.head.aerial ? S.head.aerial.source : '')
               : 'снимок 2022 года выключен: он показывает сегодняшнюю землю');
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
  applyAerial();
}

// ── солнце и небо ───────────────────────────────────────────────────────────
// Запас тепла в материалах: минимум перед рассветом, максимум ближе к вечеру —
// поэтому в тепловизоре ночной асфальт светлее ночного газона.
function storedHeat(h){
  if (h >= 5.0 && h <= 17.0) return 0.05 + 0.95 * (h - 5.0) / 12.0;  // копит
  if (h > 17.0) return 1.0 - 0.65 * (h - 17.0) / 7.0;                // отдаёт
  return 0.35 - 0.30 * (h / 5.0);                                    // к рассвету
}

function applyTime(){
  var t = parseFloat($('tod').value);
  $('todV').textContent = String(Math.floor(t)).padStart(2, '0') + ':' +
    String(Math.round((t % 1) * 60)).padStart(2, '0');
  var f = (t - 5.5) / 15;                       // 0..1 за день
  var el = Math.sin(f * Math.PI) * 1.08;        // высота солнца
  var az = (0.25 + 0.5 * f) * 2 * Math.PI;      // восток -> запад
  var sunV = new THREE.Vector3(Math.cos(az) * Math.cos(el * Math.PI/2), Math.sin(el * Math.PI/2),
                               -Math.sin(az) * Math.cos(el * Math.PI/2));
  SUN_WORLD.copy(sunV);          // единичное направление до масштабирования
  sun.position.copy(sunV.clone().multiplyScalar(3000));
  var day = Math.max(0, Math.min(1, el * 1.6));
  var warm = Math.max(0, 1 - el * 2.2);
  sun.color.setRGB(1.0, 0.96 - warm * 0.3, 0.88 - warm * 0.45);
  sun.intensity = 0.4 + 2.0 * day;
  hemi.intensity = 0.42 + 0.58 * day;   // тень держит небесную подсветку
  var sky = new THREE.Color().setRGB(
    0.34 + 0.28 * day + warm * 0.24 * day,
    0.44 + 0.28 * day - warm * 0.06 * day,
    0.62 + 0.24 * day - warm * 0.24 * day);
  if (day <= 0.02) sky.setRGB(0.05, 0.06, 0.10);
  scene.background = sky;
  scene.fog.color.copy(sky);

  U_SUNEL.value = Math.max(0, Math.min(1, el));
  sun.castShadow = U_SUNEL.value > 0.06;
  U_STORED.value = storedHeat(t);
  U_NIGHT.value = Math.max(0, Math.min(1, 1.0 - el * 2.2));
  applyMode();
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
  window.addEventListener('keydown', function(e){
    keys[e.code] = true;
    if (e.code === 'Digit1') setMode(0);
    if (e.code === 'Digit2') setMode(1);
    if (e.code === 'Digit3') setMode(2);
    if (e.code === 'Digit4') setMode(3);
  });
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
  $('lAir').addEventListener('change', function(){
    if (airMesh) airMesh.visible = this.checked; });
  $('lSat').addEventListener('change', function(){
    if (satDots) satDots.visible = this.checked;
    for (var i = 0; i < satLines.length; i++) satLines[i].visible = this.checked; });
  $('lQ').addEventListener('change', function(){
    if (quakeGroup) quakeGroup.visible = this.checked; });
  $('lCam').addEventListener('change', function(){
    if (camGroup) camGroup.visible = this.checked; });
  $('lRes').addEventListener('change', function(){
    if (resMesh) resMesh.visible = this.checked; });
  $('aer').addEventListener('change', applyAerial);
  $('spd').addEventListener('input', function(){
    LIVE_SPEED = [1, 10, 60, 300][parseInt(this.value, 10)];
    $('spdV').textContent = LIVE_SPEED; });
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
  // сначала живой слой: борта, камеры, толчки — они поверх города
  var liveHit = [];
  if (resMesh && resMesh.visible) liveHit.push(resMesh);
  if (airMesh && airMesh.visible) liveHit.push(airMesh);
  if (camGroup && camGroup.visible) liveHit = liveHit.concat(camGroup.children);
  if (quakeGroup && quakeGroup.visible) liveHit = liveHit.concat(quakeGroup.children);
  var lh = ray.intersectObjects(liveHit, false);
  if (lh.length){
    var h0 = lh[0];
    if (h0.object === resMesh){
      var card = residentCard(h0.instanceId);
      if (card){
        $('iName').textContent = card.name;
        $('iMeta').innerHTML = card.meta;
        $('info').style.display = 'block';
        return;
      }
    }
    if (showLive(h0)) return;
  }

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

// Клик по живому объекту. Кадр камеры тянется из сети ПРЯМО СЕЙЧАС: Caltrans
// отдаёт снимки с Access-Control-Allow-Origin: *, поэтому офлайн-страница
// показывает дорогу такой, какая она в эту минуту.
function showLive(hit){
  var o = hit.object, name = '', meta = '', img = '';
  if (o === airMesh){
    var a = airData[hit.instanceId];
    if (!a) return false;
    name = a.cs + (a.mil ? ' · борт военной авиации' : '');
    meta = (a.ty ? 'тип ' + a.ty + ' · ' : '')
         + (a.gnd ? 'на земле' : 'эшелон ' + Math.round(a.alt * 3.2808 / 100) * 100
            + ' футов (' + Math.round(a.alt) + ' м)')
         + ' · путевая ' + Math.round(a.v * 3.6) + ' км/ч · курс ' + Math.round(a.hdg) + '°'
         + '<br><span style="color:#88929c">ADS-B, adsb.lol · слепок '
         + (S.head.live || {}).stamp + '</span>';
  } else if (o.userData.cam){
    var c = o.userData.cam;
    name = c.n || 'дорожная камера';
    meta = (c.r ? c.r + ' ' + (c.d || '') : '')
         + '<br><span style="color:#88929c">Caltrans, кадр обновляется сам</span>';
    img = c.u;
  } else if (o.userData.q){
    var q = o.userData.q;
    name = 'землетрясение M' + (q.m != null ? q.m.toFixed(2) : '?');
    meta = (q.pl || '') + '<br>глубина ' + (q.d != null ? q.d.toFixed(1) : '?') + ' км · '
         + (q.t || '').replace('T', ' ').replace('Z', ' UTC')
         + '<br><span style="color:#88929c">USGS</span>';
  } else {
    return false;
  }
  $('iName').textContent = name;
  $('iMeta').innerHTML = meta
    + (img ? '<br><img src="' + img + '" style="width:100%;margin-top:6px;'
             + 'border-radius:6px" alt="кадр камеры" '
             + 'onerror="this.style.display=\'none\';'
             + 'this.nextSibling.style.display=\'block\'">'
             + '<span style="display:none;color:#e0a">кадр не загрузился: '
             + 'нет доступа к сети или камера молчит</span>' : '');
  $('info').style.display = 'block';
  return true;
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
  if (w.temp_c != null) U_AIRT.value = w.temp_c;   // тепловизор от реального воздуха
  var parts = [];
  if (w.temp_c != null) parts.push(w.temp_c + ' °C');
  if (w.wind_kmh != null) parts.push('ветер ' + w.wind_kmh + ' км/ч');
  if (w.text) parts.push(w.text);
  $('hWx').textContent = parts.length ? 'Сейчас: ' + parts.join(' · ') :
    'Погода: нет данных';
  var src = [];
  for (var i = 0; i < (h.sources || []).length; i++) src.push(h.sources[i].name);
  $('hSrc').textContent = 'Данные: ' + src.join(' · ');

  var lv = h.live || {}, cn = lv.counts || {};
  $('nAir').textContent = cn.aircraft || 0;
  $('nSat').textContent = cn.sats || 0;
  $('nQ').textContent = cn.quakes || 0;
  $('nCam').textContent = cn.cams || 0;
  $('nRes').textContent = (h.people || {}).n || 0;
  if (lv.stamp){
    var s = lv.stamp;
    $('liveStamp').textContent = s.slice(6,8) + '.' + s.slice(4,6) + ' '
      + s.slice(9,11) + ':' + s.slice(11,13) + ' UTC';
  }
  var td = lv.tide || {};
  if (td.level_m != null){
    var nxt = (td.next || [])[0];
    $('tideTxt').textContent = 'прилив ' + td.level_m.toFixed(2) + ' м'
      + (nxt ? ' · далее ' + (nxt.k === 'high' ? 'полная' : 'малая') + ' вода '
              + nxt.v.toFixed(2) + ' м в ' + nxt.t.slice(11) : '');
  }
}

// ── живой слой: борта, спутники, толчки, камеры ─────────────────────────────
var airMesh = null, airData = [], airLabels = [];
var satLines = [], satDots = null, satData = [];
var camGroup = null, quakeGroup = null;
var LIVE_T = 0;                     // секунды с загрузки — борта летят дальше
var LIVE_SPEED = 1;                 // ускорение живого времени (1× … 60×)
var SKY_R = 9000;                   // радиус небесного купола для спутников

function buildAircraft(){
  var arr = S.air || [];
  airData = arr;
  if (!arr.length) return;
  // простая «стрелка» самолёта: нос, крылья, киль
  var g = new THREE.BufferGeometry();
  var v = new Float32Array([
     0,0, 34,   -22,0,-16,    22,0,-16,          // крыло
     0,0, 34,     0,9,-14,     0,0,-16           // киль
  ]);
  g.setAttribute('position', new THREE.BufferAttribute(v, 3));
  g.setAttribute('aMat', new THREE.BufferAttribute(new Float32Array(6), 1));
  g.computeVertexNormals();
  var m = new THREE.MeshBasicMaterial({ color: 0xf2f6fa, side: THREE.DoubleSide,
                                        fog: false });
  airMesh = new THREE.InstancedMesh(g, m, arr.length);
  airMesh.frustumCulled = false;
  var c = new THREE.Color();
  for (var i = 0; i < arr.length; i++){
    c.set(arr[i].mil ? 0xff7043 : (arr[i].gnd ? 0x9aa6b2 : 0xf2f6fa));
    airMesh.setColorAt(i, c);
  }
  if (airMesh.instanceColor) airMesh.instanceColor.needsUpdate = true;
  scene.add(airMesh);
  updateAircraft(0);
}

function updateAircraft(dt){
  if (!airMesh) return;
  var m = new THREE.Matrix4(), q = new THREE.Quaternion(),
      p = new THREE.Vector3(), s = new THREE.Vector3(1,1,1),
      up = new THREE.Vector3(0,1,0), cam = camera.position;
  for (var i = 0; i < airData.length; i++){
    var a = airData[i];
    // курс в градусах от севера; север сцены — это -Z
    var rad = a.hdg * Math.PI / 180;
    var dx = Math.sin(rad), dz = -Math.cos(rad);
    var x = a.x + dx * a.v * LIVE_T, z = a.z + dz * a.v * LIVE_T;
    var y = a.gnd ? gH(x, z) + 4 : a.alt;
    p.set(x, y, z);
    // борт за двести километров иначе тоньше пикселя: держим постоянный
    // угловой размер, как метка на экране оператора
    var d = Math.sqrt((x-cam.x)*(x-cam.x) + (y-cam.y)*(y-cam.y) + (z-cam.z)*(z-cam.z));
    var k = Math.max(1.0, Math.min(60.0, d / 900));
    s.set(k, k, k);
    q.setFromAxisAngle(up, -rad);
    m.compose(p, q, s);
    airMesh.setMatrixAt(i, m);
  }
  airMesh.instanceMatrix.needsUpdate = true;
}

function buildSats(){
  var arr = S.sats || [];
  satData = arr;
  if (!arr.length) return;
  var lp = [], lc = [];
  var c = new THREE.Color();
  for (var i = 0; i < arr.length; i++){
    var pts = arr[i].p, prev = null;
    for (var j = 0; j < pts.length; j++){
      var cur = pts[j];
      if (cur && prev){
        var a = skyPoint(prev[0], prev[1]), b = skyPoint(cur[0], cur[1]);
        lp.push(a.x, a.y, a.z, b.x, b.y, b.z);
        var f = 0.35 + 0.65 * Math.min(1, Math.max(prev[1], cur[1]) / 60);
        c.setRGB(0.40 * f, 0.90 * f, 1.0 * f);
        lc.push(c.r, c.g, c.b, c.r, c.g, c.b);
      }
      prev = cur;
    }
  }
  var g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(lp), 3));
  g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(lc), 3));
  var line = new THREE.LineSegments(g, new THREE.LineBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.9, fog: false }));
  line.frustumCulled = false;
  scene.add(line);
  satLines.push(line);

  var dg = new THREE.BufferGeometry();
  dg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(arr.length*3), 3));
  satDots = new THREE.Points(dg, new THREE.PointsMaterial({
    color: 0xdcf3ff, size: 240, sizeAttenuation: true, fog: false }));
  satDots.frustumCulled = false;
  scene.add(satDots);
  // подписываем те аппараты, что сейчас высоко над головой
  var top = arr.slice().sort(function(a, b){
    return satElev(b) - satElev(a); }).slice(0, 8);
  for (var k = 0; k < top.length; k++){
    if (satElev(top[k]) < 25) break;
    var pt = satNow(top[k]);
    if (pt) makeLabel(top[k].n, pt.x, pt.y, pt.z, false).userData.year = 0;
  }
  updateSats();
}

function satIdx(s){
  var n = s.p.length;
  return Math.max(0, Math.min(n - 1,
    Math.round((n - 1) / 2 + LIVE_T / (s.step || 30))));
}
function satElev(s){
  var p = s.p[satIdx(s)];
  return p ? p[1] : -90;
}
function satNow(s){
  var p = s.p[satIdx(s)];
  return p && p[1] > 0 ? skyPoint(p[0], p[1]) : null;
}

function skyPoint(azDeg, elDeg){
  var az = azDeg * Math.PI / 180, el = elDeg * Math.PI / 180;
  var r = Math.cos(el) * SKY_R;
  // азимут от севера по часовой; север сцены -Z, восток +X
  return new THREE.Vector3(Math.sin(az) * r, Math.sin(el) * SKY_R, -Math.cos(az) * r);
}

function updateSats(){
  if (!satDots) return;
  var pos = satDots.geometry.attributes.position.array;
  var mid = 0;
  for (var i = 0; i < satData.length; i++){
    var p = satData[i].p[satIdx(satData[i])];
    if (!p || p[1] < 0){ pos[i*3] = 0; pos[i*3+1] = -99999; pos[i*3+2] = 0; continue; }
    var v = skyPoint(p[0], p[1]);
    pos[i*3] = v.x; pos[i*3+1] = v.y; pos[i*3+2] = v.z;
    if (p[1] > 20) mid++;
  }
  satDots.geometry.attributes.position.needsUpdate = true;
}

function buildQuakes(){
  var arr = S.quakes || [];
  if (!arr.length) return;
  quakeGroup = new THREE.Group();
  for (var i = 0; i < Math.min(arr.length, 240); i++){
    var q = arr[i], mag = q.m || 1.0;
    var rad = 60 + Math.pow(10, mag) * 0.9;      // энергия растёт степенью
    var g = new THREE.RingGeometry(rad * 0.86, rad, 40);
    g.rotateX(-Math.PI / 2);
    var col = mag >= 3 ? 0xff3b2f : (mag >= 2 ? 0xffa000 : 0xffd54f);
    var mesh = new THREE.Mesh(setMat(g, M_GROUND), new THREE.MeshBasicMaterial({
      color: col, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
    // толчки — слой РЕГИОНА, а не города: почти все за краем рельефа, где
    // высоты мы не знаем. Такие кладём на уровень моря, а не на край плато.
    var inside = Math.abs(q.x) < TER.nx * TER.dx / 20 &&
                 Math.abs(q.z) < TER.nz * Math.abs(TER.dz) / 20;
    mesh.position.set(q.x, inside ? gH(q.x, q.z) + 3 : 2, q.z);
    mesh.userData.q = q;
    quakeGroup.add(mesh);
  }
  quakeGroup.visible = false;
  scene.add(quakeGroup);
}

function buildCams(){
  var arr = S.cams || [];
  if (!arr.length) return;
  camGroup = new THREE.Group();
  for (var i = 0; i < arr.length; i++){
    var c = arr[i];
    var g = new THREE.ConeGeometry(14, 34, 4);
    g.rotateX(Math.PI);
    var mesh = new THREE.Mesh(setMat(g, M_GROUND), new THREE.MeshBasicMaterial({
      color: 0x4fc3f7 }));
    mesh.position.set(c.x, c.g + 42, c.z);
    mesh.userData.cam = c;
    camGroup.add(mesh);
  }
  camGroup.visible = false;
  scene.add(camGroup);
}

// ── жители ──────────────────────────────────────────────────────────────────
var resMesh = null, resData = [];
function buildResidents(){
  var arr = S.res || [];
  resData = arr;
  if (!arr.length) return;
  var g = new THREE.CapsuleGeometry(0.32, 1.05, 3, 6);
  g.translate(0, 0.85, 0);
  g.setAttribute('aMat', new THREE.BufferAttribute(
    new Float32Array(g.attributes.position.count).fill(M_BLD), 1));
  var mat = sensorized(new THREE.MeshLambertMaterial());
  resMesh = new THREE.InstancedMesh(g, mat, arr.length);
  resMesh.frustumCulled = false;
  var m = new THREE.Matrix4(), q = new THREE.Quaternion(),
      p = new THREE.Vector3(), s = new THREE.Vector3(1,1,1), c = new THREE.Color();
  for (var i = 0; i < arr.length; i++){
    var r = arr[i];
    // немного разводим по двору, чтобы жильцы дома не стояли одной точкой
    var a = (i * 2.399963), rad = 3 + (i % 7);
    p.set(r[0]/10 + Math.cos(a) * rad, r[2]/10, r[1]/10 + Math.sin(a) * rad);
    m.compose(p, q, s);
    resMesh.setMatrixAt(i, m);
    var age = r[3];
    c.setHSL(age < 18 ? 0.13 : (age >= 65 ? 0.58 : 0.05), 0.42, 0.58);
    resMesh.setColorAt(i, c);
  }
  resMesh.instanceMatrix.needsUpdate = true;
  if (resMesh.instanceColor) resMesh.instanceColor.needsUpdate = true;
  resMesh.visible = false;
  scene.add(resMesh);
}

function residentCard(i){
  var r = resData[i];
  if (!r) return null;
  var age = r[3];
  var who = age < 18 ? 'школьник' : (age >= 65 ? 'на покое' : 'взрослый');
  return {
    name: 'Житель, ' + age + ' ' + (age % 10 === 1 && age % 100 !== 11 ? 'год'
          : (age % 10 >= 2 && age % 10 <= 4 && (age % 100 < 10 || age % 100 >= 20)
             ? 'года' : 'лет')),
    meta: who + ' · домохозяйство ' + r[4] + ' чел. · ' + r[5]
        + '<br>занятость: ' + r[7] + ' · дорога: ' + r[6]
        + '<br><span style="color:#88929c">синтетический житель (ярус R): '
        + 'население квартала измерено переписью, человек — выдуман; '
        + 'реальным людям не соответствует</span>'
  };
}

function applyTide(){
  var td = (S.head.live || {}).tide || {};
  if (!waterMesh || td.level_m == null) return;
  // MLLW -> наша отметка: средний уровень ~1.0 м над нулём карты глубин
  waterMesh.position.y = 0.35 + (td.level_m - 1.0);
}

// ── пост-обработка сенсоров ─────────────────────────────────────────────────
// Свой мини-композер: сцена в буфер, затем полноэкранный треугольник с
// шейдером режима. EffectComposer живёт в examples/jsm, а мы вшиваем только
// ядро three — тут дешевле написать сорок строк, чем тащить зависимость.
var RT = null, postScene = null, postCam = null, postMat = null;

var POST_FRAG = [
'precision highp float;',
'uniform sampler2D tDiffuse;',
'uniform float uMode, uTime, uNoise;',
'uniform vec2 uRes;',
'varying vec2 vUv;',
'float hash(vec2 p){ return fract(sin(dot(p, vec2(41.31, 289.7))) * 43758.5453); }',
'void main(){',
'  vec2 uv = vUv;',
'  if (uMode > 2.5){',                       // ЭЛТ: искривление трубки
'    vec2 c = uv - 0.5;',
'    uv = uv + c * dot(c, c) * 0.18;',
'    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0){',
'      gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }',
'  }',
'  vec3 col;',
'  if (uMode > 2.5){',                       // хроматическое расхождение
'    float o = 0.0016;',
'    col = vec3(texture2D(tDiffuse, uv + vec2(o, 0.0)).r,',
'               texture2D(tDiffuse, uv).g,',
'               texture2D(tDiffuse, uv - vec2(o, 0.0)).b);',
'  } else {',
'    col = texture2D(tDiffuse, uv).rgb;',
'  }',
'  float grain = hash(uv * uRes + uTime) - 0.5;',
'  if (uMode > 0.5 && uMode < 1.5){',        // ПНВ: усиление, люминофор, блики
'    float l = dot(col, vec3(0.299, 0.587, 0.114));',
'    l = pow(clamp(l * 2.6 + 0.04, 0.0, 1.0), 0.72);',
'    float bloom = smoothstep(0.72, 1.0, l);',
'    col = vec3(0.10, 1.0, 0.32) * l + vec3(0.55, 1.0, 0.6) * bloom * 0.45;',
'    col += grain * 0.16;',
'    col *= 1.0 - 0.55 * pow(length(vUv - 0.5) * 1.42, 2.4);',   // виньетка трубки
'  } else if (uMode > 1.5 && uMode < 2.5){', // тепловизор: сенсорный шум и полосы
'    col += grain * 0.05;',
'    col *= 0.97 + 0.03 * sin(vUv.y * uRes.y * 0.5 + uTime * 3.0);',
'    col *= 1.0 - 0.30 * pow(length(vUv - 0.5) * 1.42, 3.0);',
'  } else if (uMode > 2.5){',                // ЭЛТ: строки развёртки и мерцание
'    float scan = 0.82 + 0.18 * sin(uv.y * uRes.y * 1.9);',
'    col *= scan;',
'    col *= 0.96 + 0.04 * sin(uTime * 7.0);',
'    col += grain * 0.05;',
'    col *= 1.0 - 0.45 * pow(length(vUv - 0.5) * 1.30, 2.2);',
'  }',
'  gl_FragColor = vec4(col, 1.0);',
'}'
].join('\n');

var POST_VERT = [
'varying vec2 vUv;',
'void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }'
].join('\n');

function initPost(){
  var dpr = renderer.getPixelRatio();
  RT = new THREE.WebGLRenderTarget(
    Math.floor(window.innerWidth * dpr), Math.floor(window.innerHeight * dpr),
    { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
  postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  postScene = new THREE.Scene();
  postMat = new THREE.ShaderMaterial({
    uniforms: { tDiffuse: { value: RT.texture }, uMode: U_MODE,
                uTime: { value: 0 }, uNoise: { value: 1 },
                uRes: { value: new THREE.Vector2(1280, 720) } },
    vertexShader: POST_VERT, fragmentShader: POST_FRAG, depthTest: false });
  postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMat));
}

function resizePost(){
  if (!RT) return;
  var dpr = renderer.getPixelRatio();
  RT.setSize(Math.floor(window.innerWidth * dpr), Math.floor(window.innerHeight * dpr));
  postMat.uniforms.uRes.value.set(window.innerWidth, window.innerHeight);
}

function applyMode(){
  var m = U_MODE.value;
  // в тепловизоре небо — холодный фон, а не голубое; в ПНВ почти чёрное
  if (m > 1.5 && m < 2.5){
    scene.background = new THREE.Color(0x05060c);
    scene.fog.color.set(0x05060c);
  } else if (m > 0.5 && m < 1.5){
    scene.background = new THREE.Color(0x02120a);
    scene.fog.color.set(0x02120a);
  }
  // подписи мест — принадлежность оптике; в сенсорах они лишь призрак
  for (var i = 0; i < labels.length; i++)
    labels[i].material.opacity = (m === 1 || m === 2) ? 0.22 : 1.0;
  var bar = $('tbar');
  if (bar){
    bar.style.display = (m === 2) ? 'block' : 'none';
    if (m === 2){
      var lo = U_AIRT.value - 8.0, hi = U_AIRT.value + 36.0;
      $('tLo').textContent = lo.toFixed(0) + ' °C';
      $('tMid').textContent = ((lo + hi) / 2).toFixed(0) + ' °C';
      $('tHi').textContent = hi.toFixed(0) + ' °C';
    }
  }
  var hint = $('modeHint');
  if (hint){
    hint.textContent = m === 2
      ? 'температура поверхности: солнце по углу падения, тепловая инерция '
        + 'материала, своё тепло здания по назначению; воздух '
        + U_AIRT.value.toFixed(1) + ' °C по данным NOAA'
      : (m === 1 ? 'усиление яркости, зелёный люминофор, шум сенсора'
        : (m === 3 ? 'строчная развёртка, искривление трубки, расхождение цветов'
        : 'как видит глаз'));
  }
}

function setMode(m){
  U_MODE.value = m;
  var btns = document.querySelectorAll('#modes button');
  for (var i = 0; i < btns.length; i++)
    btns[i].className = (i === m) ? 'on' : '';
  applyTime();                      // небо и солнце зависят от режима
}

// ── запуск ──────────────────────────────────────────────────────────────────
function start(){
  renderer = new THREE.WebGLRenderer({ canvas: $('c3d'), antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x9db8cc, 4000, 26000);
  SUN_WORLD = new THREE.Vector3(0.5, 0.8, -0.3).normalize();
  U_SUNV.value = new THREE.Vector3(0.5, 0.8, -0.3).normalize();
  // дальняя плоскость держит борта в трёхстах километрах и небесный купол
  camera = new THREE.PerspectiveCamera(58, window.innerWidth/window.innerHeight, 1, 500000);
  camera.position.set(3400, 520, -900);
  sun = new THREE.DirectionalLight(0xffffff, 2.0);
  // Тень на весь город одной картой была бы по три метра на тексель —
  // бесполезно. Поэтому она накрывает только окрестности камеры и едет
  // за ней, как это делают движки с каскадами.
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 10;
  sun.shadow.camera.far = 6000;
  sun.shadow.bias = -0.0004;
  sun.shadow.radius = 2.0;
  sun.shadow.normalBias = 0.6;
  scene.add(sun);
  scene.add(sun.target);
  hemi = new THREE.HemisphereLight(0xbcd3e8, 0x4a4238, 0.9);
  scene.add(hemi);
  window.addEventListener('resize', function(){
    camera.aspect = window.innerWidth/window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    resizePost();
  });

  var chain = Promise.resolve();
  chain = chain.then(function(){ return boot('рельеф города…'); }).then(buildTerrain);
  chain = chain.then(function(){ return boot('крупные здания…'); }).then(buildBig);
  chain = chain.then(function(){ return boot('квартальная застройка…'); }).then(buildSmall);
  chain = chain.then(function(){ return boot('улицы…'); }).then(buildRoads);
  chain = chain.then(function(){ return boot('вода и парки…'); }).then(buildLakes);
  chain = chain.then(function(){ return boot('подписи…'); }).then(buildLabels);
  chain = chain.then(function(){ return boot('живой слой: борта и спутники…'); })
    .then(function(){ buildAircraft(); buildSats(); buildQuakes(); buildCams();
                      applyTide(); buildResidents(); });
  chain = chain.then(function(){
    var tm = S.head.time_machine;
    if (tm){
      $('yr').min = tm.min; $('yr').max = tm.max; $('yr').value = tm.max;
    }
    fillHud(); setupControls(); applyTime(); applyYear();
    $('boot').classList.add('gone');
    initPost();
    resizePost();
    var clock = new THREE.Clock(), tSum = 0;
    (function tick(){
      requestAnimationFrame(tick);
      var dt = Math.min(clock.getDelta(), 0.1);
      tSum += dt;
      LIVE_T += dt * LIVE_SPEED;
      stepCamera(dt);
      updateShadow();
      updateAircraft(dt);
      updateSats();
      // солнце в системе камеры — для теплового расчёта в вершинах
      U_SUNV.value.copy(SUN_WORLD).transformDirection(camera.matrixWorldInverse);
      if (U_MODE.value === 0){
        renderer.setRenderTarget(null);
        renderer.render(scene, camera);
      } else {
        renderer.setRenderTarget(RT);
        renderer.render(scene, camera);
        renderer.setRenderTarget(null);
        postMat.uniforms.uTime.value = tSum;
        renderer.render(postScene, postCam);
      }
    })();
    window.TWIN_READY = true;
  });
  return chain;
}

// Сцена приходит либо вшитой в страницу (офлайн-файл), либо файлом рядом
// (хостинг). Во втором случае не полагаемся на заголовки: смотрим на подпись
// gzip в первых байтах — сервер мог распаковать поток за нас.
function loadScene(){
  if (typeof TWIN_GZ === 'string' && TWIN_GZ.length > 100) return ungzip(TWIN_GZ);
  if (typeof TWIN_SCENE_URL !== 'string' || !TWIN_SCENE_URL)
    return Promise.reject(new Error('нет данных сцены'));
  return fetch(TWIN_SCENE_URL).then(function(r){
    if (!r.ok) throw new Error('сцена не загрузилась: HTTP ' + r.status);
    return r.arrayBuffer();
  }).then(function(buf){
    var u8 = new Uint8Array(buf);
    if (u8.length > 2 && u8[0] === 0x1f && u8[1] === 0x8b){
      var st = new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'));
      return new Response(st).json();
    }
    return JSON.parse(new TextDecoder('utf-8').decode(u8));
  });
}

loadScene().then(function(data){ S = data; return start(); }).catch(fail);
"""
