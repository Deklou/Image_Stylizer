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

    def __init__(self, input_paths, output_dir, parameters, image_format="PNG", quality=90):
        super().__init__()
        self.input_paths = list(input_paths)
        self.output_dir = str(output_dir)
        self.parameters = dict(parameters)
        self.image_format = image_format
        self.quality = quality
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
                )
                exported += 1
            except Exception as exc:
                errors.append(f"{path} : {exc}")

            processed += 1
            self.progress.emit(processed, total)

        cancelled = self._cancel_requested.is_set() and processed < total
        self.summary = (exported, errors, cancelled)
        self.completed.emit(exported, errors, cancelled)
