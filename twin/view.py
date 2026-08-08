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
import sys

from terra.globe import _three_source
from twin import regions
from twin.build import BUILD_DIR, build_scene
from twin._view_js import CSS, BODY, APP_JS


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
    args = ap.parse_args()
    build_view(args.scene, args.out, fragment=args.fragment, tex_max=args.tex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
