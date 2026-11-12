"""Petits contrôles d'interface pour Image Stylizer.

Aucun traitement d'image ici : les widgets opèrent uniquement dans le thread Qt.
"""

from PySide6.QtCore import QEvent, Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSlider, QWidget


class ResettableSlider(QSlider):
    """Un double-clic restaure la valeur *de ce seul paramètre*."""

    def __init__(self, orientation, default_value, parent=None):
        super().__init__(orientation, parent)
        self.default_value = int(default_value)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setValue(self.default_value)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class LoadingBorder(QWidget):
    """Trait lumineux en mouvement autour de l'image visible pendant le calcul.

    Ce n'est PAS une progression en pourcentage : le moteur ne mesure pas
    l'avancement interne. L'animation s'arrête dès que l'aperçu est disponible.
    Le widget ne capte ni clic, ni molette, ni déplacement de souris.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._phase = 0.0
        self._active = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(canvas.rect())

        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._animate)

        canvas.installEventFilter(self)
        canvas.state.changed.connect(self.update)
        self.hide()

    def eventFilter(self, watched, event):
        if watched is self.canvas and event.type() in (QEvent.Resize, QEvent.Show):
            self.setGeometry(self.canvas.rect())
            self.raise_()
        return super().eventFilter(watched, event)

    def set_active(self, active):
        active = bool(active)
        if self._active == active:
            return
        self._active = active
        if active:
            self._phase = 0.0
            self.setGeometry(self.canvas.rect())
            self.show()
            self.raise_()
            self._timer.start()
        else:
            self._timer.stop()
            self.hide()

    def _animate(self):
        self._phase = (self._phase + 0.013) % 1.0
        self.update()

    def paintEvent(self, event):
        if not self._active:
            return

        # La bordure suit l'image lorsqu'elle tient dans la vue et encadre
        # la zone visible lorsqu'un zoom fait dépasser les bords de la vue.
        image_rect = self.canvas._image_rect()
        if image_rect is None:
            return
        viewport = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        rect = image_rect.intersected(viewport).adjusted(1, 1, -1, -1)
        if rect.width() < 12 or rect.height() < 12:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(Qt.NoBrush)

        outline = QPainterPath()
        outline.addRoundedRect(rect, 5.0, 5.0)
        painter.setPen(QPen(QColor(90, 185, 220, 65), 2.0))
        painter.drawPath(outline)

        # Segment animé sur environ 27 % du périmètre, avec rebouclage.
        length = outline.length()
        if length <= 0:
            painter.end()
            return
        start = self._phase * length
        end = start + 0.27 * length
        parts = [(start, min(end, length))]
        if end > length:
            parts.append((0.0, end - length))

        painter.setPen(QPen(QColor(95, 215, 245, 225), 3.0, Qt.SolidLine, Qt.RoundCap))
        for begin, stop in parts:
            segment = QPainterPath()
            segment.moveTo(outline.pointAtPercent(outline.percentAtLength(begin)))
            steps = max(2, int((stop - begin) / 5))
            for i in range(1, steps + 1):
                distance = begin + (stop - begin) * i / steps
                segment.lineTo(outline.pointAtPercent(outline.percentAtLength(distance)))
            painter.drawPath(segment)
        painter.end()
