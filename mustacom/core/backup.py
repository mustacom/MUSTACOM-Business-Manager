"""Backup and restore.

Backups are produced with the SQLite online backup API (the file stays
consistent even while the application is running), compressed, named with a
timestamp and optionally replicated to a second folder (USB stick, network
share, ...).  A small JSON manifest is written next to each archive so the
restore screen can show meaningful metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from ..config import DEFAULT_BACKUP_KEEP
from ..db.database import Database, now_iso


class BackupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupService:
    def __init__(self, db: Database, backups_dir: Path, settings=None):
        self.db = db
        self.backups_dir = Path(backups_dir)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self._timer: threading.Timer | None = None
        self._listeners: list = []

    # ------------------------------------------------------------------
    def on_event(self, callback) -> None:
        self._listeners.append(callback)

    def _emit(self, event: str, **data) -> None:
        for listener in list(self._listeners):
            try:
                listener(event, data)
            except Exception:  # pragma: no cover - UI callback safety
                pass

    # ------------------------------------------------------------------
    def location(self) -> Path:
        if self.settings is not None:
            custom = self.settings.get("backup.location", "")
            if custom:
                path = Path(custom).expanduser()
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    return path
                except OSError:
                    pass
        return self.backups_dir

    def create(self, label: str = "", mirror_to: Path | str | None = None) -> dict:
        """Create one backup archive and return its metadata."""
        target_dir = self.location()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"mustacom-backup-{stamp}{('-' + label) if label else ''}.zip"
        archive = target_dir / name
        if archive.exists():
            archive = target_dir / f"mustacom-backup-{stamp}-{abs(hash(name)) % 10000}.zip"

        tmp_db = archive.with_suffix(".db.tmp")
        try:
            self.db.backup_to(tmp_db)
            integrity, message = _check_file(tmp_db)
            if not integrity:
                raise BackupError(f"sauvegarde invalide: {message}")

            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
                bundle.write(tmp_db, arcname="mustacom.db")
                bundle.writestr("manifest.json", json.dumps({
                    "application": "MUSTACOM BUSINESS MANAGER",
                    "created_at": now_iso(),
                    "label": label,
                    "database_size": tmp_db.stat().st_size,
                }, indent=2, ensure_ascii=False))
        finally:
            if tmp_db.exists():
                tmp_db.unlink()

        meta = self._metadata(archive)
        if mirror_to:
            mirror_path = Path(mirror_to)
            try:
                mirror_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archive, mirror_path / archive.name)
                meta["mirror"] = str(mirror_path / archive.name)
            except OSError as exc:
                meta["mirror_error"] = str(exc)

        self.prune()
        self._emit("backup.created", **meta)
        return meta

    def _metadata(self, archive: Path) -> dict:
        try:
            size = archive.stat().st_size
        except OSError:
            size = 0
        return {
            "name": archive.name,
            "path": str(archive),
            "size_bytes": size,
            "size_human": _human_size(size),
            "created_at": datetime.fromtimestamp(archive.stat().st_mtime).strftime(
                "%d/%m/%Y %H:%M:%S") if size else "",
        }

    def list(self) -> list[dict]:
        archives = sorted(self.location().glob("mustacom-backup-*.zip"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        return [self._metadata(a) for a in archives]

    def verify(self, archive: Path | str) -> tuple[bool, str]:
        archive = Path(archive)
        if not archive.exists():
            return False, "fichier introuvable"
        try:
            with zipfile.ZipFile(archive) as bundle:
                bad = bundle.testzip()
                if bad:
                    return False, f"archive endommag\u00e9e: {bad}"
                if "mustacom.db" not in bundle.namelist():
                    return False, "base de donn\u00e9es absente de l'archive"
                with bundle.open("mustacom.db") as handle, _temp_file() as temp:
                    shutil.copyfileobj(handle, temp.open("wb"))
                    return _check_file(temp)
        except (zipfile.BadZipFile, OSError) as exc:
            return False, str(exc)

    def restore(self, archive: Path | str) -> None:
        archive = Path(archive)
        ok, message = self.verify(archive)
        if not ok:
            raise BackupError(message)
        with zipfile.ZipFile(archive) as bundle, _temp_file() as temp:
            with bundle.open("mustacom.db") as handle:
                shutil.copyfileobj(handle, temp.open("wb"))
            self.db.restore_from(temp)

    def prune(self, keep: int | None = None) -> int:
        keep = int(keep if keep is not None else
                   (self.settings.get_int("backup.keep", DEFAULT_BACKUP_KEEP)
                    if self.settings else DEFAULT_BACKUP_KEEP))
        archives = sorted(self.location().glob("mustacom-backup-*.zip"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for archive in archives[keep:]:
            try:
                archive.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    # ------------------------------------------------------------------
    # scheduling
    # ------------------------------------------------------------------
    def auto_backup_due(self) -> bool:
        if self.settings is None or not self.settings.get_bool("backup.auto_enabled", True):
            return False
        last = self.settings.get("backup.last_run", "")
        hour = self.settings.get_int("backup.hour", 20)
        minute = self.settings.get_int("backup.minute", 0)
        now = datetime.now()
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace(" ", "T"))
                if last_dt.date() == now.date():
                    return False
            except ValueError:
                pass
        return (now.hour, now.minute) >= (hour, minute)

    def run_auto(self) -> dict | None:
        if not self.auto_backup_due():
            return None
        meta = self.create(label="auto")
        if self.settings is not None:
            self.settings.set("backup.last_run", now_iso())
        return meta

    def start_scheduler(self, interval_seconds: int = 900) -> None:
        """Lightweight in-process scheduler (checks every ``interval``)."""
        self.stop_scheduler()

        def tick() -> None:
            try:
                self.run_auto()
            finally:
                self._timer = threading.Timer(interval_seconds, tick)
                self._timer.daemon = True
                self._timer.start()

        self._timer = threading.Timer(interval_seconds, tick)
        self._timer.daemon = True
        self._timer.start()

    def stop_scheduler(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    # ------------------------------------------------------------------
    def integrity_report(self) -> dict:
        ok, message = self.db.integrity_check()
        return {"ok": ok, "message": message,
                "foreign_key_violations": self.db.foreign_key_check(),
                "database": str(self.db.path),
                "size_human": _human_size(self.db.path.stat().st_size
                                          if self.db.path.exists() else 0)}


def _check_file(path: Path) -> tuple[bool, str]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        result = row[0] if row else "unknown"
        if result != "ok":
            return False, str(result)
        version = conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_version").fetchone()
        return True, f"ok (sch\u00e9ma v{version[0] if version else 0})"
    except sqlite3.Error as exc:
        return False, str(exc)
    finally:
        conn.close()


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            return f"{value:,.1f} {unit}".replace(",", " ")
        value /= 1024
    return f"{value:.1f} To"


class _temp_file:
    """Context manager yielding a ``Path`` that is deleted on exit."""

    def __enter__(self) -> Path:
        handle, name = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.path = Path(name)
        return self.path

    def __exit__(self, *exc) -> None:
        if getattr(self, "path", None) and self.path.exists():
            self.path.unlink()
