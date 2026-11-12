"""Dialogue d'options d'export — indépendant des paramètres de stylisation."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


class ExportOptionsDialog(QDialog):
    def __init__(self, image_count, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options d'exportation")
        self.setMinimumWidth(380)
        self.settings = settings

        layout = QVBoxLayout(self)
        scope_group = QGroupBox("Images à exporter")
        scope_layout = QVBoxLayout(scope_group)
        self.current_radio = QRadioButton("Image actuelle uniquement")
        self.all_radio = QRadioButton(f"Toutes les images ({image_count})")
        scope_layout.addWidget(self.current_radio)
        scope_layout.addWidget(self.all_radio)
        layout.addWidget(scope_group)

        # Comportement historique par défaut : exporter toute la sélection.
        scope = settings.value("export/scope", "all")
        if scope == "current":
            self.current_radio.setChecked(True)
        else:
            self.all_radio.setChecked(True)

        options_group = QGroupBox("Format de sortie")
        form = QFormLayout(options_group)
        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG — sans perte", "PNG")
        self.format_combo.addItem("JPEG — fichier léger", "JPEG")
        self.format_combo.addItem("WebP — fichier léger", "WEBP")
        self.format_combo.setMinimumHeight(32)
        fmt = settings.value("export/format", "PNG")
        fmt_index = self.format_combo.findData(fmt)
        if fmt_index >= 0:
            self.format_combo.setCurrentIndex(fmt_index)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(max(1, min(100, int(settings.value("export/quality", 90)))))
        self.quality_spin.setSuffix(" %")
        self.quality_spin.setMinimumHeight(32)
        self.quality_spin.setToolTip("Qualité de compression pour JPEG et WebP (1 à 100).")

        self.quality_note = QLabel("PNG est sans perte : le réglage de qualité ne s'applique pas.")
        self.quality_note.setWordWrap(True)

        form.addRow("Format :", self.format_combo)
        form.addRow("Qualité :", self.quality_spin)
        form.addRow(self.quality_note)
        layout.addWidget(options_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Démarrer l'export")
        buttons.button(QDialogButtonBox.Cancel).setText("Retour")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.format_combo.currentIndexChanged.connect(self.update_quality_ui)
        self.update_quality_ui()

    def update_quality_ui(self):
        fmt = self.format_combo.currentData()
        lossy = fmt in ("JPEG", "WEBP")
        self.quality_spin.setEnabled(lossy)
        self.quality_note.setText(
            "Plus la qualité est élevée, plus le fichier peut être volumineux."
            if lossy
            else "PNG est sans perte : le réglage de qualité ne s'applique pas."
        )

    def selected_options(self):
        return {
            "scope": "current" if self.current_radio.isChecked() else "all",
            "image_format": self.format_combo.currentData(),
            "quality": self.quality_spin.value(),
        }

    def accept(self):
        options = self.selected_options()
        self.settings.setValue("export/scope", options["scope"])
        self.settings.setValue("export/format", options["image_format"])
        self.settings.setValue("export/quality", options["quality"])
        super().accept()
