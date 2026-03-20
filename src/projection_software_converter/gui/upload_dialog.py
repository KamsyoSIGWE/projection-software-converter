from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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
from ..conversion.service import ConverterService, default_output_path


class UploadDialog(QDialog):
    def __init__(self, registry: ConversionRegistry, converter_service: ConverterService, parent=None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._converter_service = converter_service
        self.setWindowTitle("Upload File")
        self.setModal(True)
        self.resize(520, 230)

        self.file_path_edit = QLineEdit(self)
        self.file_path_edit.setPlaceholderText("Choose a .vpagd or .project file")
        self.file_path_edit.textChanged.connect(self._on_file_changed)

        browse_button = QPushButton("Browse", self)
        browse_button.clicked.connect(self._browse_for_file)

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_path_edit)
        file_row.addWidget(browse_button)

        self.source_combo = QComboBox(self)
        self.target_combo = QComboBox(self)
        self.source_combo.currentTextChanged.connect(self._refresh_targets)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #555;")

        convert_button = QPushButton("Convert", self)
        convert_button.clicked.connect(self._run_conversion)

        form_layout = QFormLayout()
        form_layout.addRow("File", file_row)
        form_layout.addRow("Convert from", self.source_combo)
        form_layout.addRow("Convert to", self.target_combo)

        layout = QVBoxLayout()
        helper = QLabel("Choose the source file and select a supported conversion direction.", self)
        helper.setWordWrap(True)
        helper.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(helper)
        layout.addLayout(form_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(convert_button, alignment=Qt.AlignmentFlag.AlignRight)
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
            "Projection files (*.vpagd *.project);;All files (*.*)",
        )
        if file_path:
            self.file_path_edit.setText(file_path)

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
        return None

    def _run_conversion(self) -> None:
        input_path = Path(self.file_path_edit.text().strip())
        if not input_path:
            self._show_error("Please choose a file to convert.")
            return

        source = self.source_combo.currentText().strip()
        target = self.target_combo.currentText().strip()
        output_path = default_output_path(input_path, target)

        try:
            result = self._converter_service.convert(
                ConversionRequest(
                    input_path=input_path,
                    output_path=output_path,
                    source=source,
                    target=target,
                )
            )
        except (FileNotFoundError, RegistryValidationError, ValueError) as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # pragma: no cover
            self._show_error(f"Conversion failed: {exc}")
            return

        QMessageBox.information(
            self,
            "Conversion Complete",
            f"Converted {result.item_count} item(s).\n\nSaved to:\n{result.output_path}",
        )
        self.accept()

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.warning(self, "Unable to Convert", message)
