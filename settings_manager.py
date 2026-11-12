"""Préférences Windows dédiées à l'application, avec migration sans perte.

Les anciennes versions utilisaient QSettings('OpenAI', 'ImageStylizer').
La migration n'efface pas l'ancien emplacement et ne remplace jamais une
préférence déjà enregistrée dans le nouvel emplacement.
"""

from PySide6.QtCore import QSettings


def create_settings():
    settings = QSettings("ImageStylizer", "ImageStylizer")
    legacy = QSettings("OpenAI", "ImageStylizer")
    changed = False
    for key in legacy.allKeys():
        if not settings.contains(key):
            settings.setValue(key, legacy.value(key))
            changed = True
    if changed:
        settings.sync()
    return settings
