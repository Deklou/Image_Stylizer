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
