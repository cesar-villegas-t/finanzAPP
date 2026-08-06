import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import BACKUP_DIR, DATA_DIR, ensure_private_dirs


BACKUP_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def sqlite_integrity_check(db_path):
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def _backup_path_for(db_path, backup_root=None, timestamp=None):
    db_path = Path(db_path)
    backup_root = Path(backup_root or BACKUP_DIR)
    timestamp = timestamp or datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    return backup_root / db_path.stem / f"{db_path.stem}_{timestamp}.db"


def backup_database(db_path, backup_root=None):
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    if not sqlite_integrity_check(db_path):
        raise RuntimeError(f"No se crea backup porque la base no pasa integrity_check: {db_path}")

    backup_path = _backup_path_for(db_path, backup_root)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        backup_path = _backup_path_for(
            db_path,
            backup_root,
            f"{datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)}_{os.getpid()}",
        )
    shutil.copy2(db_path, backup_path)
    if not verify_backup_restore(backup_path):
        backup_path.unlink(missing_ok=True)
        raise RuntimeError(f"El backup no supera la prueba de restauracion: {backup_path}")
    return backup_path


def verify_backup_restore(backup_path):
    backup_path = Path(backup_path)
    if not backup_path.exists():
        return False
    try:
        with sqlite3.connect(backup_path) as source, sqlite3.connect(":memory:") as target:
            source.backup(target)
            return target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return sqlite_integrity_check(backup_path)


def list_database_files():
    ensure_private_dirs()
    return sorted(path for path in DATA_DIR.glob("*.db") if path.is_file())


def _latest_backup_mtime(db_path):
    backup_dir = BACKUP_DIR / Path(db_path).stem
    backups = sorted(backup_dir.glob("*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    return backups[0].stat().st_mtime if backups else None


def create_due_backups(min_hours=None):
    if os.environ.get("FINANZAPP_BACKUP_ON_STARTUP", "1").strip() == "0":
        return []

    min_hours = min_hours if min_hours is not None else int(os.environ.get("FINANZAPP_BACKUP_MIN_HOURS", "24"))
    cutoff = (datetime.now() - timedelta(hours=min_hours)).timestamp()
    created = []
    for db_path in list_database_files():
        latest_mtime = _latest_backup_mtime(db_path)
        if latest_mtime is not None and latest_mtime >= cutoff:
            continue
        created.append(backup_database(db_path))
    return created


def verify_all_backups():
    ensure_private_dirs()
    results = {}
    for backup_path in sorted(BACKUP_DIR.glob("*/*.db")):
        results[str(backup_path)] = verify_backup_restore(backup_path)
    return results


def restore_database_backup(backup_path, target_db_name, replace=False):
    backup_path = Path(backup_path).expanduser().resolve()
    target_path = (DATA_DIR / target_db_name).resolve()
    if target_path.parent != DATA_DIR.resolve():
        raise ValueError("El destino debe estar dentro de FINANZAPP_DATA_DIR.")
    if target_path.exists() and not replace:
        raise FileExistsError(f"Ya existe {target_path}. Usa replace=True para sobrescribir.")
    if not verify_backup_restore(backup_path):
        raise RuntimeError(f"El backup no supera la prueba de restauracion: {backup_path}")

    ensure_private_dirs()
    temp_target = target_path.with_suffix(target_path.suffix + ".restore_tmp")
    with sqlite3.connect(backup_path) as source, sqlite3.connect(temp_target) as target:
        source.backup(target)
    if not sqlite_integrity_check(temp_target):
        temp_target.unlink(missing_ok=True)
        raise RuntimeError(f"La base restaurada no supera integrity_check: {temp_target}")
    os.replace(temp_target, target_path)
    return target_path


def archive_extra_data_files(keep_names):
    ensure_private_dirs()
    keep_names = set(keep_names)
    archive_root = BACKUP_DIR / "cleanup" / datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    archived = []
    for path in sorted(DATA_DIR.iterdir()):
        if path.name in keep_names or path.name.startswith("."):
            continue
        archive_root.mkdir(parents=True, exist_ok=True)
        target = archive_root / path.name
        if path.is_dir():
            shutil.move(str(path), str(target))
        else:
            shutil.move(str(path), str(target))
        archived.append(target)
    return archived
