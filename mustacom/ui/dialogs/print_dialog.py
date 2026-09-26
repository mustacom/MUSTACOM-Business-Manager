"""Print preview dialog: page preview, printer choice, copies, PDF export.

Works with A4 / A5 / thermal 80 mm / 58 mm papers.  When no physical printer
is installed (development machines), the dialog still allows PDF export, which
is how documents are produced in the sandbox and on headless servers.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout)

from ...i18n import tr
from ...reporting import render
from ..widgets.common import button, error, info


class PrintDialog(QDialog):
    def __init__(self, services, document, *, paper: str = "a4",
                 default_printer: str = "", title: str = "", parent=None):
        super().__init__(parent)
        self.services = services
        self.document = document
        self.paper = paper
        self.setWindowTitle(title or tr("print.preview_title"))
        self.resize(860, 900)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("print.printer") + " :"))
        self.printer_combo = QComboBox()
        self.printer_combo.addItem(tr("print.pdf_only"), "")
        for name in render.available_printers():
            self.printer_combo.addItem(name, name)
        if default_printer:
            index = self.printer_combo.findData(default_printer)
            if index >= 0:
                self.printer_combo.setCurrentIndex(index)
        bar.addWidget(self.printer_combo, 1)
        bar.addWidget(QLabel(tr("print.copies") + " :"))
        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.copies.setValue(self.services.settings.get_int("print.copies_invoice", 1))
        bar.addWidget(self.copies)
        bar.addWidget(button(tr("print.zoom_in"), lambda: self._zoom(1.2), icon="+"))
        bar.addWidget(button(tr("print.zoom_out"), lambda: self._zoom(1 / 1.2), icon="\u2212"))
        bar.addWidget(button(tr("common.print"), self._print, kind="primary",
                             icon="\U0001F5A8"))
        bar.addWidget(button(tr("common.export_pdf"), self._save_pdf, icon="\U0001F4C4"))
        root.addLayout(bar)

        self.pages_info = QLabel("")
        root.addWidget(self.pages_info)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        root.addWidget(self.scroll, 1)

        self._zoom_factor = 1.0
        self._render_page()

    # ------------------------------------------------------------------
    def _render_page(self) -> None:
        image = render.document_to_image(self.document, dpi=int(96 * self._zoom_factor))
        pixmap = QPixmap.fromImage(image)
        label = QLabel()
        label.setPixmap(pixmap)
        label.setStyleSheet("background: #e5e7eb;")
        self.scroll.setWidget(label)
        size = self.document.pageSize()
        self.pages_info.setText(
            f"{self.document.pageCount()} page(s)  -  {size.width() / 72 * 25.4:.0f} x "
            f"{size.height() / 72 * 25.4:.0f} mm")

    def _zoom(self, factor: float) -> None:
        self._zoom_factor = max(0.5, min(3.0, self._zoom_factor * factor))
        self._render_page()

    # ------------------------------------------------------------------
    def _print(self) -> None:
        name = self.printer_combo.currentData()
        if not name:
            self._save_pdf()
            return
        ok = render.print_document(self.document, name, self.copies.value(), self.paper)
        if ok:
            info(self, tr("print.printed"), tr("common.success"))
        else:
            error(self, tr("print.no_printer"))

    def _save_pdf(self) -> None:
        default = str(self.services.paths.exports /
                      f"document-{self.document.pageCount()}p.pdf")
        path, _ = QFileDialog.getSaveFileName(self, tr("common.export_pdf"), default,
                                              "PDF (*.pdf)")
        if not path:
            return
        render.document_to_pdf(self.services, self.document, path, self.paper)
        info(self, tr("print.pdf_saved", path=path), tr("common.success"))
