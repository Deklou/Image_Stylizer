"""Exploration de styles cohérents pour Image Stylizer.

Ce module reste volontairement indépendant de PySide6. Chaque famille
contient des plages de réglages raisonnables, plutôt que de tirer les
sept paramètres sur l'intégralité de leurs plages techniques.
"""

import random


DEFAULT_PARAMETERS = {
    "blur_kernel": 11,
    "bloom_threshold": 100,
    "bloom_intensity": 0.20,
    "poster_levels": 5,
    "noise_amount": 0,
    "blue_strength": 1.40,
    "yellow_strength": 1.10,
    # Les cinq effets sont actifs par defaut : rendu V5 préservé.
    "blur_enabled": True,
    "bloom_enabled": True,
    "posterize_enabled": True,
    "noise_enabled": True,
    "grade_enabled": True,
    "noise_seed": 12345,
    # Ajouts V8 : désactivés par défaut pour préserver tous les rendus V7.
    "contrast_enabled": False,
    "contrast_factor": 1.0,
    "vignette_enabled": False,
    "vignette_amount": 30,
}

# Chaque tuple représente (minimum, maximum, valeur privilégiée).
# Le générateur triangulaire favorise le cœur de l'identité visuelle,
# mais laisse de la place à l'exploration.
_STYLE_PROFILES = {
    "Lumière diffuse": {
        "blur_kernel": (7, 25, 13),
        "bloom_threshold": (135, 215, 170),
        "bloom_intensity": (0.12, 0.47, 0.25),
        "poster_levels": (6, 13, 9),
        "noise_amount": (0, 3, 0),
        "blue_strength": (0.92, 1.18, 1.05),
        "yellow_strength": (0.97, 1.22, 1.10),
    },
    "Nuit bleutée": {
        "blur_kernel": (3, 15, 7),
        "bloom_threshold": (145, 225, 185),
        "bloom_intensity": (0.10, 0.38, 0.21),
        "poster_levels": (5, 11, 7),
        "noise_amount": (0, 5, 2),
        "blue_strength": (1.28, 1.67, 1.49),
        "yellow_strength": (0.72, 1.02, 0.87),
    },
    "Souvenir chaleureux": {
        "blur_kernel": (5, 19, 11),
        "bloom_threshold": (145, 220, 180),
        "bloom_intensity": (0.10, 0.41, 0.22),
        "poster_levels": (6, 12, 8),
        "noise_amount": (1, 8, 4),
        "blue_strength": (0.66, 0.94, 0.78),
        "yellow_strength": (0.78, 1.02, 0.90),
    },
    "Illustration graphique": {
        "blur_kernel": (1, 9, 3),
        "bloom_threshold": (165, 235, 205),
        "bloom_intensity": (0.00, 0.16, 0.04),
        "poster_levels": (3, 6, 4),
        "noise_amount": (0, 2, 0),
        "blue_strength": (0.85, 1.35, 1.10),
        "yellow_strength": (0.83, 1.27, 1.05),
    },
    "Pellicule subtile": {
        "blur_kernel": (1, 7, 3),
        "bloom_threshold": (175, 235, 210),
        "bloom_intensity": (0.02, 0.20, 0.09),
        "poster_levels": (10, 18, 14),
        "noise_amount": (3, 10, 6),
        "blue_strength": (0.88, 1.17, 1.02),
        "yellow_strength": (0.85, 1.18, 1.00),
    },
    "Rêve étrange": {
        "blur_kernel": (9, 27, 17),
        "bloom_threshold": (125, 195, 165),
        "bloom_intensity": (0.18, 0.55, 0.33),
        "poster_levels": (4, 9, 6),
        "noise_amount": (0, 5, 2),
        "blue_strength": (1.12, 1.60, 1.35),
        "yellow_strength": (0.82, 1.17, 0.98),
    },
}

STYLE_FAMILIES = tuple(_STYLE_PROFILES)

_INT_KEYS = ("blur_kernel", "bloom_threshold", "poster_levels", "noise_amount")


def generate_style(family=None, rng=None):
    """Renvoie (nom_de_la_famille, paramètres).

    family=None : tire une famille au hasard, puis une variation mesurée.
    rng : random.Random optionnel, pratique pour les tests reproductibles.
    """
    if rng is None:
        rng = random.Random()

    if family is None:
        family = rng.choice(STYLE_FAMILIES)
    if family not in _STYLE_PROFILES:
        raise ValueError(f"Famille inconnue : {family}")

    profile = _STYLE_PROFILES[family]
    values = {}
    for name, (lower, upper, mode) in profile.items():
        picked = rng.triangular(lower, upper, mode)
        if name in _INT_KEYS:
            values[name] = round(picked)
        else:
            values[name] = round(picked, 2)

    # Le noyau de flou est défini en pixels et doit être impair dans OpenCV.
    # Le moteur corrige déjà les nombres pairs ; autant éviter ces doublons
    # en affichant directement une valeur impaire dans l'interface.
    if values["blur_kernel"] % 2 == 0:
        values["blur_kernel"] += 1

    # Avec un bloom intense, un seuil trop bas illuminerait une partie
    # excessive de la scène ; on évite les combinaisons les moins contrôlées.
    if values["bloom_intensity"] >= 0.40:
        values["bloom_threshold"] = max(155, values["bloom_threshold"])

    # Chaque style est reproductible : on mémorise une seed indépendante.
    # Les cinq effets restent actifs ; l'absence de bruit est gérée par
    # noise_amount=0 dans les familles qui n'en nécessitent pas.
    values.update({
        "blur_enabled": True,
        "bloom_enabled": True,
        "posterize_enabled": True,
        "noise_enabled": True,
        "grade_enabled": True,
        "noise_seed": rng.randrange(0, 2**31),
        "contrast_enabled": False,
        "contrast_factor": 1.0,
        "vignette_enabled": False,
        "vignette_amount": 30,
    })
    return family, values
