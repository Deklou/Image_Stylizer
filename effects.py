"""Effets pixel RGB d'Image Stylizer.

Les fonctions manipulent des tableaux numpy uint8 en ordre RGB.
"""

import cv2
import numpy as np


def gaussian_blur(image_np, kernel_size):
    kernel = max(1, int(kernel_size))
    if kernel % 2 == 0:
        kernel += 1
    return cv2.GaussianBlur(image_np, (kernel, kernel), 0)


def bloom(image_np, threshold, intensity):
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
    mask = gray > threshold
    glow = gaussian_blur(image_np, 31)
    result = image_np.astype(np.float32)
    result[mask] += glow[mask] * intensity
    return np.clip(result, 0, 255).astype(np.uint8)


def posterize_np(image_np, levels):
    """Même quantification que la V8.1 via une LUT de 256 entrées.

    Évite de transformer toute l'image en float64 (jusqu'à plusieurs
    centaines de Mo temporaires pour une grande photographie).
    """
    factor = 255 / (levels - 1)
    values = np.arange(256, dtype=np.uint8)
    lut = np.clip(np.floor(values / factor) * factor, 0, 255).astype(np.uint8)
    return cv2.LUT(image_np, lut)


def add_noise(image_np, amount, seed=12345):
    """Bruit déterministe en blocs : résultat identique à la V8.1.

    On avance le même générateur dans le même ordre, mais sans allouer
    simultanément deux tableaux float64 de la taille de toute l'image.
    """
    if amount <= 0:
        return image_np
    rng = np.random.default_rng(int(seed))
    result = np.empty_like(image_np)
    height = image_np.shape[0]
    for top in range(0, height, 128):
        bottom = min(height, top + 128)
        block = image_np[top:bottom]
        noise = rng.normal(0, amount, block.shape)
        noisy = block.astype(np.float32) + noise
        result[top:bottom] = np.clip(noisy, 0, 255).astype(np.uint8)
    return result


def color_grade(image_np, blue_strength, yellow_strength):
    # On conserve rigoureusement la convention RGB du moteur initial :
    # B (canal 2) et G (canal 1), sans renommer les réglages existants.
    img = image_np.astype(np.float32)
    img[:, :, 2] *= blue_strength
    img[:, :, 1] *= yellow_strength
    return np.clip(img, 0, 255).astype(np.uint8)


def adjust_contrast(image_np, factor):
    """Contraste autour du gris moyen, sans changer les canaux si facteur=1."""
    if abs(float(factor) - 1.0) < 1e-9:
        return image_np
    # LUT 256 éléments : plus rapide et plus économe en mémoire qu'un
    # passage de toute la photographie en float32.
    values = np.arange(256, dtype=np.float32)
    lut = np.clip((values - 127.5) * float(factor) + 127.5, 0, 255).astype(np.uint8)
    return cv2.LUT(image_np, lut)


def apply_vignette(image_np, amount):
    """Assombrit progressivement les bords, sans toucher au centre."""
    strength = float(amount) / 100.0
    if strength <= 0:
        return image_np
    height, width = image_np.shape[:2]
    # Carte de luminance 2D uniquement, sans image temporaire float64.
    x = np.linspace(-1.0, 1.0, width, dtype=np.float32)
    y = np.linspace(-1.0, 1.0, height, dtype=np.float32)
    radius = ((x[None, :] ** 2) + (y[:, None] ** 2)) * 0.5
    weight = np.float32(1.0) - np.float32(strength) * np.power(radius, 1.3)
    result = np.empty_like(image_np)
    for top in range(0, height, 128):
        bottom = min(height, top + 128)
        block = image_np[top:bottom].astype(np.float32)
        result[top:bottom] = np.clip(
            block * weight[top:bottom, :, None], 0, 255
        ).astype(np.uint8)
    return result
