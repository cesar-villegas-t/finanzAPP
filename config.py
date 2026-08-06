import os
import secrets
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
PRIVATE_DIR = Path(os.environ.get("FINANZAPP_PRIVATE_DIR", ROOT_DIR / "private")).expanduser().resolve()
DATA_DIR = Path(os.environ.get("FINANZAPP_DATA_DIR", PRIVATE_DIR / "data")).expanduser().resolve()
AUTH_USERS_FILE = Path(
    os.environ.get("FINANZAPP_AUTH_USERS_FILE", PRIVATE_DIR / "auth" / "usuarios.json")
).expanduser().resolve()
NICEGUI_STORAGE_DIR = Path(
    os.environ.get("FINANZAPP_STORAGE_DIR", PRIVATE_DIR / "nicegui")
).expanduser().resolve()
BACKUP_DIR = Path(os.environ.get("FINANZAPP_BACKUP_DIR", PRIVATE_DIR / "backups")).expanduser().resolve()

LEGACY_ROOT_DATA_DIR = ROOT_DIR / "data"
LEGACY_AUTH_USERS_FILE = ROOT_DIR / "usuarios.json"
LEGACY_NICEGUI_STORAGE_DIR = ROOT_DIR / ".nicegui"

PRODUCTION_ENV_VALUES = {"prod", "production"}
IS_PRODUCTION = os.environ.get("FINANZAPP_ENV", "").strip().lower() in PRODUCTION_ENV_VALUES


def ensure_private_dirs():
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NICEGUI_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def get_storage_secret():
    secret = os.environ.get("FINANZAPP_STORAGE_SECRET")
    if secret:
        if IS_PRODUCTION and len(secret) < 32:
            raise RuntimeError("FINANZAPP_STORAGE_SECRET debe tener al menos 32 caracteres en produccion.")
        return secret

    if IS_PRODUCTION:
        raise RuntimeError("Define FINANZAPP_STORAGE_SECRET antes de arrancar en produccion.")

    ensure_private_dirs()
    secret_path = PRIVATE_DIR / "secrets" / "storage_secret"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    generated_secret = secrets.token_urlsafe(48)
    temp_path = secret_path.with_suffix(".tmp")
    temp_path.write_text(generated_secret, encoding="utf-8")
    try:
        os.replace(temp_path, secret_path)
    except PermissionError:
        secret_path.write_text(generated_secret, encoding="utf-8")
        try:
            temp_path.unlink(missing_ok=True)
        except PermissionError:
            pass
    return generated_secret
