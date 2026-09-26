"""MUSTACOM BUSINESS MANAGER - application entry point.

Startup sequence
----------------
1. resolve the data directory and open/migrate the SQLite database,
2. seed roles, default settings and the default catalogue,
3. require a valid license (activation screen when missing),
4. create the administrator account on a brand-new database,
5. authenticate the user,
6. start the main window, the backup scheduler and the license watchdog.

Run with ``python -m mustacom`` (or the packaged ``MUSTACOM.exe``).
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mustacom", description="MUSTACOM BUSINESS MANAGER")
    parser.add_argument("--data-dir", help="override the application data directory")
    parser.add_argument("--database", help="use a specific SQLite file")
    parser.add_argument("--dark", action="store_true", help="start with the dark theme")
    parser.add_argument("--lang", choices=("fr", "ar", "en"), help="interface language")
    parser.add_argument("--demo-data", action="store_true",
                        help="load the demonstration dataset if the database is empty")
    parser.add_argument("--skip-license", action="store_true",
                        help="development only: bypass the activation screen")
    parser.add_argument("--reset", action="store_true",
                        help="delete the local database before starting (DESTRUCTIVE)")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    from .config import APP_NAME, APP_VERSION, build_paths

    if args.version:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0

    if args.data_dir:
        os.environ["MUSTACOM_DATA_DIR"] = str(Path(args.data_dir).expanduser())
    paths = build_paths(Path(os.environ["MUSTACOM_DATA_DIR"])
                        if os.environ.get("MUSTACOM_DATA_DIR") else None)
    paths.ensure()

    if args.reset and paths.db.exists():
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(paths.db) + suffix)
            if candidate.exists():
                candidate.unlink()

    from PySide6.QtWidgets import QApplication

    from .db.database import open_database
    from .i18n import I18N
    from .services import Services
    from .ui import theme

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("MUSTACOM")

    db_path = Path(args.database) if args.database else paths.db
    try:
        database = open_database(db_path)
    except Exception as exc:
        _fatal(f"Impossible d'ouvrir la base de donn\u00e9es {db_path}\n{exc}")
        return 1

    services = Services(database, paths)
    services.bootstrap()

    if args.lang:
        services.settings.set("locale.language", args.lang)
    I18N.set_language(services.settings.language())

    dark = args.dark or services.settings.get("appearance.theme") == "dark"
    theme.install(app, dark)

    if args.demo_data:
        from .core.seed import seed_demo_data

        seeded = seed_demo_data(services)
        if seeded:
            print(f"Jeu de d\u00e9monstration charg\u00e9 ({seeded} produits)")

    # ---- licensing ---------------------------------------------------------
    if not args.skip_license:
        status = services.license.status()
        if not status.active or status.blocked:
            from .ui.dialogs.activation import ActivationDialog

            dialog = ActivationDialog(services)
            dialog.exec()
            if not dialog.activated:
                return 0
            status = services.license.status()
            if status.blocked:
                _fatal(status.message)
                return 1

    # ---- first-run administrator ------------------------------------------
    if services.auth.count_users() == 0:
        from .ui.dialogs.login import FirstUserDialog

        wizard = FirstUserDialog(services)
        wizard.exec()
        if not wizard.created:
            return 0
        I18N.set_language(services.settings.language())
        theme.install(app, dark)

    # ---- authentication ----------------------------------------------------
    from .ui.dialogs.login import LoginDialog

    login = LoginDialog(services)
    login.exec()
    if login.session is None:
        return 0
    session = login.session
    session.timeout_minutes = services.settings.get_int("security.session_timeout_minutes", 0)
    services.current_user = {"id": session.user_id, "username": session.username}
    services.settings.set("locale.language", I18N.lang)

    # ---- main window -------------------------------------------------------
    from .ui.main_window import MainWindow

    window = MainWindow(services, session)
    window.show()

    services.backup.start_scheduler()
    services.license.record_seen()

    code = app.exec()
    services.backup.stop_scheduler()
    return code


def _fatal(message: str) -> None:
    print(message, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            QApplication(sys.argv)
        QMessageBox.critical(None, "MUSTACOM", message)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    raise SystemExit(main())
