"""Comparateur d'images : zoom/pan synchronisés et séparation avant/après.

Ce module ne fait aucun traitement d'image : il affiche des QPixmap préparés
par l'interface / le worker, et tous les dessins restent sur le thread GUI.
"""

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class ViewTransform(QObject):
    """Un seul état de cadrage partagé entre les deux vues et la comparaison."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom = 1.0  # 1.0 == adapté à la fenêtre
        self.center_x = 0.5  # centre en coordonnées relatives de l'image
        self.center_y = 0.5

    def reset(self):
        self.zoom = 1.0
        self.center_x = 0.5
        self.center_y = 0.5
        self.changed.emit()

    @staticmethod
    def geometry(canvas, zoom):
        pixmap = canvas.original_pixmap
        if pixmap is None or pixmap.isNull():
            return None
        iw = pixmap.width()
        ih = pixmap.height()
        cw = max(1, canvas.width())
        ch = max(1, canvas.height())
        fit = min(cw / iw, ch / ih)
        return iw * fit * zoom, ih * fit * zoom

    def _clamp(self, canvas):
        geom = self.geometry(canvas, self.zoom)
        if geom is None:
            return
        sw, sh = geom
        cw = max(1, canvas.width())
        ch = max(1, canvas.height())

        if sw <= cw:
            self.center_x = 0.5
        else:
            half_visible_x = cw / (2 * sw)
            self.center_x = min(1 - half_visible_x, max(half_visible_x, self.center_x))

        if sh <= ch:
            self.center_y = 0.5
        else:
            half_visible_y = ch / (2 * sh)
            self.center_y = min(1 - half_visible_y, max(half_visible_y, self.center_y))

    def set_zoom(self, target, canvas, anchor=None):
        target = min(12.0, max(1.0, float(target)))
        if abs(target - self.zoom) < 0.0001:
            return
        if anchor is None:
            anchor = QPointF(canvas.width() / 2, canvas.height() / 2)

        old = self.geometry(canvas, self.zoom)
        if old is not None:
            old_w, old_h = old
            dx = anchor.x() - canvas.width() / 2
            dy = anchor.y() - canvas.height() / 2
            # Point de l'image sous le curseur avant zoom.
            image_x = self.center_x + dx / old_w
            image_y = self.center_y + dy / old_h
            self.zoom = target
            new = self.geometry(canvas, self.zoom)
            new_w, new_h = new
            # Maintenir le même point sous le curseur après zoom.
            self.center_x = image_x - dx / new_w
            self.center_y = image_y - dy / new_h
        else:
            self.zoom = target

        self._clamp(canvas)
        self.changed.emit()

    def pan(self, delta, canvas):
        geom = self.geometry(canvas, self.zoom)
        if geom is None:
            return
        sw, sh = geom
        self.center_x -= delta.x() / sw
        self.center_y -= delta.y() / sh
        self._clamp(canvas)
        self.changed.emit()

    def clamp_to(self, canvas):
        before = (self.center_x, self.center_y)
        self._clamp(canvas)
        if before != (self.center_x, self.center_y):
            self.changed.emit()


class ImageCanvas(QWidget):
    """mode : 'original', 'processed' ou 'wipe'."""

    wipe_changed = Signal(int)

    def __init__(self, state, mode, parent=None):
        super().__init__(parent)
        self.state = state
        self.mode = mode
        self.original_pixmap = None
        self.processed_pixmap = None
        self.wipe_percent = 50
        self._drag_action = None
        self._last_pos = None

        self.setMinimumSize(160, 180)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.state.changed.connect(self.update)

    def set_images(self, original, processed):
        self.original_pixmap = original
        self.processed_pixmap = processed
        if self.isVisible():
            self.state.clamp_to(self)
        self.update()

    def set_wipe(self, percent):
        percent = max(0, min(100, int(percent)))
        if self.wipe_percent != percent:
            self.wipe_percent = percent
            self.update()

    def _image_rect(self):
        geom = self.state.geometry(self, self.state.zoom)
        if geom is None:
            return None
        sw, sh = geom
        return QRectF(
            self.width() / 2 - self.state.center_x * sw,
            self.height() / 2 - self.state.center_y * sh,
            sw,
            sh,
        )

    def _draw_pixmap(self, painter, pixmap, image_rect):
        if pixmap is None or pixmap.isNull():
            return
        painter.drawPixmap(
            image_rect,
            pixmap,
            QRectF(0, 0, pixmap.width(), pixmap.height()),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#22252a"))
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self._image_rect()
        if rect is None:
            painter.setPen(QColor("#b4b8c0"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aucune image")
            return

        if self.mode == "original":
            self._draw_pixmap(painter, self.original_pixmap, rect)
        elif self.mode == "processed":
            if self.processed_pixmap is None:
                painter.setPen(QColor("#b4b8c0"))
                painter.drawText(self.rect(), Qt.AlignCenter, "Calcul de l'aperçu...")
            else:
                self._draw_pixmap(painter, self.processed_pixmap, rect)
        elif self.mode == "wipe":
            split_x = self.width() * self.wipe_percent / 100.0
            painter.save()
            painter.setClipRect(QRectF(0, 0, split_x, self.height()))
            self._draw_pixmap(painter, self.original_pixmap, rect)
            painter.restore()

            painter.save()
            painter.setClipRect(QRectF(split_x, 0, self.width() - split_x, self.height()))
            self._draw_pixmap(
                painter,
                self.processed_pixmap if self.processed_pixmap is not None else self.original_pixmap,
                rect,
            )
            if self.processed_pixmap is None:
                painter.fillRect(
                    QRectF(split_x, 0, self.width() - split_x, self.height()),
                    QColor(20, 20, 20, 120),
                )
            painter.restore()

            pen = QPen(QColor("#f5f5f5"), 2)
            painter.setPen(pen)
            painter.drawLine(int(split_x), 0, int(split_x), self.height())
            painter.setBrush(QColor("#f5f5f5"))
            painter.drawEllipse(QPointF(split_x, self.height() / 2), 7, 7)
            painter.setPen(QColor("#eeeeee"))
            painter.drawText(QRectF(8, 8, max(0, split_x - 16), 24), Qt.AlignLeft, "Original")
            painter.drawText(
                QRectF(split_x + 8, 8, max(0, self.width() - split_x - 16), 24),
                Qt.AlignLeft,
                "Résultat" if self.processed_pixmap is not None else "Calcul...",
            )

        painter.end()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            factor = 1.2 ** (delta / 120.0)
            self.state.set_zoom(self.state.zoom * factor, self, event.position())
            event.accept()
        else:
            super().wheelEvent(event)

    def _change_wipe_from_mouse(self, x):
        percent = round(100 * x / max(1, self.width()))
        percent = max(0, min(100, percent))
        self.set_wipe(percent)
        self.wipe_changed.emit(percent)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        divider = self.width() * self.wipe_percent / 100
        if self.mode == "wipe" and abs(event.position().x() - divider) <= 16:
            self._drag_action = "wipe"
            self._change_wipe_from_mouse(event.position().x())
            self.setCursor(Qt.SizeHorCursor)
        else:
            self._drag_action = "pan"
            self._last_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_action == "wipe":
            self._change_wipe_from_mouse(event.position().x())
        elif self._drag_action == "pan" and self._last_pos is not None:
            self.state.pan(event.position() - self._last_pos, self)
            self._last_pos = event.position()
        elif self.mode == "wipe":
            divider = self.width() * self.wipe_percent / 100
            if abs(event.position().x() - divider) <= 16:
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.OpenHandCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_action = None
            self._last_pos = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.state.reset()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Un widget masqué (autre mode de comparaison) ne doit pas modifier
        # le cadrage partagé lorsqu'il change de taille en arrière-plan.
        if self.isVisible():
            self.state.clamp_to(self)
