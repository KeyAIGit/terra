# Обозреватель твина: twin/data/build/scene_<key>.json.gz -> twin_<key>.html
#
# Самодостаточный офлайн-HTML: three.js вшит (как в глобусе), данные сцены —
# gzip+base64, распаковка родным DecompressionStream браузера.
#
#   python3 -m twin.view sf [-o twin_sf.html]

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys

from terra.globe import _three_source
from twin import regions
from twin.build import BUILD_DIR, build_scene
from twin._view_js import CSS, BODY, APP_JS


# ── дополнения three.js для фотореалистичных плиток Google ──────────────────
# Плитки приходят как glTF со сжатием Draco, а GLTFLoader и DRACOLoader живут
# в examples/jsm и написаны модулями ESM. Ядро three мы вшиваем сборкой CJS,
# поэтому четыре модуля переписываем в обычные функции: у каждого свой замок
# (иначе `const { Loader } = THREE` объявится четырежды и сломает разбор), а
# наружу торчит только то, что модуль экспортировал.
_ADDON_FILES = (
    "utils/BufferGeometryUtils.js",
    "utils/SkeletonUtils.js",
    "loaders/DRACOLoader.js",
    "loaders/GLTFLoader.js",
)
_ADDON_EXPOSE = ("GLTFLoader", "DRACOLoader")


def _addons_dir():
    from pathlib import Path
    here = Path(__file__).resolve().parent
    for base in (here.parent, Path.cwd()):
        d = base / "node_modules" / "three" / "examples" / "jsm"
        if d.is_dir():
            return d
    raise FileNotFoundError(
        "не найден node_modules/three/examples/jsm — установите three (npm i three)")


def _addons_source() -> str:
    """Модули examples/jsm одним классическим скриптом."""
    d = _addons_dir()
    # import.meta живёт только в модулях ESM, а мы собираем обычный скрипт.
    # DRACOLoader берёт оттуда путь к декодеру по умолчанию — нам он не нужен,
    # мы задаём декодер сами через setDecoderPath({js, wasm}).
    out = ["var __TA = {};",
           "var __TA_BASE = (typeof document !== 'undefined' && document.baseURI)"
           " || 'https://localhost/';"]
    for rel in _ADDON_FILES:
        src = (d / rel).read_text(encoding="utf-8")
        # импорт из ядра three -> разбор общего объекта THREE
        src = re.sub(r"import\s*\{(.*?)\}\s*from\s*'three';",
                     lambda m: "const {" + m.group(1) + "} = THREE;", src,
                     count=1, flags=re.S)
        # импорт соседнего модуля -> берём из общей витрины
        src = re.sub(r"import\s*\{([^}]*)\}\s*from\s*'[^']*\.js';",
                     lambda m: "const {" + m.group(1) + "} = __TA;", src)
        names: list[str] = []
        for block in re.findall(r"^export\s*\{([^}]*)\};", src, flags=re.M):
            names += [n.strip() for n in block.split(",") if n.strip()]
        src = re.sub(r"^export\s*\{[^}]*\};", "", src, flags=re.M)
        src = src.replace("import.meta.url", "__TA_BASE")
        if not names:
            raise ValueError(f"не нашёл экспортов в {rel}")
        assigns = "".join(f"__TA.{n} = {n};" for n in names)
        out.append("(function(){\n" + src + "\n" + assigns + "\n})();")
    out.append("".join(f"THREE.{n} = __TA.{n};" for n in _ADDON_EXPOSE))
    body = "\n".join(out)
    return body.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def _draco_assets() -> dict:
    """Декодер Draco как data:URI — страница остаётся самодостаточной."""
    d = _addons_dir() / "libs" / "draco"
    wrapper = (d / "draco_wasm_wrapper.js").read_bytes()
    wasm = (d / "draco_decoder.wasm").read_bytes()
    return {
        "wrapper": "data:application/javascript;base64,"
                   + base64.b64encode(wrapper).decode("ascii"),
        "wasm": "data:application/wasm;base64,"
                + base64.b64encode(wasm).decode("ascii"),
    }


def _aerial_data_uri(key: str, max_px: int) -> str:
    """Аэрофотоснимок как data:URI. max_px ограничивает ширину: страница на
    четыре мегабайта хороша дома, но не в чужом окне."""
    import gzip as _gz
    from twin.state import DATA_DIR
    src = os.path.join(DATA_DIR, "imagery", f"naip_{key}.jpg")
    if not os.path.exists(src):
        return ""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(src) as im:
        if im.width > max_px:
            im = im.resize((max_px, round(max_px * im.height / im.width)),
                           Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=84, optimize=True)
            raw = buf.getvalue()
        else:
            raw = open(src, "rb").read()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def build_split(key: str, out_dir: str, tex_max: int = 4096) -> list[str]:
    """Оболочка + данные рядом, вместо одного тяжёлого файла.

    Зачем: хостинги (HF Spaces) уводят файлы тяжелее 10 МБ в LFS и отдают их
    редиректом на CDN — браузер такую страницу СКАЧИВАЕТ, а не открывает.
    Оболочка весит около полутора мегабайт и отдаётся как обычный html,
    а сцену и снимок она подтягивает сама.
    """
    sc = regions.scene(key)
    gz_path = os.path.join(BUILD_DIR, f"scene_{key}.json.gz")
    if not os.path.exists(gz_path):
        build_scene(key)
    os.makedirs(out_dir, exist_ok=True)
    written = []

    # БЕЗ расширения .gz: у HF в .gitattributes есть правило *.gz filter=lfs,
    # а файл из LFS отдаётся редиректом на CDN — браузер такое скачивает.
    # Содержимое всё равно gzip, обозреватель узнаёт его по подписи в байтах.
    scene_name = f"twin_{key}.scene"
    with open(gz_path, "rb") as src, open(os.path.join(out_dir, scene_name), "wb") as dst:
        dst.write(src.read())
    written.append(os.path.join(out_dir, scene_name))

    tex_name = ""
    tex_uri = _aerial_data_uri(key, tex_max)
    if tex_uri:
        tex_name = f"twin_{key}.jpg"
        raw = base64.b64decode(tex_uri.split(",", 1)[1])
        with open(os.path.join(out_dir, tex_name), "wb") as f:
            f.write(raw)
        written.append(os.path.join(out_dir, tex_name))

    # Скрипты — отдельными файлами: страница должна остаться КРОШЕЧНОЙ.
    # Файл покрупнее HF отдаёт редиректом на свой CDN, и браузер такую
    # страницу скачивает вместо того, чтобы открыть. На <script src> редирект
    # не влияет — он важен только для самой навигации.
    three_name = f"twin_{key}.three.js"
    with open(os.path.join(out_dir, three_name), "w", encoding="utf-8") as f:
        f.write("var module={exports:{}},exports=module.exports;\n"
                + _three_source() + "\nvar THREE=module.exports;\n")
    written.append(os.path.join(out_dir, three_name))

    # дополнения three (GLTFLoader/DRACOLoader) и декодер Draco — отдельными
    # файлами: они нужны только тем, кто включит плитки Google, и не должны
    # утяжелять первую загрузку страницы.
    addons_name = f"twin_{key}.addons.js"
    with open(os.path.join(out_dir, addons_name), "w", encoding="utf-8") as f:
        f.write(_addons_source())
    written.append(os.path.join(out_dir, addons_name))

    draco_name = f"twin_{key}.draco.js"
    with open(os.path.join(out_dir, draco_name), "w", encoding="utf-8") as f:
        f.write("var TWIN_DRACO=" + json.dumps(_draco_assets()) + ";\n")
    written.append(os.path.join(out_dir, draco_name))

    app_name = f"twin_{key}.app.js"
    with open(os.path.join(out_dir, app_name), "w", encoding="utf-8") as f:
        f.write(APP_JS)
    written.append(os.path.join(out_dir, app_name))

    meta = {"key": key, "title": sc.title}
    html = (
        "<!DOCTYPE html>\n<html lang=\"ru\"><head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>TERRA · твин · " + sc.title + "</title>\n"
        "<style>\n" + CSS + "\n</style>\n"
        "</head>\n<body>\n" + BODY + "\n"
        "<script>var TWIN=" + json.dumps(meta, ensure_ascii=False) + ";\n"
        "var TWIN_GZ=\"\";var TWIN_TEX=\"\";\n"
        "var TWIN_SCENE_URL=" + json.dumps(scene_name) + ";\n"
        "var TWIN_TEX_URL=" + json.dumps(tex_name) + ";</script>\n"
        "<script src=\"" + three_name + "\"></script>\n"
        "<script src=\"" + draco_name + "\"></script>\n"
        "<script src=\"" + addons_name + "\"></script>\n"
        "<script src=\"" + app_name + "\"></script>\n"
        "</body></html>\n"
    )
    shell = os.path.join(out_dir, f"twin_{key}.html")
    with open(shell, "w", encoding="utf-8") as f:
        f.write(html)
    written.insert(0, shell)
    for p in written:
        print(f"  {os.path.basename(p)}: {os.path.getsize(p)/1e6:.1f} МБ")
    return written


def build_view(key: str, out_path: str | None = None,
               fragment: bool = False, tex_max: int = 4096) -> str:
    """Собрать обозреватель. fragment=True — без <html>/<head>/<body>,
    для встраивания (страница-артефакт, HF Space, чужой шаблон)."""
    sc = regions.scene(key)
    gz_path = os.path.join(BUILD_DIR, f"scene_{key}.json.gz")
    if not os.path.exists(gz_path):
        build_scene(key)
    gz64 = base64.b64encode(open(gz_path, "rb").read()).decode("ascii")
    tex = _aerial_data_uri(key, tex_max)

    meta = {"key": key, "title": sc.title}
    default_name = f"twin_{key}{'_embed' if fragment else ''}.html"
    out = out_path or os.path.join(BUILD_DIR, default_name)
    body = (
        "<style>\n" + CSS + "\n</style>\n"
        + BODY + "\n"
        "<script>var module={exports:{}},exports=module.exports;\n"
        + _three_source() +
        "\nvar THREE=module.exports;</script>\n"
        "<script>var TWIN_DRACO=" + json.dumps(_draco_assets()) + ";</script>\n"
        "<script>\n" + _addons_source() + "\n</script>\n"
        "<script>var TWIN=" + json.dumps(meta, ensure_ascii=False) + ";</script>\n"
        "<script>var TWIN_GZ=\"" + gz64 + "\";</script>\n"
        "<script>var TWIN_TEX=\"" + tex + "\";</script>\n"
        "<script>\n" + APP_JS + "\n</script>\n"
    )
    if fragment:
        html = ("<title>TERRA · твин · " + sc.title + "</title>\n" + body)
    else:
        html = (
            "<!DOCTYPE html>\n<html lang=\"ru\"><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>TERRA · твин · " + sc.title + "</title>\n"
            "</head>\n<body>\n" + body + "</body></html>\n"
        )
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"обозреватель: {out} ({os.path.getsize(out)/1e6:.1f} МБ)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка 3D-обозревателя твина")
    ap.add_argument("scene", nargs="?", default="sf")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--fragment", action="store_true",
                    help="без обёртки html/head/body — для встраивания")
    ap.add_argument("--tex", type=int, default=4096,
                    help="предел ширины аэрофотоснимка в пикселях")
    ap.add_argument("--split", metavar="КАТАЛОГ", default=None,
                    help="оболочка + данные рядом (для хостинга: файл тяжелее "
                         "10 МБ уходит в LFS и скачивается вместо открытия)")
    args = ap.parse_args()
    if args.split:
        build_split(args.scene, args.split, tex_max=args.tex)
    else:
        build_view(args.scene, args.out, fragment=args.fragment, tex_max=args.tex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
