import argparse
import sys

from db.backups import (
    archive_extra_data_files,
    backup_database,
    list_database_files,
    restore_database_backup,
    verify_all_backups,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tareas de mantenimiento de FinanzAPP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("backup", help="Crea y verifica backups de las bases activas.")
    subparsers.add_parser("verify-backups", help="Prueba la restauracion de todos los backups existentes.")

    restore_parser = subparsers.add_parser("restore", help="Restaura un backup SQLite verificado.")
    restore_parser.add_argument("backup_path")
    restore_parser.add_argument("target_db_name")
    restore_parser.add_argument("--replace", action="store_true")

    clean_parser = subparsers.add_parser("clean-data", help="Archiva ficheros no activos del directorio de datos.")
    clean_parser.add_argument("keep", nargs="+")

    args = parser.parse_args(argv)

    if args.command == "backup":
        for db_path in list_database_files():
            print(backup_database(db_path))
        return 0

    if args.command == "verify-backups":
        results = verify_all_backups()
        for path, ok in results.items():
            print(f"{path}: {'ok' if ok else 'failed'}")
        return 0 if all(results.values()) else 1

    if args.command == "restore":
        print(restore_database_backup(args.backup_path, args.target_db_name, replace=args.replace))
        return 0

    if args.command == "clean-data":
        for path in archive_extra_data_files(args.keep):
            print(path)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
