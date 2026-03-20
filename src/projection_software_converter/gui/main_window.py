from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMainWindow, QMenuBar, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..config import DEFAULT_CONFIG
from ..conversion.registry import ConversionRegistry
from ..conversion.service import ConverterService
from ..updater import GitHubReleaseUpdater, ReleaseInfo, UpdateError
from .upload_dialog import UploadDialog

LOGGER = logging.getLogger(__name__)


class UpdateWorker(QThread):
    update_found = Signal(object)
    update_error = Signal(str)

    def __init__(self, updater: GitHubReleaseUpdater) -> None:
        super().__init__()
        self._updater = updater

    def run(self) -> None:
        try:
            release = self._updater.check_for_updates()
        except UpdateError as exc:
            self.update_error.emit(str(exc))
            return
        self.update_found.emit(release)


class MainWindow(QMainWindow):
    def __init__(self, registry: ConversionRegistry, converter_service: ConverterService) -> None:
        super().__init__()
        self._registry = registry
        self._converter_service = converter_service
        self._updater = GitHubReleaseUpdater(DEFAULT_CONFIG.github_updates)
        self._update_worker: UpdateWorker | None = None

        self.setWindowTitle(DEFAULT_CONFIG.app_name)
        self.resize(640, 360)

        central_widget = QWidget(self)
        layout = QVBoxLayout()
        layout.setSpacing(16)

        header = QLabel("Welcome to Projection Software Converter", self)
        header.setStyleSheet("font-size: 24px; font-weight: 700;")

        description = QLabel(
            "This app helps teams move projection content between different presentation platforms when different people use "
            "different software but need the same order, media, and presentation flow. It is designed to make conversion "
            "between supported projection software formats easier as support expands over time.",
            self,
        )
        description.setWordWrap(True)

        supported_formats = ", ".join(self._registry.query_supported_formats())
        supported_label = QLabel(f"Supported conversions: {supported_formats}", self)
        supported_label.setStyleSheet("font-weight: 600;")

        upload_button = QPushButton("Upload", self)
        upload_button.setFixedWidth(140)
        upload_button.clicked.connect(self._open_upload_dialog)

        layout.addWidget(header)
        layout.addWidget(description)
        layout.addWidget(supported_label)
        layout.addStretch()
        layout.addWidget(upload_button)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.setMenuBar(self._build_menu())
        self.check_for_updates(silent=True)

    def _build_menu(self) -> QMenuBar:
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu("File")
        help_menu = menu_bar.addMenu("Help")

        upload_action = QAction("Upload", self)
        upload_action.triggered.connect(self._open_upload_dialog)
        file_menu.addAction(upload_action)

        check_updates_action = QAction("Check for Updates", self)
        check_updates_action.triggered.connect(lambda: self.check_for_updates(silent=False))
        help_menu.addAction(check_updates_action)
        return menu_bar

    def _open_upload_dialog(self) -> None:
        dialog = UploadDialog(self._registry, self._converter_service, self)
        dialog.exec()

    def check_for_updates(self, silent: bool) -> None:
        self._update_worker = UpdateWorker(self._updater)
        self._update_worker.update_found.connect(lambda release: self._handle_update_check(release, silent))
        self._update_worker.update_error.connect(lambda message: self._handle_update_error(message, silent))
        self._update_worker.start()

    def _handle_update_check(self, release: ReleaseInfo | None, silent: bool) -> None:
        if release is None:
            if not silent:
                QMessageBox.information(self, "Updates", "You already have the latest published version.")
            return

        notes = release.notes or "No release notes were provided."
        answer = QMessageBox.question(
            self,
            "Update Available",
            f"Version {release.version} is available.\n\nRelease notes:\n{notes}\n\nDownload and install now?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            installer_path = self._updater.download_release_installer(release)
            self._updater.launch_installer(installer_path)
        except UpdateError as exc:
            QMessageBox.warning(self, "Update Failed", str(exc))
            return
        LOGGER.info("Launched installer update from %s", installer_path)
        self.close()

    def _handle_update_error(self, message: str, silent: bool) -> None:
        if silent:
            LOGGER.warning("Silent update check failed: %s", message)
            return
        QMessageBox.warning(self, "Update Check Failed", message)
