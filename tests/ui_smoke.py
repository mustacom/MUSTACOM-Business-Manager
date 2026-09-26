"""Headless UI harness: builds a demo database, logs in, and drives the UI.

Used by ``tests/test_ui_smoke.py`` and by the development screenshots.  Runs
with ``QT_QPA_PLATFORM=offscreen`` so it works on CI and in this sandbox.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mustacom.core.license import issue_license, machine_id  # noqa: E402
from mustacom.core.seed import seed_demo_data  # noqa: E402
from mustacom.db.database import open_database  # noqa: E402
from mustacom.services import Services  # noqa: E402
from mustacom.ui import theme  # noqa: E402


def build_app(with_demo: bool = True, dark: bool = False, admin_password="Admin!2345"):
    data = Path(tempfile.mkdtemp())
    os.environ["MUSTACOM_DATA_DIR"] = str(data)
    app = QApplication.instance() or QApplication(sys.argv)
    theme.install(app, dark)

    services = Services(open_database(data / "smoke.db"), None)
    services.bootstrap()
    services.auth.create_user("admin", admin_password, "Administrateur", "admin")
    payload, key, signature = issue_license("MUSTACOM", "Admin", machine_id(),
                                            "professional")
    services.license.save(payload, signature, key)
    if with_demo:
        seed_demo_data(services)

    session = services.auth.login("admin", admin_password)
    services.current_user = {"id": session.user_id, "username": session.username}

    from mustacom.ui.main_window import MainWindow

    window = MainWindow(services, session)
    window.resize(1500, 940)
    window.show()
    app.processEvents()
    return app, services, window


def grab(window, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(destination))
    return destination
