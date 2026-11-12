"""Point d'entrée Image Stylizer (Python et exe Windows)."""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from interface import ImageStylizerWindow


def resource_path(relative_path):
    """En développement: dossier du projet; en exe: dossier PyInstaller."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / relative_path


def main():
    if sys.platform == "win32":
        # Evite que la barre des tâches regroupe l'icône sous Python.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ImageStylizer.Desktop.1"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Image Stylizer")

    icon_path = resource_path("assets/image_stylizer.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = ImageStylizerWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
