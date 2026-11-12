"""Modules regroupés par responsabilité, sans changement de logique."""

# --- Ancien module : preview_worker.py ---
from PySide6.QtCore import QThread, Signal
from PIL import Image

from processor import process_image


class PreviewWorker(QThread):
    result_ready = Signal(int, object)
    error = Signal(int, str)

    def __init__(self, request_id, image_path, parameters, preview_size):
        super().__init__()
        self.request_id = request_id
        self.image_path = image_path
        self.parameters = parameters.copy()
        self.preview_size = tuple(max(1, int(x)) for x in preview_size)

    def run(self):
        try:
            with Image.open(self.image_path) as img:
                image = img.convert("RGB")
            if self.isInterruptionRequested():
                return

            # Tous les effets à la résolution source pour garder un rendu
            # fidèle à l'export. La réduction n'intervient qu'après.
            result = process_image(image, self.parameters)
            if self.isInterruptionRequested():
                return

            result.thumbnail(self.preview_size, Image.Resampling.LANCZOS)
            if self.isInterruptionRequested():
                return
            self.result_ready.emit(self.request_id, result)
        except Exception as exc:
            self.error.emit(self.request_id, str(exc))


# --- Ancien module : export_worker.py ---
"""Export en arrière-plan, annulable entre deux images.

Ne manipule aucun widget Qt. Les paramètres et chemins sont capturés
au démarrage : les réglages de l'interface peuvent ensuite changer.
"""

from threading import Event

from PySide6.QtCore import QThread, Signal

from processor import export_image


class ExportWorker(QThread):
    progress = Signal(int, int)
    completed = Signal(int, list, bool)

    def __init__(self, input_paths, output_dir, parameters, image_format="PNG", quality=90, preset_name=None):
        super().__init__()
        self.input_paths = list(input_paths)
        self.output_dir = str(output_dir)
        self.parameters = dict(parameters)
        self.image_format = image_format
        self.quality = quality
        self.preset_name = preset_name
        self._cancel_requested = Event()
        self.summary = None

    def cancel(self):
        """Demande une annulation propre après l'image actuellement traitée."""
        self._cancel_requested.set()

    def run(self):
        total = len(self.input_paths)
        exported = 0
        errors = []
        processed = 0

        for path in self.input_paths:
            if self._cancel_requested.is_set():
                break

            try:
                export_image(
                    path,
                    self.output_dir,
                    self.parameters,
                    image_format=self.image_format,
                    quality=self.quality,
                    preset_name=self.preset_name,
                )
                exported += 1
            except Exception as exc:
                errors.append(f"{path} : {exc}")

            processed += 1
            self.progress.emit(processed, total)

        cancelled = self._cancel_requested.is_set() and processed < total
        self.summary = (exported, errors, cancelled)
        self.completed.emit(exported, errors, cancelled)


# --- Ancien module : preview_cache.py ---
from collections import OrderedDict
from pathlib import Path


class PreviewCache:
    """Cache LRU de QPixmap avec limite en nombre ET en mémoire estimée."""

    def __init__(self, max_items=20, max_megabytes=192):
        self.max_items = max_items
        self.max_bytes = max_megabytes * 1024 * 1024
        self.total_bytes = 0
        # key -> (QPixmap, taille en octets estimée)
        self.data = OrderedDict()

    @staticmethod
    def normalize_parameters(parameters):
        return tuple(
            (key, round(value, 4) if isinstance(value, float) else value)
            for key, value in sorted(parameters.items())
        )

    def make_key(self, image_path, parameters, preview_size):
        path = Path(image_path)
        try:
            stat = path.stat()
            source_version = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            source_version = None
        return (
            str(path),
            source_version,
            self.normalize_parameters(parameters),
            tuple(preview_size),
        )

    def get(self, key):
        if key not in self.data:
            return None
        self.data.move_to_end(key)
        return self.data[key][0]

    def set(self, key, pixmap):
        # 4 octets/pixel : estimation prudente pour un QPixmap Qt.
        cost = pixmap.width() * pixmap.height() * 4
        if key in self.data:
            self.total_bytes -= self.data.pop(key)[1]
        # L'image courante est tout de même affichée mais pas mémorisée
        # si elle est plus grosse que la totalité du budget de cache.
        if cost > self.max_bytes:
            return
        self.data[key] = (pixmap, cost)
        self.total_bytes += cost
        while len(self.data) > self.max_items or self.total_bytes > self.max_bytes:
            _, (_, removed_cost) = self.data.popitem(last=False)
            self.total_bytes -= removed_cost

    def clear(self):
        self.data.clear()
        self.total_bytes = 0
