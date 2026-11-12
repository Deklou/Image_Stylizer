"""Galerie de navigation Image Stylizer.

Miniatures originales chargees progressivement, sans traiter les effets.
Aucune operation dans ce module ne supprime de fichier du disque.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)


class ImageGalleryDialog(QDialog):
    """Recherche, navigation directe et retrait multiple du lot courant."""

    remove_requested = Signal(list)

    def __init__(self, paths, active_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Galerie d'images")
        self.resize(920, 680)
        self.setMinimumSize(520, 340)
        self.selected_path = None
        self._paths = list(paths)
        self._items = {}
        self._pending = []
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setInterval(0)
        self._thumbnail_timer.timeout.connect(self._load_thumbnail)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.count_label = QLabel()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Rechercher une image par nom ou dossier...")
        self.search_edit.setClearButtonEnabled(True)
        top.addWidget(self.count_label)
        top.addWidget(self.search_edit, 1)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setWrapping(True)
        self.list_widget.setWordWrap(True)
        self.list_widget.setIconSize(QSize(144, 108))
        self.list_widget.setGridSize(QSize(176, 154))
        self.list_widget.setSpacing(4)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget, 1)

        actions = QHBoxLayout()
        self.selection_label = QLabel()
        actions.addWidget(self.selection_label)
        actions.addStretch(1)
        self.remove_button = QPushButton("Retirer la sélection")
        self.remove_button.setToolTip("Retirer ces images du lot, sans supprimer les fichiers")
        self.open_button = QPushButton("Afficher l'image")
        self.close_button = QPushButton("Fermer")
        actions.addWidget(self.remove_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.search_edit.textChanged.connect(self._filter_items)
        self.list_widget.itemSelectionChanged.connect(self._update_actions)
        self.list_widget.itemDoubleClicked.connect(self._open_item)
        self.open_button.clicked.connect(self._open_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        self.close_button.clicked.connect(self.reject)
        self.set_paths(self._paths, active_path=active_path)

    def set_paths(self, paths, active_path=None):
        """Reconstruit les items sans perdre l'ordre du lot."""
        self._thumbnail_timer.stop()
        self._paths = list(paths)
        self._items.clear()
        self._pending = []
        self.list_widget.clear()
        for index, path in enumerate(self._paths):
            item = QListWidgetItem(f"{index + 1}. {Path(path).name}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.list_widget.addItem(item)
            self._items[path] = item
            self._pending.append(path)
            if path == active_path:
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)
        self._filter_items(self.search_edit.text())
        self._update_actions()
        if self._pending:
            self._thumbnail_timer.start()

    def _load_thumbnail(self):
        """Une vignette par tour de boucle Qt : l'interface reste interactive."""
        if not self._pending:
            self._thumbnail_timer.stop()
            return
        path = self._pending.pop(0)
        item = self._items.get(path)
        if item is None:
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        original_size = reader.size()
        if original_size.isValid():
            reader.setScaledSize(original_size.scaled(QSize(144, 108), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if not image.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    def _filter_items(self, query):
        needle = query.strip().casefold()
        visible = 0
        for path, item in self._items.items():
            matches = needle in str(path).casefold()
            item.setHidden(not matches)
            visible += int(matches)
        self.count_label.setText(f"{visible} / {len(self._paths)} images")
        self._update_actions()

    def _selected_paths(self):
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
            if not item.isHidden()
        ]

    def _update_actions(self):
        count = len(self._selected_paths())
        self.selection_label.setText(f"{count} image(s) sélectionnée(s)")
        self.remove_button.setEnabled(count > 0)
        self.open_button.setEnabled(count > 0)

    def _open_selected(self):
        current = self.list_widget.currentItem()
        selected = self._selected_paths()
        if current is not None and current.data(Qt.ItemDataRole.UserRole) in selected:
            self.selected_path = current.data(Qt.ItemDataRole.UserRole)
        elif selected:
            self.selected_path = selected[0]
        else:
            return
        self.accept()

    def _open_item(self, item):
        self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _remove_selected(self):
        selected = self._selected_paths()
        if not selected:
            return
        self.remove_requested.emit(selected)
        # La fenetre parente est la source de verite pour les fichiers du lot.
        parent = self.parentWidget()
        remaining = parent.input_paths if parent is not None else [
            path for path in self._paths if path not in set(selected)
        ]
        active_path = None
        if parent is not None and remaining:
            active_path = remaining[parent.current_index]
        self.set_paths(remaining, active_path=active_path)

    def reject(self):
        self._thumbnail_timer.stop()
        super().reject()

    def accept(self):
        self._thumbnail_timer.stop()
        super().accept()
