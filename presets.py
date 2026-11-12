"""Sauvegarde des presets JSON, avec sauvegarde de sécurité.

Un fichier JSON endommagé n'est jamais écrasé silencieusement. Les écritures
passent d'abord par un fichier temporaire, puis un remplacement atomique.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path


class PresetManager:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir is not None else Path.home() / ".image_stylizer"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / "presets.json"
        self.backup_path = self.base_dir / "presets.json.bak"
        self.load_error = None
        self.presets = self.load()

    def load(self):
        if not self.path.exists():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not all(
                isinstance(key, str) and isinstance(value, dict)
                for key, value in data.items()
            ):
                raise ValueError("Le fichier ne contient pas un dictionnaire de presets valide.")
            self.load_error = None
            return data
        except (OSError, ValueError, UnicodeError, TypeError) as exc:
            self.load_error = (
                f"Impossible de lire le fichier des presets :\n{self.path}\n\n{exc}\n\n"
                "Le fichier a été conservé. Répare-le ou restaure "
                "presets.json.bak avant de sauvegarder à nouveau."
            )
            return {}

    def save(self):
        if self.load_error is not None:
            raise OSError(self.load_error)

        # Générer la totalité du JSON AVANT de toucher aux fichiers existants.
        content = json.dumps(self.presets, indent=2, ensure_ascii=False)
        temp_path = None
        backup_temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n",
                prefix=".presets_", suffix=".tmp", dir=self.base_dir,
                delete=False,
            ) as f:
                temp_path = Path(f.name)
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Conserver la dernière version lisible en secours.
            if self.path.exists():
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=".presets_backup_", suffix=".tmp",
                    dir=self.base_dir, delete=False,
                ) as f:
                    backup_temp_path = Path(f.name)
                    with self.path.open("rb") as original:
                        shutil.copyfileobj(original, f)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(backup_temp_path, self.backup_path)
                backup_temp_path = None

            # Même volume : le fichier final n'est jamais à moitié écrit.
            os.replace(temp_path, self.path)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if backup_temp_path is not None:
                backup_temp_path.unlink(missing_ok=True)

    def get_names(self):
        return sorted(self.presets.keys(), key=str.lower)

    def get(self, name):
        return self.presets.get(name)

    def set(self, name, parameters):
        if self.load_error is not None:
            raise OSError(self.load_error)
        before = self.presets.copy()
        self.presets[name] = dict(parameters)
        try:
            self.save()
        except Exception:
            self.presets = before
            raise

    def delete(self, name):
        if self.load_error is not None:
            raise OSError(self.load_error)
        if name in self.presets:
            before = self.presets.copy()
            del self.presets[name]
            try:
                self.save()
            except Exception:
                self.presets = before
                raise


# --- Préférences (ancien settings_manager.py) ---
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
