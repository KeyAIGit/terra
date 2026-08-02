# Загрузчик склада на Hugging Face: python3 -m atlas.upload_hf [--dry-run]
#
# Если задан env HF_TOKEN — создаёт публичный датасет Bekzod25/terra-atlas
# (repo_type=dataset, exist_ok) и заливает папки источников upload_folder'ом
# с повторами при обрыве; README датасета — из atlas/hf_readme.md.
# Без токена — печатает, что готово к загрузке и сколько ждёт.

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

from atlas.state import Manifest, DATA_DIR, ATLAS_DIR

REPO_ID = "Bekzod25/terra-atlas"
README_SRC = os.path.join(ATLAS_DIR, "hf_readme.md")
UPLOAD_STATUSES = ("done", "partial")  # failed-источники не заливаем
MAX_RETRIES = 5


def _sources_ready(man: Manifest) -> list[tuple[str, int]]:
    """Источники к загрузке: (имя, байт parquet)."""
    out = []
    for name, s in sorted(man.data.get("sources", {}).items()):
        if s.get("status") not in UPLOAD_STATUSES:
            continue
        files = glob.glob(os.path.join(DATA_DIR, name, "*.parquet"))
        size = sum(os.path.getsize(f) for f in files)
        if files:
            out.append((name, size))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Выгрузка склада на HF datasets")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать, что было бы загружено")
    args = ap.parse_args()

    man = Manifest()
    ready = _sources_ready(man)
    total_gb = sum(b for _, b in ready) / 1e9
    print(f"к загрузке в {REPO_ID}: {len(ready)} источников, {total_gb:.2f} ГБ")
    for name, b in ready:
        print(f"  {name:<16} {b / 1e6:>8.1f} МБ")

    token = os.environ.get("HF_TOKEN")
    if not token or args.dry_run:
        if not token:
            print("\nHF_TOKEN не задан — загрузчик ГОТОВ и ждёт токена.")
            print("как выстрелить: HF_TOKEN=hf_... python3 -m atlas.upload_hf")
        return 0

    from huggingface_hub import HfApi  # ставится: pip install huggingface_hub

    api = HfApi(token=token)
    api.create_repo(REPO_ID, repo_type="dataset", exist_ok=True, private=False)
    print(f"репозиторий {REPO_ID} готов")

    if os.path.exists(README_SRC):
        api.upload_file(path_or_fileobj=README_SRC, path_in_repo="README.md",
                        repo_id=REPO_ID, repo_type="dataset",
                        commit_message="Update dataset card")
        print("README.md датасета обновлён")
    if os.path.exists(os.path.join(DATA_DIR, "manifest.json")):
        api.upload_file(path_or_fileobj=os.path.join(DATA_DIR, "manifest.json"),
                        path_in_repo="manifest.json", repo_id=REPO_ID,
                        repo_type="dataset",
                        commit_message="Update provenance manifest")
        print("manifest.json загружен")

    for name, size in ready:
        folder = os.path.join(DATA_DIR, name)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[{name}] загрузка {size / 1e6:.1f} МБ "
                      f"(попытка {attempt}/{MAX_RETRIES})…")
                api.upload_folder(
                    folder_path=folder,
                    path_in_repo=f"data/{name}",
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    allow_patterns=["*.parquet"],
                    commit_message=f"Upload {name} parquet shards",
                )
                print(f"[{name}] загружен")
                break
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[{name}] обрыв: {str(e)[:200]}")
                if attempt == MAX_RETRIES:
                    print(f"[{name}] НЕ загружен после {MAX_RETRIES} попыток")
                    return 1
                time.sleep(10 * attempt)

    print(f"готово: https://huggingface.co/datasets/{REPO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
