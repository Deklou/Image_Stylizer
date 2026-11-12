"""Tests de robustesse du système de presets et de publication des exports."""

import importlib.util
import json
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from presets import PresetManager
from processor import export_image
from style_randomizer import DEFAULT_PARAMETERS


class StabilizationTests(unittest.TestCase):
    def test_presets_survive_restart_and_keep_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PresetManager(tmp)
            store.set("Premier", {"blur_kernel": 11})
            store.set("Deuxième", {"blur_kernel": 17})
            self.assertEqual(PresetManager(tmp).get("Deuxième")["blur_kernel"], 17)
            backup = Path(tmp) / "presets.json.bak"
            self.assertTrue(backup.exists())
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"Premier": {"blur_kernel": 11}})

    def test_corrupt_presets_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "presets.json"
            path.write_text("{invalid-json", encoding="utf-8")
            store = PresetManager(tmp)
            self.assertIsNotNone(store.load_error)
            with self.assertRaises(OSError):
                store.set("Nouveau", {"blur_kernel": 5})
            self.assertEqual(path.read_text(encoding="utf-8"), "{invalid-json")

    def test_failed_preset_save_restores_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PresetManager(tmp)
            store.set("OK", {"blur_kernel": 11})
            original = (Path(tmp) / "presets.json").read_bytes()
            with patch("presets.os.replace", side_effect=OSError("disque verrouillé")):
                with self.assertRaises(OSError):
                    store.set("Échec", {"blur_kernel": 15})
            self.assertNotIn("Échec", store.presets)
            self.assertEqual((Path(tmp) / "presets.json").read_bytes(), original)
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_failed_image_save_leaves_no_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            image = Image.new("RGB", (32, 24), (30, 60, 90))
            src = tmp / "photo.png"
            out = tmp / "exports"
            image.save(src)
            # Simuler une erreur d'encodage APRÈS la création d'un fichier.
            def broken_save(image_obj, fp, *args, **kwargs):
                Path(fp).write_bytes(b"PARTIAL")
                raise OSError("disque plein")
            with patch.object(Image.Image, "save", broken_save):
                with self.assertRaises(OSError):
                    export_image(src, out, DEFAULT_PARAMETERS)
            self.assertEqual(list(out.iterdir()), [])

    def test_windows_preferences_migration_only_copies_missing_keys(self):
        registries = {
            ("OpenAI", "ImageStylizer"): {
                "output_dir": "C:/ancien",
                "compare_mode": "wipe",
                "export/format": "WEBP",
            },
            ("ImageStylizer", "ImageStylizer"): {
                "output_dir": "C:/nouveau",
            },
        }

        class FakeSettings:
            def __init__(self, org, app):
                self.values = registries.setdefault((org, app), {})
            def allKeys(self):
                return list(self.values)
            def contains(self, key):
                return key in self.values
            def value(self, key):
                return self.values.get(key)
            def setValue(self, key, value):
                self.values[key] = value
            def sync(self):
                pass

        qt_core = types.ModuleType("PySide6.QtCore")
        qt_core.QSettings = FakeSettings
        pyside = types.ModuleType("PySide6")
        spec = importlib.util.spec_from_file_location(
            "settings_manager_under_test",
            Path(__file__).resolve().parent.parent / "settings_manager.py",
        )
        with patch.dict(sys.modules, {"PySide6": pyside, "PySide6.QtCore": qt_core}):
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            store = mod.create_settings()
        self.assertEqual(store.value("output_dir"), "C:/nouveau")
        self.assertEqual(store.value("compare_mode"), "wipe")
        self.assertEqual(store.value("export/format"), "WEBP")
        self.assertEqual(registries[("OpenAI", "ImageStylizer")]["output_dir"], "C:/ancien")

    def test_existing_export_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "photo.png"
            out = tmp / "exports"
            Image.new("RGB", (32, 24), (30, 60, 90)).save(src)
            first = export_image(src, out, DEFAULT_PARAMETERS)
            original_bytes = first.read_bytes()
            second = export_image(src, out, DEFAULT_PARAMETERS)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original_bytes)
            self.assertEqual(sorted(p.suffix for p in out.iterdir()), [".png", ".png"])


if __name__ == "__main__":
    unittest.main()
