"""Tests autonomes du moteur. Aucune interface Qt n'est nécessaire.

Lancer depuis le dossier bg_stylizer : python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from effects import add_noise, apply_vignette, posterize_np
from processor import export_image, process_image
from style_randomizer import DEFAULT_PARAMETERS


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(2026)
        cls.source = rng.integers(0, 256, (77, 103, 3), dtype=np.uint8)
        cls.image = Image.fromarray(cls.source.copy())

    def test_posterize_matches_original_formula(self):
        for levels in range(2, 21):
            factor = 255 / (levels - 1)
            expected = np.clip(
                np.floor(self.source / factor) * factor, 0, 255
            ).astype(np.uint8)
            np.testing.assert_array_equal(posterize_np(self.source, levels), expected)

    def test_noise_matches_original_generator(self):
        for seed in (0, 12345, 2**31 - 1):
            for amount in (0, 1, 7, 50):
                rng = np.random.default_rng(seed)
                noise = rng.normal(0, amount, self.source.shape)
                expected = np.clip(
                    self.source.astype(np.float32) + noise, 0, 255
                ).astype(np.uint8)
                np.testing.assert_array_equal(
                    add_noise(self.source, amount, seed), expected
                )

    def test_vignette_matches_original_formula(self):
        height, width = self.source.shape[:2]
        x = np.linspace(-1.0, 1.0, width, dtype=np.float32)
        y = np.linspace(-1.0, 1.0, height, dtype=np.float32)
        radius = ((x[None, :] ** 2) + (y[:, None] ** 2)) * 0.5
        for amount in (0, 1, 30, 100):
            strength = amount / 100.0
            if not strength:
                expected = self.source
            else:
                weight = np.float32(1.0) - np.float32(strength) * np.power(radius, 1.3)
                expected = np.clip(
                    self.source.astype(np.float32) * weight[:, :, None], 0, 255
                ).astype(np.uint8)
            np.testing.assert_array_equal(apply_vignette(self.source, amount), expected)

    def test_all_effects_disabled_gives_original(self):
        params = dict(DEFAULT_PARAMETERS)
        params.update({
            "blur_enabled": False,
            "bloom_enabled": False,
            "posterize_enabled": False,
            "noise_enabled": False,
            "grade_enabled": False,
            "contrast_enabled": False,
            "vignette_enabled": False,
        })
        np.testing.assert_array_equal(np.asarray(process_image(self.image, params)), self.source)

    def test_same_seed_same_pixels(self):
        params = dict(DEFAULT_PARAMETERS, noise_amount=8, noise_seed=2026)
        a = np.asarray(process_image(self.image, params))
        b = np.asarray(process_image(self.image, params))
        np.testing.assert_array_equal(a, b)

    def test_exports_full_resolution_and_dont_overwrite(self):
        params = dict(DEFAULT_PARAMETERS)
        with tempfile.TemporaryDirectory() as folder:
            input_path = Path(folder) / "source.png"
            self.image.save(input_path)
            output_dir = Path(folder) / "resultats"
            for fmt in ("PNG", "JPEG", "WEBP"):
                first = export_image(input_path, output_dir, params, image_format=fmt, quality=85)
                second = export_image(input_path, output_dir, params, image_format=fmt, quality=85)
                self.assertTrue(first.exists())
                self.assertTrue(second.exists())
                self.assertNotEqual(first, second)
                with Image.open(first) as decoded:
                    self.assertEqual(decoded.size, self.image.size)


if __name__ == "__main__":
    unittest.main()
