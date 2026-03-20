from __future__ import annotations

from PySide6.QtWidgets import QApplication

from .conversion.bootstrap import build_registry
from .conversion.service import ConverterService
from .gui.main_window import MainWindow
from .logging_config import configure_logging


def run_gui(registry=None, converter_service=None) -> int:
    configure_logging()
    app = QApplication.instance() or QApplication([])
    registry = registry or build_registry()
    converter_service = converter_service or ConverterService(registry)
    window = MainWindow(registry, converter_service)
    window.show()
    return app.exec()


def main() -> int:
    return run_gui()
