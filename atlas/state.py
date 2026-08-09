# Манифест состояния склада: atlas/data/manifest.json.
#
# По каждому источнику: статус (pending/partial/done/failed), готовые чанки
# с контрольными суммами, список выложенных parquet-файлов, размеры, ошибки.
# Повторный запуск ingest читает манифест и продолжает с места обрыва:
# готовые чанки не переделываются, полудокачанные файлы докачиваются Range'ом.

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import datetime as _dt

ATLAS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ATLAS_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "_raw")  # сырьё; удаляется после обработки
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")

STATUSES = ("pending", "partial", "done", "failed")


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


class Manifest:
    """Обёртка над manifest.json с атомарной записью."""

    def __init__(self, path: str = MANIFEST_PATH):
        self.path = path
        # корень данных: пути files в манифесте — относительно него
        # (наследники, напр. twin.state.Manifest, задают свой)
        self.data_dir = os.path.dirname(path)
        self.data: dict = {"version": 1, "updated": None, "sources": {}}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self.data.setdefault("sources", {})

    # ---------- запись ----------

    def save(self) -> None:
        self.data["updated"] = now_iso()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)  # атомарно
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ---------- источники ----------

    def src(self, name: str) -> dict:
        """Запись источника (создаёт pending-заготовку при первом обращении)."""
        s = self.data["sources"].setdefault(name, {
            "status": "pending",
            "chunks": {},       # имя чанка -> {done, rows, sha256, bytes, note}
            "files": [],        # итоговые parquet: {path, bytes, sha256, rows}
            "pending_urls": [],  # что ещё известно, но не скачано (например HYDE)
            "error": None,
            "attempts": 0,
            "last_attempt": None,
        })
        return s

    def set_status(self, name: str, status: str, error: str | None = None) -> None:
        assert status in STATUSES, status
        s = self.src(name)
        s["status"] = status
        s["error"] = error
        s["last_attempt"] = now_iso()
        self.save()

    def bump_attempt(self, name: str) -> None:
        s = self.src(name)
        s["attempts"] = s.get("attempts", 0) + 1
        s["last_attempt"] = now_iso()
        self.save()

    # ---------- чанки (резюмируемость) ----------

    def chunk_done(self, name: str, chunk: str) -> bool:
        return bool(self.src(name)["chunks"].get(chunk, {}).get("done"))

    def mark_chunk(self, name: str, chunk: str, rows: int = 0,
                   note: str = "", files: list[str] | None = None) -> None:
        """Чанк завершён; files — записанные им parquet (пути от DATA_DIR)."""
        s = self.src(name)
        entry = {"done": True, "rows": int(rows), "at": now_iso()}
        if note:
            entry["note"] = note
        s["chunks"][chunk] = entry
        for rel in files or []:
            full = os.path.join(self.data_dir, rel)
            info = {
                "path": rel,
                "bytes": os.path.getsize(full),
                "sha256": sha256_file(full),
                "rows": int(rows) if len(files or []) == 1 else None,
            }
            s["files"] = [f for f in s["files"] if f["path"] != rel] + [info]
        self.save()

    def files_of(self, name: str) -> list[dict]:
        return list(self.src(name)["files"])

    def set_pending_urls(self, name: str, urls: list[str]) -> None:
        self.src(name)["pending_urls"] = urls
        self.save()

    # ---------- сводка ----------

    def summary(self) -> list[dict]:
        out = []
        for name, s in sorted(self.data["sources"].items()):
            total_bytes = sum(f.get("bytes", 0) for f in s.get("files", []))
            total_rows = sum(c.get("rows", 0) for c in s.get("chunks", {}).values())
            out.append({
                "source": name,
                "status": s.get("status"),
                "files": len(s.get("files", [])),
                "rows": total_rows,
                "mb": round(total_bytes / 1e6, 1),
                "error": s.get("error"),
            })
        return out


def disk_free_gb(path: str = DATA_DIR) -> float:
    """Свободно на диске, ГБ."""
    os.makedirs(path, exist_ok=True)
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9
