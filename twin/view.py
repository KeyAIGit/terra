# Обозреватель твина: twin/data/build/scene_<key>.json.gz -> twin_<key>.html
#
# Самодостаточный офлайн-HTML: three.js вшит (как в глобусе), данные сцены —
# gzip+base64, распаковка родным DecompressionStream браузера.
#
#   python3 -m twin.view sf [-o twin_sf.html]

from __future__ import annotations

import argparse
import base64
import json
import os
import sys

from terra.globe import _three_source
from twin import regions
from twin.build import BUILD_DIR, build_scene
from twin._view_js import CSS, BODY, APP_JS


def build_view(key: str, out_path: str | None = None,
               fragment: bool = False) -> str:
    """Собрать обозреватель. fragment=True — без <html>/<head>/<body>,
    для встраивания (страница-артефакт, HF Space, чужой шаблон)."""
    sc = regions.scene(key)
    gz_path = os.path.join(BUILD_DIR, f"scene_{key}.json.gz")
    if not os.path.exists(gz_path):
        build_scene(key)
    gz64 = base64.b64encode(open(gz_path, "rb").read()).decode("ascii")

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
    args = ap.parse_args()
    build_view(args.scene, args.out, fragment=args.fragment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
