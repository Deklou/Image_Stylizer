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
