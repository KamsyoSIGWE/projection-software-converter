from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..conversion.base import ConversionRequest
from ..conversion.registry import ConversionRegistry, RegistryValidationError
from ..conversion.service import ConverterService, default_output_path_in_dir


class ConversionWorker(QThread):
    conversion_finished = Signal(object)
    conversion_failed = Signal(str)

    def __init__(self, converter_service: ConverterService, request: ConversionRequest) -> None:
        super().__init__()
        self._converter_service = converter_service
        self._request = request

    def run(self) -> None:
        try:
            result = self._converter_service.convert(self._request)
        except (FileNotFoundError, RegistryValidationError, ValueError) as exc:
            self.conversion_failed.emit(str(exc))
            return
        except Exception as exc:  # pragma: no cover
            self.conversion_failed.emit(f"Conversion failed: {exc}")
            return
        self.conversion_finished.emit(result)


class UploadDialog(QDialog):
    def __init__(self, registry: ConversionRegistry, converter_service: ConverterService, parent=None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._converter_service = converter_service
        self._conversion_worker: ConversionWorker | None = None
        self.setWindowTitle("Upload File")
        self.setModal(True)
        self.resize(520, 230)

        self.file_path_edit = QLineEdit(self)
        self.file_path_edit.setPlaceholderText("Choose a .vpagd, .project, or .ewsx file")
        self.file_path_edit.textChanged.connect(self._on_file_changed)

        self.output_folder_edit = QLineEdit(self)
        self.output_folder_edit.setPlaceholderText("Choose where the converted file should be saved")
        self.output_folder_edit.setText(str(self._default_output_folder()))

        self.browse_button = QPushButton("Browse", self)
        self.browse_button.clicked.connect(self._browse_for_file)

        self.output_browse_button = QPushButton("Browse", self)
        self.output_browse_button.clicked.connect(self._browse_for_output_folder)

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_path_edit)
        file_row.addWidget(self.browse_button)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_folder_edit)
        output_row.addWidget(self.output_browse_button)

        self.source_combo = QComboBox(self)
        self.target_combo = QComboBox(self)
        self.source_combo.currentTextChanged.connect(self._refresh_targets)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #555;")

        self.convert_button = QPushButton("Convert", self)
        self.convert_button.clicked.connect(self._run_conversion)

        form_layout = QFormLayout()
        form_layout.addRow("File", file_row)
        form_layout.addRow("Convert from", self.source_combo)
        form_layout.addRow("Convert to", self.target_combo)
        form_layout.addRow("Save to folder", output_row)

        layout = QVBoxLayout()
        helper = QLabel("Choose the source file, select a supported conversion direction, and pick where the converted file should be saved.", self)
        helper.setWordWrap(True)
        helper.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(helper)
        layout.addLayout(form_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.convert_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(layout)

        self._populate_sources()

    def _populate_sources(self) -> None:
        self.source_combo.clear()
        self.source_combo.addItems(self._registry.query_available_sources())
        self._refresh_targets()

    def _refresh_targets(self) -> None:
        source = self.source_combo.currentText()
        targets = self._registry.query_available_targets(source) if source else []
        self.target_combo.clear()
        self.target_combo.addItems(targets)

    def _browse_for_file(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose a file to convert",
            "",
            "Projection files (*.vpagd *.project *.ewsx);;All files (*.*)",
        )
        if file_path:
            self.file_path_edit.setText(file_path)

    def _browse_for_output_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Choose where to save the converted file",
            self.output_folder_edit.text().strip() or str(self._default_output_folder()),
        )
        if folder_path:
            self.output_folder_edit.setText(folder_path)

    def _on_file_changed(self, file_path: str) -> None:
        detected_source = self._detect_source(Path(file_path)) if file_path else None
        if detected_source and detected_source in [self.source_combo.itemText(index) for index in range(self.source_combo.count())]:
            self.source_combo.setCurrentText(detected_source)
        self._refresh_targets()
        if detected_source is None and file_path:
            self.status_label.setText("The file extension was not recognized. Choose the source format manually.")
        else:
            self.status_label.setText("")

    @staticmethod
    def _detect_source(path: Path) -> str | None:
        if path.suffix.lower() == ".vpagd":
            return "VideoPsalm"
        if path.suffix.lower() == ".project":
            return "FreeShow"
        if path.suffix.lower() == ".ewsx":
            return "EasyWorship"
        return None

    @staticmethod
    def _default_output_folder() -> Path:
        downloads = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if downloads:
            download_path = Path(downloads)
            if download_path.exists():
                return download_path
            return download_path
        home = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.HomeLocation)
        if home:
            return Path(home)
        return Path.home()

    def _run_conversion(self) -> None:
        if self._conversion_worker is not None and self._conversion_worker.isRunning():
            return

        input_path = Path(self.file_path_edit.text().strip())
        if not input_path:
            self._show_error("Please choose a file to convert.")
            return

        source = self.source_combo.currentText().strip()
        target = self.target_combo.currentText().strip()
        output_dir = Path(self.output_folder_edit.text().strip()) if self.output_folder_edit.text().strip() else self._default_output_folder()
        output_path = default_output_path_in_dir(input_path, target, output_dir)
        request = ConversionRequest(
            input_path=input_path,
            output_path=output_path,
            source=source,
            target=target,
        )

        self._set_conversion_running(True)
        self._conversion_worker = ConversionWorker(self._converter_service, request)
        self._conversion_worker.conversion_finished.connect(self._handle_conversion_finished)
        self._conversion_worker.conversion_failed.connect(self._handle_conversion_failed)
        self._conversion_worker.finished.connect(self._cleanup_worker)
        self._conversion_worker.start()

    def _handle_conversion_finished(self, result) -> None:
        self._set_conversion_running(False)
        QMessageBox.information(
            self,
            "Conversion Complete",
            f"Converted {result.item_count} item(s).\n\nSaved to:\n{result.output_path}",
        )
        self.accept()

    def _handle_conversion_failed(self, message: str) -> None:
        self._set_conversion_running(False)
        self._show_error(message)

    def _cleanup_worker(self) -> None:
        if self._conversion_worker is not None:
            self._conversion_worker.deleteLater()
            self._conversion_worker = None

    def _set_conversion_running(self, running: bool) -> None:
        self.file_path_edit.setEnabled(not running)
        self.output_folder_edit.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.output_browse_button.setEnabled(not running)
        self.source_combo.setEnabled(not running)
        self.target_combo.setEnabled(not running)
        self.convert_button.setEnabled(not running)
        if running:
            self.status_label.setText("Converting... This can take a moment for larger files.")
        elif self.status_label.text().startswith("Converting..."):
            self.status_label.setText("")

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.warning(self, "Unable to Convert", message)
