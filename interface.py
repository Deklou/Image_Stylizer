from pathlib import Path
import secrets
import os

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QGroupBox,
    QFileDialog,
    QSpinBox,
    QDoubleSpinBox,
    QProgressBar,
    QMessageBox,
    QComboBox,
    QInputDialog,
    QStackedWidget,
    QScrollArea,
    QFrame,
    QDialog,
    QApplication,
    QAbstractSpinBox,
    QAbstractSlider,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QAbstractItemView,
)

from workers import ExportWorker
from export_dialog import ExportOptionsDialog
from workers import PreviewWorker
from workers import PreviewCache
from presets import PresetManager
from presets import create_settings
from widgets import ImageCanvas, ViewTransform
from style_randomizer import DEFAULT_PARAMETERS, STYLE_FAMILIES, generate_style
from widgets import ResettableSlider, LoadingBorder


class ImageStylizerWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Image Stylizer")
        self.resize(1450, 900)

        self.settings = create_settings()
        self.preset_manager = PresetManager()

        self.input_paths = []
        self.output_dir = self.settings.value("output_dir", "")
        self.last_input_dir = self.settings.value("last_input_dir", str(Path.home()))
        self.current_index = 0
        self.original_image = None
        self.processed_image = None
        self.export_worker = None
        self.export_result = None
        self.preview_worker = None
        self.preview_cache = PreviewCache(max_items=20, max_megabytes=192)
        # Un seul worker de preview vivant à la fois.
        # On garde une référence Python jusqu'au signal finished de Qt.
        self.request_counter = 0
        self.active_preview_request = None
        self.active_cache_key = None
        self.desired_cache_key = None
        self.failed_cache_key = None
        self._close_after_preview = False
        self.applying_preset = False
        self.view_state = ViewTransform(self)
        self.original_pixmap = None
        self.result_pixmap = None
        self._preview_state = "empty"

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(250)
        self.preview_timer.timeout.connect(self.start_preview_processing)

        self.setup_ui()
        self.restore_paths()
        self.refresh_presets()
        self.restore_last_selected_preset()
        if self.preset_manager.load_error:
            QMessageBox.warning(self, "Presets illisibles", self.preset_manager.load_error)
        self.set_preview_state("empty")
        self.refresh_action_availability()
        # Recevoir les touches AVANT les widgets ayant le focus :
        # keyPressEvent() seul ne reçoit pas les flèches consommées par un bouton.
        QApplication.instance().installEventFilter(self)
        self._install_image_drop_targets()

    def setup_ui(self):
        # Un viewport avec défilement laisse la fenêtre se réduire même si les
        # trois panneaux supérieurs et les aperçus nécessitent plus de place.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumSize(0, 0)
        central_widget = QWidget()
        central_widget.setMinimumSize(0, 0)
        scroll.setWidget(central_widget)
        self.setCentralWidget(scroll)
        self.setMinimumSize(620, 340)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Ligne superieure : trois blocs distincts, chacun de la largeur
        # de la colonne des parametres. Aucun ne s'etire sur l'ecran entier.
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        top_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        main_layout.addLayout(top_layout)

        # 1) Commandes fichiers : selection manuelle des images conservee.
        left_top_panel = QWidget()
        left_top_panel.setFixedWidth(360)
        left_top_layout = QVBoxLayout(left_top_panel)
        left_top_layout.setContentsMargins(0, 0, 0, 0)
        left_top_layout.setSpacing(8)

        self.import_button = QPushButton("Importer des images")
        self.output_button = QPushButton("Choisir le dossier de sortie")
        self.export_button = QPushButton("Exporter")
        for button in (self.import_button, self.output_button, self.export_button):
            button.setMinimumHeight(38)
            left_top_layout.addWidget(button)

        self.input_dir_label = QLabel("Dossier d'entrée : -")
        self.output_dir_label = QLabel("Dossier de sortie : -")
        for label in (self.input_dir_label, self.output_dir_label):
            label.setWordWrap(True)
            label.setStyleSheet(
                "padding: 6px; background-color: #232323; "
                "border: 1px solid #444; border-radius: 6px;"
            )
            left_top_layout.addWidget(label)

        top_layout.addWidget(left_top_panel)

        # 2) Presets : meme largeur que la colonne de gauche.
        presets_group = QGroupBox("Presets")
        presets_group.setFixedWidth(360)
        presets_layout = QVBoxLayout(presets_group)
        presets_layout.setContentsMargins(10, 12, 10, 10)
        presets_layout.setSpacing(8)

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumHeight(34)
        presets_layout.addWidget(self.preset_combo)

        preset_buttons = QHBoxLayout()
        self.preset_save_button = QPushButton("Sauvegarder")
        self.preset_delete_button = QPushButton("Supprimer")
        for button in (self.preset_save_button, self.preset_delete_button):
            button.setMinimumHeight(34)
            preset_buttons.addWidget(button)
        presets_layout.addLayout(preset_buttons)
        top_layout.addWidget(presets_group)

        # 3) Explorer des styles : meme largeur, zone independante.
        exploration_group = QGroupBox("Explorer des styles")
        exploration_group.setFixedWidth(360)
        exploration_layout = QVBoxLayout(exploration_group)
        exploration_layout.setContentsMargins(10, 12, 10, 10)
        exploration_layout.setSpacing(8)

        self.style_family_combo = QComboBox()
        self.style_family_combo.setMinimumHeight(34)
        self.style_family_combo.addItem("Surprise (toutes les ambiances)", None)
        for family in STYLE_FAMILIES:
            self.style_family_combo.addItem(family, family)
        self.style_family_combo.setToolTip(
            "Surprise choisit une famille au hasard. "
            "Selectionne une famille pour explorer ses variations."
        )
        exploration_layout.addWidget(self.style_family_combo)

        exploration_buttons = QHBoxLayout()
        self.randomize_button = QPushButton("Générer un style")
        self.reset_button = QPushButton("Réinitialiser")
        for button in (self.randomize_button, self.reset_button):
            button.setMinimumHeight(34)
            exploration_buttons.addWidget(button)
        exploration_layout.addLayout(exploration_buttons)

        self.style_info_label = QLabel("Prêt à explorer")
        self.style_info_label.setWordWrap(True)
        self.style_info_label.setStyleSheet("color: #b7b7b7;")
        exploration_layout.addWidget(self.style_info_label)
        top_layout.addWidget(exploration_group)
        top_layout.addStretch()

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)
        main_layout.addLayout(content_layout, 1)

        settings_panel = QWidget()
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(0, 0, 8, 0)
        settings_layout.setSpacing(6)

        parameters_title = QLabel("Paramètres")
        parameters_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        settings_layout.addWidget(parameters_title)

        self.controls = {}
        self.scales = {}
        self.effect_groups = {}

        # Cinq effets, sept réglages. Le bloom et l'étalonnage possèdent
        # chacun deux réglages mais un seul interrupteur par effet.
        self.add_effect_group(settings_layout, "Flou", "blur_enabled", [
            ("Intensité", "blur_kernel", 1, 101, 11, 1),
        ])
        self.add_effect_group(settings_layout, "Bloom", "bloom_enabled", [
            ("Seuil", "bloom_threshold", 0, 255, 100, 1),
            ("Intensité", "bloom_intensity", 0, 200, 20, 100),
        ])
        self.add_effect_group(settings_layout, "Postérisation", "posterize_enabled", [
            ("Niveaux", "poster_levels", 2, 20, 5, 1),
        ])
        noise_layout = self.add_effect_group(settings_layout, "Bruit", "noise_enabled", [
            ("Quantité", "noise_amount", 0, 50, 0, 1),
        ])
        self.add_noise_seed_row(noise_layout)
        self.add_effect_group(settings_layout, "Couleurs", "grade_enabled", [
            ("Bleu", "blue_strength", 50, 200, 140, 100),
            ("Jaune", "yellow_strength", 50, 200, 110, 100),
        ])

        self.add_effect_group(settings_layout, "Contraste", "contrast_enabled", [
            ("Facteur", "contrast_factor", 50, 180, 100, 100),
        ], checked=False)
        self.add_effect_group(settings_layout, "Vignettage", "vignette_enabled", [
            ("Intensité", "vignette_amount", 0, 100, 30, 1),
        ], checked=False)

        settings_layout.addStretch()
        settings_scroll = QScrollArea()
        settings_scroll.setFixedWidth(360)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_scroll.setWidget(settings_panel)
        content_layout.addWidget(settings_scroll)

        preview_column = QWidget()
        preview_column_layout = QVBoxLayout(preview_column)
        preview_column_layout.setContentsMargins(0, 0, 0, 0)
        preview_column_layout.setSpacing(10)

        # Le nom ne fait pas partie des chemins : centre au-dessus des images.
        self.image_name_label = QLabel("Aucune image sélectionnée")
        self.image_name_label.setAlignment(Qt.AlignCenter)
        self.image_name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.image_name_label.setWordWrap(True)

        self.image_counter = QLabel("0 / 0")
        self.image_counter.setAlignment(Qt.AlignCenter)
        self.image_counter.setStyleSheet("color: #bbbbbb;")

        preview_column_layout.addWidget(self.image_name_label)
        preview_column_layout.addWidget(self.image_counter)

        # Comparateur : cadrage partagé entre côte à côte et avant/après.
        controls_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Côte à côte", "side")
        self.mode_combo.addItem("Avant / après", "wipe")
        self.mode_combo.setMinimumWidth(150)
        controls_row.addWidget(QLabel("Comparaison :"))
        controls_row.addWidget(self.mode_combo)
        controls_row.addStretch()

        self.zoom_out_button = QPushButton("−")
        self.zoom_in_button = QPushButton("+")
        self.zoom_reset_button = QPushButton("Adapter")
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setMinimumWidth(55)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_out_button.setToolTip("Dézoomer")
        self.zoom_in_button.setToolTip("Zoomer")
        self.zoom_reset_button.setToolTip("Réinitialiser le zoom et le cadrage")
        for button in (self.zoom_out_button, self.zoom_in_button):
            button.setFixedWidth(36)
        controls_row.addWidget(self.zoom_out_button)
        controls_row.addWidget(self.zoom_label)
        controls_row.addWidget(self.zoom_in_button)
        controls_row.addWidget(self.zoom_reset_button)
        self.preview_status_label = QLabel("")
        self.preview_status_label.setMinimumWidth(105)
        self.preview_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.preview_status_label.setStyleSheet("color: #9ca8b5;")
        controls_row.addWidget(self.preview_status_label)
        preview_column_layout.addLayout(controls_row)

        self.preview_stack = QStackedWidget()
        self.original_view = ImageCanvas(self.view_state, "original")
        self.result_view = ImageCanvas(self.view_state, "processed")
        self.wipe_view = ImageCanvas(self.view_state, "wipe")

        side_widget = QWidget()
        side_layout = QHBoxLayout(side_widget)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(12)
        for title, canvas in (("Original", self.original_view), ("Résultat", self.result_view)):
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(title)
            label.setAlignment(Qt.AlignCenter)
            column_layout.addWidget(label)
            column_layout.addWidget(canvas, 1)
            side_layout.addWidget(column, 1)
        self.preview_stack.addWidget(side_widget)
        self.preview_stack.addWidget(self.wipe_view)

        # Dessin superposé : aucun recalcul d'image, aucun clic intercepté.
        self.side_loading_border = LoadingBorder(self.result_view)
        self.wipe_loading_border = LoadingBorder(self.wipe_view)
        preview_column_layout.addWidget(self.preview_stack, 1)

        wipe_controls = QWidget()
        wipe_layout = QHBoxLayout(wipe_controls)
        wipe_layout.setContentsMargins(0, 0, 0, 0)
        self.wipe_slider = QSlider(Qt.Horizontal)
        self.wipe_slider.setRange(0, 100)
        self.wipe_slider.setValue(50)
        wipe_layout.addWidget(QLabel("Original"))
        wipe_layout.addWidget(self.wipe_slider, 1)
        wipe_layout.addWidget(QLabel("Résultat"))
        preview_column_layout.addWidget(wipe_controls)
        self.wipe_controls = wipe_controls

        self.mode_combo.currentIndexChanged.connect(self.change_compare_mode)
        self.zoom_out_button.clicked.connect(lambda: self.zoom_by(1 / 1.25))
        self.zoom_in_button.clicked.connect(lambda: self.zoom_by(1.25))
        self.zoom_reset_button.clicked.connect(self.view_state.reset)
        self.view_state.changed.connect(self.update_zoom_label)
        self.wipe_slider.valueChanged.connect(self.wipe_view.set_wipe)
        self.wipe_view.wipe_changed.connect(self.wipe_slider.setValue)

        saved_mode = self.settings.value("compare_mode", "side")
        index = self.mode_combo.findData(saved_mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self.change_compare_mode()

        navigation_layout = QHBoxLayout()
        self.previous_button = QPushButton("← Précédente")
        self.next_button = QPushButton("Suivante →")
        self.previous_button.setMinimumHeight(34)
        self.next_button.setMinimumHeight(34)
        navigation_layout.addStretch()
        navigation_layout.addWidget(self.previous_button)
        navigation_layout.addWidget(self.next_button)
        navigation_layout.addStretch()

        preview_column_layout.addLayout(navigation_layout)
        content_layout.addWidget(preview_column, 1)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        progress_row.addWidget(self.progress_bar, 1)

        self.cancel_export_button = QPushButton("Annuler l'export")
        self.cancel_export_button.setMinimumHeight(32)
        self.cancel_export_button.setVisible(False)
        self.cancel_export_button.clicked.connect(self.cancel_export)
        progress_row.addWidget(self.cancel_export_button)
        main_layout.addLayout(progress_row)

        self.import_button.clicked.connect(self.import_images)
        self.output_button.clicked.connect(self.select_output_dir)
        self.export_button.clicked.connect(self.start_export)
        self.previous_button.clicked.connect(self.previous_image)
        self.next_button.clicked.connect(self.next_image)
        self.preset_combo.currentIndexChanged.connect(self.apply_selected_preset)
        self.preset_save_button.clicked.connect(self.save_preset)
        self.preset_delete_button.clicked.connect(self.delete_selected_preset)
        self.randomize_button.clicked.connect(self.randomize_parameters)
        self.reset_button.clicked.connect(self.reset_parameters)

    def set_preview_state(self, state):
        """État visible de l'aperçu, indépendamment de l'exportation."""
        self._preview_state = state
        labels = {
            "empty": "",
            "loading": "Calcul en cours…",
            "ready": "Aperçu à jour",
            "cached": "Depuis le cache",
            "error": "Aperçu indisponible",
        }
        self.preview_status_label.setText(labels.get(state, ""))
        self.refresh_loading_border()

    def refresh_loading_border(self):
        loading = self._preview_state == "loading"
        wipe = self.mode_combo.currentData() == "wipe"
        self.side_loading_border.set_active(loading and not wipe)
        self.wipe_loading_border.set_active(loading and wipe)

    def refresh_action_availability(self):
        has_images = bool(self.input_paths)
        valid_preview = self.original_image is not None
        exporting = self.export_worker is not None
        self.previous_button.setEnabled(has_images and self.current_index > 0)
        self.next_button.setEnabled(
            has_images and self.current_index < len(self.input_paths) - 1
        )
        self.export_button.setEnabled(has_images and bool(self.output_dir) and not exporting)
        self.preset_delete_button.setEnabled(bool(self.preset_combo.currentData()))
        for control in (self.zoom_out_button, self.zoom_in_button, self.zoom_reset_button):
            control.setEnabled(valid_preview)

    def eventFilter(self, watched, event):
        # Le filtre global installé plus haut permet de recevoir aussi
        # les dépôts sur les zones d'aperçu et le panneau de réglages.
        if (
            event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop)
            and isinstance(watched, QWidget)
            and watched.window() is self
            and event.mimeData().hasUrls()
        ):
            if self.export_worker is not None:
                event.ignore()
                return True
            local_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if not local_paths:
                event.ignore()
                return True
            if event.type() == QEvent.Type.Drop:
                self._handle_dropped_images(local_paths)
            event.acceptProposedAction()
            return True

        # Les flèches parcourent les images sauf quand un contrôle éditable
        # les utilise. Échap réinitialise tous les paramètres comme le
        # bouton « Réinitialiser » d'Explorer les styles.
        # On préserve Échap dans les fenêtres modales et les menus ouverts.
        if event.type() != QEvent.KeyPress:
            return super().eventFilter(watched, event)

        if event.key() not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Escape):
            return super().eventFilter(watched, event)

        if event.modifiers() != Qt.NoModifier:
            return super().eventFilter(watched, event)

        if (
            QApplication.activeWindow() is not self
            or QApplication.activeModalWidget() is not None
            or QApplication.activePopupWidget() is not None
            or not isinstance(watched, QWidget)
            or watched.window() is not self
        ):
            return super().eventFilter(watched, event)

        if event.key() == Qt.Key_Escape:
            self.reset_parameters()
            event.accept()
            return True

        editing_widgets = (
            QAbstractSpinBox, QAbstractSlider, QComboBox,
            QLineEdit, QTextEdit, QPlainTextEdit, QAbstractItemView,
        )
        focused = QApplication.focusWidget()
        if isinstance(focused, editing_widgets):
            return super().eventFilter(watched, event)

        if not self.input_paths:
            return super().eventFilter(watched, event)

        if event.key() == Qt.Key_Left and self.previous_button.isEnabled():
            self.previous_image()
        elif event.key() == Qt.Key_Right and self.next_button.isEnabled():
            self.next_image()
        # Aux extrémités du lot, la flèche est tout de même consommée
        # pour ne pas déplacer le focus vers un contrôle inattendu.
        event.accept()
        return True

    def add_effect_group(self, layout, title, enabled_key, parameters, checked=True):
        group = QGroupBox(title)
        group.setCheckable(True)
        group.setChecked(checked)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(9, 10, 9, 5)
        group_layout.setSpacing(4)
        self.effect_groups[enabled_key] = group

        for label, key, minimum, maximum, default, scale in parameters:
            self.add_parameter_row(
                group_layout, label, key, minimum, maximum, default, scale
            )

        group.toggled.connect(lambda _checked: self.on_parameter_changed())
        layout.addWidget(group)
        return group_layout

    def add_parameter_row(self, layout, label, key, minimum, maximum, default, scale=1):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        row_label = QLabel(label)
        row_label.setFixedWidth(65)
        row.addWidget(row_label)

        slider = ResettableSlider(Qt.Horizontal, default)
        slider.setRange(minimum, maximum)
        slider.setValue(default)
        slider.setToolTip(
            f"Double-clique pour réinitialiser ce réglage (défaut : {default / scale:g})."
        )
        row.addWidget(slider, 1)

        if scale == 1:
            value_box = QSpinBox()
        else:
            value_box = QDoubleSpinBox()
            value_box.setDecimals(2)
            value_box.setSingleStep(1 / scale)

        value_box.setRange(minimum / scale, maximum / scale)
        value_box.setValue(default / scale)
        value_box.setFixedWidth(85)
        value_box.setMinimumHeight(28)
        row.addWidget(value_box)

        slider.valueChanged.connect(
            lambda value, box=value_box, s=scale: box.setValue(value / s)
        )
        value_box.valueChanged.connect(
            lambda value, sld=slider, s=scale: sld.setValue(round(value * s))
        )
        value_box.valueChanged.connect(lambda _=None: self.on_parameter_changed())

        layout.addLayout(row)
        self.controls[key] = value_box
        self.scales[key] = scale

    def add_noise_seed_row(self, layout):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel("Seed")
        label.setFixedWidth(65)
        row.addWidget(label)

        self.noise_seed_control = QSpinBox()
        self.noise_seed_control.setRange(0, 2_147_483_647)
        self.noise_seed_control.setValue(DEFAULT_PARAMETERS["noise_seed"])
        self.noise_seed_control.setMinimumHeight(28)
        self.noise_seed_control.setToolTip(
            "Même image + mêmes paramètres + même seed = même motif de bruit."
        )
        self.noise_seed_control.valueChanged.connect(
            lambda _=None: self.on_parameter_changed()
        )
        row.addWidget(self.noise_seed_control, 1)

        self.new_seed_button = QPushButton("Nouvelle")
        self.new_seed_button.setToolTip("Choisir un nouveau motif de bruit")
        self.new_seed_button.setMinimumHeight(28)
        self.new_seed_button.clicked.connect(
            lambda: self.noise_seed_control.setValue(
                secrets.randbelow(2_147_483_648)
            )
        )
        row.addWidget(self.new_seed_button)

        layout.addLayout(row)

    def restore_paths(self):
        if self.output_dir:
            self.update_output_dir_label(self.output_dir)
        else:
            self.update_output_dir_label("")

        if self.last_input_dir:
            self.update_input_dir_label(self.last_input_dir)
        else:
            self.update_input_dir_label("")

    def update_input_dir_label(self, path):
        display = path if path else "-"
        self.input_dir_label.setText(f"Dossier d'entrée : {display}")
        self.input_dir_label.setToolTip(display)

    def update_output_dir_label(self, path):
        display = path if path else "-"
        self.output_dir_label.setText(f"Dossier de sortie : {display}")
        self.output_dir_label.setToolTip(display)

    def refresh_presets(self):
        current = self.preset_combo.currentData()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Personnalisé", None)
        for name in self.preset_manager.get_names():
            self.preset_combo.addItem(name, name)
        if current:
            index = self.preset_combo.findData(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)
        self.refresh_action_availability()

    def restore_last_selected_preset(self):
        """Recharge un preset existant, sinon conserve Personnalisé."""
        name = self.settings.value("ui/last_selected_preset", "") or ""
        if not isinstance(name, str) or not name:
            return
        index = self.preset_combo.findData(name)
        if index > 0:
            # currentIndexChanged applique le preset via le signal existant.
            self.preset_combo.setCurrentIndex(index)

    def on_parameter_changed(self):
        if self.applying_preset:
            return
        # Modifier manuellement un effet ne modifie jamais le preset sauvegardé.
        if self.preset_combo.currentIndex() != 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(0)
            self.preset_combo.blockSignals(False)
        self.refresh_action_availability()
        self.update_preview()

    def get_parameters(self):
        values = {}
        for key, control in self.controls.items():
            value = control.value()
            scale = self.scales.get(key, 1)
            if scale == 1:
                values[key] = int(value)
            else:
                values[key] = float(value)

        values["noise_seed"] = int(self.noise_seed_control.value())
        for key, group in self.effect_groups.items():
            values[key] = bool(group.isChecked())
        return values

    def set_parameters(self, parameters):
        # Compatibilité avec les presets des versions précédentes :
        # les clés absentes récupèrent les valeurs par défaut de la V6.
        values = dict(DEFAULT_PARAMETERS)
        values.update(parameters)

        self.applying_preset = True
        try:
            for key, control in self.controls.items():
                control.setValue(values[key])
            self.noise_seed_control.setValue(int(values["noise_seed"]))
            for key, group in self.effect_groups.items():
                group.setChecked(bool(values[key]))
        finally:
            self.applying_preset = False
        # Un seul recalcul, lorsque tous les contrôles ont été mis à jour.
        self.update_preview()

    def switch_to_custom_preset(self):
        """Détache les sliders du preset, sans déclencher le chargement."""
        if self.preset_combo.currentIndex() != 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(0)
            self.preset_combo.blockSignals(False)
        self.refresh_action_availability()

    def randomize_parameters(self):
        family_filter = self.style_family_combo.currentData()
        family, parameters = generate_style(family=family_filter)
        self.switch_to_custom_preset()
        self.set_parameters(parameters)
        self.style_info_label.setText(f"Inspiration : {family}")
        self.statusBar().showMessage(f"Nouveau style proposé : {family}")

    def reset_parameters(self):
        self.switch_to_custom_preset()
        self.set_parameters(DEFAULT_PARAMETERS)
        self.style_info_label.setText("Paramètres par défaut")
        self.statusBar().showMessage("Paramètres réinitialisés")

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Sauvegarder un preset", "Nom du preset :")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            self.preset_manager.set(name, self.get_parameters())
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Sauvegarde impossible", str(exc))
            return
        self.refresh_presets()
        index = self.preset_combo.findData(name)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self.statusBar().showMessage(f"Preset sauvegardé : {name}")

    def apply_selected_preset(self, index=None):
        # La sélection dans le menu applique immédiatement le preset.
        self.refresh_action_availability()
        name = self.preset_combo.currentData()
        if not name:
            return
        preset = self.preset_manager.get(name)
        if not preset:
            QMessageBox.warning(self, "Presets", "Preset introuvable.")
            return
        self.set_parameters(preset)
        self.style_info_label.setText(f"Preset : {name}")
        self.statusBar().showMessage(f"Preset chargé : {name}")

    def delete_selected_preset(self):
        name = self.preset_combo.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Supprimer le preset",
            f"Supprimer le preset '{name}' ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            try:
                self.preset_manager.delete(name)
            except (OSError, ValueError, TypeError) as exc:
                QMessageBox.warning(self, "Suppression impossible", str(exc))
                return
            self.refresh_presets()
            self.statusBar().showMessage(f"Preset supprimé : {name}")

    def import_images(self):
        start_dir = self.last_input_dir if self.last_input_dir else str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner des images",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )

        if paths:
            self._set_input_images(paths)

    def _install_image_drop_targets(self):
        """Autorise le drop dans la fenêtre, notamment les aperçus Qt imbriqués."""
        scroll = self.centralWidget()
        content = scroll.widget()
        for widget in (
            self, scroll, scroll.viewport(), content,
            self.preview_stack, self.original_view, self.result_view,
            self.wipe_view, self.input_dir_label,
        ):
            widget.setAcceptDrops(True)
        self.import_button.setToolTip(
            "Choisir des images ou glisser ici des images / un dossier"
        )

    def _handle_dropped_images(self, paths):
        """Le dépôt remplace la sélection, comme le bouton Importer des images."""
        extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        images = []
        seen = set()
        dropped_folders = []
        for raw in paths:
            path = Path(raw)
            try:
                if path.is_dir():
                    dropped_folders.append(path)
                    candidates = path.rglob("*")
                elif path.is_file():
                    candidates = (path,)
                else:
                    continue
                for candidate in candidates:
                    if not candidate.is_file() or candidate.suffix.lower() not in extensions:
                        continue
                    canonical = str(candidate.resolve())
                    key = os.path.normcase(canonical)
                    if key not in seen:
                        seen.add(key)
                        images.append(canonical)
            except OSError:
                continue

        if not images:
            self.statusBar().showMessage("Aucune image compatible dans le dépôt.", 6000)
            return

        images.sort(key=str.casefold)
        # Un dossier déposé devient le chemin d'entrée affiché ; sinon
        # il s'agit du dossier parent de la première image.
        source_dir = str(dropped_folders[0]) if dropped_folders else str(Path(images[0]).parent)
        self._set_input_images(images, source_dir=source_dir)
        self.statusBar().showMessage(f"Glisser-déposer : {len(images)} image(s) importée(s).", 6000)

    def _set_input_images(self, paths, source_dir=None):
        """Chargement commun au bouton Importer et au glisser-déposer."""
        if not paths or self.export_worker is not None:
            return
        self.input_paths = list(paths)
        self.current_index = 0
        self.preview_cache.clear()
        self.desired_cache_key = None
        if self.preview_worker is not None:
            self.preview_worker.requestInterruption()
        self.last_input_dir = source_dir or str(Path(paths[0]).parent)
        self.settings.setValue("last_input_dir", self.last_input_dir)
        self.load_current_image()
        self.update_input_dir_label(self.last_input_dir)
        self.refresh_action_availability()
        self.statusBar().showMessage(f"{len(paths)} image(s) sélectionnée(s)")

    def select_output_dir(self):
        start_dir = self.output_dir if self.output_dir else str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier de sortie", start_dir)

        if directory:
            self.output_dir = directory
            self.settings.setValue("output_dir", self.output_dir)
            self.update_output_dir_label(directory)
            self.refresh_action_availability()
            self.statusBar().showMessage(f"Dossier de sortie : {directory}")

    def active_canvas(self):
        return self.wipe_view if self.mode_combo.currentData() == "wipe" else self.original_view

    def change_compare_mode(self, index=None):
        wipe = self.mode_combo.currentData() == "wipe"
        self.preview_stack.setCurrentIndex(1 if wipe else 0)
        self.wipe_controls.setVisible(wipe)
        self.settings.setValue("compare_mode", "wipe" if wipe else "side")
        self.view_state.clamp_to(self.active_canvas())
        self.refresh_loading_border()

    def zoom_by(self, factor):
        canvas = self.active_canvas()
        self.view_state.set_zoom(self.view_state.zoom * factor, canvas)

    def update_zoom_label(self):
        self.zoom_label.setText(f"{round(self.view_state.zoom * 100)} %")

    def set_viewer_images(self):
        for canvas in (self.original_view, self.result_view, self.wipe_view):
            canvas.set_images(self.original_pixmap, self.result_pixmap)

    def set_result_pixmap(self, pixmap):
        self.result_pixmap = pixmap
        self.result_view.set_images(self.original_pixmap, self.result_pixmap)
        self.wipe_view.set_images(self.original_pixmap, self.result_pixmap)

    def load_current_image(self):
        if not self.input_paths:
            self.set_preview_state("empty")
            self.refresh_action_availability()
            return

        path = self.input_paths[self.current_index]
        try:
            with Image.open(path) as img:
                # JPEG peut être décodé directement en résolution réduite
                # (1/2, 1/4, 1/8) pour accélérer la navigation sur gros fichiers.
                # Le calcul de l'aperçu et l'export restent pleine résolution.
                img.draft("RGB", (2048, 2048))
                original = img.convert("RGB")
            # Preview de l'original à résolution suffisante pour zoomer,
            # sans garder un QPixmap pleine résolution en mémoire.
            original.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            self.original_image = original
            self.original_pixmap = QPixmap.fromImage(ImageQt(original))
        except Exception as exc:
            self.original_image = None
            self.original_pixmap = None
            self.result_pixmap = None
            self.desired_cache_key = None
            if self.preview_worker is not None:
                self.preview_worker.requestInterruption()
            self.image_name_label.setText(Path(path).name)
            self.image_counter.setText(f"Image {self.current_index + 1} / {len(self.input_paths)}")
            self.update_input_dir_label(str(Path(path).parent))
            self.set_viewer_images()
            self.set_preview_state("error")
            self.refresh_action_availability()
            QMessageBox.warning(self, "Importation", f"Impossible d'ouvrir l'image :\n{path}\n\n{exc}")
            return

        self.image_name_label.setText(Path(path).name)
        self.image_counter.setText(f"Image {self.current_index + 1} / {len(self.input_paths)}")
        self.update_input_dir_label(str(Path(path).parent))

        # Un nouvel original ne doit jamais être juxtaposé à l'ancien résultat.
        self.result_pixmap = None
        self.view_state.reset()
        self.set_viewer_images()
        self.refresh_action_availability()
        self.update_preview()

    def get_preview_size(self):
        # Taille FIXE : le zoom, le mode de comparaison et le redimensionnement
        # ne provoquent plus aucun nouveau calcul et ne cassent pas le cache.
        return (2048, 2048)

    def update_preview(self):
        if self.original_image is None or not self.input_paths:
            self.set_preview_state("empty")
            return

        # Annule le délai précédent si l'utilisateur continue à manipuler.
        self.preview_timer.stop()
        path = self.input_paths[self.current_index]
        key = self.preview_cache.make_key(
            path, self.get_parameters(), self.get_preview_size()
        )
        self.desired_cache_key = key
        self.failed_cache_key = None

        cached_pixmap = self.preview_cache.get(key)
        if cached_pixmap is not None:
            # Si un calcul plus ancien termine après ce cache-hit, son résultat
            # ne remplacera jamais le rendu actuellement demandé.
            if self.preview_worker is not None and self.active_cache_key != key:
                self.preview_worker.requestInterruption()
            self.set_result_pixmap(cached_pixmap)
            self.set_preview_state("cached")
            self.statusBar().showMessage("Aperçu chargé depuis le cache")
            return

        if self.preview_worker is not None and self.active_cache_key != key:
            self.preview_worker.requestInterruption()
        self.set_preview_state("loading")
        self.preview_timer.start()

    def start_preview_processing(self):
        if self.original_image is None or not self.input_paths:
            return

        key = self.desired_cache_key
        if key is None:
            return

        # Les deux opérations successives suivantes ne démarrent jamais
        # deux threads en parallèle. Le plus récent attend la fin de l'ancien.
        if self.preview_worker is not None:
            return

        cached_pixmap = self.preview_cache.get(key)
        if cached_pixmap is not None:
            self.set_result_pixmap(cached_pixmap)
            self.set_preview_state("cached")
            self.statusBar().showMessage("Aperçu chargé depuis le cache")
            return

        self.request_counter += 1
        request_id = self.request_counter
        self.active_preview_request = request_id
        self.active_cache_key = key

        self.preview_worker = PreviewWorker(
            request_id,
            self.input_paths[self.current_index],
            self.get_parameters(),
            self.get_preview_size(),
        )
        self.preview_worker.result_ready.connect(self.on_preview_ready)
        self.preview_worker.error.connect(self.on_preview_error)
        self.preview_worker.finished.connect(self.on_preview_finished)
        self.preview_worker.start()
        self.statusBar().showMessage("Calcul de l’aperçu...")

    def on_preview_ready(self, request_id, image):
        if self._close_after_preview:
            return
        if request_id != self.active_preview_request or image is None:
            return

        key = self.active_cache_key
        if key is None:
            return

        self.processed_image = image
        # L'image a déjà été réduite par le worker. Le QPixmap est créé
        # uniquement dans le thread de l'interface.
        qimage = ImageQt(image)
        pixmap = QPixmap.fromImage(qimage)
        self.preview_cache.set(key, pixmap)

        # Une réponse tardive ne doit pas remplacer la nouvelle photo ou
        # un autre réglage (notamment après un changement de preset).
        if key == self.desired_cache_key:
            self.set_result_pixmap(pixmap)
            self.set_preview_state("ready")
            self.statusBar().showMessage("Aperçu mis à jour")

    def on_preview_error(self, request_id, message):
        if self._close_after_preview:
            return
        if request_id != self.active_preview_request:
            return
        if self.active_cache_key == self.desired_cache_key:
            self.failed_cache_key = self.active_cache_key
            self.set_preview_state("error")
            QMessageBox.warning(
                self, "Prévisualisation", f"Impossible de calculer l’aperçu.\n\n{message}"
            )

    def on_preview_finished(self):
        # Le signal finished est le SEUL endroit où la référence au worker
        # est libérée. Ainsi, plus de RuntimeError « object already deleted ».
        worker = self.preview_worker
        self.preview_worker = None
        self.active_preview_request = None
        self.active_cache_key = None
        if worker is not None:
            worker.deleteLater()

        if self._close_after_preview:
            # Différer la fermeture : Qt a terminé le thread et peut libérer
            # ses ressources. L'interface reste réactive pendant le calcul.
            QTimer.singleShot(0, self.close)
            return

        key = self.desired_cache_key
        if key is not None and key != self.failed_cache_key and self.preview_cache.get(key) is None:
            if not self.preview_timer.isActive():
                self.preview_timer.start(0)

    def previous_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()
            self.refresh_action_availability()

    def next_image(self):
        if self.current_index < len(self.input_paths) - 1:
            self.current_index += 1
            self.load_current_image()
            self.refresh_action_availability()

    def start_export(self):
        # Une seconde exportation ne doit pas démarrer avant la fin du worker.
        if self.export_worker is not None:
            return

        if not self.input_paths:
            QMessageBox.warning(self, "Exportation", "Aucune image n'a été importée.")
            return

        if not self.output_dir:
            QMessageBox.warning(self, "Exportation", "Sélectionne d'abord un dossier de sortie.")
            return

        dialog = ExportOptionsDialog(len(self.input_paths), self.settings, self)
        if dialog.exec() != QDialog.Accepted:
            return

        options = dialog.selected_options()
        if options["scope"] == "current":
            selected_paths = [self.input_paths[self.current_index]]
        else:
            selected_paths = list(self.input_paths)

        self.export_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.output_button.setEnabled(False)
        self.export_result = None

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_export_button.setEnabled(True)
        self.cancel_export_button.setVisible(True)

        self.export_worker = ExportWorker(
            selected_paths,
            self.output_dir,
            self.get_parameters(),
            image_format=options["image_format"],
            quality=options["quality"],
            preset_name=self.preset_combo.currentData(),
        )
        self.export_worker.progress.connect(self.update_export_progress)
        self.export_worker.completed.connect(self.export_finished)
        self.export_worker.finished.connect(self.on_export_thread_finished)
        self.export_worker.start()
        self.refresh_action_availability()
        self.statusBar().showMessage(f"Exportation de {len(selected_paths)} image(s) en cours...")

    def cancel_export(self):
        if self.export_worker is None:
            return
        self.export_worker.cancel()
        self.cancel_export_button.setEnabled(False)
        self.statusBar().showMessage(
            "Annulation demandée : l'image en cours sera terminée avant l'arrêt."
        )

    def update_export_progress(self, current, total):
        percentage = round(current / total * 100) if total else 0
        self.progress_bar.setValue(percentage)
        if self.cancel_export_button.isEnabled():
            self.statusBar().showMessage(
                f"Exportation : {current}/{total} image(s) traitée(s)"
            )

    def export_finished(self, exported, errors, cancelled):
        # Le signal est émis à la fin du travail, mais Qt peut ne pas avoir
        # encore émis `finished`. La réactivation et le nettoyage se font là.
        self.export_result = (exported, errors, cancelled)

    def on_export_thread_finished(self):
        worker = self.export_worker
        summary = self.export_result
        if summary is None and worker is not None:
            summary = getattr(worker, "summary", None)
        self.export_worker = None
        if worker is not None:
            worker.deleteLater()

        self.export_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.output_button.setEnabled(True)
        self.refresh_action_availability()
        self.cancel_export_button.setVisible(False)
        self.progress_bar.setVisible(False)

        if summary is None:
            QMessageBox.warning(
                self, "Exportation", "L'export s'est terminé sans résultat."
            )
            return

        exported, errors, cancelled = summary
        self.export_result = None
        if cancelled:
            title = "Exportation annulée"
            message = f"Annulation effectuée. {exported} image(s) enregistrée(s)."
        else:
            title = "Exportation terminée"
            message = f"{exported} image(s) exportée(s)."

        if errors:
            message += (
                f"\n\n{len(errors)} erreur(s) :\n"
                + "\n".join(errors[:10])
            )
            QMessageBox.warning(self, title, message)
        else:
            QMessageBox.information(self, title, message)

        self.statusBar().showMessage(message.split("\n")[0])

    def closeEvent(self, event):
        # Ne pas détruire le QThread d'export pendant son exécution.
        if self.export_worker is not None and self.export_worker.isRunning():
            QMessageBox.information(
                self, "Exportation en cours",
                "Attends la fin de l'exportation avant de fermer l'application.",
            )
            event.ignore()
            return

        self.preview_timer.stop()
        self.desired_cache_key = None
        self.set_preview_state("empty")
        if self.preview_worker is not None:
            # Ne jamais bloquer la boucle GUI avec QThread.wait() : sur une
            # photo 4K, la fenêtre paraîtrait figée jusqu'à la fin du calcul.
            self._close_after_preview = True
            self.preview_worker.requestInterruption()
            self.statusBar().showMessage("Fermeture dès la fin du calcul en cours...")
            event.ignore()
            return
        # Ne sauvegarder qu'à la fermeture réellement autorisée.
        self.settings.setValue("ui/last_selected_preset", self.preset_combo.currentData() or "")
        self.settings.sync()
        super().closeEvent(event)

